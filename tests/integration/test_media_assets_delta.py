from __future__ import annotations

import hashlib
import io
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import DeviceRow
from cloudctl_api.media_store import InMemoryObjectStore
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import select

TENANT = "00000000-0000-7000-8000-000000000111"
FOREIGN_TENANT = "00000000-0000-7000-8000-000000000999"
USER = "00000000-0000-7000-8000-000000000222"


def headers(roles: str, *, tenant: str = TENANT) -> dict[str, str]:
    return {
        "X-Tenant-Id": tenant,
        "X-User-Id": USER,
        "X-Roles": roles,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


def png_bytes(color: tuple[int, int, int] = (30, 90, 150)) -> bytes:
    image = Image.new("RGB", (320, 200), color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def upload_image(
    client: httpx.AsyncClient,
    store: InMemoryObjectStore,
    content: bytes,
    *,
    tenant: str = TENANT,
) -> str:
    digest = hashlib.sha256(content).hexdigest()
    object_key = f"tenants/{tenant}/fixtures/{digest}.png"
    store.put(object_key, content, "image/png")
    response = await client.post(
        "/api/v1/media/assets:register",
        headers=headers("content_editor", tenant=tenant),
        json={
            "sha256": digest,
            "objectKey": object_key,
            "contentType": "image/png",
            "sizeBytes": len(content),
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI, InMemoryObjectStore]]:
    store = InMemoryObjectStore()
    app = create_app(
        Settings(env="test", repository_mode="memory", dev_auth_bypass=True),
        object_store=store,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app, store


@pytest.mark.asyncio
async def test_watermark_derivative_is_real_deterministic_and_tenant_scoped(
    api: tuple[httpx.AsyncClient, FastAPI, InMemoryObjectStore],
) -> None:
    client, _, store = api
    source = await upload_image(client, store, png_bytes())
    request = {
        "text": "云控素材",
        "position": "bottom_right",
        "opacity": 65,
        "fontSize": 24,
        "margin": 16,
        "ruleVersionId": "wm-v1",
    }
    first = await client.post(
        f"/api/v1/media-assets/{source}/watermark:render",
        headers=headers("content_editor"),
        json=request,
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["previewSha256"] == body["publishDerivativeSha256"]
    output_id = body["outputAsset"]["id"]
    downloaded = await client.get(
        f"/api/v1/media/assets/{output_id}/content", headers=headers("viewer")
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("image/png")
    assert hashlib.sha256(downloaded.content).hexdigest() == body["previewSha256"]
    with Image.open(io.BytesIO(downloaded.content)) as image:
        assert image.size == (320, 200)
        assert image.format == "PNG"

    replay = await client.post(
        f"/api/v1/media-assets/{source}/watermark:render",
        headers=headers("content_editor"),
        json=request,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["previewSha256"] == body["previewSha256"]
    assert replay.json()["outputAsset"]["id"] == output_id

    hidden = await client.get(
        f"/api/v1/media/assets/{output_id}/content",
        headers=headers("viewer", tenant=FOREIGN_TENANT),
    )
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_pool_freeze_replays_original_selection_after_membership_changes(
    api: tuple[httpx.AsyncClient, FastAPI, InMemoryObjectStore],
) -> None:
    client, _, store = api
    assets = [
        await upload_image(client, store, png_bytes((index * 20, 40, 90)))
        for index in range(1, 5)
    ]
    group = await client.post(
        "/api/v1/media-groups",
        headers=headers("content_editor"),
        json={"name": "Publish covers"},
    )
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]
    for asset_id in assets[:3]:
        response = await client.put(
            f"/api/v1/media/assets/{asset_id}/taxonomy",
            headers=headers("content_editor"),
            json={"tags": ["cover"], "groupIds": [group_id]},
        )
        assert response.status_code == 200, response.text

    request = {"taskKey": "task-media-freeze-1", "groupId": group_id, "count": 2}
    first = await client.post(
        "/api/v1/media-assets/pools:freeze",
        headers=headers("content_editor"),
        json=request,
    )
    assert first.status_code == 200, first.text
    assert first.json()["replayed"] is False
    assert len(first.json()["mediaAssetIds"]) == 2

    for asset_id in assets:
        response = await client.put(
            f"/api/v1/media/assets/{asset_id}/taxonomy",
            headers=headers("content_editor"),
            json={"tags": ["cover"], "groupIds": [group_id] if asset_id == assets[3] else []},
        )
        assert response.status_code == 200, response.text

    replay = await client.post(
        "/api/v1/media-assets/pools:freeze",
        headers=headers("content_editor"),
        json=request,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["mediaAssetIds"] == first.json()["mediaAssetIds"]
    assert replay.json()["snapshotSha256"] == first.json()["snapshotSha256"]

    conflict = await client.post(
        "/api/v1/media-assets/pools:freeze",
        headers=headers("content_editor"),
        json={**request, "count": 3},
    )
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_publish_preflight_is_explainable_and_has_no_side_effect(
    api: tuple[httpx.AsyncClient, FastAPI, InMemoryObjectStore],
) -> None:
    client, app, store = api
    media_id = await upload_image(client, store, png_bytes())
    security = headers("security_admin")
    edge = await client.post(
        "/api/v1/edges",
        headers=security,
        json={"logicalName": "edge-f10", "certificateFingerprint": "ab" * 32},
    )
    assert edge.status_code == 201, edge.text
    device = await client.post(
        "/api/v1/devices",
        headers=security,
        json={
            "edgeId": edge.json()["id"],
            "logicalName": "device-f10",
            "androidVersion": "14",
            "lamdaVersion": "10.8",
            "targetAppVersions": {"com.taobao.idlefish": "7.24.20"},
            "capabilities": {"accessibilityEnabled": True},
        },
    )
    assert device.status_code == 201, device.text
    device_id = device.json()["id"]
    async with app.state.database.unit_of_work() as session:
        row = await session.scalar(select(DeviceRow).where(DeviceRow.id == device_id))
        assert row is not None
        row.state = "ONLINE"

    account = await client.post(
        "/api/v1/accounts",
        headers=headers("device_operator"),
        json={
            "platform": "xianyu",
            "externalSubjectRef": "f10-account",
            "displayLabel": "F10 account",
            "secretRef": "vault://cloudctl/accounts/f10",
            "authorizationBasis": "Owner approved the managed publish preflight.",
        },
    )
    assert account.status_code == 201, account.text
    account_id = account.json()["id"]
    binding = await client.post(
        f"/api/v1/accounts/{account_id}/bindings",
        headers=headers("device_operator"),
        json={"deviceId": device_id, "confirmationNote": "Owner confirmed this device."},
    )
    assert binding.status_code == 201, binding.text
    product = await client.post(
        "/api/v1/products",
        headers=headers("content_editor"),
        json={
            "spuCode": "F10-1",
            "title": "国家级收纳工具",
            "description": "普通二手商品说明",
            "category": "home",
            "price": "19.90",
            "stock": 1,
            "mediaAssetIds": [media_id],
        },
    )
    assert product.status_code == 201, product.text

    before_tasks = await client.get("/api/v1/platform-tasks", headers=headers("device_operator"))
    preflight = await client.post(
        "/api/v1/media-assets/publish:preflight",
        headers=headers("publisher"),
        json={
            "productId": product.json()["id"],
            "accountId": account_id,
            "deviceId": device_id,
            "platform": "xianyu",
        },
    )
    assert preflight.status_code == 200, preflight.text
    body = preflight.json()
    assert body["ready"] is True
    checks = {item["id"]: item for item in body["checks"]}
    assert checks["content.word.国家级"]["status"] == "WARNING"
    assert checks["media.assets"]["status"] == "PASS"
    assert checks["account.binding"]["status"] == "PASS"
    assert checks["device.accessibility"]["status"] == "PASS"
    assert body["snapshot"]["mediaAssetIds"] == [media_id]
    after_tasks = await client.get("/api/v1/platform-tasks", headers=headers("device_operator"))
    assert before_tasks.status_code == after_tasks.status_code
    if before_tasks.status_code == 200:
        assert before_tasks.json() == after_tasks.json()

    blocked_product = await client.post(
        "/api/v1/products",
        headers=headers("content_editor"),
        json={
            "spuCode": "F10-2",
            "title": "微信联系",
            "description": "站外交易",
            "category": "home",
            "price": "1",
            "stock": 1,
            "mediaAssetIds": [media_id],
        },
    )
    assert blocked_product.status_code == 201, blocked_product.text
    blocked = await client.post(
        "/api/v1/media-assets/publish:preflight",
        headers=headers("publisher"),
        json={
            "productId": blocked_product.json()["id"],
            "accountId": account_id,
            "deviceId": device_id,
            "platform": "xianyu",
        },
    )
    assert blocked.status_code == 200
    assert blocked.json()["ready"] is False
    assert any(item["status"] == "BLOCKED" for item in blocked.json()["checks"])
