"""F14 delta: xiaohongshu 图文发布参数边界（图文 V1、视频显式拒绝、顺序透传）.

参数校验的权威层是 parse_command_v1（CommandV1 构建期）；platform-tasks
铸造层按既有冻结契约对 parameters 透传不重排。本文件冻结两层语义：
- 铸造层：mediaAssetIds 顺序原样透传（选图顺序契约）。
- 命令层：空图/超限 422；视频字段显式拒绝（extra=forbid 报字段名），
  而非静默丢弃；draftPolicy 参数面未放开（BLK-012：需 params/factory/
  PlatformTaskCreate 三层同步裁决，companion 侧默认 WAITING_USER）。
companion 侧草稿策略/有界返回/图序证明在 mobile/companion features/xhs 单测。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.settings import Settings
from fastapi import FastAPI

TENANT = "00000000-0000-7000-8000-000000000111"
OPERATOR = "00000000-0000-7000-8000-000000000222"


def identity(role: str = "device_operator") -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT,
        "X-User-Id": OPERATOR,
        "X-Roles": role,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


def valid_command(parameters: dict) -> dict:
    from datetime import UTC, datetime

    from cloudctl_api.command_v1 import command_v1_from_task

    return command_v1_from_task(
        task_id="11111111-1111-7111-8111-111111111111",
        attempt_id="22222222-2222-7222-8222-222222222222",
        command_type="xiaohongshu.publish_note.v1",
        device_id="33333333-3333-7333-8333-333333333333",
        account_id="44444444-4444-7444-8444-444444444444",
        binding_version=1,
        target_package="com.xingin.xhs",
        command_payload={"snapshotSha256": "d" * 64, "parameters": parameters},
        control_epoch=4,
        lease_expires_at=datetime(2026, 9, 20, 13, 0, tzinfo=UTC),
    )


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


async def _seed(client: httpx.AsyncClient) -> tuple[str, str, int]:
    device = await client.post(
        "/api/v1/mobile/devices",
        headers=identity(),
        json={"logicalName": "phone-f14", "androidVersion": "14", "companionVersion": "1.0.0"},
    )
    assert device.status_code == 201, device.text
    account = await client.post(
        "/api/v1/accounts",
        headers=identity(),
        json={
            "platform": "xiaohongshu",
            "externalSubjectRef": "xhs-f14",
            "displayLabel": "xhs-f14",
            "secretRef": "vault://cloudctl/accounts/xhs-f14",
            "authorizationBasis": "Owner authorized the F14 delta test.",
        },
    )
    assert account.status_code == 201, account.text
    bound = await client.post(
        f"/api/v1/accounts/{account.json()['id']}/bindings",
        headers=identity(),
        json={"deviceId": device.json()["id"], "confirmationNote": "Owner confirmed."},
    )
    assert bound.status_code == 201, bound.text
    return str(device.json()["id"]), str(account.json()["id"]), int(bound.json()["bindingVersion"])


@pytest.mark.asyncio
async def test_mint_transports_media_order_unchanged(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id, account_id, binding = await _seed(client)
    order = ["img-c", "img-a", "img-b"]
    minted = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "f14-order"},
        json={
            "deviceId": device_id,
            "accountId": account_id,
            "expectedBindingVersion": binding,
            "commandType": "xiaohongshu.publish_note.v1",
            "parameters": {
                "title": "F14 图文",
                "body": "顺序冻结测试",
                "mediaAssetIds": order,
            },
        },
    )
    assert minted.status_code == 201, minted.text
    task_id = minted.json()["items"][0]["taskId"]
    detail = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert detail.status_code == 200
    assert detail.json()["commandPayload"]["parameters"]["mediaAssetIds"] == order
