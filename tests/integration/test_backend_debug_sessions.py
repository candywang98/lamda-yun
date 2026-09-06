from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.settings import Settings

TENANT = "00000000-0000-7000-8000-000000004111"
CREATOR = "00000000-0000-7000-8000-000000004222"
OTHER = "00000000-0000-7000-8000-000000004333"
DEVELOPMENT_TENANT = "00000000-0000-7000-8000-000000001111"
DEVELOPMENT_OPERATOR = "00000000-0000-7000-8000-000000002206"


def headers(user: str = CREATOR, roles: str = "automation_developer") -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT,
        "X-User-Id": user,
        "X-Roles": roles,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as value:
            yield value


async def maintenance_device(client: httpx.AsyncClient) -> str:
    admin = headers(roles="security_admin")
    edge = (
        await client.post(
            "/api/v1/edges",
            headers=admin,
            json={"logicalName": "debug-edge", "certificateFingerprint": "ab" * 32},
        )
    ).json()
    device = (
        await client.post(
            "/api/v1/devices",
            headers=admin,
            json={"edgeId": edge["id"], "logicalName": "debug-device", "labels": ["lab"]},
        )
    ).json()
    changed = await client.post(
        f"/api/v1/devices/{device['id']}:maintenance",
        headers=admin,
        json={"enabled": True, "reason": "authorized debug session"},
    )
    assert changed.status_code == 200, changed.text
    return str(device["id"])


