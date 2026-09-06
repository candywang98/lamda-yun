from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).parents[1]
for source in ("packages/edge-protocol/src", "edge/gateway/src"):
    sys.path.insert(0, str(ROOT / source))

from cloudctl_edge.companion_api import CompanionAuthStore, create_companion_app
from cloudctl_edge.operator_actions import OperatorActionCoordinator
from cloudctl_edge.spool import EdgeSpool
from cloudctl_edge_protocol import edge_control_pb2 as pb


class FakeSupervisor:
    def __init__(self) -> None:
        self.active: dict[str, str] = {}
        self.canceled: list[str] = []

    def active_command(self, device_id: str) -> str | None:
        return self.active.get(device_id)

    async def cancel(self, command_id: str) -> bool:
        if command_id not in self.active.values():
            return False
        self.canceled.append(command_id)
        return True


@pytest.mark.asyncio
async def test_enrollment_is_one_time_and_token_is_device_bound(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")
    auth = CompanionAuthStore(spool)
    auth.issue_enrollment_code(
        code="ABCD-1234",
        device_id="device-a",
        tenant_name="Tenant A",
        site_name="Site A",
    )
    supervisor = FakeSupervisor()
    app = create_companion_app(
        spool=spool,
        auth_store=auth,
        operator_actions=OperatorActionCoordinator(spool, supervisor),
        supervisor=supervisor,
        current_version="0.1.0",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://edge.local"
    ) as client:
        enrolled = await client.post("/companion/v1/enroll", json={"code": "ABCD-1234"})
        assert enrolled.status_code == 200
        body = enrolled.json()
        token = body["bindingToken"]
        assert body["deviceId"] == "device-a"
        assert token
        assert (
            await client.post("/companion/v1/enroll", json={"code": "ABCD-1234"})
        ).status_code == 409
        assert (await client.get("/companion/v1/devices/device-a/snapshot")).status_code == 401
        assert (
            await client.get(
                "/companion/v1/devices/device-b/snapshot",
                headers={"Authorization": f"Bearer {token}"},
            )
        ).status_code == 403

    database_files = await asyncio.to_thread(lambda: list(tmp_path.glob("spool.sqlite3*")))
    database_payloads = await asyncio.gather(
        *(asyncio.to_thread(path.read_bytes) for path in database_files)
    )
    assert all(token.encode() not in payload for payload in database_payloads)


@pytest.mark.asyncio
async def test_binding_revocation_invalidates_token_immediately(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")
    auth = CompanionAuthStore(spool)
    auth.issue_enrollment_code(
        code="DEVICE-CODE",
        device_id="device-a",
        tenant_name="Tenant A",
        site_name="Site A",
    )
    supervisor = FakeSupervisor()
    app = create_companion_app(
        spool=spool,
        auth_store=auth,
        operator_actions=OperatorActionCoordinator(spool, supervisor),
        supervisor=supervisor,
        current_version="0.1.0",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://edge.local"
    ) as client:
        token = (await client.post("/companion/v1/enroll", json={"code": "DEVICE-CODE"})).json()[
            "bindingToken"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        assert (
            await client.delete("/companion/v1/devices/device-b/binding", headers=headers)
        ).status_code == 403
        assert (
            await client.get("/companion/v1/devices/device-a/snapshot", headers=headers)
        ).status_code == 200
        assert (
            await client.delete("/companion/v1/devices/device-a/binding", headers=headers)
        ).status_code == 204
        assert (
            await client.get("/companion/v1/devices/device-a/snapshot", headers=headers)
        ).status_code == 401
        assert (
            await client.delete("/companion/v1/devices/device-a/binding", headers=headers)
        ).status_code == 401


def test_python_normalizer_matches_shared_android_code_contract() -> None:
    cases = ROOT.joinpath("contracts/companion-enrollment-code-cases.tsv").read_text(
        encoding="utf-8"
    )
    for line in cases.splitlines():
        if not line or line.startswith("#"):
            continue
        accepted, value, expected = line.split("\t")
        if accepted == "true":
            assert CompanionAuthStore._normalize_code(value) == expected
        else:
            with pytest.raises(ValueError):
                CompanionAuthStore._normalize_code(value)


@pytest.mark.asyncio
async def test_health_snapshot_confirmation_and_stop_are_authenticated(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")
    auth = CompanionAuthStore(spool)
    auth.issue_enrollment_code(
        code="DEVICE-CODE",
        device_id="device-a",
        tenant_name="Tenant A",
        site_name="Site A",
    )
    supervisor = FakeSupervisor()
    actions = OperatorActionCoordinator(spool, supervisor)
    app = create_companion_app(
        spool=spool,
        auth_store=auth,
        operator_actions=actions,
        supervisor=supervisor,
        current_version="0.1.0",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://edge.local"
    ) as client:
        token = (await client.post("/companion/v1/enroll", json={"code": "DEVICE-CODE"})).json()[
            "bindingToken"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        health = {
            "batteryPercent": 71,
            "charging": True,
            "network": "WIFI",
            "temperatureCelsius": 31.5,
            "freeStorageBytes": 4096,
            "companionVersion": "0.1.0",
            "observedAt": datetime.now(UTC).isoformat(),
        }
        assert (
            await client.post("/companion/v1/devices/device-a/health", json=health, headers=headers)
        ).status_code == 204
        snapshot = (
            await client.get("/companion/v1/devices/device-a/snapshot", headers=headers)
        ).json()
        assert snapshot["health"]["batteryPercent"] == 71
        assert snapshot["update"]["currentVersion"] == "0.1.0"
        assert snapshot["task"] is None
        assert snapshot["deliveries"] == []
        assert snapshot["currentTask"] is None
        assert snapshot["automationStopped"] is False

        required = pb.ConfirmationRequired(
            confirmation_id="confirm-a",
            command_id="command-a",
            task_run_id="task-a",
            device_id="device-a",
            title="Publish",
            detail="Confirm the authorized publish operation",
            risk_level="HIGH",
        )
        required.expires_at.FromDatetime(datetime.now(UTC) + timedelta(minutes=2))
        actions.require_confirmation(required)
        confirmed = await client.post(
            "/companion/v1/confirmations/confirm-a",
            json={"approved": True},
            headers=headers,
        )
        assert confirmed.status_code == 202

        assert (
            await client.post(
                "/companion/v1/devices/device-a/emergency-stop", json={}, headers=headers
            )
        ).status_code == 409
        supervisor.active["device-a"] = "command-a"
        stopped = await client.post(
            "/companion/v1/devices/device-a/emergency-stop", json={}, headers=headers
        )
        assert stopped.status_code == 202
        assert supervisor.canceled == ["command-a"]

    actions_outbound = [
        message.operator_action.action
        for message in spool.replay_edge_messages()
        if message.WhichOneof("body") == "operator_action"
    ]
    assert actions_outbound == ["CONFIRM", "STOP_AUTOMATION"]
