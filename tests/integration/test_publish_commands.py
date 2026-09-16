"""A05 integration: web business objects → CommandV1 mint + stable publishTargetId.

Covers the K05 platform-recipe/v1 §4/§6/§7 semantics for the two officially
allowed publish command types:

- Product → xianyu.publish_listing.v1, ContentRevision →
  xiaohongshu.publish_note.v1, both open-only.
- Stable publishTargetId derived from (content_id, revision_no, platform,
  account_id, device_id) and stamped into command_payload through the
  existing PlatformTaskCreate.publishTargetId channel.
- Fail-closed pre-mint validation matrix (422/404/403/409 by semantics).
- Open-only result identity: "reached confirmation point + evidence ref",
  never a publish-completion claim.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import hashlib

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.command_factory import (
    OPEN_ONLY_RESULT_EVIDENCE_KEY,
    OPEN_ONLY_RESULT_OUTCOME,
    PUBLISH_TARGET_NAMESPACE,
    _validate_publish_media,
    derive_publish_target_id,
    mint_publish_command,
    platform_task_create_fields,
    validate_open_only_task_result,
)
from cloudctl_api.settings import Settings
from cloudctl_domain import ConflictError, ForbiddenError, NotFoundError, ValidationError
from fastapi import FastAPI

TENANT = "00000000-0000-7000-8000-000000000111"
OPERATOR = "00000000-0000-7000-8000-000000000222"


def identity(*, role: str = "device_operator") -> dict[str, str]:
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


async def create_direct_device(client: httpx.AsyncClient, name: str) -> str:
    response = await client.post(
        "/api/v1/mobile/devices",
        headers=identity(),
        json={"logicalName": name, "androidVersion": "14", "companionVersion": "1.0.0"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def create_account(client: httpx.AsyncClient, subject: str, platform: str) -> str:
    response = await client.post(
        "/api/v1/accounts",
        headers=identity(),
        json={
            "platform": platform,
            "externalSubjectRef": subject,
            "displayLabel": subject,
            "secretRef": f"vault://cloudctl/accounts/{subject}",
            "authorizationBasis": "Owner authorized the test account.",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def bind(client: httpx.AsyncClient, account_id: str, device_id: str) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/accounts/{account_id}/bindings",
        headers=identity(),
        json={"deviceId": device_id, "confirmationNote": "Owner confirmed."},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def register_asset(
    client: httpx.AsyncClient, key: str, *, content_type: str = "image/jpeg"
) -> str:
    response = await client.post(
        "/api/v1/media/assets:register",
        headers=identity(role="content_editor"),
        json={
            "sha256": hashlib.sha256(key.encode()).hexdigest(),
            "objectKey": f"tenant/publish/{key}",
            "contentType": content_type,
            "sizeBytes": 12,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def create_product(
    client: httpx.AsyncClient, media_asset_ids: list[str]
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/products",
        headers=identity(role="content_editor"),
        json={
            "spuCode": f"SPU-A05-{uuid.uuid4().hex[:8]}",
            "title": "Notion Business 一年免费兑换",
            "description": "Notion Business 兑换券，图示价值 $240。拍下后按说明发送兑换方式。支持当面交易。",
            "category": "虚拟",
            "price": "199",
            "stock": 1,
            "mediaAssetIds": media_asset_ids,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_content(
    client: httpx.AsyncClient, media_asset_ids: list[str], *, target_app: str = "xiaohongshu"
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/content",
        headers=identity(role="content_editor"),
        json={
            "title": "闲置好物分享",
            "payload": {
                "kind": "post",
                "body": "正文不少于一个字，记录这次闲置流转。",
                "mediaAssetIds": media_asset_ids,
                "targetApp": target_app,
                "draftState": "待复核",
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def mint(app: FastAPI, **kwargs: Any) -> dict[str, Any]:
    async with app.state.database.session_factory() as session:
        return await mint_publish_command(session, tenant_id=TENANT, **kwargs)


async def create_platform_task(
    client: httpx.AsyncClient, key: str, fields: dict[str, Any]
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": key},
        json=fields,
    )
    assert response.status_code == 201, response.text
    return response.json()["items"][0]


async def enroll_and_claim(
    client: httpx.AsyncClient, device_id: str, instance: str
) -> tuple[dict[str, str], dict[str, Any]]:
    enroll = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(),
        json={"deviceId": device_id, "ttlSeconds": 600},
    )
    token = (
        await client.post(
            "/companion/v2/enroll",
            json={
                "code": enroll.json()["code"],
                "appInstanceId": instance,
                "companionVersion": "1.0.0",
            },
        )
    ).json()["bindingToken"]
    auth = {"Authorization": f"Bearer {token}"}
    claimed = await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})
    assert claimed.status_code == 200, claimed.text
    return auth, claimed.json()


@pytest.mark.asyncio
async def test_product_mints_stable_open_only_xianyu_command(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """Product → xianyu.publish_listing.v1 (K05 k05-positive semantics)."""
    from cloudctl_api.builtin_recipes import builtin_recipe_ref
    from cloudctl_api.command_v1 import parse_command_v1

    client, app = api
    device_id = await create_direct_device(client, "phone-a05-xy")
    account = await create_account(client, "xy-a05", "xianyu")
    bound = await bind(client, account, device_id)
    asset_a = await register_asset(client, "a" * 60 + "cover")
    asset_b = await register_asset(client, "b" * 60 + "detail")
    product = await create_product(client, [asset_a, asset_b])

    minted = await mint(
        app,
        command_type="xianyu.publish_listing.v1",
        device_id=device_id,
        account_id=account,
        product_id=product["id"],
    )
    assert minted["commandType"] == "xianyu.publish_listing.v1"
    assert minted["targetPackage"] == "com.taobao.idlefish"
    assert minted["openOnly"] is True
    assert minted["operationId"] == "xy-tasks-01"
    assert minted["catalogCommandType"] == "xianyu.publish_goods"
    assert minted["recipe"] == builtin_recipe_ref("xianyu.publish_listing.v1")
    # Frozen catalog copy: product description/price win, media order preserved.
    assert minted["parameters"]["listingBody"] == product["description"]
    assert minted["parameters"]["price"] == "199"
    assert minted["parameters"]["mediaAssetIds"] == [asset_a, asset_b]
    assert minted["parameters"]["productId"] == product["id"]
    # Stable identity: derived from the frozen target tuple, re-mint is stable.
    expected_target_id = derive_publish_target_id(
        content_id=product["id"],
        revision_no=product["revision"],
        platform="xianyu",
        account_id=account,
        device_id=device_id,
    )
    assert minted["publishTargetId"] == expected_target_id
    assert minted["mediaDeliveryId"] == f"delivery-xianyu-{product['id']}-{product['revision']}"
    reminted = await mint(
        app,
        command_type="xianyu.publish_listing.v1",
        device_id=device_id,
        account_id=account,
        product_id=product["id"],
    )
    assert reminted == minted

    # The mint output flows through the existing stamping channel.
    fields = platform_task_create_fields(
        minted,
        device_id=device_id,
        account_id=account,
        expected_binding_version=bound["bindingVersion"],
    )
    task = await create_platform_task(client, "a05-xy-publish", fields)
    payload = task["commandPayload"]
    assert payload["publishTargetId"] == expected_target_id
    assert payload["operationId"] == "xy-tasks-01"
    assert payload["parameters"] == minted["parameters"]
    assert payload["recipe"] == builtin_recipe_ref("xianyu.publish_listing.v1")
    assert task["commandPayload"]["mediaDeliveryId"] == minted["mediaDeliveryId"]

    _, claimed = await enroll_and_claim(client, device_id, "instance-a05-xy")
    command = parse_command_v1(claimed["command"])
    assert command["commandType"] == "xianyu.publish_listing.v1"
    assert command["targetPackage"] == "com.taobao.idlefish"
    assert command["recipe"] == builtin_recipe_ref("xianyu.publish_listing.v1")
    assert command["parameters"] == minted["parameters"]
    assert command["legacyStepsEnabled"] is False
    assert "steps" not in claimed


@pytest.mark.asyncio
async def test_content_revision_mints_stable_open_only_xhs_command(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """ContentRevision → xiaohongshu.publish_note.v1 (K05 D2 family A)."""
    from cloudctl_api.builtin_recipes import builtin_recipe_ref
    from cloudctl_api.command_v1 import parse_command_v1

    client, app = api
    device_id = await create_direct_device(client, "phone-a05-xhs")
    account = await create_account(client, "xhs-a05", "xiaohongshu")
    bound = await bind(client, account, device_id)
    asset = await register_asset(client, "c" * 60 + "note")
    content = await create_content(client, [asset])

    minted = await mint(
        app,
        command_type="xiaohongshu.publish_note.v1",
        device_id=device_id,
        account_id=account,
        content_id=content["id"],
    )
    assert minted["commandType"] == "xiaohongshu.publish_note.v1"
    assert minted["targetPackage"] == "com.xingin.xhs"
    assert minted["openOnly"] is True
    assert minted["operationId"] == "red-tasks-01"
    assert minted["recipe"] == builtin_recipe_ref("xiaohongshu.publish_note.v1")
    assert minted["parameters"]["title"] == content["title"]
    assert minted["parameters"]["body"] == content["revision"]["payload"]["body"]
    assert minted["parameters"]["mediaAssetIds"] == [asset]
    revision_no = content["revision"]["revision_no"]
    assert minted["publishTargetId"] == derive_publish_target_id(
        content_id=content["id"],
        revision_no=revision_no,
        platform="xiaohongshu",
        account_id=account,
        device_id=device_id,
    )

    # A new revision is a new target: stable id per revision, different across.
    add_revision = await client.post(
        f"/api/v1/content/{content['id']}/revisions",
        headers=identity(role="content_editor"),
        json={
            "payload": {
                "kind": "post",
                "body": "改稿后的正文，仍然是同一条笔记。",
                "mediaAssetIds": [asset],
                "targetApp": "xiaohongshu",
                "draftState": "待复核",
            }
        },
    )
    assert add_revision.status_code == 201, add_revision.text
    reminted = await mint(
        app,
        command_type="xiaohongshu.publish_note.v1",
        device_id=device_id,
        account_id=account,
        content_id=content["id"],
    )
    assert reminted["publishTargetId"] != minted["publishTargetId"]
    assert reminted["parameters"]["body"] == "改稿后的正文，仍然是同一条笔记。"
    # Explicit revision_no freezes that exact revision.
    pinned = await mint(
        app,
        command_type="xiaohongshu.publish_note.v1",
        device_id=device_id,
        account_id=account,
        content_id=content["id"],
        revision_no=revision_no,
    )
    assert pinned == minted

    fields = platform_task_create_fields(
        reminted,
        device_id=device_id,
        account_id=account,
        expected_binding_version=bound["bindingVersion"],
    )
    task = await create_platform_task(client, "a05-xhs-publish", fields)
    assert task["commandPayload"]["publishTargetId"] == reminted["publishTargetId"]
    assert task["commandPayload"]["parameters"] == reminted["parameters"]

    _, claimed = await enroll_and_claim(client, device_id, "instance-a05-xhs")
    command = parse_command_v1(claimed["command"])
    assert command["commandType"] == "xiaohongshu.publish_note.v1"
    assert command["targetPackage"] == "com.xingin.xhs"
    assert command["parameters"] == reminted["parameters"]
    assert command["legacyStepsEnabled"] is False


@pytest.mark.asyncio
async def test_publish_mint_fail_closed_validation_matrix(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id = await create_direct_device(client, "phone-a05-matrix")
    other_device = await create_direct_device(client, "phone-a05-matrix-b")
    account = await create_account(client, "xy-a05-matrix", "xianyu")
    await bind(client, account, device_id)
    asset = await register_asset(client, "d" * 60 + "matrix")
    product = await create_product(client, [asset])
    xhs_account = await create_account(client, "xhs-a05-matrix", "xiaohongshu")
    await bind(client, xhs_account, device_id)
    content = await create_content(client, [asset])

    base_xy = {
        "command_type": "xianyu.publish_listing.v1",
        "device_id": device_id,
        "account_id": account,
        "product_id": product["id"],
    }
    base_xhs = {
        "command_type": "xiaohongshu.publish_note.v1",
        "device_id": device_id,
        "account_id": xhs_account,
        "content_id": content["id"],
    }

    # 422: only the two publish CommandV1 types are mintable from business objects.
    with pytest.raises(ValidationError):
        await mint(app, **{**base_xy, "command_type": "xianyu.collect_orders.v1"})
    with pytest.raises(ValidationError):
        await mint(app, **{**base_xy, "command_type": "device.probe_capabilities.v1"})
    # 422: the business object reference is mandatory.
    with pytest.raises(ValidationError):
        await mint(app, **{k: v for k, v in base_xy.items() if k != "product_id"})
    with pytest.raises(ValidationError):
        await mint(app, **{k: v for k, v in base_xhs.items() if k != "content_id"})

    # 404: referenced identities that do not exist in the tenant.
    with pytest.raises(NotFoundError):
        await mint(app, **{**base_xy, "account_id": str(uuid.uuid4())})
    with pytest.raises(NotFoundError):
        await mint(app, **{**base_xy, "product_id": str(uuid.uuid4())})
    with pytest.raises(NotFoundError):
        await mint(app, **{**base_xhs, "content_id": str(uuid.uuid4())})
    with pytest.raises(NotFoundError):
        await mint(app, **{**base_xhs, "revision_no": 99})

    # 403: platform mismatch and device binding.
    with pytest.raises(ForbiddenError):
        await mint(app, **{**base_xhs, "account_id": account})  # xianyu account, xhs command
    with pytest.raises(ForbiddenError):
        await mint(app, **{**base_xy, "device_id": other_device})  # account bound elsewhere

    # 409: business object state.
    archive = await client.post(
        f"/api/v1/content/{content['id']}:archive",
        headers=identity(role="content_editor"),
        json={"reason": "a05 fail-closed matrix"},
    )
    assert archive.status_code in {200, 204}, archive.text
    with pytest.raises(ConflictError):
        await mint(app, **base_xhs)
    product_archive = await client.post(
        f"/api/v1/products/{product['id']}:archive",
        headers=identity(role="content_editor"),
        json={"reason": "operator removed the listing source"},
    )
    assert product_archive.status_code in {200, 204}, product_archive.text
    with pytest.raises(ConflictError):
        await mint(app, **base_xy)

    # 422: douyin-targeted revision cannot mint an xhs command.
    douyin_asset = await register_asset(client, "e" * 60 + "douyin")
    douyin_content = await create_content(client, [douyin_asset], target_app="douyin")
    with pytest.raises(ValidationError):
        await mint(
            app,
            command_type="xiaohongshu.publish_note.v1",
            device_id=device_id,
            account_id=xhs_account,
            content_id=douyin_content["id"],
        )


@pytest.mark.asyncio
async def test_publish_mint_media_limits_and_types(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id = await create_direct_device(client, "phone-a05-media")
    account = await create_account(client, "xhs-a05-media", "xiaohongshu")
    await bind(client, account, device_id)

    # 19 registered images: the content payload accepts 20, the xhs mint caps at 18.
    many = [await register_asset(client, f"{index:02d}" + "f" * 58) for index in range(19)]
    content = await create_content(client, many)
    with pytest.raises(ValidationError, match="platform limit"):
        await mint(
            app,
            command_type="xiaohongshu.publish_note.v1",
            device_id=device_id,
            account_id=account,
            content_id=content["id"],
        )

    # Non-image media fails closed even though the content payload accepts it.
    video = await register_asset(client, "9" * 60 + "video", content_type="video/mp4")
    video_content = await create_content(client, [video])
    with pytest.raises(ValidationError, match="image"):
        await mint(
            app,
            command_type="xiaohongshu.publish_note.v1",
            device_id=device_id,
            account_id=account,
            content_id=video_content["id"],
        )

    # A note with no media is not a publishable target.
    empty_content = await create_content(client, [])
    with pytest.raises(ValidationError, match="at least one"):
        await mint(
            app,
            command_type="xiaohongshu.publish_note.v1",
            device_id=device_id,
            account_id=account,
            content_id=empty_content["id"],
        )

    # White-box: duplicate ids break the order guarantee (both ingestion paths
    # dedupe, so the guard is defense-in-depth at the mint itself).
    asset = many[0]
    async with app.state.database.session_factory() as session:
        with pytest.raises(ValidationError, match="duplicate-free"):
            await _validate_publish_media(
                session,
                tenant_id=TENANT,
                platform="xiaohongshu",
                media_asset_ids=[asset, asset],
                require_at_least_one=True,
            )


@pytest.mark.asyncio
async def test_open_only_result_identity_at_the_task_layer(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """K05 k05-positive-openonly-publish / negative semantics.

    The open-only result identity is "reached the confirmation point + an
    evidence ref". The validator rejects publish-completion claims before the
    terminal result is persisted; probes and other command families keep
    their own result shapes.
    """
    client, app = api
    device_id = await create_direct_device(client, "phone-a05-result")
    account = await create_account(client, "xhs-a05-result", "xiaohongshu")
    bound = await bind(client, account, device_id)
    asset = await register_asset(client, "7" * 60 + "result")
    content = await create_content(client, [asset])

    minted = await mint(
        app,
        command_type="xiaohongshu.publish_note.v1",
        device_id=device_id,
        account_id=account,
        content_id=content["id"],
    )
    fields = platform_task_create_fields(
        minted,
        device_id=device_id,
        account_id=account,
        expected_binding_version=bound["bindingVersion"],
    )
    task = await create_platform_task(client, "a05-xhs-result", fields)
    auth, claimed = await enroll_and_claim(client, device_id, "instance-a05-result")
    lease_id = claimed["leaseId"]

    # A publish-completion claim is rejected by the open-only result contract.
    for bad_result in (
        {"outcome": "published"},
        {"outcome": "ok", "resultType": "XiaohongshuPublishNoteResult"},
        {"resultType": "XiaohongshuPublishNoteResult", "published": True},
        {"outcome": OPEN_ONLY_RESULT_OUTCOME, "resultType": "XiaohongshuPublishNoteResult"},
    ):
        with pytest.raises(ValidationError):
            validate_open_only_task_result("xiaohongshu.publish_note.v1", bad_result)

    # The checkpoint result is the accepted terminal identity.
    checkpoint_result = {
        "outcome": OPEN_ONLY_RESULT_OUTCOME,
        OPEN_ONLY_RESULT_EVIDENCE_KEY: "s3://evidence/xhs-note-checkpoint.png",
        "resultType": "XiaohongshuPublishNoteResult",
        "schemaVersion": 1,
    }
    validate_open_only_task_result("xiaohongshu.publish_note.v1", checkpoint_result)
    completed = await client.post(
        f"/companion/v2/tasks/{task['taskId']}/complete",
        headers=auth,
        json={"leaseId": lease_id, "result": checkpoint_result},
    )
    assert completed.status_code == 200, completed.text
    detail = await client.get(f"/api/v1/platform-tasks/{task['taskId']}", headers=identity())
    assert detail.json()["state"] == "SUCCEEDED"
    assert detail.json()["result"]["outcome"] == OPEN_ONLY_RESULT_OUTCOME
    # Probes are not publishes: their result identity is untouched.
    validate_open_only_task_result("device.probe_capabilities.v1", {"outcome": "ok"})


def test_publish_target_namespace_is_pinned() -> None:
    # The namespace literal is part of the frozen derivation rule; changing it
    # would re-key every existing publishTargetId.
    assert str(PUBLISH_TARGET_NAMESPACE) == "2b3a7893-01af-4137-8d07-7459ef8785c8"
