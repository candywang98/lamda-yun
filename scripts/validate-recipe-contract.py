#!/usr/bin/env python3
"""B16 recipe contract validator (single-source dual-out).

The accepted schema is derived from ONE spec file:
  mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/recipes/contract/recipe-contract-spec.json
The Kotlin goldens (automation/recipes/RecipeContract.kt +
RecipeContractGoldenTest) mirror the same file value-for-value; any drift on
either side fails its own test suite.

Usage:
  validate-recipe-contract.py [--spec PATH] [--no-strict-signature] RECIPE.json [...]
  validate-recipe-contract.py --self-test

Exit codes: 0 = valid, 1 = contract violation(s), 2 = usage/IO error.

A signature proves provenance, NEVER sandboxing: every rule below applies to
signed and unsigned packages alike.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_SPEC = (
    SCRIPT_DIR.parent / "mobile/companion/app/src/main/java/com/company/cloudctl/companion/"
    "automation/recipes/contract/recipe-contract-spec.json"
)

TERMINALS = {"SUCCEEDED", "FAILED", "WAITING_USER"}
STATE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
VALUE_REF_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def canonical_dumps(value) -> str:
    """Byte-compatible with Kotlin CanonicalJson.dumps (sorted keys, compact, raw unicode)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def recipe_hash_payload(root: dict) -> bytes:
    payload = {
        "apiVersion": root["apiVersion"],
        "kind": root["kind"],
        "manifest": {k: v for k, v in root["manifest"].items() if k != "hash"},
        "graph": root["graph"],
    }
    return canonical_dumps(payload).encode("utf-8")


def walk_forbidden(value, fragments, path, violations):
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.lower()
            for fragment in fragments:
                if fragment in lowered:
                    violations.append(f"FORBIDDEN_FIELD: '{key}' at {path} contains '{fragment}'")
                    break
            walk_forbidden(child, fragments, f"{path}.{key}", violations)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk_forbidden(child, fragments, f"{path}[{index}]", violations)


def can_reach_terminal(node, edges, memo, visiting):
    if node in TERMINALS:
        return True
    if node in memo:
        return memo[node]
    if node not in edges or node in visiting:
        if node not in edges:
            memo[node] = False
            return False
        return False
    visiting.add(node)
    result = any(can_reach_terminal(n, edges, memo, visiting) for n in edges[node])
    visiting.discard(node)
    memo[node] = result
    return result


def on_cycle(node, edges):
    queue = list(edges.get(node, ()))
    seen = set()
    while queue:
        nxt = queue.pop()
        if nxt == node:
            return True
        if nxt in seen or nxt not in edges:
            continue
        seen.add(nxt)
        queue.extend(edges[nxt])
    return False


