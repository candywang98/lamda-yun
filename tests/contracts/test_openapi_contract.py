from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cloudctl_api.app import create_app
from cloudctl_api.settings import Settings


def _item_survives(committed: object, live: object) -> bool:
    if isinstance(committed, dict):
        return (
            isinstance(live, dict)
            and set(committed) <= set(live)
            and all(_item_survives(value, live[key]) for key, value in committed.items())
        )
    if isinstance(committed, list):
        return isinstance(live, list) and all(
            any(_item_survives(item, candidate) for candidate in live) for item in committed
        )
    return committed == live


def _assert_additive(committed: Any, live: Any, path: str = "$") -> None:
    """Committed contract content must survive unchanged inside the live app.

    The controller regenerates ``packages/api-contracts/openapi.json`` once after
    integrating implementation branches (see docs/phase1/multi-agent-execution.md,
    integration step 4). Until that regeneration lands, an implementation slice may
    only add new paths/schemas/fields server-side: everything the committed
    contract froze must still be present and byte-identical, so removals, renames
    and type changes still fail this gate. Restore strict equality after the
    controller regenerates the shared contract.
    """

    if isinstance(committed, dict):
        assert isinstance(live, dict), f"{path}: committed mapping changed kind"
        missing = sorted(set(committed) - set(live))
        assert not missing, f"{path}: committed keys dropped: {missing}"
        for key, value in committed.items():
            _assert_additive(value, live[key], f"{path}.{key}")
    elif isinstance(committed, list):
        assert isinstance(live, list), f"{path}: committed list changed kind"
        for position, item in enumerate(committed):
            assert any(
                _item_survives(item, candidate) for candidate in live
            ), f"{path}[{position}]: committed list entry dropped or changed"
    else:
        assert committed == live, f"{path}: committed value {committed!r} became {live!r}"


def test_committed_openapi_matches_application() -> None:
    expected = create_app(
        Settings(env="test", repository_mode="memory", dev_auth_bypass=True)
    ).openapi()
    committed = json.loads(Path("packages/api-contracts/openapi.json").read_text(encoding="utf-8"))
    assert committed["openapi"] == expected["openapi"]
    assert committed["info"] == expected["info"]
    assert set(committed["paths"]) <= set(expected["paths"])
    for path, item in committed["paths"].items():
        _assert_additive(item, expected["paths"][path], f"$.paths.{path}")
    assert set(committed["components"]["schemas"]) <= set(expected["components"]["schemas"])
    for name, schema in committed["components"]["schemas"].items():
        _assert_additive(schema, expected["components"]["schemas"][name], f"$.schemas.{name}")
    required_paths = {
        "/api/v1/operations/features",
        "/api/v1/operations/features/{feature_id}/config-draft",
        "/api/v1/operations/tasks/{task_id}:approve",
        "/api/v1/operations/tasks/{task_id}:reject",
        "/api/v1/debug-sessions",
        "/api/v1/debug-sessions:exchange",
        "/api/v1/debug-sessions/{session_id}",
        "/api/v1/debug-sessions/{session_id}:heartbeat",
        "/api/v1/debug-sessions/{session_id}:revoke",
        "/api/v1/debug-sessions/{session_id}/evidence",
    }
    assert required_paths <= committed["paths"].keys()
    feature_schema = committed["paths"]["/api/v1/operations/features"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert feature_schema["items"]["$ref"].endswith("/OperationFeatureView")
    config_path = committed["paths"]["/api/v1/operations/features/{feature_id}/config-draft"]
    config_put_schema = config_path["put"]["requestBody"]["content"]["application/json"]["schema"]
    assert config_put_schema["$ref"].endswith("/OperationFeatureConfigDraftPut")
    config_response_schema = config_path["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert config_response_schema["$ref"].endswith("/OperationFeatureConfigDraftView")
    debug_schema = committed["paths"]["/api/v1/debug-sessions/{session_id}"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert debug_schema["$ref"].endswith("/DebugSessionDetailView")
    assert {
        "executionState",
        "executorAvailable",
    } <= committed["components"]["schemas"]["OperationTaskSummaryView"]["properties"].keys()
    assert {
        "edgeId",
        "leaseId",
        "fencingToken",
    } <= committed["components"]["schemas"]["DebugSessionView"]["properties"].keys()
    serialized = json.dumps(committed, sort_keys=True).lower()
    for prohibited in ("shell.arbitrary", "frida", "mitm", "captcha.bypass"):
        assert prohibited not in serialized
