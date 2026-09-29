"""Controller-only, read-only cloud snapshot. Run on the existing server."""

import asyncio
import importlib.util
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import httpx
from dotenv import dotenv_values

ROOT = Path("/home/ubuntu/cloudctl-mobile")
DEVICES = {
    "b0644fb5": "4aabc387-6e4b-4b59-a525-b1c119ec7f5b",
    "15faee1d": "9b095c03-0781-480b-b392-8b5cb96de17b",
    "APH0219624006517": "769d67a5-679c-4655-aeb9-60a2a265fbc6",
}
EXPECTED_BINDINGS = {
    "b0644fb5": "202ff9cb-6b6d-4ccc-bbf7-31bd91edb51e",
    "15faee1d": "5881e652-2983-4095-9849-6157e7f3ca99",
    "APH0219624006517": "31a74c77-6aac-4f66-bd79-f41d7293f54c",
}


async def main():
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
    connection = await asyncpg.connect(
        values["CLOUDCTL_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"),
        server_settings={"timezone": "UTC", "statement_timeout": "10000"},
        timeout=10,
    )
    try:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            result = {
                "observedAt": datetime.now(UTC).isoformat(),
                "readOnly": True,
                "schema": await connection.fetchval("SELECT version_num FROM alembic_version"),
                "taskCount": await connection.fetchval("SELECT count(*) FROM mobile_task"),
                "outCount": await connection.fetchval(
                    "SELECT count(*) FROM im_message WHERE direction='OUT'"
                ),
                "devices": [],
            }
            checks = {
                "leases": "SELECT count(*) FROM device_lease "
                "WHERE canceled_at IS NULL AND expires_at>now()",
                "tasks": "SELECT count(*) FROM mobile_task WHERE status NOT IN "
                "('SUCCEEDED','FAILED','CANCELED','CANCELLED','EXPIRED')",
                "schedules": "SELECT count(*) FROM task_schedule",
                "previews": "SELECT count(*) FROM device_preview WHERE session_expires_at>now()",
                "debugSessions": "SELECT count(*) FROM debug_session "
                "WHERE revoked_at IS NULL AND expires_at>now()",
            }
            result["occupancy"] = {
                name: await connection.fetchval(query) for name, query in checks.items()
            }
            for serial, device_id in DEVICES.items():
                row = await connection.fetchrow(
                    "SELECT id,tenant_id,state,maintenance,version,last_seen_at,"
                    "active_binding_id,capabilities->>'companionVersion' AS companion_version,"
                    "capabilities->>'accessibilityEnabled' AS accessibility_enabled,"
                    "capabilities->>'runnerState' AS runner_state,"
                    "capabilities->>'safetyBarrier' AS safety_barrier,"
                    "capabilities->>'orderDeliveryProtocol' AS order_delivery_protocol "
                    "FROM device WHERE id=$1",
                    device_id,
                )
                item = {"serial": serial, "device": dict(row) if row else None}
                item["mobileBindings"] = [
                    dict(binding)
                    for binding in await connection.fetch(
                        "SELECT id,tenant_id,companion_version,last_seen_at,revoked_at "
                        "FROM mobile_binding WHERE device_id=$1 AND revoked_at IS NULL",
                        device_id,
                    )
                ]
                item["accountBindings"] = [
                    dict(binding)
                    for binding in await connection.fetch(
                        "SELECT platform,status,binding_version FROM account_device_binding "
                        "WHERE device_id=$1",
                        device_id,
                    )
                ]
                item["expectedBindingActive"] = any(
                    binding["id"] == EXPECTED_BINDINGS[serial] for binding in item["mobileBindings"]
                )
                result["devices"].append(item)
        spec = importlib.util.spec_from_file_location(
            "existing_release_ops", ROOT / "incoming/im-notify-bb19ad2/cloud_release.py"
        )
        assert spec is not None and spec.loader is not None
        ops = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ops)
        async with httpx.AsyncClient(timeout=15, trust_env=False, auth=ops.auth()) as client:
            for item in result["devices"]:
                response = await client.get(
                    ops.HOST + "/api/v1/im/config",
                    params={"deviceId": DEVICES[item["serial"]]},
                )
                item["operatorImRead"] = {"httpStatus": response.status_code}
                if response.status_code == 200:
                    config = response.json()
                    item["operatorImRead"].update(
                        {key: config.get(key) for key in ("receiveOnly", "mode", "enabled")}
                    )
        print(json.dumps(result, indent=2, default=str))
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