def validate_recipe(root, spec, strict_signature=True):
    violations: list[str] = []
    caps = spec["actions"]["parameterCaps"]
    graph_range = spec["graph"]["maxIterations"]
    duration_range = spec["graph"]["maxDurationMs"]

    if root.get("apiVersion") != spec["protocol"]:
        violations.append(f"UNSUPPORTED_PROTOCOL: apiVersion must be {spec['protocol']}")
    if root.get("kind") != spec["kind"]:
        violations.append(f"UNSUPPORTED_RECIPE: kind must be {spec['kind']}")
    walk_forbidden(root, spec["forbiddenFieldFragments"], "$", violations)

    manifest = root.get("manifest")
    graph = root.get("graph")
    if not isinstance(manifest, dict) or not isinstance(graph, dict):
        violations.append("RECIPE_MALFORMED: manifest and graph objects are required")
        return violations

    declared = manifest.get("hash", "")
    if not SHA256_RE.match(str(declared)):
        violations.append("HASH_MALFORMED: manifest.hash must be lowercase sha256 hex")
    else:
        computed = hashlib.sha256(recipe_hash_payload(root)).hexdigest()
        if declared != computed:
            violations.append(f"HASH_MISMATCH: manifest.hash {declared} != canonical {computed}")

    if manifest.get("minEngineVersion", -1) < 1:
        violations.append("ENGINE_VERSION_INVALID: minEngineVersion must be >= 1")
    if not manifest.get("commandTypes"):
        violations.append("COMMAND_TYPES_EMPTY: commandTypes must be a non-empty array")
    if not STATE_ID_RE.match(str(manifest.get("id", ""))):
        violations.append("RECIPE_ID_INVALID: manifest.id violates charset/length")

    if strict_signature:
        signature = root.get("signature")
        if not isinstance(signature, dict):
            violations.append(
                "SIGNATURE_MISSING: packages must carry a signature block (provenance)"
            )
        elif signature.get("algorithm") != "Ed25519":
            violations.append("SIGNATURE_ALGORITHM: signature.algorithm must be Ed25519")

    iterations = graph.get("maxIterations", -1)
    if not (graph_range[0] <= iterations <= graph_range[1]):
        violations.append(f"GRAPH_MAX_ITERATIONS_OUT_OF_RANGE: {iterations} outside {graph_range}")
    duration = graph.get("maxDurationMs", -1)
    if not (duration_range[0] <= duration <= duration_range[1]):
        violations.append(f"GRAPH_MAX_DURATION_OUT_OF_RANGE: {duration} outside {duration_range}")

    states_json = graph.get("states")
    if not isinstance(states_json, list) or not states_json:
        violations.append("STATES_EMPTY: graph.states must be a non-empty array")
        return violations
    if len(states_json) > caps["maxStates"]:
        violations.append(f"STATES_OVER_CAP: {len(states_json)} > {caps['maxStates']}")

    whitelist = set(spec["actions"]["whitelist"])
    on_exhausted_values = set(spec["wait"]["onExhaustedValues"])
    states: dict[str, dict] = {}
    edges: dict[str, set] = {}
    for state in states_json:
        state_id = str(state.get("stateId", ""))
        if not STATE_ID_RE.match(state_id):
            violations.append(f"STATE_ID_INVALID: '{state_id}' violates charset/length")
        if state_id in states:
            violations.append(f"STATE_ID_DUPLICATE: '{state_id}' appears twice")
        states[state_id] = state
        edges.setdefault(state_id, set())
        action = state.get("action", "")
        if action not in whitelist:
            violations.append(
                f"ACTION_NOT_WHITELISTED: '{state_id}' action '{action}' not on whitelist"
            )
        value_ref = state.get("valueRef")
        if isinstance(value_ref, str) and value_ref and not VALUE_REF_RE.match(value_ref):
            violations.append(
                f"VALUE_REF_INVALID: '{state_id}' valueRef '{value_ref}' violates shape"
            )
        bounded_fields = [
            f
            for f in ("maxAttempts", "noProgressBudget", "deadlineMs", "onExhausted")
            if state.get(f) is not None
        ]
        if bounded_fields:
            if action not in ("wait", "tap", "media"):
                violations.append(
                    f"BOUNDS_ON_NON_RETRYABLE: '{state_id}' carries retry budgets "
                    f"on action '{action}'"
                )
            if "maxAttempts" in bounded_fields:
                value = state["maxAttempts"]
                if not (1 <= value <= caps["maxWaitAttempts"]):
                    violations.append(
                        f"MAX_ATTEMPTS_OUT_OF_RANGE: '{state_id}' maxAttempts {value}"
                    )
            if "noProgressBudget" in bounded_fields:
                value = state["noProgressBudget"]
                if not (1 <= value <= caps["maxNoProgressPolls"]):
                    violations.append(
                        f"NO_PROGRESS_OUT_OF_RANGE: '{state_id}' noProgressBudget {value}"
                    )
            if "deadlineMs" in bounded_fields:
                value = state["deadlineMs"]
                if not (caps["minStateDeadlineMs"] <= value <= duration):
                    violations.append(
                        f"STATE_DEADLINE_OUT_OF_RANGE: '{state_id}' deadlineMs {value}"
                    )
            if "onExhausted" in bounded_fields and state["onExhausted"] not in on_exhausted_values:
                violations.append(
                    f"ON_EXHAUSTED_INVALID: '{state_id}' onExhausted {state['onExhausted']!r}"
                )
        for edge in ("onSuccess", "onFailure"):
            target = state.get(edge)
            if target is None or (isinstance(target, str) and not target.strip()):
                continue
            edges[state_id].add(target)
        # NOTE: edge-target resolution happens in a second pass below, once
        # every state id is known (forward references are legal).

    start = graph.get("startStateId", "")
    if start not in states:
        violations.append(f"START_STATE_MISSING: startStateId '{start}' is not a state")

    # Second pass: every edge target must resolve to a state or a terminal outcome.
    for state_id, targets in edges.items():
        for target in targets:
            if target not in states and target not in TERMINALS:
                violations.append(
                    f"EDGE_TARGET_UNKNOWN: {state_id} edge -> '{target}' resolves to nothing"
                )

    commit_id = graph.get("commitActionId")
    if commit_id:
        commit = states.get(commit_id)
        if commit is None:
            violations.append(f"COMMIT_STATE_MISSING: commitActionId '{commit_id}' is not a state")
        else:
            if (
                commit.get("action") != "tap"
                or not commit.get("locatorRef")
                or not commit.get("postcondition")
                or commit.get("onSuccess") != "SUCCEEDED"
                or commit.get("onFailure") is not None
            ):
                violations.append(
                    "COMMIT_SHAPE_INVALID: commit must be one tap with distinct postcondition"
                )
            if any(
                commit.get(f) is not None
                for f in ("maxAttempts", "noProgressBudget", "deadlineMs", "onExhausted")
            ):
                violations.append(
                    "COMMIT_NOT_RETRYABLE: the commit state must not carry retry budgets"
                )

    # Loop policy: bounded cycles pass; dead cycles and irreversible-in-cycle never.
    memo: dict[str, bool] = {}
    for state_id in states:
        if not can_reach_terminal(state_id, edges, memo, set()):
            violations.append(
                f"LOOP_NON_TERMINATING: '{state_id}' can never reach a terminal outcome"
            )
    irreversible = set(spec["loopPolicy"]["irreversibleLocators"])
    for state_id in states:
        if not on_cycle(state_id, edges):
            continue
        locator = states[state_id].get("locatorRef")
        if locator in irreversible:
            violations.append(
                f"IRREVERSIBLE_IN_LOOP: '{state_id}' taps irreversible locator "
                f"'{locator}' inside a retry loop"
            )
        if state_id == commit_id:
            violations.append(
                f"IRREVERSIBLE_IN_LOOP: commit state '{state_id}' sits inside a retry loop; "
                "commits are single-shot"
            )
    return violations


