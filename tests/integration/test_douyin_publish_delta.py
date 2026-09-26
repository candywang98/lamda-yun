"""F15 delta: freeze the current Douyin server-driven steps boundary.

The production CommandV1 minting surface intentionally has no douyin command.
The existing steps protocol shape is inspected here without minting, dispatching,
or calling a real platform. Android-side planner and wait decisions are covered
by pure unit tests under ``mobile/companion``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.command_v1 import COMMAND_PACKAGES
from cloudctl_api.fleet_identity import FLEET_REQUIRED_CAPABILITIES
from cloudctl_api.mobile_actions import STEPS_SHAPES
from cloudctl_api.settings import Settings
from fastapi import FastAPI

TENANT = "00000000-0000-7000-8000-000000000111"
OPERATOR = "00000000-0000-7000-8000-000000000222"
DOUYIN_PACKAGE = "com.ss.android.ugc.aweme"
DOUYIN_STEPS_COMMAND = "douyin.publish_note.steps.v1"


def identity(role: str = "device_operator") -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT,
        "X-User-Id": OPERATOR,
        "X-Roles": role,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


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
        json={"logicalName": "phone-f15", "androidVersion": "14", "companionVersion": "1.0.0"},
    )
    assert device.status_code == 201, device.text
    account = await client.post(
        "/api/v1/accounts",
        headers=identity(),
        json={
            "platform": "douyin",
            "externalSubjectRef": "douyin-f15",
            "displayLabel": "douyin-f15",
            "secretRef": "vault://cloudctl/accounts/douyin-f15",
            "authorizationBasis": "Owner authorized the F15 delta test.",
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
async def test_mint_rejects_douyin_command_type_with_literal_error(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id, account_id, binding = await _seed(client)
    minted = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "f15-douyin-not-registered"},
        json={
            "deviceId": device_id,
            "accountId": account_id,
            "expectedBindingVersion": binding,
            "commandType": DOUYIN_STEPS_COMMAND,
            "parameters": {"title": "F15 视频", "videoAssetIds": ["video-001"]},
        },
    )
    assert minted.status_code == 422, minted.text
    problem = minted.json()
    assert problem["code"] == "VALIDATION_ERROR"
    assert problem["retryable"] is False
    message = problem["fields"]["commandType"]
    for registered in COMMAND_PACKAGES:
        assert registered in message
    assert "douyin" not in message


def test_douyin_steps_shape_is_not_a_command_v1_registration() -> None:
    assert not any(command.startswith("douyin.") for command in COMMAND_PACKAGES)

    shape = STEPS_SHAPES[DOUYIN_PACKAGE]
    assert shape["command_type"] == DOUYIN_STEPS_COMMAND
    assert shape["publish_button"] == "dy_publish_button"
    assert shape["postcondition"] == "dy_publish_success"
    assert shape["content_input"] == "dy_note_body"
    assert FLEET_REQUIRED_CAPABILITIES[DOUYIN_STEPS_COMMAND] == (
        "accessibility",
        "ime",
        "screen_capture",
    )
