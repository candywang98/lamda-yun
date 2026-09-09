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
    for params in ({"page": 0}, {"pageSize": 101}, {"tag": " "}):
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
    assert upload["uploadUrl"].startswith("memory://uploads/")

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
    assert payload["mobileTask"]["steps"][4]["value"] == "自用闲置，功能正常，支持当面交易"
    assert payload["mobileTask"]["steps"][5]["value"] == "128"
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
    assert foreign.status_code == 422


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