def validate_template(root, spec):
    violations: list[str] = []
    if root.get("protocol") != spec["templateProtocol"]:
        violations.append(
            f"UNSUPPORTED_PROTOCOL: template protocol must be {spec['templateProtocol']}"
        )
    walk_forbidden(root, spec["forbiddenFieldFragments"], "$", violations)
    actions = set(spec["templateActions"])
    forbidden_actions = set(spec["templateForbiddenActions"])
    steps = root.get("steps")
    if not isinstance(steps, list) or not steps:
        violations.append("STEPS_EMPTY: template steps must be a non-empty array")
        return violations
    caps = spec["actions"]["parameterCaps"]
    for step in steps:
        step_id = str(step.get("stepId", ""))
        action = step.get("action", "")
        if action not in actions or action in forbidden_actions:
            violations.append(
                f"TEMPLATE_ACTION_NOT_WHITELISTED: '{step_id}' action '{action}' is not declarative"
            )
        if action == "submit":
            violations.append(
                f"SUBMIT_FORBIDDEN_IN_TEMPLATES: '{step_id}' — irreversible submit "
                "stays a signed-recipe concern"
            )
        bounds = step.get("bounds") or {}
        if "maxAttempts" in bounds and not (1 <= bounds["maxAttempts"] <= caps["maxWaitAttempts"]):
            violations.append(f"MAX_ATTEMPTS_OUT_OF_RANGE: '{step_id}' {bounds['maxAttempts']}")
        if "noProgressBudget" in bounds and not (
            1 <= bounds["noProgressBudget"] <= caps["maxNoProgressPolls"]
        ):
            violations.append(f"NO_PROGRESS_OUT_OF_RANGE: '{step_id}' {bounds['noProgressBudget']}")
        value_ref = step.get("valueRef")
        if isinstance(value_ref, str) and value_ref and not VALUE_REF_RE.match(value_ref):
            violations.append(f"VALUE_REF_INVALID: '{step_id}' valueRef '{value_ref}'")
        if action == "input" and not value_ref:
            violations.append(f"INPUT_REQUIRES_VALUE_REF: '{step_id}'")
        locator = step.get("locatorRef", "")
        if action in ("navigate", "wait", "media") and not locator:
            violations.append(f"LOCATOR_REQUIRED: '{step_id}' action '{action}' needs locatorRef")
        if locator in set(spec["loopPolicy"]["irreversibleLocators"]):
            violations.append(f"IRREVERSIBLE_LOCATOR_IN_TEMPLATE: '{step_id}' -> '{locator}'")
    return violations


