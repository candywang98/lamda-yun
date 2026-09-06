from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.settings import Settings
from pydantic import SecretStr

TENANT = "00000000-0000-7000-8000-000000005111"
USER = "00000000-0000-7000-8000-000000005222"
SERVICE = "00000000-0000-7000-8000-000000005333"


def headers(role: str, *, user: str = USER, key: str | None = None) -> dict[str, str]:
    result = {
        "X-Tenant-Id": TENANT,
        "X-User-Id": user,
        "X-Roles": role,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }
    if key is not None:
        result["Idempotency-Key"] = key
    return result


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        Settings(
            env="test",
            repository_mode="memory",
            dev_auth_bypass=True,
            operation_executor_urls={
                "accounts.authorization.health_check": "https://executor.test/account-health",
                "devices.capabilities.refresh": "https://executor.test/device-capabilities",
                "groups.membership.reindex": "https://executor.test/group-reindex",
                "media.derivative.generate": "https://executor.test/media-derivative",
                "task_runs.evidence.export": "https://executor.test/evidence-export",
                "watermarks.preview.render": "https://executor.test/watermark-preview",
            },
            operation_executor_bearer_token=SecretStr("operation-test-token"),
        )
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
            yield value


MAPPED_CASES: tuple[tuple[str, str, dict[str, Any]], ...] = (
    (
        "system-home-02",
        "devices.capabilities.refresh",
        {
            "healthScope": "全部授权设备",
            "clientVersion": "全部版本",
            "groupNumber": "全部组",
            "includeOffline": True,
        },
    ),
    (
        "system-home-03",
        "accounts.authorization.health_check",
        {
            "licenseKey": "",
            "licenseAction": "激活",
            "deviceQuota": "4 台",
            "confirmOwner": True,
        },
    ),
    (
        "task-queue-01",
        "task_runs.evidence.export",
        {
            "taskKeyword": "",
            "runState": "全部状态",
            "executionApp": "全部应用",
            "scheduledAfter": "2026-09-01T09:00",
        },
    ),
    (
        "product-editor-03",
        "watermarks.preview.render",
        {
            "watermarkTemplate": "品牌角标",
            "watermarkPosition": "右下角",
            "watermarkOpacity": 72,
            "previewOnly": True,
        },
    ),
    (
        "product-management-03",
        "groups.membership.reindex",
        {
            "groupName": "商品默认分组",
            "groupCode": "product-default",
            "sortOrder": 10,
            "defaultGroup": False,
        },
    ),
    (
        "product-management-05",
        "publish_plans.snapshot.validate",
        {
            "contentScope": "选中内容",
            "accountScope": "选择授权账号",
            "distributionMode": "均匀分配",
            "publishAt": "2026-09-01T09:00",
        },
    ),
    (
        "product-management-09",
        "works.revision.validate",
        {
            "contentScope": "全部商品",
            "ruleSet": "平台基础规则",
            "includeMediaOcr": True,
            "onMatch": "阻止提交",
        },
    ),
    (
        "post-management-05",
        "watermarks.preview.render",
        {
            "watermarkTemplate": "账号标识",
            "watermarkPosition": "左下角",
            "watermarkOpacity": 65,
            "previewOnly": True,
        },
    ),
    (
        "post-management-07",
        "publish_plans.snapshot.validate",
        {
            "contentScope": "选中内容",
            "accountScope": "选择授权账号",
            "distributionMode": "均匀分配",
            "publishAt": "2026-09-01T09:00",
        },
    ),
    (
        "post-management-08",
        "publish_plans.snapshot.validate",
        {
            "contentScope": "当前分组",
            "accountScope": "按账号组分配",
            "distributionMode": "人工指定",
            "publishAt": "2026-09-01T10:00",
        },
    ),
    (
        "xy-tasks-01",
        "xianyu.listing.publish",
        {
            "listingBody": "自用闲置，功能正常，支持当面交易",
            "listingPrice": "128",
            "contentScope": "选中内容",
            "accountScope": "选择授权账号",
            "distributionMode": "均匀分配",
            "schedule": "2026-09-01T09:00",
            "dryRun": False,
        },
    ),
    *(
        (
            feature_id,
            "publish_plans.snapshot.validate",
            {
                "contentScope": "选中内容",
                "accountScope": "选择授权账号",
                "distributionMode": "均匀分配",
                "schedule": "2026-09-01T09:00",
                "dryRun": True,
            },
        )
        for feature_id in ("xy-tasks-02", "zz-tasks-01", "red-tasks-01")
    ),
    (
        "assets-01",
        "watermarks.preview.render",
        {
            "watermarkTemplate": "售后说明",
            "watermarkPosition": "居中",
            "watermarkOpacity": 50,
            "previewOnly": True,
        },
    ),
    (
        "assets-02",
        "media.derivative.generate",
        {
            "assetName": "product-cover.jpg",
            "assetScope": "全部内容",
            "fileReference": "s3://tenant/media/product-cover.jpg",
            "versionNote": "初始版本",
            "active": True,
        },
    ),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("feature_id", "operation_key", "page_parameters"), MAPPED_CASES)
