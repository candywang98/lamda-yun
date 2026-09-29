"""Controller-owned cloud gates for the bounded OnePlus v6 acceptance window."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from dotenv import dotenv_values

ROOT = Path("/home/ubuntu/cloudctl-mobile")
DEVICE = "4aabc387-6e4b-4b59-a525-b1c119ec7f5b"
EXPECTED_BINDING = "202ff9cb-6b6d-4ccc-bbf7-31bd91edb51e"
EXPECTED_TENANT = "00000000-0000-7000-8000-000000001111"
IDENTITY_STATE = ROOT / "backups/oneplus-v4-20260928/identity-before.json"
EXPECTED_COUNTS = {
    "mobileTasks": 379,
    "outgoingMessages": 23,
    "deviceOrders": 14,
    "deviceReceipts": 6,
}
TERMINAL_TASK_STATES = ("SUCCEEDED", "FAILED", "CANCELED", "CANCELLED", "EXPIRED")
OCCUPANCY_FIELDS = {
    "activeLeases",
    "unfinishedTasks",
    "enabledSchedules",
    "activePreviews",
    "activeDebugSessions",
}


def load_release_ops() -> Any:
    spec = importlib.util.spec_from_file_location(
        "existing_release_ops", ROOT / "incoming/im-notify-bb19ad2/cloud_release.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("approved cloud release helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def normalized(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, sort_keys=True))


def assert_snapshot(
    snapshot: dict[str, Any],
    *,
    maintenance: bool,
    version: int,
) -> None:
    assert snapshot["device"]["maintenance"] is maintenance, "maintenance state drift"
    assert snapshot["device"]["version"] == version, "maintenance version drift"
    assert snapshot["device"]["tenantMatchesExpected"], "tenant drift"
    assert snapshot["device"]["activeBindingMatchesExpected"], "active binding drift"
    assert snapshot["identity"]["retained"], "binding/account identity drift"
    assert snapshot["identity"]["activeBindingCount"] == 1, "active binding count drift"
    assert snapshot["identity"]["accountBindingCount"] == 1, "account binding count drift"
    assert snapshot["identity"]["boundAccountCount"] == 1, "bound account count drift"
    assert snapshot["occupancy"]["globalIdle"], "global cloud occupancy is not idle"
    assert snapshot["occupancy"]["targetIdle"], "target cloud occupancy is not idle"
    for scope in ("global", "targetDevice"):
        values = snapshot["occupancy"].get(scope)
        assert isinstance(values, dict), "cloud occupancy map is missing"
        assert set(values) == OCCUPANCY_FIELDS, "cloud occupancy map is incomplete"
        assert all(value == 0 for value in values.values()), "cloud occupancy is non-zero"
    assert snapshot["counts"] == EXPECTED_COUNTS, "business aggregate count drift"
    assert snapshot["imConfig"] == {
        "httpStatus": 200,
        "receiveOnly": True,
        "mode": "NOTIFICATION",
        "enabled": True,
    }, "receive-only configuration drift"


def assert_cleanup_identity(snapshot: dict[str, Any]) -> None:
    if not snapshot["device"]["tenantMatchesExpected"]:
        raise RuntimeError("cleanup refused: tenant drift")
    if not snapshot["device"]["activeBindingMatchesExpected"]:
        raise RuntimeError("cleanup refused: active binding drift")
    identity = snapshot["identity"]
    if not identity["retained"]:
        raise RuntimeError("cleanup refused: binding/account identity drift")
    if identity["activeBindingCount"] != 1:
        raise RuntimeError("cleanup refused: active binding count drift")
    if identity["accountBindingCount"] != 1 or identity["boundAccountCount"] != 1:
        raise RuntimeError("cleanup refused: account binding drift")


async def database_connection() -> asyncpg.Connection:
    values = dict(os.environ)
    for name in (
        "control-api.env",
        "p14-runtime.env",
        "im-3a1d306-jev.env",
        "im-3a1d306-rollout.env",
    ):
        values.update(
            {
                key: value
                for key, value in dotenv_values(ROOT / "shared" / name).items()
                if value is not None
            }
        )
    return await asyncpg.connect(
        values["CLOUDCTL_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"),
        server_settings={"timezone": "UTC", "statement_timeout": "10000"},
        timeout=10,
    )


async def count(connection: asyncpg.Connection, sql: str, *args: Any) -> int:
    return int(await connection.fetchval(sql, *args))


async def snapshot(ops: Any, client: httpx.AsyncClient) -> dict[str, Any]:
    before = json.loads(IDENTITY_STATE.read_text())
    connection = await database_connection()
    try:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            observed_at = datetime.now(UTC).isoformat()
            row = await connection.fetchrow(
                "SELECT tenant_id,state,maintenance,version,last_seen_at,"
                "active_binding_id,capabilities FROM device WHERE id=$1",
                DEVICE,
            )
            if row is None:
                raise RuntimeError("target device is missing")
            device = dict(row)
            bindings = [
                dict(item)
                for item in await connection.fetch(
                    "SELECT id,tenant_id,device_id,token_digest,app_instance_id "
                    "FROM mobile_binding WHERE device_id=$1 AND revoked_at IS NULL ORDER BY id",
                    DEVICE,
                )
            ]
            accounts = [
                dict(item)
                for item in await connection.fetch(
                    "SELECT id,tenant_id,account_id,device_id,status,binding_version,platform "
                    "FROM account_device_binding WHERE device_id=$1 ORDER BY id",
                    DEVICE,
                )
            ]
            occupancy_global = {
                "activeLeases": await count(
                    connection,
                    "SELECT count(*) FROM device_lease "
                    "WHERE canceled_at IS NULL AND expires_at>now()",
                ),
                "unfinishedTasks": await count(
                    connection,
                    "SELECT count(*) FROM mobile_task WHERE status != ALL($1::varchar[])",
                    list(TERMINAL_TASK_STATES),
                ),
                "enabledSchedules": await count(
                    connection, "SELECT count(*) FROM task_schedule WHERE enabled IS TRUE"
                ),
                "activePreviews": await count(
                    connection,
                    "SELECT count(*) FROM device_preview WHERE session_expires_at>now()",
                ),
                "activeDebugSessions": await count(
                    connection,
                    "SELECT count(*) FROM debug_session "
                    "WHERE revoked_at IS NULL AND expires_at>now()",
                ),
            }
            occupancy_target = {
                "activeLeases": await count(
                    connection,
                    "SELECT count(*) FROM device_lease WHERE device_id=$1 "
                    "AND canceled_at IS NULL AND expires_at>now()",
                    DEVICE,
                ),
                "unfinishedTasks": await count(
                    connection,
                    "SELECT count(*) FROM mobile_task WHERE device_id=$1 "
                    "AND status != ALL($2::varchar[])",
                    DEVICE,
                    list(TERMINAL_TASK_STATES),
                ),
                "enabledSchedules": await count(
                    connection,
                    "SELECT count(*) FROM task_schedule WHERE enabled IS TRUE "
                    "AND device_ids::jsonb ? $1",
                    DEVICE,
                ),
                "activePreviews": await count(
                    connection,
                    "SELECT count(*) FROM device_preview WHERE device_id=$1 "
                    "AND session_expires_at>now()",
                    DEVICE,
                ),
                "activeDebugSessions": await count(
                    connection,
                    "SELECT count(*) FROM debug_session WHERE device_id=$1 "
                    "AND revoked_at IS NULL AND expires_at>now()",
                    DEVICE,
                ),
            }
            counts = {
                "mobileTasks": await count(connection, "SELECT count(*) FROM mobile_task"),
                "outgoingMessages": await count(
                    connection, "SELECT count(*) FROM im_message WHERE direction='OUT'"
                ),
                "deviceOrders": await count(
                    connection, "SELECT count(*) FROM xianyu_order WHERE device_id=$1", DEVICE
                ),
                "deviceReceipts": await count(
                    connection,
                    "SELECT count(*) FROM order_delivery_receipt WHERE device_id=$1",
                    DEVICE,
                ),
            }
            schema = await connection.fetchval("SELECT version_num FROM alembic_version")
    finally:
        await connection.close()

    response = await client.get(ops.HOST + "/api/v1/im/config", params={"deviceId": DEVICE})
    config = response.json() if response.status_code == 200 else {}
    capabilities = device["capabilities"]
    if isinstance(capabilities, str):
        capabilities = json.loads(capabilities)
    retained = normalized(bindings) == normalized(before["identity"]["bindings"]) and normalized(
        accounts
    ) == normalized(before["identity"]["accounts"])
    return {
        "observedAt": observed_at,
        "schema": schema,
        "device": {
            "state": device["state"],
            "maintenance": device["maintenance"],
            "version": device["version"],
            "lastSeenAt": device["last_seen_at"],
            "tenantMatchesExpected": device["tenant_id"] == EXPECTED_TENANT,
            "activeBindingMatchesExpected": device["active_binding_id"] == EXPECTED_BINDING,
        },
        "identity": {
            "retained": retained,
            "activeBindingCount": len(bindings),
            "accountBindingCount": len(accounts),
            "boundAccountCount": sum(item["status"] == "BOUND" for item in accounts),
        },
        "occupancy": {
            "global": occupancy_global,
            "targetDevice": occupancy_target,
            "globalIdle": all(value == 0 for value in occupancy_global.values()),
            "targetIdle": all(value == 0 for value in occupancy_target.values()),
        },
        "counts": counts,
        "imConfig": {
            "httpStatus": response.status_code,
            "receiveOnly": config.get("receiveOnly"),
            "mode": config.get("mode"),
            "enabled": config.get("enabled"),
        },
        "capabilities": {
            key: capabilities.get(key)
            for key in (
                "companionVersion",
                "accessibilityEnabled",
                "runnerState",
                "safetyBarrier",
                "orderDeliveryProtocol",
            )
        },
    }


async def set_maintenance(
    ops: Any,
    client: httpx.AsyncClient,
    *,
    enabled: bool,
    expected_version: int,
    reason: str,
) -> None:
    response = await client.post(
        ops.HOST + f"/api/v1/devices/{DEVICE}:maintenance",
        json={
            "enabled": enabled,
            "expectedVersion": expected_version,
            "reason": reason,
        },
    )
    response.raise_for_status()


async def run_action(action: str, window_id: str | None = None) -> dict[str, Any]:
    if action not in {"snapshot", "prepare-cas", "finish-owned"}:
        raise ValueError("unsupported action")
    if action != "snapshot":
        if window_id is None or not re.fullmatch(r"v6-[a-f0-9]{32}", window_id):
            raise ValueError("exact v6 window id is required")
    ops = load_release_ops()
    async with httpx.AsyncClient(timeout=20, trust_env=False, auth=ops.auth()) as client:
        current = await snapshot(ops, client)
        if action == "snapshot":
            return {"action": action, **current}
        if action == "prepare-cas":
            assert_snapshot(current, maintenance=False, version=12)
            await set_maintenance(
                ops,
                client,
                enabled=True,
                expected_version=12,
                reason=f"Authorized OnePlus v6 maintenance-recovery acceptance {window_id}",
            )
            return {
                "action": action,
                "windowId": window_id,
                "acknowledged": True,
                "expectedResult": {"maintenance": True, "version": 13},
                "acknowledgedAt": datetime.now(UTC).isoformat(),
            }

        assert_cleanup_identity(current)
        if current["device"]["maintenance"] is True and current["device"]["version"] == 13:
            await set_maintenance(
                ops,
                client,
                enabled=False,
                expected_version=13,
                reason=f"End authorized OnePlus v6 maintenance-recovery acceptance {window_id}",
            )
            updated = await snapshot(ops, client)
            assert_cleanup_identity(updated)
            if updated["device"]["maintenance"] is not False or updated["device"]["version"] != 14:
                raise RuntimeError("owned maintenance finish verification failed")
            return {"action": action, "changed": True, **updated}
        if current["device"]["maintenance"] is False and current["device"]["version"] == 14:
            return {"action": action, "changed": False, **current}
        raise RuntimeError("owned maintenance finish conflict")


def journal_evidence(since_epoch: str, until_epoch: str) -> dict[str, Any]:
    result = subprocess.run(  # noqa: S603 - fixed read-only journalctl argv
        [
            "/usr/bin/journalctl",
            "-u",
            "cloudctl-mobile-api.service",
            "--since",
            f"@{since_epoch}",
            "--until",
            f"@{until_epoch}",
            "--no-pager",
            "-o",
            "short-iso",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError("journalctl read failed")
    events: list[dict[str, str | int]] = []
    needles = {
        "/companion/v2/devices/heartbeat": 200,
        "/companion/v2/tasks/claim": 409,
    }
    for line in result.stdout.splitlines():
        for endpoint, status in needles.items():
            if endpoint in line and f" {status} " in line:
                events.append(
                    {
                        "timestamp": line.split(" ", 1)[0],
                        "endpoint": endpoint,
                        "status": status,
                    }
                )
                break
    return {
        "action": "journal",
        "sinceEpoch": since_epoch,
        "untilEpoch": until_epoch,
        "targetAttribution": False,
        "events": events,
    }


def main(argv: list[str]) -> None:
    os.umask(0o077)
    if len(argv) == 2:
        print(json.dumps(asyncio.run(run_action(argv[1])), default=str))
        return
    if len(argv) == 3 and argv[1] in {"prepare-cas", "finish-owned"}:
        print(json.dumps(asyncio.run(run_action(argv[1], argv[2])), default=str))
        return
    if len(argv) == 4 and argv[1] == "journal":
        print(json.dumps(journal_evidence(argv[2], argv[3]), default=str))
        return
    raise SystemExit(
        "usage: oneplus-v6-cloud.py snapshot|prepare-cas WINDOW|"
        "finish-owned WINDOW|journal SINCE UNTIL"
    )


if __name__ == "__main__":
    main(sys.argv)