@pytest.mark.asyncio
async def test_development_memory_startup_seeds_authorized_studio_device() -> None:
    settings = Settings(env="development", repository_mode="memory", dev_auth_bypass=True)
    app = create_app(settings)
    development_headers = {
        "X-Tenant-Id": DEVELOPMENT_TENANT,
        "X-User-Id": DEVELOPMENT_OPERATOR,
        "X-Roles": "device_operator",
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as development_client:
            response = await development_client.post(
                "/api/v1/debug-sessions",
                headers=development_headers,
                json={
                    "deviceId": "dev-bj-008",
                    "capabilities": ["view.frame", "view.layout", "input.tap"],
                    "ttlSeconds": 900,
                    "purpose": "browser to Studio development acceptance",
                    "returnUrl": "http://127.0.0.1:5173/studio",
                },
            )

    assert response.status_code == 201, response.text
    assert response.json()["session"]["deviceId"] == "dev-bj-008"
    assert response.json()["session"]["status"] == "PENDING_EXCHANGE"
    assert response.json()["session"]["expiresAt"].endswith(("Z", "+00:00"))
    assert response.json()["session"]["createdAt"].endswith(("Z", "+00:00"))


def test_demo_seed_is_disabled_outside_bypassed_development_memory() -> None:
    assert Settings(
        env="development", repository_mode="memory", dev_auth_bypass=True
    ).auto_seed_development_data()
    assert not Settings(
        env="development", repository_mode="memory", dev_auth_bypass=False
    ).auto_seed_development_data()
    assert not Settings(
        env="test", repository_mode="memory", dev_auth_bypass=True
    ).auto_seed_development_data()
    assert not Settings(
        env="development", repository_mode="sqlite", dev_auth_bypass=True
    ).auto_seed_development_data()


@pytest.mark.asyncio
async def test_debug_session_one_time_exchange_heartbeat_evidence_and_revoke(
    client: httpx.AsyncClient,
) -> None:
    device_id = await maintenance_device(client)
    created = await client.post(
        "/api/v1/debug-sessions",
        headers=headers(),
        json={
            "deviceId": device_id,
            "capabilities": ["view.frame", "view.layout", "input.tap", "evidence.capture"],
            "ttlSeconds": 900,
            "purpose": "authorized locator debugging",
            "returnUrl": "http://127.0.0.1:5174/session",
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    session_id = payload["session"]["id"]
    launch_code = payload["launchCode"]
    lease_id = payload["session"]["leaseId"]
    fencing_token = payload["session"]["fencingToken"]
    assert lease_id
    assert fencing_token >= 1
    assert launch_code not in str(payload["session"])

    duplicate = await client.post(
        "/api/v1/debug-sessions",
        headers=headers(),
        json={
            "deviceId": device_id,
            "capabilities": ["view.frame"],
            "purpose": "must not create a second runner",
        },
    )
    assert duplicate.status_code == 409

    maintenance_change = await client.post(
        f"/api/v1/devices/{device_id}:maintenance",
        headers=headers(roles="security_admin"),
        json={"enabled": False, "reason": "must wait for debug lease release"},
    )
    assert maintenance_change.status_code == 409

    exchanged = await client.post(
        "/api/v1/debug-sessions:exchange",
        headers=headers(),
        json={"launchCode": launch_code},
    )
    assert exchanged.status_code == 200, exchanged.text
    relay_token = exchanged.json()["relayToken"]
    assert exchanged.json()["session"]["status"] == "ACTIVE"
    replay = await client.post(
        "/api/v1/debug-sessions:exchange",
        headers=headers(),
        json={"launchCode": launch_code},
    )
    assert replay.status_code == 409

    heartbeat = await client.post(
        f"/api/v1/debug-sessions/{session_id}:heartbeat",
        headers=headers() | {"X-Debug-Relay-Token": relay_token},
        json={"stage": "LOCATOR_LAB", "event": "FRAME_READY", "detail": "frame 1"},
    )
    assert heartbeat.status_code == 200, heartbeat.text

    evidence_body = {
        "kind": "SCREENSHOT",
        "sha256": "a" * 64,
        "objectRef": "s3://tenant/debug/frame-1.png",
        "metadata": {"width": 1080, "height": 2400},
    }
    evidence = await client.post(
        f"/api/v1/debug-sessions/{session_id}/evidence",
        headers=headers() | {"X-Debug-Relay-Token": relay_token},
        json=evidence_body,
    )
    replay_evidence = await client.post(
        f"/api/v1/debug-sessions/{session_id}/evidence",
        headers=headers() | {"X-Debug-Relay-Token": relay_token},
        json=evidence_body,
    )
    assert evidence.status_code == 201, evidence.text
    assert replay_evidence.status_code == 200

    unsafe_metadata = await client.post(
        f"/api/v1/debug-sessions/{session_id}/evidence",
        headers=headers() | {"X-Debug-Relay-Token": relay_token},
        json={
            "kind": "DIAGNOSTIC",
            "sha256": "b" * 64,
            "objectRef": "s3://tenant/debug/diagnostic.json",
            "metadata": {"nested": {"accessToken": "must-not-be-recorded"}},
        },
    )
    assert unsafe_metadata.status_code == 422

    unsafe_reference = await client.post(
        f"/api/v1/debug-sessions/{session_id}:heartbeat",
        headers=headers() | {"X-Debug-Relay-Token": relay_token},
        json={
            "stage": "LOCATOR_LAB",
            "event": "BAD_REFERENCE",
            "evidenceRefs": ["file:///tmp/frame.png"],
        },
    )
    assert unsafe_reference.status_code == 422

    forbidden_revoke = await client.post(
        f"/api/v1/debug-sessions/{session_id}:revoke",
        headers=headers(OTHER),
        json={"reason": "not my session"},
    )
    assert forbidden_revoke.status_code == 403
    revoked = await client.post(
        f"/api/v1/debug-sessions/{session_id}:revoke",
        headers=headers(),
        json={"reason": "debug complete"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "REVOKED"
    denied_after_revoke = await client.post(
        f"/api/v1/debug-sessions/{session_id}:heartbeat",
        headers=headers() | {"X-Debug-Relay-Token": relay_token},
        json={"stage": "DONE", "event": "LATE"},
    )
    assert denied_after_revoke.status_code == 409

    maintenance_released = await client.post(
        f"/api/v1/devices/{device_id}:maintenance",
        headers=headers(roles="security_admin"),
        json={"enabled": False, "reason": "debug complete"},
    )
    assert maintenance_released.status_code == 200, maintenance_released.text


@pytest.mark.asyncio
async def test_debug_relay_stops_when_its_device_lease_is_released(
    client: httpx.AsyncClient,
) -> None:
    device_id = await maintenance_device(client)
    created = await client.post(
        "/api/v1/debug-sessions",
        headers=headers(),
        json={
            "deviceId": device_id,
            "capabilities": ["view.frame"],
            "purpose": "fencing lease validation",
        },
    )
    payload = created.json()
    exchanged = await client.post(
        "/api/v1/debug-sessions:exchange",
        headers=headers(),
        json={"launchCode": payload["launchCode"]},
    )
    relay_token = exchanged.json()["relayToken"]
    released = await client.delete(
        f"/api/v1/devices/{device_id}/leases/{payload['session']['leaseId']}",
        headers=headers(roles="security_admin"),
    )
    assert released.status_code == 204, released.text

    denied = await client.post(
        f"/api/v1/debug-sessions/{payload['session']['id']}:heartbeat",
        headers=headers() | {"X-Debug-Relay-Token": relay_token},
        json={"stage": "FRAME", "event": "AFTER_LEASE_RELEASE"},
    )
    assert denied.status_code == 409
    reconciled = await client.get(
        f"/api/v1/debug-sessions/{payload['session']['id']}",
        headers=headers(),
    )
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["status"] == "REVOKED"
    assert reconciled.json()["revokeReason"] == "device lease lost"


@pytest.mark.asyncio
async def test_debug_session_rejects_unsafe_capability_and_non_maintenance_device(
    client: httpx.AsyncClient,
) -> None:
    device_id = await maintenance_device(client)
    unsafe = await client.post(
        "/api/v1/debug-sessions",
        headers=headers(),
        json={
            "deviceId": device_id,
            "capabilities": ["shell.arbitrary"],
            "purpose": "unsafe",
        },
    )
    assert unsafe.status_code == 403

    await client.post(
        f"/api/v1/devices/{device_id}:maintenance",
        headers=headers(roles="security_admin"),
        json={"enabled": False, "reason": "resume operations"},
    )
    not_maintenance = await client.post(
        "/api/v1/debug-sessions",
        headers=headers(),
        json={"deviceId": device_id, "capabilities": ["view.frame"], "purpose": "read only"},
    )
    assert not_maintenance.status_code == 409