async def test_all_web_mappings_have_strict_persisted_parameter_contracts(
    client: httpx.AsyncClient,
    feature_id: str,
    operation_key: str,
    page_parameters: dict[str, Any],
) -> None:
    resource_id = f"resource-{feature_id}"
    if operation_key == "xianyu.listing.publish":
        device = await client.post(
            "/api/v1/mobile/devices",
            headers=headers("security_admin"),
            json={
                "logicalName": "xianyu-publish-device",
                "androidVersion": "14",
                "companionVersion": "1.0.0",
                "labels": ["mobile-direct"],
            },
        )
        assert device.status_code == 201, device.text
        resource_id = str(device.json()["id"])
    created = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("security_admin", key=f"mapping-{feature_id}"),
        json={
            "featureId": feature_id,
            "operationKey": operation_key,
            "resourceId": resource_id,
            "parameters": {"pageParameters": page_parameters},
        },
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["parameters"]["pageParameters"] == page_parameters
    fetched = await client.get(
        f"/api/v1/operations/tasks/{task['id']}", headers=headers("security_admin")
    )
    assert fetched.status_code == 200
    assert fetched.json()["parameters"] == task["parameters"]


@pytest.mark.asyncio
async def test_catalog_exposes_machine_readable_parameter_schemas(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/operations/catalog", headers=headers("security_admin"))
    assert response.status_code == 200
    catalog = {item["key"]: item for item in response.json()}
    watermark = catalog["watermarks.preview.render"]["parameterSchema"]
    assert watermark["core"]["additionalProperties"] is False
    assert "assets-01" in watermark["pageParametersByFeatureId"]
    opacity = watermark["pageParametersByFeatureId"]["assets-01"]["properties"]["watermarkOpacity"]
    assert opacity["maximum"] == 100


@pytest.mark.asyncio
async def test_core_and_page_parameters_reject_unknown_fields_and_wrong_types(
    client: httpx.AsyncClient,
) -> None:
    base = {
        "featureId": "assets-01",
        "operationKey": "watermarks.preview.render",
        "resourceId": "asset-1",
        "parameters": {
            "pageParameters": {
                "watermarkTemplate": "品牌角标",
                "watermarkPosition": "右下角",
                "watermarkOpacity": 72,
                "previewOnly": True,
            }
        },
    }
    unknown_core = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("security_admin", key="unknown-core"),
        json=base | {"parameters": base["parameters"] | {"unexpected": True}},
    )
    assert unknown_core.status_code == 422
    assert "unexpected" in unknown_core.json()["detail"]

    bad_page = dict(base["parameters"]["pageParameters"])
    bad_page["watermarkOpacity"] = "seventy"
    wrong_type = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("security_admin", key="wrong-page-type"),
        json=base | {"parameters": {"pageParameters": bad_page}},
    )
    assert wrong_type.status_code == 422

    unknown_page = dict(base["parameters"]["pageParameters"])
    unknown_page["coordinates"] = "10,20"
    rejected_page = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("security_admin", key="unknown-page"),
        json=base | {"parameters": {"pageParameters": unknown_page}},
    )
    assert rejected_page.status_code == 422


@pytest.mark.asyncio
async def test_item_result_and_aggregate_remain_persisted(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("security_admin", key="persisted-result"),
        json={
            "featureId": "assets-02",
            "operationKey": "media.derivative.generate",
            "resourceId": "asset-result-1",
            "parameters": {
                "derivativeProfileId": "webp-v2",
                "pageParameters": MAPPED_CASES[-1][2],
            },
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    result = await client.post(
        f"/api/v1/operations/tasks/{task_id}/items/asset-result-1:result",
        headers=headers("system_service", user=SERVICE),
        json={
            "status": "SUCCEEDED",
            "detail": "derivative generated",
            "evidenceRefs": ["s3://tenant/evidence/asset-result-1.json"],
        },
    )
    assert result.status_code == 200, result.text
    fetched = await client.get(
        f"/api/v1/operations/tasks/{task_id}", headers=headers("security_admin")
    )
    body = fetched.json()
    assert body["status"] == "SUCCEEDED"
    assert body["resultSummary"]["succeeded"] == 1
    assert body["items"][0]["detail"] == "derivative generated"
    assert body["items"][0]["evidenceRefs"] == ["s3://tenant/evidence/asset-result-1.json"]

    inconsistent = await client.post(
        f"/api/v1/operations/tasks/{task_id}/items/asset-result-1:result",
        headers=headers("system_service", user=SERVICE),
        json={"status": "SUCCEEDED", "errorCode": "IMPOSSIBLE"},
    )
    assert inconsistent.status_code == 422
