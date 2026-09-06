from __future__ import annotations

import json
from pathlib import Path

from cloudctl_api.app import create_app
from cloudctl_api.settings import Settings


def test_committed_openapi_matches_application() -> None:
    expected = create_app(
        Settings(env="test", repository_mode="memory", dev_auth_bypass=True)
    ).openapi()
    committed = json.loads(Path("packages/api-contracts/openapi.json").read_text(encoding="utf-8"))
    assert committed == expected
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
