from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.media_store import InMemoryObjectStore
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import event

TENANT = "00000000-0000-7000-8000-000000000111"
USER = "00000000-0000-7000-8000-000000000222"
SERVICE = "00000000-0000-7000-8000-000000000333"


@pytest.mark.asyncio
async def test_media_taxonomy_and_references(api: tuple[httpx.AsyncClient, FastAPI]) -> None:
    client, _ = api
    editor = headers("content_editor")
    viewer = headers("viewer")
    asset = await client.post(
        "/api/v1/media/assets:register",
        headers=editor,
        json={
            "sha256": "c" * 64,
            "objectKey": "taxonomy/image.jpg",
            "contentType": "image/jpeg",
            "sizeBytes": 10,
        },
    )
    assert asset.status_code == 201
    aid = asset.json()["id"]
    group = await client.post("/api/v1/media-groups", headers=editor, json={"name": "Campaign"})
    assert group.status_code == 201
    gid = group.json()["id"]
    duplicate = await client.post("/api/v1/media-groups", headers=editor, json={"name": "Campaign"})
    assert duplicate.status_code == 409
    renamed = await client.put(
        f"/api/v1/media-groups/{gid}",
        headers=editor,
        json={"name": "Renamed Campaign", "description": "updated"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed Campaign"
    forbidden_rename = await client.put(
        f"/api/v1/media-groups/{gid}",
        headers=headers("viewer"),
        json={"name": "Nope"},
    )
    assert forbidden_rename.status_code == 403
    url = f"/api/v1/media/assets/{aid}/taxonomy"
    updated = await client.put(
        url, headers=editor, json={"tags": [" cover ", "cover"], "groupIds": [gid]}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["tags"] == ["cover"]
    invalid = await client.put(
        url, headers=editor, json={"tags": ["lost"], "groupIds": ["missing"]}
    )
    assert invalid.status_code == 422
    forbidden = await client.put(url, headers=headers("viewer"), json={"tags": []})
    assert forbidden.status_code == 403
    foreign = headers("content_editor", tenant="00000000-0000-7000-8000-000000000999")
    hidden = await client.get(f"/api/v1/media/assets/{aid}/references", headers=foreign)
    assert hidden.status_code == 404
    hidden_write = await client.put(url, headers=foreign, json={"tags": []})
    assert hidden_write.status_code == 404
    product = await client.post(
        "/api/v1/products",
        headers=editor,
        json={
            "spuCode": "REF-1",
            "title": "Referenced",
            "category": "photo",
            "price": "1",
            "stock": 1,
            "mediaAssetIds": [aid],
        },
    )
    assert product.status_code == 201
    content = await client.post(
        "/api/v1/content",
        headers=editor,
        json={
            "title": "Referenced content",
            "payload": {"mediaAssetIds": [aid]},
        },
    )
    assert content.status_code == 201, content.text
    refs = await client.get(f"/api/v1/media/assets/{aid}/references", headers=headers("viewer"))
    assert refs.status_code == 200
    assert refs.json()["tags"] == ["cover"]
    assert refs.json()["productIds"] == [product.json()["id"]]
    assert refs.json()["contentReferences"][0]["contentId"] == content.json()["id"]
    assert refs.json()["contentReferences"][0]["revisionNo"] == 1
    assert refs.json()["publishPlanReferences"] == []
    listed = await client.get("/api/v1/media-groups", headers=headers("viewer"))
    assert listed.json()[0]["mediaAssetIds"] == [aid]
    cleared = await client.put(url, headers=editor, json={"tags": [], "groupIds": []})
    assert cleared.status_code == 200
    refs = await client.get(f"/api/v1/media/assets/{aid}/references", headers=headers("viewer"))
    assert refs.json()["tags"] == []
    assert refs.json()["groupIds"] == []
    deleted = await client.delete(f"/api/v1/media-groups/{gid}", headers=editor)
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/media-groups", headers=viewer)).json() == []
    assert (await client.get(f"/api/v1/media/assets/{aid}/references", headers=viewer)).json()[
        "mediaAssetId"
    ] == aid
    missing_delete = await client.delete(f"/api/v1/media-groups/{gid}", headers=editor)
    assert missing_delete.status_code == 404


@pytest.mark.asyncio
async def test_media_assets_filtering_and_pagination(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    editor = headers("content_editor")
    viewer = headers("viewer")
    group = await client.post("/api/v1/media-groups", headers=editor, json={"name": "Filter"})
    assert group.status_code == 201
    gid = group.json()["id"]
    ids = []
    for index in range(3):
        asset = await client.post(
            "/api/v1/media/assets:register",
            headers=editor,
            json={
                "sha256": str(index) * 64,
                "objectKey": f"filter/{index}.jpg",
                "contentType": "image/jpeg",
                "sizeBytes": 10,
            },
        )
        assert asset.status_code == 201
        aid = asset.json()["id"]
        ids.append(aid)
        updated = await client.put(
            f"/api/v1/media/assets/{aid}/taxonomy",
            headers=editor,
            json={
                "tags": ["campaign"] if index != 0 else ["other"],
                "groupIds": [gid] if index != 2 else [],
            },
        )
        assert updated.status_code == 200
    url = "/api/v1/media/assets"
    first = await client.get(url, headers=viewer, params={"pageSize": 2})
    assert first.status_code == 200
    assert first.json()["total"] == 3
    assert [item["id"] for item in first.json()["items"]] == ids[::-1][:2]
    second = await client.get(url, headers=viewer, params={"pageSize": 2, "page": 2})
    assert [item["id"] for item in second.json()["items"]] == [ids[0]]
    combined = await client.get(url, headers=viewer, params={"tag": "campaign", "groupId": gid})
    assert combined.json()["total"] == 1
    assert combined.json()["items"][0]["id"] == ids[1]
    assert combined.json()["items"][0]["tags"] == ["campaign"]
    assert combined.json()["items"][0]["groupIds"] == [gid]
    tagged = await client.get(url, headers=viewer, params={"tag": "campaign"})
    assert tagged.json()["total"] == 2
    grouped = await client.get(url, headers=viewer, params={"groupId": gid})
    assert grouped.json()["total"] == 2
    for params in ({"page": 0}, {"pageSize": 201}, {"tag": " "}):
        invalid = await client.get(url, headers=viewer, params=params)
        assert invalid.status_code == 422
    foreign = await client.get(
        url,
        headers=headers("viewer", tenant="00000000-0000-7000-8000-000000000999"),
        params={"groupId": gid},
    )
    assert foreign.json()["total"] == 0
    beyond = await client.get(url, headers=viewer, params={"page": 10})
    assert beyond.json()["items"] == []


def headers(roles: str, *, tenant: str = TENANT, user: str = USER) -> dict[str, str]:
    return {
        "X-Tenant-Id": tenant,
        "X-User-Id": user,
        "X-Roles": roles,
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


@pytest.mark.asyncio
async def test_content_media_flushes_parent_revision_before_reference() -> None:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))

    @event.listens_for(app.state.control_service.database.engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            editor = headers("content_editor")
            asset = await client.post(
                "/api/v1/media/assets:register",
                headers=editor,
                json={
                    "sha256": "9" * 64,
                    "objectKey": "posts/foreign-key-order.jpg",
                    "contentType": "image/jpeg",
                    "sizeBytes": 10,
                },
            )
            assert asset.status_code == 201, asset.text
            created = await client.post(
                "/api/v1/content",
                headers=editor,
                json={
                    "title": "带图帖子",
                    "payload": {
                        "kind": "post",
                        "body": "验证父修订先于媒体关联写入",
                        "mediaAssetIds": [asset.json()["id"]],
                        "targetApp": "unspecified",
                        "draftState": "草稿",
                    },
                },
            )
            assert created.status_code == 201, created.text
            assert created.json()["revision"]["payload"]["mediaAssetIds"] == [asset.json()["id"]]
            revised = await client.post(
                f"/api/v1/content/{created.json()['id']}/revisions",
                headers=editor,
                json={
                    "payload": {
                        "kind": "post",
                        "body": "再次编辑带图帖子",
                        "mediaAssetIds": [asset.json()["id"]],
                        "targetApp": "unspecified",
                        "draftState": "待复核",
                    },
                },
            )
            assert revised.status_code == 201, revised.text
            assert revised.json()["revision"]["revision_no"] == 2


async def create_device(client: httpx.AsyncClient) -> str:
    security = headers("security_admin")
    edge_response = await client.post(
        "/api/v1/edges",
        headers=security,
        json={"logicalName": "edge-a", "certificateFingerprint": "ab" * 32},
    )
    assert edge_response.status_code == 201, edge_response.text
    device_response = await client.post(
        "/api/v1/devices",
        headers=security,
        json={
            "edgeId": edge_response.json()["id"],
            "logicalName": "device-a",
            "androidVersion": "14",
            "lamdaVersion": "10.8",
        },
    )
    assert device_response.status_code == 201, device_response.text
    return str(device_response.json()["id"])


@pytest.mark.asyncio
async def test_account_authorization_binding_and_revocation(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_device(client)
    operator = headers("device_operator")
    create_response = await client.post(
        "/api/v1/accounts",
        headers=operator,
        json={
            "platform": "authorized-platform-adapter",
            "externalSubjectRef": "tenant-owned-account-001",
            "displayLabel": "Authorized account",
            "secretRef": "vault://cloudctl/accounts/001",
            "authorizationBasis": "Account owner approved managed publishing.",
        },
    )
    assert create_response.status_code == 201, create_response.text
    account = create_response.json()
    account_id = str(account["id"])
    assert account["secretConfigured"] is True
    assert "secretRef" not in account

    duplicate = await client.post(
        "/api/v1/accounts",
        headers=operator,
        json={
            "platform": "authorized-platform-adapter",
            "externalSubjectRef": "tenant-owned-account-001",
            "displayLabel": "Duplicate",
            "secretRef": "secret://cloudctl/accounts/duplicate",
            "authorizationBasis": "Duplicate authorization must be rejected.",
        },
    )
    assert duplicate.status_code == 409

    binding = await client.post(
        f"/api/v1/accounts/{account_id}/bindings",
        headers=operator,
        json={"deviceId": device_id, "confirmationNote": "Owner confirmed this device."},
    )
    assert binding.status_code == 201, binding.text
    assert binding.json()["status"] == "BOUND"

    accounts = await client.get("/api/v1/accounts", headers=headers("viewer"))
    assert accounts.status_code == 200, accounts.text
    current = accounts.json()[0]
    assert current["bindings"][0]["deviceId"] == device_id

    unbound = await client.delete(
        f"/api/v1/accounts/{account_id}/bindings/{device_id}", headers=operator
    )
    assert unbound.status_code == 204, unbound.text
    rebound = await client.post(
        f"/api/v1/accounts/{account_id}/bindings",
        headers=operator,
        json={"deviceId": device_id, "confirmationNote": "Owner reconfirmed this device."},
    )
    assert rebound.status_code == 201, rebound.text

    accounts = await client.get("/api/v1/accounts", headers=headers("viewer"))
    current = accounts.json()[0]
    suspended = await client.post(
        f"/api/v1/accounts/{account_id}:status",
        headers=operator,
        json={
            "status": "SUSPENDED",
            "reason": "Authorization health check requires manual review.",
            "expectedVersion": current["version"],
        },
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "SUSPENDED"
    assert suspended.json()["bindings"] == []

    rejected_binding = await client.post(
        f"/api/v1/accounts/{account_id}/bindings",
        headers=operator,
        json={"deviceId": device_id, "confirmationNote": "Must remain suspended."},
    )
    assert rejected_binding.status_code == 409


@pytest.mark.asyncio
async def test_one_bound_account_per_device_platform_and_history_preserved(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_device(client)
    operator = headers("device_operator")

    async def create_account(platform: str, subject: str, label: str) -> str:
        response = await client.post(
            "/api/v1/accounts",
            headers=operator,
            json={
                "platform": platform,
                "externalSubjectRef": subject,
                "displayLabel": label,
                "secretRef": f"vault://cloudctl/accounts/{subject}",
                "authorizationBasis": "Owner authorized managed publishing.",
            },
        )
        assert response.status_code == 201, response.text
        return str(response.json()["id"])

    xianyu_a = await create_account("xianyu", "xianyu-a", "闲鱼甲")
    xianyu_b = await create_account("xianyu", "xianyu-b", "闲鱼乙")
    xhs = await create_account("xiaohongshu", "xhs-a", "小红书甲")

    first = await client.post(
        f"/api/v1/accounts/{xianyu_a}/bindings",
        headers=operator,
        json={"deviceId": device_id, "confirmationNote": "Bind xianyu A."},
    )
    assert first.status_code == 201, first.text
    assert first.json()["bindingVersion"] == 1
    assert first.json()["platform"] == "xianyu"

    xhs_bind = await client.post(
        f"/api/v1/accounts/{xhs}/bindings",
        headers=operator,
        json={"deviceId": device_id, "confirmationNote": "Bind xiaohongshu."},
    )
    assert xhs_bind.status_code == 201, xhs_bind.text

    rebound = await client.post(
        f"/api/v1/accounts/{xianyu_b}/bindings",
        headers=operator,
        json={"deviceId": device_id, "confirmationNote": "Replace with xianyu B."},
    )
    assert rebound.status_code == 201, rebound.text
    assert rebound.json()["status"] == "BOUND"

    listed = await client.get("/api/v1/accounts", headers=headers("viewer"))
    assert listed.status_code == 200, listed.text
    by_id = {row["id"]: row for row in listed.json()}
    assert any(item["status"] == "UNBOUND" for item in by_id[xianyu_a]["bindings"])
    assert any(item["status"] == "BOUND" for item in by_id[xianyu_b]["bindings"])
    assert any(item["status"] == "BOUND" for item in by_id[xhs]["bindings"])
    assert all(item.get("historical") is True for item in by_id[xianyu_a]["bindings"])

    ownership = await client.get(
        f"/api/v1/accounts/{xianyu_a}/ownership", headers=headers("viewer")
    )
    assert ownership.status_code == 200, ownership.text
    assert ownership.json()["unbound"] is True
    assert ownership.json()["account"]["id"] == xianyu_a


@pytest.mark.asyncio
async def test_checksum_bound_media_upload_and_derivative_result(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    editor = headers("content_editor")
    content = b"authorized media payload"
    digest = hashlib.sha256(content).hexdigest()
    upload_response = await client.post(
        "/api/v1/media/uploads",
        headers=editor,
        json={
            "fileName": "payload.txt",
            "sha256": digest,
            "contentType": "text/plain",
            "sizeBytes": len(content),
            "metadata": {"source": "integration-test"},
        },
    )
    assert upload_response.status_code == 201, upload_response.text
    upload = upload_response.json()
    assert upload["uploadUrl"] == f"/api/v1/media/uploads/{upload['id']}/content"

    store = app.state.object_store
    assert isinstance(store, InMemoryObjectStore)
    store.put(upload["objectKey"], content, "text/plain")
    completed = await client.post(
        f"/api/v1/media/uploads/{upload['id']}:complete", headers=editor, json={}
    )
    assert completed.status_code == 200, completed.text
    source_asset = completed.json()
    assert source_asset["sha256"] == digest
    assert source_asset["size_bytes"] == len(content)

    replay = await client.post(
        f"/api/v1/media/uploads/{upload['id']}:complete", headers=editor, json={}
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == source_asset["id"]

    derivative_content = b"derived media payload"
    derivative_asset = await client.post(
        "/api/v1/media/assets:register",
        headers=editor,
        json={
            "sha256": hashlib.sha256(derivative_content).hexdigest(),
            "objectKey": "tenant/derived/payload.txt",
            "contentType": "text/plain",
            "sizeBytes": len(derivative_content),
            "sourceAssetId": source_asset["id"],
        },
    )
    assert derivative_asset.status_code == 201, derivative_asset.text
    requested = await client.post(
        f"/api/v1/media/{source_asset['id']}/derivatives",
        headers=editor,
        json={"profileId": "normalized-text-v1"},
    )
    assert requested.status_code == 202, requested.text
    result = await client.post(
        f"/api/v1/media/derivatives/{requested.json()['id']}:result",
        headers=headers("system_service", user=SERVICE),
        json={"status": "SUCCEEDED", "outputAssetId": derivative_asset.json()["id"]},
    )
    assert result.status_code == 200, result.text
    assert result.json()["state"] == "SUCCEEDED"

    bad_upload = await client.post(
        "/api/v1/media/uploads",
        headers=editor,
        json={
            "fileName": "bad.txt",
            "sha256": "f" * 64,
            "contentType": "text/plain",
            "sizeBytes": 3,
        },
    )
    store.put(bad_upload.json()["objectKey"], b"bad", "text/plain")
    rejected = await client.post(
        f"/api/v1/media/uploads/{bad_upload.json()['id']}:complete", headers=editor, json={}
    )
    assert rejected.status_code == 409


@pytest.mark.asyncio
async def test_content_revisions_groups_and_archive(api: tuple[httpx.AsyncClient, FastAPI]) -> None:
    client, _ = api
    editor = headers("content_editor")
    created = await client.post(
        "/api/v1/content",
        headers=editor,
        json={"title": "Launch content", "payload": {"caption": "version one"}},
    )
    assert created.status_code == 201, created.text
    content_id = str(created.json()["id"])
    assert created.json()["revision"]["revision_no"] == 1

    revised = await client.post(
        f"/api/v1/content/{content_id}/revisions",
        headers=editor,
        json={"payload": {"caption": "version two"}},
    )
    assert revised.status_code == 201, revised.text
    assert revised.json()["revision"]["revision_no"] == 2

    group_response = await client.post(
        "/api/v1/content-groups",
        headers=editor,
        json={"name": "September launch", "description": "Approved launch assets."},
    )
    assert group_response.status_code == 201, group_response.text
    group_id = str(group_response.json()["id"])
    membership = await client.post(
        f"/api/v1/content-groups/{group_id}/members",
        headers=editor,
        json={"contentId": content_id},
    )
    assert membership.status_code == 201, membership.text

    content_list = await client.get("/api/v1/content", headers=headers("viewer"))
    assert content_list.status_code == 200, content_list.text
    assert content_list.json()[0]["latestRevision"] == 2
    assert content_list.json()[0]["groupIds"] == [group_id]
    group_list = await client.get("/api/v1/content-groups", headers=headers("viewer"))
    assert group_list.json()[0]["contentIds"] == [content_id]

    removed = await client.delete(
        f"/api/v1/content-groups/{group_id}/members/{content_id}", headers=editor
    )
    assert removed.status_code == 204, removed.text
    archived = await client.post(
        f"/api/v1/content/{content_id}:archive",
        headers=editor,
        json={"reason": "Campaign completed."},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "ARCHIVED"

    rejected_revision = await client.post(
        f"/api/v1/content/{content_id}/revisions",
        headers=editor,
        json={"payload": {"caption": "must not be accepted"}},
    )
    assert rejected_revision.status_code == 409


@pytest.mark.asyncio
async def test_post_editor_creates_revisions_and_rejects_unknown_media(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    editor = headers("content_editor")
    group = await client.post(
        "/api/v1/content-groups",
        headers=editor,
        json={"name": "默认分组", "description": "帖子默认分组"},
    )
    assert group.status_code == 201, group.text
    group_id = str(group.json()["id"])

    created = await client.post(
        "/api/v1/content",
        headers=editor,
        json={
            "title": "九成新显示器",
            "groupId": group_id,
            "payload": {
                "kind": "post",
                "body": "自用闲置，功能正常，支持当面交易",
                "mediaAssetIds": [],
                "targetApp": "xiaohongshu",
                "draftState": "草稿",
            },
        },
    )
    assert created.status_code == 201, created.text
    content_id = str(created.json()["id"])
    assert created.json()["kind"] == "post"
    assert created.json()["groupIds"] == [group_id]
    assert created.json()["revision"]["payload"]["draftState"] == "草稿"

    fetched = await client.get(f"/api/v1/content/{content_id}", headers=headers("viewer"))
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["revision"]["payload"]["body"] == "自用闲置，功能正常，支持当面交易"

    revised = await client.post(
        f"/api/v1/content/{content_id}/revisions",
        headers=editor,
        json={
            "groupId": group_id,
            "payload": {
                "kind": "post",
                "body": "已清洁，包装齐全",
                "mediaAssetIds": [],
                "targetApp": "xiaohongshu",
                "draftState": "待复核",
            },
        },
    )
    assert revised.status_code == 201, revised.text
    assert revised.json()["revision"]["revision_no"] == 2
    listed = await client.get("/api/v1/content", headers=headers("viewer"), params={"kind": "post"})
    assert listed.status_code == 200
    assert listed.json()[0]["draftState"] == "待复核"
    assert listed.json()[0]["latestRevision"] == 2

    rejected = await client.post(
        "/api/v1/content",
        headers=editor,
        json={
            "title": "坏媒体引用",
            "payload": {
                "kind": "post",
                "body": "正文",
                "mediaAssetIds": ["00000000-0000-7000-8000-000000000999"],
                "draftState": "草稿",
            },
        },
    )
    assert rejected.status_code == 422
    forbidden = await client.post(
        "/api/v1/content",
        headers=headers("viewer"),
        json={
            "title": "无权限",
            "payload": {"kind": "post", "body": "正文", "draftState": "草稿"},
        },
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_saved_product_can_dispatch_text_publish_to_direct_device(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    operator = headers("security_admin")
    device = await client.post(
        "/api/v1/mobile/devices",
        headers=operator,
        json={
            "logicalName": "post-dispatch-phone",
            "androidVersion": "14",
            "companionVersion": "1.0.0",
            "labels": ["mobile-direct"],
        },
    )
    assert device.status_code == 201, device.text
    device_id = str(device.json()["id"])
    created = await client.post(
        "/api/v1/content",
        headers=operator,
        json={
            "title": "九成新显示器",
            "payload": {
                "kind": "product",
                "body": "自用闲置，功能正常，支持当面交易",
                "listingPrice": "128",
                "category": "数码",
                "stock": 1,
                "mediaAssetIds": [],
                "draftState": "待复核",
            },
        },
    )
    assert created.status_code == 201, created.text
    content_id = str(created.json()["id"])
    dispatched = await client.post(
        f"/api/v1/content/{content_id}:dispatch-xianyu",
        headers={**operator, "Idempotency-Key": "post-dispatch-1"},
        json={"deviceId": device_id},
    )
    assert dispatched.status_code == 201, dispatched.text
    payload = dispatched.json()
    assert payload["deviceId"] == device_id
    assert payload["tapsPublish"] is False
    assert payload["mobileTask"]["targetPackage"] == "com.taobao.idlefish"
    steps = {step["stepId"]: step for step in payload["mobileTask"]["steps"]}
    assert steps["fill-description"]["value"] == "自用闲置，功能正常，支持当面交易"
    assert steps["fill-price"]["value"] == "128"
    replay = await client.post(
        f"/api/v1/content/{content_id}:dispatch-xianyu",
        headers={**operator, "Idempotency-Key": "post-dispatch-1"},
        json={"deviceId": device_id},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["mobileTask"]["taskId"] == payload["mobileTask"]["taskId"]
    missing_price_content = await client.post(
        "/api/v1/content",
        headers=operator,
        json={
            "title": "未定价稿",
            "payload": {
                "kind": "post",
                "body": "小红书笔记草稿",
                "mediaAssetIds": [],
                "targetApp": "xiaohongshu",
                "draftState": "草稿",
            },
        },
    )
    assert missing_price_content.status_code == 201, missing_price_content.text
    missing_price = await client.post(
        f"/api/v1/content/{missing_price_content.json()['id']}:dispatch-xianyu",
        headers=operator,
        json={"deviceId": device_id},
    )
    assert missing_price.status_code == 422


@pytest.mark.asyncio
async def test_saved_product_can_dispatch_media_publish_to_direct_device(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    operator = headers("security_admin")
    device = await client.post(
        "/api/v1/mobile/devices",
        headers=operator,
        json={
            "logicalName": "media-dispatch-phone",
            "androidVersion": "14",
            "companionVersion": "1.0.0",
        },
    )
    assert device.status_code == 201, device.text
    asset = await client.post(
        "/api/v1/media/assets:register",
        headers=operator,
        json={
            "sha256": "e" * 64,
            "objectKey": "listing/dispatch-cover.jpg",
            "contentType": "image/jpeg",
            "sizeBytes": 10,
        },
    )
    assert asset.status_code == 201, asset.text
    asset_id = asset.json()["id"]
    created = await client.post(
        "/api/v1/content",
        headers=operator,
        json={
            "title": "带图显示器",
            "payload": {
                "kind": "product",
                "body": "带图商品描述",
                "listingPrice": "128",
                "category": "数码",
                "stock": 1,
                "mediaAssetIds": [asset_id],
                "draftState": "待复核",
            },
        },
    )
    assert created.status_code == 201, created.text
    dispatched = await client.post(
        f"/api/v1/content/{created.json()['id']}:dispatch-xianyu",
        headers={**operator, "Idempotency-Key": "media-post-dispatch-1"},
        json={"deviceId": device.json()["id"]},
    )
    assert dispatched.status_code == 201, dispatched.text
    task = dispatched.json()["mobileTask"]
    assert task["mediaDelivery"]["assetIds"] == [asset_id]
    assert any(step["stepId"] == "select-media-0" for step in task["steps"])


@pytest.mark.asyncio
async def test_product_catalog_creates_lists_and_rejects_duplicate_or_cross_tenant_media(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    editor = headers("content_editor")
    asset = await client.post(
        "/api/v1/media/assets:register",
        headers=editor,
        json={
            "sha256": "a" * 64,
            "objectKey": "tenant/products/cover.jpg",
            "contentType": "image/jpeg",
            "sizeBytes": 10,
        },
    )
    assert asset.status_code == 201, asset.text
    asset_id = asset.json()["id"]
    product = await client.post(
        "/api/v1/products",
        headers=editor,
        json={
            "spuCode": "SPU-001",
            "title": "Test product",
            "description": "Listing description",
            "category": "数码",
            "price": "99.00",
            "stock": 3,
            "mediaAssetIds": [asset_id, asset_id],
        },
    )
    assert product.status_code == 201, product.text
    assert product.json()["mediaAssetIds"] == [asset_id]
    detail_asset = await client.post(
        "/api/v1/media/assets:register",
        headers=editor,
        json={
            "sha256": "b" * 64,
            "objectKey": "tenant/products/detail.jpg",
            "contentType": "image/jpeg",
            "sizeBytes": 11,
        },
    )
    assert detail_asset.status_code == 201, detail_asset.text
    detail_asset_id = detail_asset.json()["id"]
    media_update = await client.put(
        f"/api/v1/products/{product.json()['id']}/media",
        headers=editor,
        json={
            "expectedRevision": 1,
            "items": [
                {"mediaAssetId": detail_asset_id, "sortOrder": 1, "role": "detail"},
                {"mediaAssetId": asset_id, "sortOrder": 0, "role": "cover"},
            ],
        },
    )
    assert media_update.status_code == 200, media_update.text
    assert media_update.json()["revision"] == 2
    assert media_update.json()["media"][0]["mediaAssetId"] == asset_id
    assert media_update.json()["media"][1]["role"] == "detail"
    bad_media_update = await client.put(
        f"/api/v1/products/{product.json()['id']}/media",
        headers=editor,
        json={"expectedRevision": 1, "items": []},
    )
    assert bad_media_update.status_code == 409
    listed = await client.get("/api/v1/products", headers=headers("viewer"))
    assert listed.status_code == 200
    assert listed.json()[0]["spuCode"] == "SPU-001"
    detail = await client.get(f"/api/v1/products/{product.json()['id']}", headers=headers("viewer"))
    assert detail.status_code == 200
    assert detail.json()["revision"] == 2
    missing = await client.get(
        "/api/v1/products/00000000-0000-0000-0000-000000000404",
        headers=headers("viewer"),
    )
    assert missing.status_code == 404
    updated = await client.put(
        f"/api/v1/products/{product.json()['id']}",
        headers=editor,
        json={
            "spuCode": "SPU-001",
            "title": "Updated product",
            "description": "Updated description",
            "category": "数码",
            "price": "109.00",
            "stock": 4,
            "mediaAssetIds": [],
            "expectedRevision": 2,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 3
    assert updated.json()["title"] == "Updated product"
    stale = await client.put(
        f"/api/v1/products/{product.json()['id']}",
        headers=editor,
        json={
            "spuCode": "SPU-001",
            "title": "Stale update",
            "category": "数码",
            "price": "109",
            "stock": 4,
            "expectedRevision": 2,
        },
    )
    assert stale.status_code == 409
    archived = await client.post(
        f"/api/v1/products/{product.json()['id']}:archive",
        headers=editor,
        json={"reason": "Product test completed."},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
    assert archived.json()["revision"] == 4
    archived_again = await client.post(
        f"/api/v1/products/{product.json()['id']}:archive",
        headers=editor,
        json={"reason": "Idempotent archive."},
    )
    assert archived_again.status_code == 200
    assert archived_again.json()["status"] == "ARCHIVED"
    assert archived_again.json()["mediaAssetIds"] == archived.json()["mediaAssetIds"]
    duplicate = await client.post(
        "/api/v1/products",
        headers=editor,
        json={
            "spuCode": "SPU-001",
            "title": "Duplicate",
            "category": "数码",
            "price": "1",
            "stock": 1,
        },
    )
    assert duplicate.status_code == 409
    foreign = await client.post(
        "/api/v1/products",
        headers=headers(
            "content_editor",
            tenant="00000000-0000-0000-0000-000000000999",
            user="00000000-0000-0000-0000-000000000998",
        ),
        json={
            "spuCode": "SPU-FOREIGN",
            "title": "Foreign",
            "category": "数码",
            "price": "1",
            "stock": 1,
            "mediaAssetIds": [asset_id],
        },
    )
    # K02 data-assets/v1: cross-tenant media reference is isolation (403),
    # not absence (404).
    assert foreign.status_code == 403
    assert foreign.json()["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_product_catalog_rejects_invalid_fields_and_write_without_permission(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    viewer = headers("viewer")
    forbidden = await client.post(
        "/api/v1/products",
        headers=viewer,
        json={
            "spuCode": "SPU-NO-WRITE",
            "title": "No write",
            "category": "数码",
            "price": "1",
            "stock": 1,
        },
    )
    assert forbidden.status_code == 403
    invalid = await client.post(
        "/api/v1/products",
        headers=headers("content_editor"),
        json={
            "spuCode": "SPU-BAD-PRICE",
            "title": "Bad price",
            "category": "数码",
            "price": "1.999",
            "stock": 1,
        },
    )
    assert invalid.status_code == 422


# ---------------------------------------------------------------------------
# K02 data-assets/v1 fixture scenarios (contracts/parallel/K02/fixtures/, frozen
# 20260916.1). One test per fixture plus the A03 edit-readback acceptance.
# ---------------------------------------------------------------------------


async def _upload_media_asset(
    client: httpx.AsyncClient,
    app: FastAPI,
    editor: dict[str, str],
    content: bytes,
    file_name: str,
) -> dict[str, object]:
    upload = await client.post(
        "/api/v1/media/uploads",
        headers=editor,
        json={
            "fileName": file_name,
            "sha256": hashlib.sha256(content).hexdigest(),
            "contentType": "text/plain",
            "sizeBytes": len(content),
        },
    )
    assert upload.status_code == 201, upload.text
    store = app.state.object_store
    assert isinstance(store, InMemoryObjectStore)
    store.put(upload.json()["objectKey"], content, "text/plain")
    completed = await client.post(
        f"/api/v1/media/uploads/{upload.json()['id']}:complete", headers=editor, json={}
    )
    assert completed.status_code == 200, completed.text
    return completed.json()


@pytest.mark.asyncio
async def test_k02_positive_product_price_boundary_media_reference_and_idempotency(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """Fixture k02-positive-product: price '12.80' decimal-string, media
    reference, Idempotency-Key replay -> 200 + Idempotency-Replayed: true."""
    client, app = api
    editor = headers("content_editor")
    content = b"k02 fixture product cover"
    asset = await _upload_media_asset(client, app, editor, content, "cover.txt")
    asset_id = str(asset["id"])

    # (tenant, sha256) dedup: re-initiating the same content short-circuits.
    dedup = await client.post(
        "/api/v1/media/uploads",
        headers=editor,
        json={
            "fileName": "cover-again.txt",
            "sha256": hashlib.sha256(content).hexdigest(),
            "contentType": "text/plain",
            "sizeBytes": len(content),
        },
    )
    assert dedup.status_code == 201, dedup.text
    assert dedup.json()["state"] == "COMPLETED"
    assert dedup.json()["asset"]["id"] == asset_id

    body = {
        "spuCode": "BOOK-0001",
        "title": "如果历史是一群喵4",
        "description": "个人闲置",
        "category": "图书",
        "price": "12.80",
        "stock": 1,
        "mediaAssetIds": [asset_id],
    }
    created = await client.post(
        "/api/v1/products",
        headers={**editor, "Idempotency-Key": "k02-fixture-pos-001"},
        json=body,
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["price"] == "12.80"
    assert payload["revision"] == 1
    assert payload["mediaAssetIds"] == [asset_id]
    assert payload["media"][0]["mediaAssetId"] == asset_id
    assert payload["media"][0]["role"] == "cover"
    assert created.headers["Idempotency-Replayed"] == "false"
    product_id = payload["id"]

    # Replay with the same Idempotency-Key: 200 + Idempotency-Replayed: true.
    replay = await client.post(
        "/api/v1/products",
        headers={**editor, "Idempotency-Key": "k02-fixture-pos-001"},
        json=body,
    )
    assert replay.status_code == 200, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["id"] == product_id
    assert replay.json()["price"] == "12.80"

    # Same key with a different body must not silently create.
    mutated = dict(body)
    mutated["price"] = "13.00"
    conflict = await client.post(
        "/api/v1/products",
        headers={**editor, "Idempotency-Key": "k02-fixture-pos-001"},
        json=mutated,
    )
    assert conflict.status_code == 409

    # Without the header a duplicate SPU stays a plain conflict.
    duplicate = await client.post("/api/v1/products", headers=editor, json=body)
    assert duplicate.status_code == 409

    # Price '0' is the other legal boundary (D1: 0 is valid, null is not).
    zero = await client.post(
        "/api/v1/products",
        headers=editor,
        json={
            "spuCode": "BOOK-0001-FREE",
            "title": "零元边界",
            "category": "图书",
            "price": "0",
            "stock": 1,
        },
    )
    assert zero.status_code == 201, zero.text
    assert zero.json()["price"] == "0"


@pytest.mark.asyncio
async def test_k02_negative_price_null_and_malformed_values(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """Fixture k02-negative-price-null: null price -> 422 VALIDATION_ERROR with
    a `price` field; '12.800'/'-1'/'abc' are equally invalid (D1)."""
    client, _ = api
    editor = headers("content_editor")

    null_price = await client.post(
        "/api/v1/products",
        headers=editor,
        json={
            "spuCode": "BOOK-0002",
            "title": "坏例",
            "description": "x",
            "category": "图书",
            "price": None,
        },
    )
    assert null_price.status_code == 422, null_price.text
    assert null_price.headers["content-type"].startswith("application/problem+json")
    problem = null_price.json()
    assert problem["code"] == "VALIDATION_ERROR"
    assert "price" in problem["fields"]

    for bad_price in ("12.800", "-1", "abc"):
        rejected = await client.post(
            "/api/v1/products",
            headers=editor,
            json={
                "spuCode": f"BOOK-0002-{bad_price}",
                "title": "坏例",
                "description": "x",
                "category": "图书",
                "price": bad_price,
            },
        )
        assert rejected.status_code == 422, bad_price
        assert rejected.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_k02_negative_media_reference_404_and_cross_tenant_403(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """Fixture k02-negative-media-404: unknown media id -> 404 NOT_FOUND;
    cross-tenant media id -> 403 FORBIDDEN (isolation, not absence)."""
    client, app = api
    editor = headers("content_editor")
    foreign_editor = headers(
        "content_editor",
        tenant="00000000-0000-7000-8000-000000000999",
        user="00000000-0000-7000-8000-000000000998",
    )

    missing = await client.post(
        "/api/v1/products",
        headers=editor,
        json={
            "spuCode": "BOOK-0003",
            "title": "坏例",
            "description": "x",
            "category": "图书",
            "price": "8.88",
            "stock": 1,
            "mediaAssetIds": ["00000000-0000-7000-8000-00000000dead"],
        },
    )
    assert missing.status_code == 404, missing.text
    assert missing.json()["code"] == "NOT_FOUND"

    # The same rule applies to product updates and media reordering.
    asset = await _upload_media_asset(client, app, editor, b"owned asset", "own.txt")
    owned_id = str(asset["id"])
    created = await client.post(
        "/api/v1/products",
        headers=editor,
        json={
            "spuCode": "BOOK-0003-OK",
            "title": "好例",
            "category": "图书",
            "price": "8.88",
            "stock": 1,
            "mediaAssetIds": [owned_id],
        },
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    stale_update = await client.put(
        f"/api/v1/products/{product_id}",
        headers=editor,
        json={
            "spuCode": "BOOK-0003-OK",
            "title": "坏引用更新",
            "category": "图书",
            "price": "8.88",
            "stock": 1,
            "mediaAssetIds": ["00000000-0000-7000-8000-00000000dead"],
            "expectedRevision": 1,
        },
    )
    assert stale_update.status_code == 404
    stale_media = await client.put(
        f"/api/v1/products/{product_id}/media",
        headers=editor,
        json={
            "expectedRevision": 1,
            "items": [
                {
                    "mediaAssetId": "00000000-0000-7000-8000-00000000dead",
                    "sortOrder": 0,
                    "role": "cover",
                }
            ],
        },
    )
    assert stale_media.status_code == 404

    # Cross-tenant reference: the asset exists, but not for this tenant.
    cross = await client.post(
        "/api/v1/products",
        headers=foreign_editor,
        json={
            "spuCode": "BOOK-0003-CROSS",
            "title": "跨租户引用",
            "category": "图书",
            "price": "8.88",
            "stock": 1,
            "mediaAssetIds": [owned_id],
        },
    )
    assert cross.status_code == 403, cross.text
    assert cross.json()["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_k02_positive_derivative_roundtrip(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """Fixture k02-positive-derivative: 202 PENDING -> :result SUCCEEDED with
    outputAssetId -> references.sources traces the derivative; errorCode
    without outputAssetId -> FAILED."""
    client, _ = api
    editor = headers("content_editor")
    service = headers("system_service", user=SERVICE)

    source = await client.post(
        "/api/v1/media/assets:register",
        headers=editor,
        json={
            "sha256": "1" * 64,
            "objectKey": "k02/source.png",
            "contentType": "image/png",
            "sizeBytes": 16,
        },
    )
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]

    requested = await client.post(
        f"/api/v1/media/{source_id}/derivatives",
        headers=editor,
        json={"profileId": "watermark-v1"},
    )
    assert requested.status_code == 202, requested.text
    assert requested.json()["state"] == "PENDING"
    derivative_id = requested.json()["id"]

    derivative_content = b"k02 watermarked output"
    output = await client.post(
        "/api/v1/media/assets:register",
        headers=editor,
        json={
            "sha256": hashlib.sha256(derivative_content).hexdigest(),
            "objectKey": "k02/derived.png",
            "contentType": "image/png",
            "sizeBytes": len(derivative_content),
            "sourceAssetId": source_id,
        },
    )
    assert output.status_code == 201, output.text
    output_id = output.json()["id"]

    recorded = await client.post(
        f"/api/v1/media/derivatives/{derivative_id}:result",
        headers=service,
        json={"status": "SUCCEEDED", "outputAssetId": output_id},
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["state"] == "SUCCEEDED"

    references = await client.get(
        f"/api/v1/media/assets/{output_id}/references", headers=headers("viewer")
    )
    assert references.status_code == 200, references.text
    sources = references.json()["sources"]
    assert [item["derivativeId"] for item in sources] == [derivative_id]
    assert sources[0]["sourceAssetId"] == source_id
    assert sources[0]["state"] == "SUCCEEDED"

    # A result carrying errorCode instead of outputAssetId fails the job.
    failed_request = await client.post(
        f"/api/v1/media/{source_id}/derivatives",
        headers=editor,
        json={"profileId": "watermark-v1"},
    )
    assert failed_request.status_code == 202
    failed_id = failed_request.json()["id"]
    failed = await client.post(
        f"/api/v1/media/derivatives/{failed_id}:result",
        headers=service,
        json={"status": "FAILED", "errorCode": "RENDER_TIMEOUT"},
    )
    assert failed.status_code == 200, failed.text
    assert failed.json()["state"] == "FAILED"
    assert failed.json()["errorCode"] == "RENDER_TIMEOUT"


@pytest.mark.asyncio
async def test_k02_product_edit_readback_consistency(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """A03 acceptance: after editing a product, GET must read back the same
    data, including media ordering with role/sortOrder."""
    client, app = api
    editor = headers("content_editor")
    first = await _upload_media_asset(client, app, editor, b"readback-a", "a.txt")
    second = await _upload_media_asset(client, app, editor, b"readback-b", "b.txt")
    first_id, second_id = str(first["id"]), str(second["id"])

    created = await client.post(
        "/api/v1/products",
        headers=editor,
        json={
            "spuCode": "BOOK-RB-1",
            "title": "回读基线",
            "category": "图书",
            "price": "15.00",
            "stock": 2,
            "mediaAssetIds": [first_id, second_id],
        },
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    assert created.json()["media"] == [
        {"mediaAssetId": first_id, "sortOrder": 0, "role": "cover"},
        {"mediaAssetId": second_id, "sortOrder": 1, "role": "detail"},
    ]

    updated = await client.put(
        f"/api/v1/products/{product_id}",
        headers=editor,
        json={
            "spuCode": "BOOK-RB-1",
            "title": "回读更新",
            "description": "改价并反转媒体顺序",
            "category": "图书",
            "price": "16.50",
            "stock": 1,
            "mediaAssetIds": [second_id, first_id],
            "expectedRevision": 1,
        },
    )
    assert updated.status_code == 200, updated.text

    readback = await client.get(f"/api/v1/products/{product_id}", headers=headers("viewer"))
    assert readback.status_code == 200, readback.text
    detail = readback.json()
    assert detail["title"] == "回读更新"
    assert detail["description"] == "改价并反转媒体顺序"
    assert detail["price"] == "16.50"
    assert detail["stock"] == 1
    assert detail["revision"] == 2
    assert detail["mediaAssetIds"] == [second_id, first_id]
    assert detail["media"] == [
        {"mediaAssetId": second_id, "sortOrder": 0, "role": "cover"},
        {"mediaAssetId": first_id, "sortOrder": 1, "role": "detail"},
    ]
    assert updated.json()["media"] == detail["media"]

    reordered = await client.put(
        f"/api/v1/products/{product_id}/media",
        headers=editor,
        json={
            "expectedRevision": 2,
            "items": [
                {"mediaAssetId": first_id, "sortOrder": 1, "role": "detail"},
                {"mediaAssetId": second_id, "sortOrder": 0, "role": "cover"},
            ],
        },
    )
    assert reordered.status_code == 200, reordered.text
    after_media_update = await client.get(
        f"/api/v1/products/{product_id}", headers=headers("viewer")
    )
    assert after_media_update.json()["revision"] == 3
    assert after_media_update.json()["media"] == [
        {"mediaAssetId": second_id, "sortOrder": 0, "role": "cover"},
        {"mediaAssetId": first_id, "sortOrder": 1, "role": "detail"},
    ]

    listed = await client.get("/api/v1/products", headers=headers("viewer"))
    entry = next(item for item in listed.json() if item["id"] == product_id)
    assert entry["media"] == after_media_update.json()["media"]

    for asset_id in (first_id, second_id):
        refs = await client.get(
            f"/api/v1/media/assets/{asset_id}/references", headers=headers("viewer")
        )
        assert refs.status_code == 200
        assert refs.json()["productIds"] == [product_id]
