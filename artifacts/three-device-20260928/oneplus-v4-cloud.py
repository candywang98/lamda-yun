"""Controller-only maintenance window for the explicitly authorized OnePlus upgrade."""

import asyncio
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path("/home/ubuntu/cloudctl-mobile")
DEVICE = "4aabc387-6e4b-4b59-a525-b1c119ec7f5b"
BINDING = "202ff9cb-6b6d-4ccc-bbf7-31bd91edb51e"
TENANT = "00000000-0000-7000-8000-000000001111"
STATE = ROOT / "backups/oneplus-v4-20260928/identity-before.json"


def operations():
    spec = importlib.util.spec_from_file_location(
        "existing_ops", ROOT / "incoming/im-notify-bb19ad2/cloud_release.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def snapshot(ops, client):
    connection = await ops.database()
    try:
        await connection.execute("SET statement_timeout = '10s'")
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            await ops.idle(connection)
            assert (
                await connection.fetchval("SELECT version_num FROM alembic_version")
                == "20260926_0035"
            )
            device = dict(
                await connection.fetchrow(
                    "SELECT tenant_id,active_binding_id,maintenance,version,last_seen_at,"
                    "capabilities FROM device WHERE id=$1",
                    DEVICE,
                )
            )
            assert device["tenant_id"] == TENANT and device["active_binding_id"] == BINDING
            bindings = [
                dict(row)
                for row in await connection.fetch(
                    "SELECT id,tenant_id,device_id,token_digest,app_instance_id "
                    "FROM mobile_binding WHERE device_id=$1 AND revoked_at IS NULL ORDER BY id",
                    DEVICE,
                )
            ]
            assert len(bindings) == 1 and bindings[0]["id"] == BINDING
            accounts = [
                dict(row)
                for row in await connection.fetch(
                    "SELECT id,tenant_id,account_id,device_id,status,binding_version,platform "
                    "FROM account_device_binding WHERE device_id=$1 ORDER BY id",
                    DEVICE,
                )
            ]
            counts = {
                "tasks": await connection.fetchval("SELECT count(*) FROM mobile_task"),
                "outgoingMessages": await connection.fetchval(
                    "SELECT count(*) FROM im_message WHERE direction='OUT'"
                ),
            }
            orders = {
                "orders": await connection.fetchval(
                    "SELECT count(*) FROM xianyu_order WHERE device_id=$1", DEVICE
                ),
                "receipts": await connection.fetchval(
                    "SELECT count(*) FROM order_delivery_receipt WHERE device_id=$1", DEVICE
                ),
            }
    finally:
        await connection.close()
    response = await client.get(ops.HOST + "/api/v1/im/config", params={"deviceId": DEVICE})
    response.raise_for_status()
    config = response.json()
    assert config["receiveOnly"] is True and config["mode"] == "NOTIFICATION"
    return {
        "observedAt": datetime.now(UTC).isoformat(),
        "device": device,
        "identity": {"bindings": bindings, "accounts": accounts},
        "counts": counts,
        "orders": orders,
    }


def compare(before, current):
    assert before["identity"] == current["identity"], "Binding/account identity drift"
    assert before["counts"] == current["counts"], "Unexpected task or outgoing-message change"


async def main(action):
    assert action in {"prepare", "verify", "finish"}
    os.umask(0o077)
    ops = operations()
    async with httpx.AsyncClient(timeout=20, trust_env=False, auth=ops.auth()) as client:
        current = await snapshot(ops, client)
        if action == "prepare":
            assert not current["device"]["maintenance"]
            STATE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with STATE.open("x") as output:
                json.dump(current, output, default=str)
                output.flush()
                os.fsync(output.fileno())
            response = await client.post(
                ops.HOST + f"/api/v1/devices/{DEVICE}:maintenance",
                json={
                    "enabled": True,
                    "expectedVersion": current["device"]["version"],
                    "reason": "Authorized OnePlus v4 update; preserve binding and data",
                },
            )
            response.raise_for_status()
            before = current
            current = await snapshot(ops, client)
            compare(before, current)
            assert current["device"]["maintenance"]
            assert current["device"]["version"] == before["device"]["version"] + 1
        else:
            before = json.loads(STATE.read_text())
            compare(before, current)
            if action == "finish" and current["device"]["maintenance"]:
                assert current["device"]["version"] == before["device"]["version"] + 1
                response = await client.post(
                    ops.HOST + f"/api/v1/devices/{DEVICE}:maintenance",
                    json={
                        "enabled": False,
                        "expectedVersion": current["device"]["version"],
                        "reason": "End authorized OnePlus v4 update; retain identities",
                    },
                )
                response.raise_for_status()
                current = await snapshot(ops, client)
                compare(before, current)
                assert not current["device"]["maintenance"]
                assert current["device"]["version"] == before["device"]["version"] + 2
        capabilities = current["device"].pop("capabilities")
        if isinstance(capabilities, str):
            capabilities = json.loads(capabilities)
        current.pop("identity")
        current.update(
            {
                "action": action,
                "idle": True,
                "bindingAndCredentialRetained": True,
                "accountBindingsRetained": True,
                "receiveOnly": True,
                "mode": "NOTIFICATION",
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
        )
        print(json.dumps(current, default=str))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
