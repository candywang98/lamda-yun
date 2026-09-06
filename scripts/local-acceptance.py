#!/usr/bin/env python3
"""Run a process-level local acceptance suite without touching real devices.

The suite starts the Control API and a mock-only Companion API on loopback ports,
then exercises their public HTTP contracts. It never opens ADB, device port 65000,
or a LAMDA session, and its result is not hardware acceptance evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = (
    "packages/domain/src",
    "packages/edge-protocol/src",
    "packages/lamda-driver/src",
    "packages/automation-sdk/src",
    "packages/observability/src",
    "services/control-api/src",
    "services/temporal-worker/src",
    "services/edge-hub/src",
    "services/outbox-dispatcher/src",
    "edge/gateway/src",
)
EXPECTED_FEATURE_COUNTS = {
    "system-home": 10,
    "task-queue": 1,
    "product-editor": 10,
    "collection": 14,
    "product-management": 10,
    "post-management": 9,
    "orders": 5,
    "analytics": 3,
    "xy-tasks": 31,
    "zz-tasks": 9,
    "red-tasks": 4,
    "creative": 4,
    "chat": 11,
    "assets": 8,
    "profile": 5,
}
TENANT_ID = "00000000-0000-7000-8000-00000000a001"
CREATOR_ID = "00000000-0000-7000-8000-00000000a002"
APPROVER_ID = "00000000-0000-7000-8000-00000000a003"
DEVICE_ID = "device-local-acceptance"
COMMAND_ID = "command-local-acceptance"
CONFIRMATION_ID = "confirmation-local-acceptance"
ENROLLMENT_CODE = "LOCAL-ACCEPTANCE-ONLY"


class AcceptanceError(RuntimeError):
    """Raised when a runtime acceptance assertion fails."""


@dataclass(frozen=True, slots=True)
class CheckResult:
    component: str
    check: str
    status: str
    detail: str


class Recorder:
    def __init__(self) -> None:
        self.results: list[CheckResult] = []

    def pass_check(self, component: str, check: str, detail: str) -> None:
        self.results.append(CheckResult(component, check, "passed", detail))
        print(f"PASS [{component}] {check}: {detail}")


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise AcceptanceError(detail)


def _headers(
    roles: str,
    *,
    user_id: str = CREATOR_ID,
    idempotency_key: str | None = None,
    relay_token: str | None = None,
) -> dict[str, str]:
    values = {
        "X-Tenant-Id": TENANT_ID,
        "X-User-Id": user_id,
        "X-Roles": roles,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }
    if idempotency_key is not None:
        values["Idempotency-Key"] = idempotency_key
    if relay_token is not None:
        values["X-Debug-Relay-Token"] = relay_token
    return values


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected: int | set[int] = 200,
    **kwargs: Any,
) -> httpx.Response:
    response = client.request(method, path, **kwargs)
    allowed = {expected} if isinstance(expected, int) else expected
    if response.status_code not in allowed:
        raise AcceptanceError(
            f"{method} {path} returned {response.status_code}; "
            f"expected {sorted(allowed)}: {response.text[:500]}"
        )
    return response


def _python_environment() -> dict[str, str]:
    environment = os.environ.copy()
    source_paths = [str(ROOT / path) for path in SOURCE_DIRS]
    existing = environment.get("PYTHONPATH")
    if existing:
        source_paths.append(existing)
    environment["PYTHONPATH"] = os.pathsep.join(source_paths)
    environment["PYTHONUNBUFFERED"] = "1"
    return environment


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _log_tail(path: Path, lines: int = 40) -> str:
    if not path.exists():
        return "process log was not created"
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


@contextmanager
def _managed_process(
    command: Sequence[str],
    *,
    environment: dict[str, str],
    log_path: Path,
) -> Iterator[subprocess.Popen[str]]:
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(  # noqa: S603
            list(command),
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def _wait_for_http(process: subprocess.Popen[str], url: str, log_path: Path) -> None:
    deadline = time.monotonic() + 25
    with httpx.Client(timeout=1.0, trust_env=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AcceptanceError(
                    f"process exited before {url} became ready\n{_log_tail(log_path)}"
                )
            try:
                response = client.get(url)
                if response.status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
    raise AcceptanceError(f"timed out waiting for {url}\n{_log_tail(log_path)}")


def _run_edge_check(environment: dict[str, str], recorder: Recorder) -> None:
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "cloudctl_edge", "--check"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    _require(completed.returncode == 0, completed.stderr or completed.stdout)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AcceptanceError("Edge --check did not return JSON") from exc
    _require(payload == {"mode": "network-free-check", "status": "ok"}, str(payload))
    recorder.pass_check(
        "edge-gateway",
        "network-free startup check",
        "cloudctl_edge --check imported the composed runtime without network or hardware access",
    )


def _control_contract(client: httpx.Client, recorder: Recorder) -> None:
    live = _request(client, "GET", "/health/live").json()
    ready = _request(client, "GET", "/health/ready").json()
    _require(live == {"status": "ok"}, str(live))
    _require(ready == {"status": "ok", "repositoryMode": "memory"}, str(ready))
    recorder.pass_check("control-api", "health", "live and ready endpoints passed in memory mode")

    openapi = _request(client, "GET", "/openapi.json").json()
    required_paths = {
        "/api/v1/operations/catalog",
        "/api/v1/operations/features",
        "/api/v1/operations/tasks",
        "/api/v1/operations:batch",
        "/api/v1/operations/tasks/{task_id}",
        "/api/v1/operations/tasks/{task_id}:cancel",
        "/api/v1/operations/tasks/{task_id}:approve",
        "/api/v1/operations/tasks/{task_id}/audit-result",
        "/api/v1/debug-sessions",
        "/api/v1/debug-sessions:exchange",
        "/api/v1/debug-sessions/{session_id}",
        "/api/v1/debug-sessions/{session_id}:heartbeat",
        "/api/v1/debug-sessions/{session_id}/evidence",
        "/api/v1/debug-sessions/{session_id}:revoke",
    }
    missing = sorted(required_paths - set(openapi.get("paths", {})))
    _require(not missing, f"OpenAPI is missing paths: {missing}")
    recorder.pass_check(
        "control-api", "OpenAPI surface", f"{len(required_paths)} required paths found"
    )

    viewer = _headers("viewer")
    catalog = _request(client, "GET", "/api/v1/operations/catalog", headers=viewer).json()
    features = _request(client, "GET", "/api/v1/operations/features", headers=viewer).json()
    _require(len(catalog) == 15, f"expected 15 catalog modules, got {len(catalog)}")
    _require(len({item["module"] for item in catalog}) == 15, "catalog modules are not unique")
    _require(len(features) == 134, f"expected 134 features, got {len(features)}")
    feature_ids = [str(item["featureId"]) for item in features]
    _require(len(set(feature_ids)) == 134, "feature IDs are not unique")
    counts = Counter(feature_id.rsplit("-", 1)[0] for feature_id in feature_ids)
    _require(dict(counts) == EXPECTED_FEATURE_COUNTS, f"feature module counts differ: {counts}")
    policies = Counter(str(item["policy"]) for item in features)
    _require(set(policies) <= {"mapped", "unmapped", "blocked"}, str(policies))
    deployed = {
        str(item["operationKey"]) for item in features if item["executionState"] == "implemented"
    }
    _require(
        deployed == {"publish_plans.snapshot.validate", "works.revision.validate"},
        f"unexpected local executor set: {sorted(deployed)}",
    )
    recorder.pass_check(
        "control-api",
        "15 modules and 134 features",
        f"catalog=15, features=134, policies={dict(sorted(policies.items()))}, "
        f"localExecutors={sorted(deployed)}",
    )


def _operations_contract(client: httpx.Client, recorder: Recorder) -> None:
    creator = _headers("content_editor", idempotency_key="runtime-standard-1")
    created = _request(
        client,
        "POST",
        "/api/v1/operations/tasks",
        expected=201,
        headers=creator,
        json={
            "featureId": "product-management-09",
            "operationKey": "works.revision.validate",
            "resourceId": "revision-runtime-1",
            "parameters": {"policyVersion": "baseline-v1"},
            "context": {"source": "local-acceptance", "reason": "runtime contract"},
        },
    )
    standard = created.json()
    standard_id = str(standard["id"])
    _require(standard["status"] == "QUEUED", str(standard))

    listed = _request(
        client,
        "GET",
        "/api/v1/operations/tasks",
        headers=_headers("content_editor"),
        params={"status": "QUEUED"},
    ).json()
    _require(standard_id in {str(item["id"]) for item in listed}, "created task was not listed")
    fetched = _request(
        client,
        "GET",
        f"/api/v1/operations/tasks/{standard_id}",
        headers=_headers("content_editor"),
    ).json()
    _require(fetched["id"] == standard_id, "task lookup returned the wrong task")
    canceled = _request(
        client,
        "POST",
        f"/api/v1/operations/tasks/{standard_id}:cancel",
        headers=_headers("content_editor"),
        json={"reason": "local acceptance cancellation"},
    ).json()
    _require(canceled["status"] == "CANCELED", str(canceled))
    audit = _request(
        client,
        "GET",
        f"/api/v1/operations/tasks/{standard_id}/audit-result",
        headers=_headers("content_editor"),
    ).json()
    actions = {str(event["action"]) for event in audit["auditEvents"]}
    _require("operation.task.created" in actions, str(actions))
    _require(any("cancel" in action for action in actions), str(actions))
    recorder.pass_check(
        "control-api",
        "operation create/list/get/cancel/audit",
        "queued task was discoverable, canceled, and returned durable audit events",
    )

    approval = _request(
        client,
        "POST",
        "/api/v1/operations/tasks",
        expected=201,
        headers=_headers("publisher", idempotency_key="runtime-approval-1"),
        json={
            "featureId": "product-management-05",
            "operationKey": "publish_plans.snapshot.validate",
            "resourceId": "snapshot-runtime-1",
            "parameters": {"strict": True},
            "context": {"source": "local-acceptance", "reason": "approval contract"},
        },
    ).json()
    approval_id = str(approval["id"])
    _require(approval["status"] == "PENDING_APPROVAL", str(approval))
    _request(
        client,
        "POST",
        f"/api/v1/operations/tasks/{approval_id}:approve",
        expected=403,
        headers=_headers("approver"),
        json={"reason": "self approval must remain forbidden"},
    )
    approved = _request(
        client,
        "POST",
        f"/api/v1/operations/tasks/{approval_id}:approve",
        headers=_headers("approver", user_id=APPROVER_ID),
        json={"reason": "independent local acceptance approval"},
    ).json()
    _require(approved["status"] == "QUEUED", str(approved))
    _require(approved["approvalDecision"] == "APPROVED", str(approved))
    approval_audit = _request(
        client,
        "GET",
        f"/api/v1/operations/tasks/{approval_id}/audit-result",
        headers=_headers("publisher"),
    ).json()
    approval_actions = {str(event["action"]) for event in approval_audit["auditEvents"]}
    _require(any("approv" in action for action in approval_actions), str(approval_actions))
    recorder.pass_check(
        "control-api",
        "operation approval separation",
        "self-approval was denied and an independent MFA approver released the task",
    )


def _debug_contract(client: httpx.Client, recorder: Recorder) -> None:
    admin = _headers("security_admin")
    edge = _request(
        client,
        "POST",
        "/api/v1/edges",
        expected=201,
        headers=admin,
        json={"logicalName": "runtime-edge", "certificateFingerprint": "ab" * 32},
    ).json()
    device = _request(
        client,
        "POST",
        "/api/v1/devices",
        expected=201,
        headers=admin,
        json={"edgeId": edge["id"], "logicalName": "runtime-device", "labels": ["mock"]},
    ).json()
    device_id = str(device["id"])
    _request(
        client,
        "POST",
        f"/api/v1/devices/{device_id}:maintenance",
        headers=admin,
        json={"enabled": True, "reason": "authorized local acceptance debugging"},
    )

    developer = _headers("automation_developer")
    created = _request(
        client,
        "POST",
        "/api/v1/debug-sessions",
        expected=201,
        headers=developer,
        json={
            "deviceId": device_id,
            "capabilities": ["view.frame", "view.layout", "input.tap", "evidence.capture"],
            "ttlSeconds": 900,
            "purpose": "authorized local locator acceptance",
            "returnUrl": "http://127.0.0.1:5174/session",
        },
    ).json()
    session_id = str(created["session"]["id"])
    launch_code = str(created["launchCode"])
    _require(launch_code not in json.dumps(created["session"]), "launch code leaked into session")
    exchanged = _request(
        client,
        "POST",
        "/api/v1/debug-sessions:exchange",
        headers=developer,
        json={"launchCode": launch_code},
    ).json()
    relay_token = str(exchanged["relayToken"])
    _require(exchanged["session"]["status"] == "ACTIVE", str(exchanged["session"]))
    _request(
        client,
        "POST",
        "/api/v1/debug-sessions:exchange",
        expected=409,
        headers=developer,
        json={"launchCode": launch_code},
    )
    fetched = _request(
        client,
        "GET",
        f"/api/v1/debug-sessions/{session_id}",
        headers=developer,
    ).json()
    _require(fetched["status"] == "ACTIVE", str(fetched))
    _request(
        client,
        "POST",
        f"/api/v1/debug-sessions/{session_id}:heartbeat",
        headers=_headers("automation_developer", relay_token=relay_token),
        json={"stage": "LOCATOR_LAB", "event": "FRAME_READY", "detail": "mock frame"},
    )
    evidence = _request(
        client,
        "POST",
        f"/api/v1/debug-sessions/{session_id}/evidence",
        expected=201,
        headers=_headers("automation_developer", relay_token=relay_token),
        json={
            "kind": "SCREENSHOT",
            "sha256": "a" * 64,
            "objectRef": "s3://local-acceptance/debug/frame-1.png",
            "metadata": {"mock": True, "width": 1080, "height": 2400},
        },
    ).json()
    _require(evidence["kind"] == "SCREENSHOT", str(evidence))
    revoked = _request(
        client,
        "POST",
        f"/api/v1/debug-sessions/{session_id}:revoke",
        headers=developer,
        json={"reason": "local acceptance complete"},
    ).json()
    _require(revoked["status"] == "REVOKED", str(revoked))
    _request(
        client,
        "POST",
        f"/api/v1/debug-sessions/{session_id}:heartbeat",
        expected=409,
        headers=_headers("automation_developer", relay_token=relay_token),
        json={"stage": "DONE", "event": "LATE_HEARTBEAT"},
    )
    recorder.pass_check(
        "control-api",
        "debug session lifecycle",
        "create/exchange/get/heartbeat/evidence/revoke passed; "
        "code replay and late heartbeat denied",
    )


def _companion_contract(client: httpx.Client, recorder: Recorder) -> None:
    enrolled = _request(
        client,
        "POST",
        "/companion/v1/enroll",
        json={"code": ENROLLMENT_CODE},
    ).json()
    _require(enrolled["deviceId"] == DEVICE_ID, str(enrolled))
    token = str(enrolled["bindingToken"])
    _request(
        client,
        "POST",
        "/companion/v1/enroll",
        expected=409,
        json={"code": ENROLLMENT_CODE},
    )
    headers = {"Authorization": f"Bearer {token}"}
    _request(
        client,
        "GET",
        "/companion/v1/devices/another-device/snapshot",
        expected=403,
        headers=headers,
    )
    _request(
        client,
        "POST",
        f"/companion/v1/devices/{DEVICE_ID}/health",
        expected=204,
        headers=headers,
        json={
            "batteryPercent": 73,
            "charging": True,
            "network": "WIFI",
            "temperatureCelsius": 31.5,
            "freeStorageBytes": 4096,
            "companionVersion": "0.1.0-local-acceptance",
            "observedAt": datetime.now(UTC).isoformat(),
        },
    )
    snapshot = _request(
        client,
        "GET",
        f"/companion/v1/devices/{DEVICE_ID}/snapshot",
        headers=headers,
    ).json()
    _require(snapshot["health"]["batteryPercent"] == 73, str(snapshot["health"]))
    _require(snapshot["task"]["state"] == "RUNNING", str(snapshot["task"]))
    _require(snapshot["confirmation"]["id"] == CONFIRMATION_ID, str(snapshot["confirmation"]))
    recorder.pass_check(
        "companion-api",
        "enrollment, health, and snapshot",
        "one-time enrollment, device-bound auth, health upload, task and confirmation "
        "snapshot passed",
    )

    confirmed = _request(
        client,
        "POST",
        f"/companion/v1/confirmations/{CONFIRMATION_ID}",
        expected=202,
        headers=headers,
        json={"approved": True},
    ).json()
    _require(confirmed["state"] == "ACCEPTED", str(confirmed))
    stopped = _request(
        client,
        "POST",
        f"/companion/v1/devices/{DEVICE_ID}/emergency-stop",
        expected=202,
        headers=headers,
        json={},
    ).json()
    _require(stopped == {"state": "STOPPING", "commandId": COMMAND_ID}, str(stopped))
    stopped_snapshot = _request(
        client,
        "GET",
        f"/companion/v1/devices/{DEVICE_ID}/snapshot",
        headers=headers,
    ).json()
    _require(stopped_snapshot["automationStopped"] is True, str(stopped_snapshot))
    recorder.pass_check(
        "companion-api",
        "confirmation and emergency stop",
        "approved confirmation and emergency stop were recorded through the mock supervisor",
    )


def _serve_mock_companion(port: int, state_dir: Path) -> int:
    for source in SOURCE_DIRS:
        source_path = str(ROOT / source)
        if source_path not in sys.path:
            sys.path.insert(0, source_path)

    import uvicorn
    from cloudctl_edge.companion_api import CompanionAuthStore, create_companion_app
    from cloudctl_edge.operator_actions import OperatorActionCoordinator
    from cloudctl_edge.spool import EdgeSpool
    from cloudctl_edge_protocol import edge_control_pb2 as pb

    class MockSupervisor:
        def __init__(self) -> None:
            self.active = {DEVICE_ID: COMMAND_ID}

        def active_command(self, device_id: str) -> str | None:
            return self.active.get(device_id)

        async def cancel(self, command_id: str) -> bool:
            await asyncio.sleep(0)
            if command_id not in self.active.values():
                return False
            return True

    spool = EdgeSpool(state_dir / "mock-companion.sqlite3")
    auth = CompanionAuthStore(spool)
    auth.issue_enrollment_code(
        code=ENROLLMENT_CODE,
        device_id=DEVICE_ID,
        tenant_name="Local acceptance tenant",
        site_name="Loopback mock site",
    )
    supervisor = MockSupervisor()
    actions = OperatorActionCoordinator(spool, supervisor)
    command = pb.StartCommand(
        command_id=COMMAND_ID,
        task_run_id="task-local-acceptance",
        device_id=DEVICE_ID,
        lease_id="lease-local-acceptance",
        fencing_token=1,
        command_type="RUN_AUTOMATION",
    )
    command.deadline.FromDatetime(datetime.now(UTC) + timedelta(minutes=5))
    spool.accept_command(command)
    spool.set_command_state(COMMAND_ID, "STARTED")
    required = pb.ConfirmationRequired(
        confirmation_id=CONFIRMATION_ID,
        command_id=COMMAND_ID,
        task_run_id="task-local-acceptance",
        device_id=DEVICE_ID,
        title="Approve local mock step",
        detail="This is a mock-only runtime acceptance confirmation.",
        risk_level="HIGH",
    )
    required.expires_at.FromDatetime(datetime.now(UTC) + timedelta(minutes=5))
    actions.require_confirmation(required)
    app = create_companion_app(
        spool=spool,
        auth_store=auth,
        operator_actions=actions,
        supervisor=supervisor,
        current_version="0.1.0-local-acceptance",
    )
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    finally:
        spool.close()
    return 0


def _build_report(recorder: Recorder, component: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "passed",
        "requestedComponent": component,
        "evidenceClass": "mock_only",
        "hardwareEvidence": False,
        "warning": (
            "This report proves local process and HTTP contract behavior only. It is not evidence "
            "of an APK build, APK installation, a real LAMDA session, or authorized device control."
        ),
        "checks": [asdict(result) for result in recorder.results],
    }


def run_acceptance(report_path: Path | None, component: str) -> int:
    environment = _python_environment()
    environment.update(
        {
            "CLOUDCTL_ENV": "test",
            "CLOUDCTL_REPOSITORY_MODE": "memory",
            "CLOUDCTL_DEV_AUTH_BYPASS": "true",
        }
    )
    recorder = Recorder()
    if component in {"all", "edge"}:
        _run_edge_check(environment, recorder)

    with tempfile.TemporaryDirectory(prefix="cloudctl-local-acceptance-") as temporary:
        temp_dir = Path(temporary)
        if component in {"all", "control"}:
            control_port = _free_loopback_port()
            control_url = f"http://127.0.0.1:{control_port}"
            control_log = temp_dir / "control-api.log"
            control_command = [
                sys.executable,
                "-m",
                "uvicorn",
                "cloudctl_api.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(control_port),
                "--log-level",
                "warning",
                "--no-access-log",
            ]
            with _managed_process(
                control_command,
                environment=environment,
                log_path=control_log,
            ) as process:
                _wait_for_http(process, f"{control_url}/health/live", control_log)
                with httpx.Client(base_url=control_url, timeout=5.0, trust_env=False) as client:
                    _control_contract(client, recorder)
                    _operations_contract(client, recorder)
                    _debug_contract(client, recorder)

        if component in {"all", "edge"}:
            companion_port = _free_loopback_port()
            companion_url = f"http://127.0.0.1:{companion_port}"
            companion_log = temp_dir / "companion-api.log"
            companion_command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--serve-mock-companion",
                "--port",
                str(companion_port),
                "--state-dir",
                str(temp_dir / "edge-state"),
            ]
            with _managed_process(
                companion_command,
                environment=environment,
                log_path=companion_log,
            ) as process:
                _wait_for_http(process, f"{companion_url}/openapi.json", companion_log)
                with httpx.Client(base_url=companion_url, timeout=5.0, trust_env=False) as client:
                    _companion_contract(client, recorder)

    report = _build_report(recorder, component)
    if report_path is not None:
        resolved = report_path if report_path.is_absolute() else ROOT / report_path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(
            json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
        )
        print(f"REPORT {resolved}")
    print("PASS [summary] local acceptance completed in mock_only mode; hardwareEvidence=false")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        help="write a machine-readable JSON report relative to the repository root",
    )
    parser.add_argument(
        "--component",
        choices=("all", "control", "edge"),
        default="all",
        help="run the full suite or one independently restartable component",
    )
    parser.add_argument(
        "--serve-mock-companion",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--port", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--state-dir", type=Path, help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    if arguments.serve_mock_companion:
        if arguments.port is None or arguments.state_dir is None:
            parser.error("internal mock Companion mode requires --port and --state-dir")
        return _serve_mock_companion(arguments.port, arguments.state_dir)
    try:
        return run_acceptance(arguments.report, arguments.component)
    except (AcceptanceError, httpx.HTTPError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL [summary] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