def load_spec(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_file(path: pathlib.Path, spec, strict_signature: bool) -> list[str]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            root = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        return [f"RECIPE_MALFORMED: {path}: {error}"]
    if not isinstance(root, dict):
        return [f"RECIPE_MALFORMED: {path}: top level must be an object"]
    if root.get("protocol") == spec["templateProtocol"] or "steps" in root and "graph" not in root:
        return validate_template(root, spec)
    return validate_recipe(root, spec, strict_signature)


def _sample_recipe(states, max_iterations=40, max_duration_ms=600000):
    root = {
        "apiVersion": "cloudctl.recipe/v1",
        "kind": "LocalRecipePackage",
        "manifest": {
            "id": "recipe-self-test",
            "version": "1.0.0",
            "hash": "0" * 64,
            "signingKeyId": "self-test",
            "minEngineVersion": 1,
            "platform": "xianyu",
            "app": "com.taobao.idlefish",
            "commandTypes": ["xianyu.publish_listing.v1"],
        },
        "graph": {
            "startStateId": states[0]["stateId"],
            "maxIterations": max_iterations,
            "maxDurationMs": max_duration_ms,
            "states": states,
        },
        "signature": {"algorithm": "Ed25519", "keyId": "self-test", "digest": "unsigned"},
    }
    return root


def _sign_sample(root):
    payload = recipe_hash_payload(root)
    root["manifest"]["hash"] = hashlib.sha256(payload).hexdigest()
    return root


def self_test(spec) -> int:
    """Bounded loops pass; dead loops, irreversible-in-loop, eval/shell fields and
    cap violations fail.

    The self-test exercises the same fail-closed validator used by the CLI.
    """
    failures = 0

    def expect(name, root, should_pass, strict_signature=True):
        nonlocal failures
        violations = validate_recipe(root, spec, strict_signature=strict_signature)
        passed = not violations
        if passed != should_pass:
            failures += 1
            print(
                f"SELF-TEST FAIL {name}: expected "
                f"{'valid' if should_pass else 'invalid'}, got {violations}"
            )
        else:
            print(f"self-test ok  {name}" + ("" if should_pass else f" -> {violations[0]}"))

    # 1. bounded retry cycle (finite repeat with a reachable terminal) is allowed.
    expect(
        "bounded-retry-cycle-allowed",
        _sign_sample(
            _sample_recipe(
                [
                    {
                        "stateId": "open",
                        "action": "tap",
                        "locatorRef": "xianyu_home_sell",
                        "onSuccess": "await",
                        "onFailure": "FAILED",
                    },
                    {
                        "stateId": "await",
                        "action": "wait",
                        "locatorRef": "xianyu_publish_page",
                        "onSuccess": "SUCCEEDED",
                        "onFailure": "open",
                        "maxAttempts": 3,
                        "noProgressBudget": 2,
                        "deadlineMs": 20000,
                        "onExhausted": "FAIL",
                    },
                ]
            )
        ),
        should_pass=True,
    )
    # 2. non-terminating loop (no terminal reachable) is rejected.
    expect(
        "non-terminating-loop-rejected",
        _sign_sample(
            _sample_recipe(
                [
                    {
                        "stateId": "a",
                        "action": "wait",
                        "locatorRef": "xianyu_home_sell",
                        "onSuccess": "b",
                        "onFailure": "b",
                    },
                    {
                        "stateId": "b",
                        "action": "wait",
                        "locatorRef": "xianyu_home_sell",
                        "onSuccess": "a",
                        "onFailure": "a",
                    },
                ]
            )
        ),
        should_pass=False,
    )
    # 3. irreversible submit inside a loop body is rejected.
    expect(
        "irreversible-submit-in-loop-rejected",
        _sign_sample(
            _sample_recipe(
                [
                    {
                        "stateId": "loop",
                        "action": "tap",
                        "locatorRef": "xianyu_publish_button",
                        "onSuccess": "loop2",
                        "onFailure": "FAILED",
                    },
                    {
                        "stateId": "loop2",
                        "action": "wait",
                        "locatorRef": "xianyu_home_sell",
                        "onSuccess": "loop",
                        "onFailure": "FAILED",
                    },
                ]
            )
        ),
        should_pass=False,
    )
    # 4. eval/shell/js fields are rejected even on a signed, hash-consistent package.
    evil = _sign_sample(
        _sample_recipe(
            [
                {
                    "stateId": "open",
                    "action": "wait",
                    "locatorRef": "xianyu_home_sell",
                    "onSuccess": "SUCCEEDED",
                    "onFailure": None,
                    "eval": "1+1",
                },
            ]
        )
    )
    expect("eval-field-rejected-signature-not-sandbox", evil, should_pass=False)
    # 5. per-action cap violations are rejected.
    expect(
        "max-attempts-cap-rejected",
        _sign_sample(
            _sample_recipe(
                [
                    {
                        "stateId": "await",
                        "action": "wait",
                        "locatorRef": "xianyu_publish_page",
                        "onSuccess": "SUCCEEDED",
                        "onFailure": "FAILED",
                        "maxAttempts": 999,
                    },
                ]
            )
        ),
        should_pass=False,
    )
    # 6. hash mismatch (in-place byte edit of a published recipe) is rejected.
    tampered = _sign_sample(
        _sample_recipe(
            [
                {
                    "stateId": "open",
                    "action": "wait",
                    "locatorRef": "xianyu_home_sell",
                    "onSuccess": "SUCCEEDED",
                    "onFailure": None,
                },
            ]
        )
    )
    tampered["graph"]["maxDurationMs"] = 600001
    expect("in-place-edit-hash-mismatch-rejected", tampered, should_pass=False)
    return 1 if failures else 0


def main(argv) -> int:
    args = list(argv[1:])
    spec_path = DEFAULT_SPEC
    strict_signature = True
    files: list[pathlib.Path] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--spec":
            index += 1
            if index >= len(args):
                print("usage: --spec needs a path", file=sys.stderr)
                return 2
            spec_path = pathlib.Path(args[index])
        elif arg == "--no-strict-signature":
            strict_signature = False
        elif arg in ("--self-test", "--selftest"):
            try:
                spec = load_spec(spec_path)
            except (OSError, json.JSONDecodeError) as error:
                print(f"SELF-TEST SPEC UNREADABLE: {spec_path}: {error}", file=sys.stderr)
                return 2
            return self_test(spec)
        elif arg in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            files.append(pathlib.Path(arg))
        index += 1
    if not files:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        spec = load_spec(spec_path)
    except (OSError, json.JSONDecodeError) as error:
        print(f"SPEC UNREADABLE: {spec_path}: {error}", file=sys.stderr)
        return 2
    exit_code = 0
    for path in files:
        violations = validate_file(path, spec, strict_signature)
        if violations:
            exit_code = 1
            for violation in violations:
                print(f"{path}: {violation}")
        else:
            print(f"{path}: OK")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
