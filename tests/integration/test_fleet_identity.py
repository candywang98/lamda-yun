"""A10 fleet-identity/v1@20260916.1 mirror tests.

Consumes the frozen K10 fixtures (contracts/fleet/v1/fixtures/) and covers the
A10 backend delta: capability negotiation with the closed key set, the
online/executable split, account write mutual exclusion (ACCOUNT_BUSY), the
open-UNKNOWN reclaim guard (RECONCILE_REQUIRED), authorization-envelope
staleness for late heartbeats (AUTHORIZATION_ENVELOPE_STALE), dispatch-gate
capability eligibility (INELIGIBLE_CAPABILITY), and device/task scoped media
download authorization.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from cloudctl_api import create_app
from cloudctl_api.db import (
    AccountDeviceBindingRow,
    DeviceLeaseRow,
    MobileActionCommitRow,
    MobileTaskRow,
)
from cloudctl_api.fleet_identity import (
    AUTHORIZATION_ENVELOPE_FIELDS,
    CAPABILITY_KEYS,
    EXECUTABLE_GATE_ORDER,
    FLEET_IDENTITY_CONTRACT,
    AccountBusyError,
    AuthorizationEnvelopeStaleError,
    IneligibleCapabilityError,
    ReconcileRequiredError,
    action_key,
    build_authorization_envelope,
    normalize_capabilities,
    parameter_hash,
)
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import select
from test_platform_tasks import (
    PROBE,
    _enroll,
    bind,
    create_account,
    create_direct_device,
    identity,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPOSITORY_ROOT / "contracts" / "fleet" / "v1" / "fixtures"
ALEMBIC_INI = REPOSITORY_ROOT / "services" / "control-api" / "alembic.ini"

OPERATOR = identity()


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    await app.state.database.create_schema()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


def full_capabilities(**overrides: Any) -> dict[str, Any]:
    table: dict[str, Any] = {
        "accessibility": {"supported": True, "engineMin": 1},
        "ime": {"supported": True, "engineMin": 1},
        "screen_capture": {"supported": True, "engineMin": 1},
        "media_projection": {"supported": False},
        "flutter_anchors": {"supported": True, "engineMin": 2},
        "im_listen": {"supported": True, "engineMin": 1},
    }
    table.update(overrides)
    return table


async def negotiate(
    app: FastAPI,
    token: str,
    *,
    boot_id: str | None = "boot-20260916-01",
    capabilities: dict[str, Any] | None = None,
    accessibility_enabled: bool | None = True,
    accessibility_active: bool | None = True,
    ime_ready: bool | None = True,
    screen_unlocked: bool | None = True,
    engine_version: int | None = 2,
) -> dict[str, Any]:
    service = app.state.mobile_task_service
    binding = await service.authenticate(token)
    return await service.register_fleet_session(
        binding,
        boot_id=boot_id,
        companion_version="1.0.0",
        capabilities=capabilities if capabilities is not None else full_capabilities(),
        accessibility_enabled=accessibility_enabled,
        accessibility_active=accessibility_active,
        ime_ready=ime_ready,
        screen_unlocked=screen_unlocked,
        engine_version=engine_version,
    )


# Frozen publish steps shape (same as the p09 ledger tests): one gated publish
# tap, postcondition wait, description input.
PUBLISH_STEPS = [
    {
        "stepId": "find-home-sell",
        "locatorRef": "xianyu_home_sell",
        "timeoutMs": 8000,
        "action": "ui.find",
    },
    {
        "stepId": "fill-description",
        "locatorRef": "xianyu_description",
        "timeoutMs": 20000,
        "action": "ui.input",
        "value": "A10 fleet identity publish probe",
        "replace": True,
        "sensitive": False,
    },
    {
        "stepId": "wait-publish-button",
        "locatorRef": "xianyu_publish_button",
        "timeoutMs": 8000,
        "action": "ui.wait",
        "condition": "EXISTS",
        "pollMs": 200,
    },
    {
        "stepId": "click-publish",
        "locatorRef": "xianyu_publish_button",
        "timeoutMs": 5000,
        "action": "ui.tap",
    },
    {
        "stepId": "wait-publish-complete",
        "locatorRef": "xianyu_publish_success",
        "timeoutMs": 15000,
        "action": "ui.wait",
        "condition": "EXISTS",
        "pollMs": 500,
    },
]


async def create_publish_task(
    client: httpx.AsyncClient,
    device_id: str,
    *,
    account_id: str | None = None,
    media_delivery: dict[str, Any] | None = None,
) -> str:
    body: dict[str, Any] = {
        "deviceId": device_id,
        "targetPackage": "com.taobao.idlefish",
        "totalTimeoutMs": 120_000,
        "steps": PUBLISH_STEPS,
    }
    if account_id is not None:
        body["accountId"] = account_id
    if media_delivery is not None:
        body["mediaDelivery"] = media_delivery
    response = await client.post(
        "/api/v1/mobile/tasks",
        headers={**OPERATOR, "Idempotency-Key": f"a10-{uuid.uuid4()}"},
        json=body,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["taskId"])


async def claim_task(client: httpx.AsyncClient, auth: dict[str, str]) -> httpx.Response:
    return await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )


async def start_task(
    client: httpx.AsyncClient, auth: dict[str, str], task_id: str, lease_id: str
) -> None:
    response = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": lease_id, "currentStep": 0},
    )
    assert response.status_code == 200, response.text


def problem_codes(response: httpx.Response) -> tuple[int, str, str]:
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    return response.status_code, str(body["code"]), str(body["type"])


# ---------------------------------------------------------------------------
# K10 fixture mirrors (fleet-identity/v1@20260916.1 §10 consumer obligation)
# ---------------------------------------------------------------------------


def test_positive_fleet_claim_fixture_mirror() -> None:
    fixture = load_fixture("k10-positive-fleet-claim.json")
    assert fixture["contract"] == FLEET_IDENTITY_CONTRACT
    identity_block = fixture["actionIdentity"]
    computed_key = action_key(
        identity_block["taskId"], identity_block["recipeSha256"], identity_block["actionId"]
    )
    assert computed_key == identity_block["expectedActionKey"]
    assert (
        parameter_hash(
            identity_block["taskId"],
            identity_block["commandType"],
            fixture["envelope"]["accountId"],
            fixture["envelope"]["bindingVersion"],
            identity_block["snapshotSha256"],
            identity_block["recipeSha256"],
        )
        == identity_block["expectedParameterHash"]
    )
    envelope = fixture["envelope"]
    assert set(envelope["capabilities"]) == set(CAPABILITY_KEYS)
    assert envelope["executableGates"] == list(EXECUTABLE_GATE_ORDER)
    normalized = normalize_capabilities(envelope["capabilities"])
    assert normalized == envelope["capabilities"]


def test_negative_actionkey_contains_epoch_fixture_mirror() -> None:
    fixture = load_fixture("k10-negative-actionkey-contains-epoch.json")
    assert fixture["expect"] == "REJECT"
    inputs = fixture["identityInputs"]
    expected = load_fixture("k10-positive-fleet-claim.json")["actionIdentity"]
    stable = action_key(inputs["taskId"], inputs["recipeSha256"], inputs["actionId"])
    assert stable == expected["expectedActionKey"]
    # Injecting any dynamic authorization field into the frozen preimage must
    # change the digest: the identity channel has no slot for them.
    dynamic_values = {
        "controlEpoch": str(inputs["controlEpoch"]),
        "fencingToken": str(inputs["fencingToken"]),
        "sessionId": inputs["sessionId"],
    }
    for value in dynamic_values.values():
        mixed_preimage = (
            f"cloudctl.action/v1\n{inputs['taskId']}\n"
            f"{inputs['recipeSha256']}\n{inputs['actionId']}\n{value}"
        )
        assert hashlib.sha256(mixed_preimage.encode()).hexdigest() != expected["expectedActionKey"]
        mixed_parameters = (
            f"cloudctl.action-parameters/v1\n{inputs['taskId']}\n"
            f"{expected['commandType']}\nacc-xianyu-01\n7\n"
            f"{expected['snapshotSha256']}\n{inputs['recipeSha256']}\n{value}"
        )
        assert (
            hashlib.sha256(mixed_parameters.encode()).hexdigest()
            != expected["expectedParameterHash"]
        )
    # The dynamic fields live only in the authorization envelope.
    positive = load_fixture("k10-positive-fleet-claim.json")
    envelope = build_authorization_envelope(
        control_epoch=positive["authorizationEnvelope"]["controlEpoch"],
        fencing_token=positive["authorizationEnvelope"]["fencingToken"],
        lease_expires_at=positive["authorizationEnvelope"]["leaseExpiresAt"],
        session_id=positive["authorizationEnvelope"]["sessionId"],
        boot_id=positive["authorizationEnvelope"]["bootId"],
    )
    assert set(envelope) == set(AUTHORIZATION_ENVELOPE_FIELDS)
    assert envelope["sessionId"] not in stable


def test_capability_table_is_a_closed_key_set() -> None:
    normalized = normalize_capabilities({"accessibility": {"supported": True}})
    assert normalized["accessibility"] == {"supported": True}
    # Keys the device did not report count as unsupported (fail-closed).
    assert normalized["ime"] == {"supported": False}
    with pytest.raises(Exception):  # noqa: B017 - closed set, unknown key rejected
        normalize_capabilities({"telepathy": {"supported": True}})
    with pytest.raises(Exception):  # noqa: B017 - engineMin must be a positive int
        normalize_capabilities({"accessibility": {"supported": True, "engineMin": 0}})


def test_negative_account_busy_fixture_rules_are_wired() -> None:
    fixture = load_fixture("k10-negative-account-busy.json")
    assert fixture["expect"]["code"] == AccountBusyError.code == "ACCOUNT_BUSY"
    assert fixture["expect"]["status"] == AccountBusyError.status == 409


def test_negative_reclaim_fixture_rules_are_wired() -> None:
    fixture = load_fixture("k10-negative-reclaim-open-unknown.json")
    assert fixture["expect"]["code"] == ReconcileRequiredError.code == "RECONCILE_REQUIRED"
    assert fixture["expect"]["status"] == ReconcileRequiredError.status == 409


# ---------------------------------------------------------------------------
# Account write mutual exclusion (fleet-identity/v1 §6.2)
# ---------------------------------------------------------------------------


async def test_second_device_claim_for_running_write_account_gets_409(api) -> None:
    client, app = api
    device_a = await create_direct_device(client, "fleet-busy-a")
    device_b = await create_direct_device(client, "fleet-busy-b")
    account = await create_account(client, "fleet-busy-account")
    await bind(client, account, device_a)
    await bind(client, account, device_b)

    task_a = await create_publish_task(client, device_a, account_id=account)
    task_b = await create_publish_task(client, device_b, account_id=account)

    auth_a = await _enroll(client, device_a, "instance-busy-a")
    auth_b = await _enroll(client, device_b, "instance-busy-b")

    claimed_a = await claim_task(client, auth_a)
    assert claimed_a.status_code == 200, claimed_a.text
    assert claimed_a.json()["taskId"] == task_a
    await start_task(client, auth_a, task_a, claimed_a.json()["leaseId"])

    busy = await claim_task(client, auth_b)
    status, code, type_ = problem_codes(busy)
    assert (status, code) == (409, "ACCOUNT_BUSY")
    assert type_ == "urn:cloudctl:problem:account_busy"
    detail = busy.json()["detail"]
    assert "account" in detail.lower()

    # The blocked task is not failed - it stays QUEUED (KEEP_WAITING).
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_b)
        assert row is not None
        assert row.status == "QUEUED"
        assert row.business_state == "QUEUED"

    # Once the RUNNING write task settles, the same account becomes claimable.
    finished = await client.post(
        f"/companion/v2/tasks/{task_a}/complete",
        headers=auth_a,
        json={"leaseId": claimed_a.json()["leaseId"], "result": {}},
    )
    assert finished.status_code == 200, finished.text
    retry = await claim_task(client, auth_b)
    assert retry.status_code == 200, retry.text
    assert retry.json()["taskId"] == task_b


async def test_read_tasks_are_exempt_from_the_account_write_mutex(api) -> None:
    client, _ = api
    device_a = await create_direct_device(client, "fleet-read-a")
    device_b = await create_direct_device(client, "fleet-read-b")
    account = await create_account(client, "fleet-read-account")
    await bind(client, account, device_a)
    await bind(client, account, device_b)

    task_write = await create_publish_task(client, device_a, account_id=account)
    created_read = await client.post(
        "/api/v1/platform-tasks",
        headers={**OPERATOR, "Idempotency-Key": f"fleet-read-{uuid.uuid4()}"},
        json={"deviceId": device_b, "accountId": account, **PROBE},
    )
    assert created_read.status_code == 201, created_read.text
    task_read = created_read.json()["items"][0]["taskId"]

    auth_a = await _enroll(client, device_a, "instance-read-a")
    auth_b = await _enroll(client, device_b, "instance-read-b")
    claimed = await claim_task(client, auth_a)
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == task_write
    await start_task(client, auth_a, task_write, claimed.json()["leaseId"])

    # A read task for the same busy account still dispatches (writeEffect=false
    # by frozen task-family declaration).
    readable = await claim_task(client, auth_b)
    assert readable.status_code == 200, readable.text
    assert readable.json()["taskId"] == task_read


# ---------------------------------------------------------------------------
# Open-UNKNOWN reclaim guard (fleet-identity/v1 §8)
# ---------------------------------------------------------------------------


async def test_open_unknown_ledger_row_blocks_reclaim_until_reconciled(api) -> None:
    client, app = api
    from cloudctl_api.mobile_actions import steps_action_identity

    device = await create_direct_device(client, "fleet-unknown")
    auth = await _enroll(client, device, "instance-unknown")
    task_id = await create_publish_task(client, device)

    claimed = await claim_task(client, auth)
    assert claimed.status_code == 200, claimed.text
    lease_id = claimed.json()["leaseId"]
    await start_task(client, auth, task_id, lease_id)

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        frozen = steps_action_identity(row)
    intent = await client.post(
        f"/companion/v2/tasks/{task_id}/actions/intent",
        headers=auth,
        json={
            "leaseId": lease_id,
            "actionId": frozen["action_id"],
            "actionKey": frozen["action_key"],
            "parameterHash": frozen["parameter_hash"],
            "beforeEvidence": "evidence://before",
        },
    )
    assert intent.status_code == 201, intent.text
    outcome = await client.post(
        f"/companion/v2/tasks/{task_id}/actions/{frozen['action_key']}/outcome",
        headers=auth,
        json={
            "leaseId": lease_id,
            "parameterHash": frozen["parameter_hash"],
            "status": "UNKNOWN",
            "evidence": "evidence://lost",
        },
    )
    assert outcome.status_code == 200, outcome.text
    async with app.state.database.unit_of_work() as session:
        ledger = await session.get(MobileActionCommitRow, frozen["action_key"])
        assert ledger is not None and ledger.status == "UNKNOWN"
        assert ledger.resolved_at is None

    # Simulate the crash-requeue path: the task returns to QUEUED while the
    # UNKNOWN ledger row is still open.
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        row.status = "QUEUED"
        row.business_state = "QUEUED"
        row.lease_id = None
        row.lease_expires_at = None
        lease = await session.get(DeviceLeaseRow, device)
        if lease is not None:
            lease.canceled_at = datetime.now(UTC)

    blocked = await claim_task(client, auth)
    status, code, _ = problem_codes(blocked)
    assert (status, code) == (409, "RECONCILE_REQUIRED")

    # Explicit operator reconciliation closes the UNKNOWN row and unblocks.
    reopened = await client.post(
        f"/api/v1/platform-tasks/{task_id}:mark-unknown",
        headers=OPERATOR,
        json={"reason": "reclaim blocked; reopen for reconciliation"},
    )
    assert reopened.status_code == 200, reopened.text
    reconciled = await client.post(
        f"/api/v1/platform-tasks/{task_id}:reconcile",
        headers=OPERATOR,
        json={
            "decision": "CONFIRMED_NOT_SUBMITTED",
            "evidence": "operator verified the publish never landed",
        },
    )
    assert reconciled.status_code == 200, reconciled.text
    follow_up = await create_publish_task(client, device)
    reclaimed = await claim_task(client, auth)
    assert reclaimed.status_code == 200, reclaimed.text
    assert reclaimed.json()["taskId"] == follow_up


# ---------------------------------------------------------------------------
# Capability negotiation, online/executable split, dispatch eligibility
# ---------------------------------------------------------------------------


async def test_executable_gates_block_and_release_dispatch(api) -> None:
    client, app = api
    device = await create_direct_device(client, "fleet-gates")
    auth = await _enroll(client, device, "instance-gates")
    token = auth["Authorization"].split(" ", 1)[1]
    task_id = await create_publish_task(client, device)

    # accessibility reported disabled -> device online but not executable.
    envelope = await negotiate(
        app, token, accessibility_enabled=False, accessibility_active=False
    )
    assert envelope["online"] is True
    assert envelope["executable"] is False
    assert envelope["failedGates"] == ["accessibility-enabled", "accessibility-active"]
    idle = await claim_task(client, auth)
    assert idle.status_code == 204

    # Full gates green -> dispatch proceeds and the fleet envelope is healthy.
    envelope = await negotiate(app, token)
    assert envelope["executable"] is True
    assert envelope["failedGates"] == []
    assert envelope["executableGates"] == list(EXECUTABLE_GATE_ORDER)
    assert envelope["sessionId"].startswith("sess-")
    assert envelope["bootId"] == "boot-20260916-01"
    claimed = await claim_task(client, auth)
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == task_id


async def test_engine_below_recipe_minimum_is_not_executable(api) -> None:
    client, app = api
    device = await create_direct_device(client, "fleet-engine")
    auth = await _enroll(client, device, "instance-engine")
    token = auth["Authorization"].split(" ", 1)[1]
    await create_publish_task(client, device)

    envelope = await negotiate(app, token, engine_version=0)
    assert envelope["failedGates"] == ["engine>=min"]
    idle = await claim_task(client, auth)
    assert idle.status_code == 204

    await negotiate(app, token, engine_version=2)
    claimed = await claim_task(client, auth)
    assert claimed.status_code == 200, claimed.text


async def test_missing_required_capability_is_ineligible_not_failed(api) -> None:
    client, app = api
    device = await create_direct_device(client, "fleet-ineligible")
    auth = await _enroll(client, device, "instance-ineligible")
    token = auth["Authorization"].split(" ", 1)[1]
    task_id = await create_publish_task(client, device)

    await negotiate(
        app,
        token,
        capabilities=full_capabilities(
            ime={"supported": False}, screen_capture={"supported": False}
        ),
    )
    rejected = await claim_task(client, auth)
    status, code, _ = problem_codes(rejected)
    assert (status, code) == (422, "INELIGIBLE_CAPABILITY")
    assert IneligibleCapabilityError.status == 422

    # The task is not failed: it stays QUEUED for a capable device/session.
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        assert row.status == "QUEUED"
        assert row.business_state == "QUEUED"

    await negotiate(app, token)
    claimed = await claim_task(client, auth)
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == task_id


async def test_unequipped_new_capability_key_only_blocks_its_task_family(api) -> None:
    client, app = api
    device = await create_direct_device(client, "fleet-compat")
    auth = await _enroll(client, device, "instance-compat")
    token = auth["Authorization"].split(" ", 1)[1]

    # A device that never negotiated flutter_anchors keeps serving the xianyu
    # publish family (compat: unreported key = unsupported only for families
    # that require it).
    task_id = await create_publish_task(client, device)
    await negotiate(
        app, token, capabilities=full_capabilities(flutter_anchors={"supported": False})
    )
    claimed = await claim_task(client, auth)
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == task_id


# ---------------------------------------------------------------------------
# Session envelope: revocation, reinstall, late heartbeats (§2, §4)
# ---------------------------------------------------------------------------


async def test_late_heartbeat_after_boot_change_does_not_resurrect_old_session(api) -> None:
    client, app = api
    device = await create_direct_device(client, "fleet-boot")
    auth = await _enroll(client, device, "instance-boot")
    token = auth["Authorization"].split(" ", 1)[1]
    task_id = await create_publish_task(client, device)

    await negotiate(app, token, boot_id="boot-one")
    claimed = await claim_task(client, auth)
    assert claimed.status_code == 200, claimed.text
    old_lease = claimed.json()["leaseId"]
    await start_task(client, auth, task_id, old_lease)

    # Device reboots: a fresh process session with a new bootId is registered.
    await negotiate(app, token, boot_id="boot-two")

    late = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": old_lease, "currentStep": 1},
    )
    status, code, _ = problem_codes(late)
    assert (status, code) == (409, "AUTHORIZATION_ENVELOPE_STALE")
    assert AuthorizationEnvelopeStaleError.status == 409

    # The stale task is requeued once its lease expires; the new session can
    # reclaim and heartbeat under a fresh lease.
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    reclaimed = await claim_task(client, auth)
    assert reclaimed.status_code == 200, reclaimed.text
    assert reclaimed.json()["taskId"] == task_id
    fresh = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": reclaimed.json()["leaseId"], "currentStep": 1},
    )
    assert fresh.status_code == 200, fresh.text


async def test_revoked_binding_and_reinstall_invalidate_old_credentials(api) -> None:
    client, _ = api
    device = await create_direct_device(client, "fleet-revoke")
    task_id = await create_publish_task(client, device)

    auth_old = await _enroll(client, device, "instance-old")
    claimed = await claim_task(client, auth_old)
    assert claimed.status_code == 200, claimed.text
    lease_old = claimed.json()["leaseId"]

    revoked = await client.delete("/companion/v2/binding", headers=auth_old)
    assert revoked.status_code == 204
    stale = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth_old,
        json={"leaseId": lease_old, "currentStep": 0},
    )
    assert stale.status_code == 401, stale.text

    # Reinstall (new app instance) supersedes every prior binding; only the
    # new credential may drive the device.
    auth_new = await _enroll(client, device, "instance-new")
    resurrect = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth_old,
        json={"leaseId": lease_old, "currentStep": 0},
    )
    assert resurrect.status_code == 401, resurrect.text
    device_heartbeat = await client.post(
        "/companion/v2/devices/heartbeat",
        headers=auth_new,
        json={
            "companionVersion": "1.1.0",
            "accessibilityEnabled": True,
            "runnerState": "IDLE",
        },
    )
    assert device_heartbeat.status_code == 200, device_heartbeat.text


async def test_account_rebinding_invalidates_old_task_authorization(api) -> None:
    client, app = api
    device = await create_direct_device(client, "fleet-rebind")
    account = await create_account(client, "fleet-rebind-account")
    bound = await bind(client, account, device)
    task_id = await create_publish_task(client, device, account_id=account)

    # A rebind bumps the live binding version; the frozen task is superseded.
    async with app.state.database.unit_of_work() as session:
        row = await session.scalar(
            select(AccountDeviceBindingRow).where(
                AccountDeviceBindingRow.account_id == account,
                AccountDeviceBindingRow.device_id == device,
            )
        )
        assert row is not None
        row.binding_version = int(bound["bindingVersion"]) + 1

    auth = await _enroll(client, device, "instance-rebind")
    response = await claim_task(client, auth)
    assert response.status_code == 204
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        assert row.status == "FAILED"
        assert row.error_code == "ACCOUNT_CHANGED"


# ---------------------------------------------------------------------------
# Media download authorization: tenant + task scope (task card acceptance)
# ---------------------------------------------------------------------------


async def register_media_asset(
    client: httpx.AsyncClient, content: bytes
) -> tuple[str, str]:
    """Register an asset; returns (assetId, objectKey)."""
    object_key = f"fleet/{uuid.uuid4().hex}.bin"
    response = await client.post(
        "/api/v1/media/assets:register",
        headers=identity(role="content_editor"),
        json={
            "sha256": hashlib.sha256(content).hexdigest(),
            "objectKey": object_key,
            "contentType": "image/jpeg",
            "sizeBytes": len(content),
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"]), object_key


async def test_media_download_requires_device_task_authorization(api) -> None:
    client, app = api
    content = b"fleet-media-payload"
    asset_id, object_key = await register_media_asset(client, content)
    app.state.object_store.put(object_key, content, "image/jpeg")

    device_a = await create_direct_device(client, "fleet-media-a")
    device_b = await create_direct_device(client, "fleet-media-b")
    await create_publish_task(
        client,
        device_a,
        media_delivery={"deliveryId": "delivery-fleet-1", "assetIds": [asset_id]},
    )

    auth_a = await _enroll(client, device_a, "instance-media-a")
    auth_b = await _enroll(client, device_b, "instance-media-b")

    allowed = await client.get(f"/companion/v2/media/{asset_id}", headers=auth_a)
    assert allowed.status_code == 200, allowed.text
    assert allowed.content == content

    # Same tenant, but the asset belongs to device A's task only.
    denied = await client.get(f"/companion/v2/media/{asset_id}", headers=auth_b)
    assert denied.status_code == 404, denied.text
    manifest_denied = await client.post(
        "/companion/v2/media/manifest",
        headers=auth_b,
        json={"deliveryId": "delivery-fleet-1", "assetIds": [asset_id]},
    )
    assert manifest_denied.status_code == 404, manifest_denied.text
    manifest_allowed = await client.post(
        "/companion/v2/media/manifest",
        headers=auth_a,
        json={"deliveryId": "delivery-fleet-1", "assetIds": [asset_id]},
    )
    assert manifest_allowed.status_code == 200, manifest_allowed.text


async def test_cross_tenant_media_and_task_access_is_denied(api) -> None:
    client, app = api
    content = b"fleet-cross-tenant"
    asset_id, object_key = await register_media_asset(client, content)
    app.state.object_store.put(object_key, content, "image/jpeg")

    device_a = await create_direct_device(client, "fleet-cross-a")
    await create_publish_task(
        client,
        device_a,
        media_delivery={"deliveryId": "delivery-cross-1", "assetIds": [asset_id]},
    )
    auth_a = await _enroll(client, device_a, "instance-cross-a")

    other_tenant = {
        **identity(),
        "X-Tenant-Id": "00000000-0000-7000-8000-000000000999",
        "X-User-Id": "00000000-0000-7000-8000-000000000888",
    }
    device_b = await create_direct_device_for(client, "fleet-cross-b", other_tenant)
    auth_b = await enroll_for(client, device_b, other_tenant, "instance-cross-b")

    # Tenant B's binding cannot read tenant A's media even with the id.
    denied = await client.get(f"/companion/v2/media/{asset_id}", headers=auth_b)
    assert denied.status_code == 404, denied.text
    # And tenant A's device credentials cannot fetch tenant B's tasks.
    foreign = await client.get(f"/companion/v2/tasks/{uuid.uuid4()}", headers=auth_a)
    assert foreign.status_code == 404, foreign.text
    allowed = await client.get(f"/companion/v2/media/{asset_id}", headers=auth_a)
    assert allowed.status_code == 200, allowed.text


async def create_direct_device_for(
    client: httpx.AsyncClient, name: str, headers: dict[str, str]
) -> str:
    response = await client.post(
        "/api/v1/mobile/devices",
        headers=headers,
        json={"logicalName": name, "androidVersion": "14", "companionVersion": "1.0.0"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def enroll_for(
    client: httpx.AsyncClient, device_id: str, headers: dict[str, str], instance: str
) -> dict[str, str]:
    enroll = await client.post(
        "/api/v1/mobile/enrollments",
        headers=headers,
        json={"deviceId": device_id, "ttlSeconds": 600},
    )
    assert enroll.status_code == 201, enroll.text
    token_resp = await client.post(
        "/companion/v2/enroll",
        json={
            "code": enroll.json()["code"],
            "appInstanceId": instance,
            "companionVersion": "1.0.0",
        },
    )
    assert token_resp.status_code == 201, token_resp.text
    return {"Authorization": f"Bearer {token_resp.json()['bindingToken']}"}


# ---------------------------------------------------------------------------
# Migration 20260916_0023 (fleet_device_session)
# ---------------------------------------------------------------------------


def test_fleet_session_migration_0023_updown_is_symmetric(tmp_path: Path) -> None:
    database_path = tmp_path / "fleet-session-migrations.db"
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "20260916_0022")
    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "fleet_device_session" not in tables

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(fleet_device_session)")
        }
        assert {
            "id",
            "session_id",
            "tenant_id",
            "device_id",
            "binding_id",
            "boot_id",
            "companion_version",
            "engine_version",
            "capabilities",
            "accessibility_enabled",
            "accessibility_active",
            "ime_ready",
            "screen_unlocked",
            "last_seen_at",
            "revoked_at",
            "created_at",
        } <= columns
        # Compat-first: every fleet extension column stays nullable.
        notnull = {
            str(row[1]): int(row[3])
            for row in connection.execute("PRAGMA table_info(fleet_device_session)")
        }
        for column in ("boot_id", "engine_version", "capabilities", "revoked_at"):
            assert notnull[column] == 0

    command.downgrade(config, "20260916_0022")
    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "fleet_device_session" not in tables
    command.upgrade(config, "head")
