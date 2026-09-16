#!/usr/bin/env python3
"""fleet-identity/v1 fixture checker.

Recomputes digests with the frozen action-identity formulas (identical to
mobile_actions.py action_identity / canonical_steps, which are already
cross-language verified by ControlledStepsIdentityTest against
steps-identity-golden.json), then validates K10 fixtures and fills/pins their
expected digests. Exit 0 = pass.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT_DIR = HERE.parent
REPO = CONTRACT_DIR.parents[2]
GOLDEN = REPO / "mobile/companion/app/src/test/resources/steps-identity-golden.json"


def action_key(task_id: str, recipe_sha: str, action_id: str) -> str:
    return hashlib.sha256(
        f"cloudctl.action/v1\n{task_id}\n{recipe_sha}\n{action_id}".encode()
    ).hexdigest()


def parameter_hash(
    task_id: str, command_type: str, account_id: str,
    binding_version: int, snapshot_sha: str, recipe_sha: str,
) -> str:
    params = (
        f"cloudctl.action-parameters/v1\n{task_id}\n{command_type}\n{account_id}\n"
        f"{binding_version}\n{snapshot_sha}\n{recipe_sha}"
    )
    return hashlib.sha256(params.encode()).hexdigest()


def check_algorithm_parity() -> None:
    """The same algorithm must reproduce the cross-language golden digests."""
    g = json.loads(GOLDEN.read_text())
    steps_sha = hashlib.sha256(
        "\n".join(
            "\n".join(
                f"{k}={'true' if step[k] is True else 'false' if step[k] is False else step[k]}"
                for k in sorted(step)
            )
            for step in g["steps"]
        ).encode()
    ).hexdigest()
    assert steps_sha == g["stepsSha256"], "canonical_steps diverged from golden"
    key = action_key(g["taskId"], steps_sha, "click-publish")
    assert key == g["actionKey"], "actionKey diverged from golden"
    params = parameter_hash(
        g["taskId"], "xianyu.publish_listing.steps.v1", g["deviceId"],
        g["bindingVersion"], steps_sha, steps_sha,
    )
    assert params == g["parameterHash"], "parameterHash diverged from golden"


def digest64(v: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{64}", v or ""))


def main() -> int:
    check_algorithm_parity()
    print("algorithm parity: OK (steps-identity-golden.json reproduced)")

    pos = json.loads((CONTRACT_DIR / "fixtures/k10-positive-fleet-claim.json").read_text())
    ai = pos["actionIdentity"]
    key = action_key(ai["taskId"], ai["recipeSha256"], ai["actionId"])
    params = parameter_hash(
        ai["taskId"], ai["commandType"], pos["envelope"]["accountId"],
        pos["envelope"]["bindingVersion"], ai["snapshotSha256"], ai["recipeSha256"],
    )
    if ai.get("expectedActionKey"):
        assert ai["expectedActionKey"] == key, "positive fixture actionKey mismatch"
    if ai.get("expectedParameterHash"):
        assert ai["expectedParameterHash"] == params, "positive fixture parameterHash mismatch"
    # Pin the digests into the fixture so consumers can mirror them.
    ai["expectedActionKey"] = key
    ai["expectedParameterHash"] = params
    (CONTRACT_DIR / "fixtures/k10-positive-fleet-claim.json").write_text(
        json.dumps(pos, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"positive: actionKey={key[:16]}… parameterHash={params[:16]}… pinned")

    assert digest64(ai["recipeSha256"]) and digest64(ai["snapshotSha256"])

    # Negative fixtures: structure assertions only (rejections happen in consumers).
    neg_epoch = json.loads((CONTRACT_DIR / "fixtures/k10-negative-actionkey-contains-epoch.json").read_text())
    assert neg_epoch["expect"] == "REJECT"
    assert "controlEpoch" in json.dumps(neg_epoch["identityInputs"])
    neg_busy = json.loads((CONTRACT_DIR / "fixtures/k10-negative-account-busy.json").read_text())
    assert neg_busy["expect"]["code"] == "ACCOUNT_BUSY" and neg_busy["expect"]["status"] == 409
    running = neg_busy["precondition"]["runningTask"]
    assert running["tenantId"] == neg_busy["incomingTask"]["tenantId"]
    assert running["accountId"] == neg_busy["incomingTask"]["accountId"]
    assert running["taskId"] != neg_busy["incomingTask"]["taskId"]
    assert neg_busy["incomingTask"]["writeEffect"] is True
    neg_unknown = json.loads((CONTRACT_DIR / "fixtures/k10-negative-reclaim-open-unknown.json").read_text())
    assert neg_unknown["expect"]["code"] == "RECONCILE_REQUIRED" and neg_unknown["expect"]["status"] == 409
    assert any(r["status"] == "UNKNOWN" for r in neg_unknown["precondition"]["ledgerRows"])

    print("negative fixtures: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
