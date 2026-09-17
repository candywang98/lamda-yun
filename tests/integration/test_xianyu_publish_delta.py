"""P10 xianyu publish delta: completion boundaries, field-level validation,
publish-target persistence and the serial single-item queue.

Acceptance focus (fleet-first-20260916.1 P10):
- 新旧草稿混合/价格未验证/媒体未齐全 → 不能记完全自动成功（完成度明确降级）。
- 授权单件发布：手机侧目标与 Web/服务端记录同一目标同一结果。
- 批量部分成功：已成功项不重做（队列推进只取未确认失败/未开始项）。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from alembic import command
from cloudctl_api import create_app
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from test_control_api_migrations import migration_config, table_columns, tables

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


async def setup_device_and_account(client: httpx.AsyncClient) -> tuple[str, str]:
    device = await client.post(
        "/api/v1/mobile/devices",
        headers=identity(),
        json={"logicalName": "p10-phone", "androidVersion": "14", "companionVersion": "1.0.0"},
    )
    assert device.status_code == 201, device.text
    account = await client.post(
        "/api/v1/accounts",
        headers=identity(),
        json={
            "platform": "xianyu",
            "externalSubjectRef": "p10-xy-owner",
            "displayLabel": "p10-xy-owner",
            "secretRef": "vault://cloudctl/accounts/p10-xy-owner",
            "authorizationBasis": "Owner authorized the test account.",
        },
    )
    assert account.status_code == 201, account.text
    device_id = str(device.json()["id"])
    account_id = str(account.json()["id"])
    binding = await client.post(
        f"/api/v1/accounts/{account_id}/bindings",
        headers=identity(),
        json={"deviceId": device_id, "confirmationNote": "Owner confirmed."},
    )
    assert binding.status_code == 201, binding.text
    return device_id, account_id


def queue_payload(
    device_id: str,
    account_id: str,
    items: list[dict],
    *,
    queue_id: str | None = None,
) -> dict:
    body: dict = {"deviceId": device_id, "accountId": account_id, "items": items}
    if queue_id:
        body["queueId"] = queue_id
    return body


def item(
    description: str = "九成新显示器，自用一年",
    price: str = "199.00",
    boundary: str = "FULL_AUTO",
) -> dict:
    return {"description": description, "price": price, "completionBoundary": boundary}


FULL_MACHINE_EVIDENCE = {
    "descriptionProof": True,
    "priceEnteredByMachine": True,
    "priceHumanConfirmed": False,
    "commitClickedByMachine": True,
    "commitHumanConfirmed": False,
    "successObserved": True,
    "mediaComplete": True,
    "requiredFieldsComplete": True,
}

HUMAN_PRICE_HUMAN_COMMIT_EVIDENCE = {
    "descriptionProof": True,
    "priceEnteredByMachine": False,
    "priceHumanConfirmed": True,
    "commitClickedByMachine": False,
    "commitHumanConfirmed": True,
    "successObserved": True,
    "mediaComplete": True,
    "requiredFieldsComplete": True,
}


# ---------------------------------------------------------------------------
# 1. 字段级校验：field/loc 结构 + 未知字段拒绝（不静默丢弃）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_field_level_validation_carries_loc_and_rejects_unknown_fields(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id, account_id = await setup_device_and_account(client)
    response = await client.post(
        "/api/v1/xianyu/publish/queues",
        headers=identity(),
        json=queue_payload(
            device_id,
            account_id,
            [
                {
                    "description": "x",
                    "price": "not-a-price",
                    "mediaAssetIds": ["m1", "m1"],
                    "completionBoundary": "FULLY_AUTOMATIC",
                    "draftMode": "legacy",
                }
            ],
            queue_id="p10-invalid",
        ),
    )
    assert response.status_code == 422, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "PUBLISH_FIELD_VALIDATION"
    issues = {
        (error["field"], tuple(error["loc"]), error["code"]) for error in body["errors"]
    }
    # 未知字段拒绝（item 内），带精确 loc。
    assert ("items.0.draftMode", ("items", 0, "draftMode"), "UNKNOWN_FIELD") in issues
    assert ("items.0.price", ("items", 0, "price"), "FIELD_PATTERN") in issues
    assert (
        "items.0.completionBoundary",
        ("items", 0, "completionBoundary"),
        "FIELD_ENUM",
    ) in issues
    assert ("items.0.mediaAssetIds", ("items", 0, "mediaAssetIds"), "FIELD_DUPLICATE") in issues
    assert ("items.0.deliveryId", ("items", 0, "deliveryId"), "FIELD_REQUIRED_DEPENDENT") in issues

    # 顶层未知字段同样拒绝。
    response = await client.post(
        "/api/v1/xianyu/publish/queues",
        headers=identity(),
        json={
            "deviceId": device_id,
            "accountId": account_id,
            "items": [item()],
            "typoField": 1,
        },
    )
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert [e["code"] for e in errors] == ["UNKNOWN_FIELD"]
    assert errors[0]["loc"] == ["typoField"]
    assert errors[0]["field"] == "typoField"


@pytest.mark.asyncio
async def test_confirm_request_rejects_unknown_evidence_flags(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id, account_id = await setup_device_and_account(client)
    created = await client.post(
        "/api/v1/xianyu/publish/queues",
        headers=identity(),
        json=queue_payload(device_id, account_id, [item()], queue_id="p10-ev"),
    )
    assert created.status_code == 201, created.text
    target_id = created.json()["targets"][0]["targetId"]
    confirm = await client.post(
        f"/api/v1/xianyu/publish/queues/p10-ev/targets/{target_id}/confirm",
        headers=identity(),
        json={"decision": "SUCCEEDED", "evidence": {"mediaComplete": True, "vibes": True}},
    )
    assert confirm.status_code == 422, confirm.text
    issues = {(e["field"], tuple(e["loc"]), e["code"]) for e in confirm.json()["errors"]}
    assert ("evidence.vibes", ("evidence", "vibes"), "UNKNOWN_FIELD") in issues


# ---------------------------------------------------------------------------
# 2. 四种完成边界的服务端判定：低完成度不记全自动
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_auto_success_recorded_only_with_complete_machine_evidence(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id, account_id = await setup_device_and_account(client)
    created = await client.post(
        "/api/v1/xianyu/publish/queues",
        headers=identity(),
        json=queue_payload(device_id, account_id, [item(boundary="FULL_AUTO")], queue_id="p10-fa"),
    )
    assert created.status_code == 201, created.text
    target = created.json()["targets"][0]
    dispatch = await client.post(
        f"/api/v1/xianyu/publish/queues/p10-fa/targets/{target['targetId']}/dispatch",
        headers=identity(),
    )
    assert dispatch.status_code == 200, dispatch.text
    confirm = await client.post(
        f"/api/v1/xianyu/publish/queues/p10-fa/targets/{target['targetId']}/confirm",
        headers=identity(),
        json={
            "decision": "SUCCEEDED",
            "platformItemId": "xy-item-p10-fa",
            "evidence": FULL_MACHINE_EVIDENCE,
        },
    )
    assert confirm.status_code == 200, confirm.text
    view = confirm.json()
    assert view["state"] == "SUCCEEDED_CONFIRMED"
    assert view["recordedBoundary"] == "FULL_AUTO"
    assert view["boundaryDowngraded"] is False
    assert view["externalItemId"] == "xy-item-p10-fa"


@pytest.mark.asyncio
async def test_human_acts_downgrade_a_full_auto_claim(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id, account_id = await setup_device_and_account(client)
    created = await client.post(
        "/api/v1/xianyu/publish/queues",
        headers=identity(),
        json=queue_payload(device_id, account_id, [item(boundary="FULL_AUTO")], queue_id="p10-dg"),
    )
    target = created.json()["targets"][0]
    await client.post(
        f"/api/v1/xianyu/publish/queues/p10-dg/targets/{target['targetId']}/dispatch",
        headers=identity(),
    )
    # 现生产行为证据：人工填价 + 人工点击 → 记录边界必须是双人工，绝不记全自动。
    confirm = await client.post(
        f"/api/v1/xianyu/publish/queues/p10-dg/targets/{target['targetId']}/confirm",
        headers=identity(),
        json={
            "decision": "SUCCEEDED",
            "platformItemId": "xy-item-p10-dg",
            "evidence": HUMAN_PRICE_HUMAN_COMMIT_EVIDENCE,
        },
    )
    assert confirm.status_code == 200, confirm.text
    view = confirm.json()
    assert view["recordedBoundary"] == "HUMAN_PRICE_HUMAN_COMMIT"
    assert view["boundaryDowngraded"] is True
    assert view["claimedBoundary"] == "FULL_AUTO"
    assert view["judgment"]["evidenceBoundary"] == "HUMAN_PRICE_HUMAN_COMMIT"


@pytest.mark.asyncio
async def test_incomplete_media_or_unverified_price_cannot_confirm_success(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id, account_id = await setup_device_and_account(client)

    async def confirm_with(evidence: dict, queue_id: str) -> httpx.Response:
        created = await client.post(
            "/api/v1/xianyu/publish/queues",
            headers=identity(),
            json=queue_payload(
                device_id, account_id, [item(boundary="FULL_AUTO")], queue_id=queue_id
            ),
        )
        target = created.json()["targets"][0]
        await client.post(
            f"/api/v1/xianyu/publish/queues/{queue_id}/targets/{target['targetId']}/dispatch",
            headers=identity(),
        )
        return await client.post(
            f"/api/v1/xianyu/publish/queues/{queue_id}/targets/{target['targetId']}/confirm",
            headers=identity(),
            json={
                "decision": "SUCCEEDED",
                "platformItemId": f"xy-{queue_id}",
                "evidence": evidence,
            },
        )

    # 媒体未齐全（新旧草稿混合后只回传部分媒体）→ 拒绝记成功。
    media_incomplete = {**FULL_MACHINE_EVIDENCE, "mediaComplete": False}
    refused = await confirm_with(media_incomplete, "p10-miss-media")
    assert refused.status_code == 422, refused.text
    assert "mediaComplete" in refused.json()["fields"]

    # 价格未验证（机器没证明，人工也没确认）→ 拒绝记成功（完成度降级后判据仍缺）。
    price_unverified = {
        **FULL_MACHINE_EVIDENCE,
        "priceEnteredByMachine": False,
        "priceHumanConfirmed": False,
    }
    refused = await confirm_with(price_unverified, "p10-miss-price")
    assert refused.status_code == 422, refused.text
    assert "priceHumanConfirmed" in refused.json()["fields"]

    # 拒绝后目标保持未确认失败前的状态（IN_FLIGHT），队列不前进。
    queue = await client.get("/api/v1/xianyu/publish/queues/p10-miss-media", headers=identity())
    assert queue.json()["targets"][0]["state"] == "IN_FLIGHT"
    assert queue.json()["serialAdvanceBlocked"] is True


@pytest.mark.asyncio
async def test_success_requires_platform_item_id(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id, account_id = await setup_device_and_account(client)
    created = await client.post(
        "/api/v1/xianyu/publish/queues",
        headers=identity(),
        json=queue_payload(device_id, account_id, [item()], queue_id="p10-pid"),
    )
    target = created.json()["targets"][0]
    await client.post(
        f"/api/v1/xianyu/publish/queues/p10-pid/targets/{target['targetId']}/dispatch",
        headers=identity(),
    )
    confirm = await client.post(
        f"/api/v1/xianyu/publish/queues/p10-pid/targets/{target['targetId']}/confirm",
        headers=identity(),
        json={"decision": "SUCCEEDED", "evidence": FULL_MACHINE_EVIDENCE},
    )
    assert confirm.status_code == 422
    assert "platformItemId" in confirm.json()["fields"]


# ---------------------------------------------------------------------------
# 3. 授权单件发布：手机侧目标与 Web/服务端记录同一目标同一结果
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dual_side_consistency_single_authorized_publish(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id, account_id = await setup_device_and_account(client)
    created = await client.post(
        "/api/v1/xianyu/publish/queues",
        headers=identity(),
        json=queue_payload(
            device_id,
            account_id,
            [item(boundary="AUTO_FILL_HUMAN_PRICE")],
            queue_id="p10-dual",
        ),
    )
    assert created.status_code == 201, created.text
    target = created.json()["targets"][0]
    assert target["claimedBoundary"] == "AUTO_FILL_HUMAN_PRICE"

    dispatch = await client.post(
        f"/api/v1/xianyu/publish/queues/p10-dual/targets/{target['targetId']}/dispatch",
        headers=identity(),
    )
    assert dispatch.status_code == 200, dispatch.text
    task_id = dispatch.json()["taskId"]
    assert task_id in dispatch.json()["taskIds"]

    # 手机侧（任务视角）：冻结的任务快照携带同一目标身份 + 声称边界。
    task_view = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert task_view.status_code == 200, task_view.text
    payload = task_view.json()["commandPayload"]
    assert payload["publishTargetId"] == target["targetId"]
    assert payload["completionBoundary"] == "AUTO_FILL_HUMAN_PRICE"
    assert task_view.json()["batchId"] == "p10-dual"

    confirm = await client.post(
        f"/api/v1/xianyu/publish/queues/p10-dual/targets/{target['targetId']}/confirm",
        headers=identity(),
        json={
            "decision": "SUCCEEDED",
            "platformItemId": "xy-item-p10-dual",
            "evidence": HUMAN_PRICE_HUMAN_COMMIT_EVIDENCE,
        },
    )
    assert confirm.status_code == 200, confirm.text

    # Web/服务端（队列视角）与手机侧（任务视角）：同一目标、同一结果、同一记录边界。
    queue = await client.get("/api/v1/xianyu/publish/queues/p10-dual", headers=identity())
    target_view = queue.json()["targets"][0]
    assert target_view["state"] == "SUCCEEDED_CONFIRMED"
    assert target_view["externalItemId"] == "xy-item-p10-dual"
    assert target_view["recordedBoundary"] == "HUMAN_PRICE_HUMAN_COMMIT"
    assert target_view["boundaryDowngraded"] is True

    task_view = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    result = task_view.json()["result"]
    assert result["publishTargetId"] == target["targetId"]
    assert result["completionBoundary"] == "HUMAN_PRICE_HUMAN_COMMIT"
    assert result["completionBoundaryClaimed"] == "AUTO_FILL_HUMAN_PRICE"
    assert result["completionBoundaryDowngraded"] is True
    assert result["platformItemId"] == "xy-item-p10-dual"
    assert task_view.json()["state"] == "SUCCEEDED"


# ---------------------------------------------------------------------------
# 4. 批量部分成功：已成功项不重做；队列推进只取未确认失败/未开始项
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_serial_advance_and_partial_success_batch(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id, account_id = await setup_device_and_account(client)
    created = await client.post(
        "/api/v1/xianyu/publish/queues",
        headers=identity(),
        json=queue_payload(
            device_id,
            account_id,
            [item(description=f"批量商品-{i}", boundary="FULL_AUTO") for i in (1, 2, 3)],
            queue_id="p10-batch",
        ),
    )
    targets = created.json()["targets"]
    assert [t["position"] for t in targets] == [0, 1, 2]

    base = "/api/v1/xianyu/publish/queues/p10-batch"

    # t1 发放后：单件串行——没有确认前 next 拿不到任何目标。
    first = (await client.post(f"{base}/next", headers=identity())).json()
    assert first["targetId"] == targets[0]["targetId"]
    dispatch1 = await client.post(
        f"{base}/targets/{first['targetId']}/dispatch", headers=identity()
    )
    assert dispatch1.status_code == 200
    blocked = await client.post(f"{base}/next", headers=identity())
    assert blocked.status_code == 204

    # t1 确认成功 → 队列前进到 t2。
    confirmed1 = await client.post(
        f"{base}/targets/{first['targetId']}/confirm",
        headers=identity(),
        json={
            "decision": "SUCCEEDED",
            "platformItemId": "xy-batch-1",
            "evidence": FULL_MACHINE_EVIDENCE,
        },
    )
    assert confirmed1.status_code == 200
    second = (await client.post(f"{base}/next", headers=identity())).json()
    assert second["targetId"] == targets[1]["targetId"]

    # 已成功项不重做：t1 不能再发放。
    redispatch = await client.post(
        f"{base}/targets/{targets[0]['targetId']}/dispatch", headers=identity()
    )
    assert redispatch.status_code == 409

    # t2 执行失败（未确认）→ 队列只取未确认失败/未开始项：t2 优先重发。
    dispatch2 = await client.post(
        f"{base}/targets/{second['targetId']}/dispatch", headers=identity()
    )
    assert dispatch2.status_code == 200
    failure = await client.post(
        f"{base}/targets/{second['targetId']}/report-failure",
        headers=identity(),
        json={"errorCode": "STEP_TIMEOUT", "detail": "price sheet did not settle"},
    )
    assert failure.status_code == 200
    assert failure.json()["state"] == "FAILED_UNCONFIRMED"
    retry_view = (await client.post(f"{base}/next", headers=identity())).json()
    assert retry_view["targetId"] == targets[1]["targetId"]

    # 重发铸造新任务，目标身份不变（任务身份与发布目标分离）。
    dispatch2b = await client.post(
        f"{base}/targets/{second['targetId']}/dispatch", headers=identity()
    )
    assert dispatch2b.status_code == 200
    assert dispatch2b.json()["taskId"] != dispatch2.json()["taskId"]
    assert set(dispatch2b.json()["taskIds"]) == {
        dispatch2.json()["taskId"],
        dispatch2b.json()["taskId"],
    }

    # t2 重试后确认失败（终态）→ 队列前进到 t3；t1/t2 都不再出现。
    confirmed2 = await client.post(
        f"{base}/targets/{second['targetId']}/confirm",
        headers=identity(),
        json={
            "decision": "FAILED",
            "operatorNote": "seller decided to drop this listing",
            "evidence": HUMAN_PRICE_HUMAN_COMMIT_EVIDENCE,
        },
    )
    assert confirmed2.status_code == 200
    assert confirmed2.json()["state"] == "FAILED_CONFIRMED"
    third = (await client.post(f"{base}/next", headers=identity())).json()
    assert third["targetId"] == targets[2]["targetId"]

    dispatch3 = await client.post(
        f"{base}/targets/{third['targetId']}/dispatch", headers=identity()
    )
    assert dispatch3.status_code == 200
    await client.post(
        f"{base}/targets/{third['targetId']}/confirm",
        headers=identity(),
        json={
            "decision": "SUCCEEDED",
            "platformItemId": "xy-batch-3",
            "evidence": FULL_MACHINE_EVIDENCE,
        },
    )
    exhausted = await client.post(f"{base}/next", headers=identity())
    assert exhausted.status_code == 204

    queue = (await client.get(base, headers=identity())).json()
    assert [t["state"] for t in queue["targets"]] == [
        "SUCCEEDED_CONFIRMED",
        "FAILED_CONFIRMED",
        "SUCCEEDED_CONFIRMED",
    ]


# ---------------------------------------------------------------------------
# 5. 队列幂等重放与迁移升降级
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_replay_with_same_items_is_idempotent(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id, account_id = await setup_device_and_account(client)
    body = queue_payload(device_id, account_id, [item()], queue_id="p10-replay")
    first = await client.post("/api/v1/xianyu/publish/queues", headers=identity(), json=body)
    assert first.status_code == 201
    assert first.json()["replayed"] is False
    replay = await client.post("/api/v1/xianyu/publish/queues", headers=identity(), json=body)
    assert replay.status_code == 201
    assert replay.json()["replayed"] is True
    assert (
        replay.json()["targets"][0]["targetId"] == first.json()["targets"][0]["targetId"]
    )
    diverged = await client.post(
        "/api/v1/xianyu/publish/queues",
        headers=identity(),
        json=queue_payload(device_id, account_id, [item(price="1.00")], queue_id="p10-replay"),
    )
    assert diverged.status_code == 409


def test_xianyu_publish_target_migration_updown(tmp_path) -> None:
    import sqlite3

    database_path = tmp_path / "p10-migration.db"
    config = migration_config(database_path)
    command.upgrade(config, "20260917_0027")
    with sqlite3.connect(database_path) as connection:
        assert "xianyu_publish_target" in tables(connection)
        columns = table_columns(connection, "xianyu_publish_target")
    assert {
        "id",
        "tenant_id",
        "queue_id",
        "device_id",
        "account_id",
        "position",
        "item",
        "claimed_boundary",
        "state",
        "task_ids",
        "external_item_id",
        "recorded_boundary",
        "boundary_downgraded",
        "judgment",
        "result",
        "requested_by",
        "confirmed_at",
        "created_at",
    } <= columns
    command.downgrade(config, "20260917_0026")
    with sqlite3.connect(database_path) as connection:
        assert "xianyu_publish_target" not in tables(connection)
