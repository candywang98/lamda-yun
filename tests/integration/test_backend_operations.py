from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.settings import Settings
from pydantic import SecretStr

TENANT = "00000000-0000-7000-8000-000000001111"
USER = "00000000-0000-7000-8000-000000002222"
SERVICE = "00000000-0000-7000-8000-000000003333"


def headers(
    roles: str,
    *,
    tenant_id: str = TENANT,
    user_id: str = USER,
    idempotency_key: str | None = None,
    mfa: bool = True,
) -> dict[str, str]:
    values = {
        "X-Tenant-Id": tenant_id,
        "X-User-Id": user_id,
        "X-Roles": roles,
        "X-MFA": str(mfa).lower(),
        "X-Request-Id": str(uuid.uuid4()),
    }
    if idempotency_key:
        values["Idempotency-Key"] = idempotency_key
    return values


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        Settings(
            env="test",
            repository_mode="memory",
            dev_auth_bypass=True,
            operation_executor_urls={
                "apk_artifacts.analysis.run": "https://executor.test/apk-analysis",
                "media.derivative.generate": "https://executor.test/media-derivative",
                "task_runs.evidence.export": "https://executor.test/evidence-export",
                "watermarks.preview.render": "https://executor.test/watermark-preview",
            },
            operation_executor_bearer_token=SecretStr("test-operation-token"),
        )
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
            yield value


@pytest.mark.asyncio
async def test_catalog_has_15_safe_modules_and_rbac_flags(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/operations/catalog", headers=headers("viewer"))
    assert response.status_code == 200
    catalog = response.json()
    assert len(catalog) == 16
    assert len({entry["module"] for entry in catalog}) == 16
    assert any(entry["allowed"] for entry in catalog)
    serialized = str(catalog).lower()
    for prohibited in ("captcha", "frida", "mitm", "shell.arbitrary", "proxy.mutate"):
        assert prohibited not in serialized

    features = await client.get("/api/v1/operations/features", headers=headers("viewer"))
    assert features.status_code == 200
    feature_policies = features.json()
    assert len(feature_policies) == 134
    assert len({entry["featureId"] for entry in feature_policies}) == 134
    blocked = next(entry for entry in feature_policies if entry["featureId"] == "collection-01")
    assert blocked["title"] == "商品链接采集"
    assert blocked["moduleLabel"] == "采集管理"
    assert blocked["policy"] == "blocked"
    assert blocked["executionState"] == "blocked"
    assert blocked["executable"] is False
    mapped = next(entry for entry in feature_policies if entry["featureId"] == "assets-01")
    assert mapped["operationKey"] == "watermarks.preview.render"
    assert mapped["executionState"] == "implemented"
    assert mapped["executable"] is False
    ui_only = next(entry for entry in feature_policies if entry["featureId"] == "system-home-01")
    assert ui_only["executionState"] == "ui_only"
    assert ui_only["operationKey"] is None
    implemented = {entry["key"] for entry in catalog if entry["executorAvailable"]}
    assert {
        "apk_artifacts.analysis.run",
        "media.derivative.generate",
        "publish_plans.snapshot.validate",
        "xianyu.listing.publish",
        "task_runs.evidence.export",
        "watermarks.preview.render",
        "works.revision.validate",
    } <= implemented
    unavailable = next(entry for entry in catalog if entry["key"] == "devices.capabilities.refresh")
    assert unavailable["executionState"] == "contract_only"
    assert unavailable["allowed"] is False

    unavailable_create = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("device_operator", idempotency_key="missing-device-executor"),
        json={
            "operationKey": "devices.capabilities.refresh",
            "resourceId": "device-1",
        },
    )
    assert unavailable_create.status_code == 409


@pytest.mark.asyncio
async def test_single_operation_is_idempotent_and_rejects_key_reuse(
    client: httpx.AsyncClient,
) -> None:
    request_headers = headers("content_editor", idempotency_key="media-derive-1")
    body = {
        "operationKey": "media.derivative.generate",
        "resourceId": "media-1",
        "parameters": {"derivativeProfileId": "profile-webp-v2"},
        "context": {
            "source": "web",
            "sourcePage": 51,
            "sourceRoute": "#/goods/analyze_foul",
            "pageParameters": {
                "scope": "all",
                "includeOcr": True,
            },
        },
    }
    first = await client.post("/api/v1/operations/tasks", headers=request_headers, json=body)
    replay = await client.post("/api/v1/operations/tasks", headers=request_headers, json=body)
    assert first.status_code == 201, first.text
    assert replay.status_code == 200, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["id"] == first.json()["id"]
    assert first.json()["context"]["sourcePage"] == 51
    assert first.json()["context"]["pageParameters"]["includeOcr"] is True

    changed = await client.post(
        "/api/v1/operations/tasks",
        headers=request_headers,
        json=body | {"resourceId": "media-2"},
    )
    assert changed.status_code == 409


@pytest.mark.asyncio
async def test_batch_results_are_aggregated_and_audited(client: httpx.AsyncClient) -> None:
    resources = ["apk-1", "apk-2", "apk-3"]
    created = await client.post(
        "/api/v1/operations:batch",
        headers=headers("security_admin", idempotency_key="apk-analysis-batch-1"),
        json={
            "operationKey": "apk_artifacts.analysis.run",
            "resourceIds": resources,
            "parameters": {"scanners": ["malware", "signature", "sbom"]},
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    results = [
        {"status": "SUCCEEDED", "evidenceRefs": ["s3://tenant/evidence/apk-1.json"]},
        {"status": "FAILED", "errorCode": "SIGNATURE_MISMATCH", "detail": "blocked"},
        {"status": "BLOCKED", "errorCode": "SCAN_PENDING", "detail": "manual review"},
    ]
    latest = None
    for resource_id, result in zip(resources, results, strict=True):
        response = await client.post(
            f"/api/v1/operations/tasks/{task_id}/items/{resource_id}:result",
            headers=headers("system_service", user_id=SERVICE),
            json=result,
        )
        assert response.status_code == 200, response.text
        latest = response.json()
    assert latest is not None
    assert latest["status"] == "PARTIAL"
    assert latest["succeededCount"] == 1
    assert latest["failedCount"] == 1
    assert latest["blockedCount"] == 1

    replay = await client.post(
        f"/api/v1/operations/tasks/{task_id}/items/apk-3:result",
        headers=headers("system_service", user_id=SERVICE),
        json=results[2],
    )
    assert replay.status_code == 200

    audit = await client.get(
        f"/api/v1/operations/tasks/{task_id}/audit-result",
        headers=headers("security_admin"),
    )
    assert audit.status_code == 200, audit.text
    actions = [event["action"] for event in audit.json()["auditEvents"]]
    assert actions.count("operation.task.created") == 1
    assert actions.count("operation.item.result_recorded") == 3
    result_events = [
        event
        for event in audit.json()["auditEvents"]
        if event["action"] == "operation.item.result_recorded"
    ]
    assert {event["actorType"] for event in result_events} == {"service"}
    assert all(event["resourceType"] == "operation_task" for event in result_events)


@pytest.mark.asyncio
async def test_operations_enforce_tenant_rbac_and_capability_whitelist(
    client: httpx.AsyncClient,
) -> None:
    forbidden = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("content_editor", idempotency_key="forbidden-apk"),
        json={
            "operationKey": "apk_artifacts.analysis.run",
            "resourceId": "apk-1",
            "parameters": {},
        },
    )
    assert forbidden.status_code == 403

    unsafe = await client.post(
        "/api/v1/operations:batch",
        headers=headers("security_admin", idempotency_key="unsafe-capability"),
        json={
            "operationKey": "apk_artifacts.analysis.run",
            "resourceIds": ["apk-1", "apk-2"],
            "parameters": {"scanners": ["frida"]},
        },
    )
    assert unsafe.status_code == 422

    unsafe_evidence = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("content_editor", idempotency_key="unsafe-evidence-ref"),
        json={
            "operationKey": "works.revision.validate",
            "resourceId": "revision-evidence",
        },
    )
    assert unsafe_evidence.status_code == 201
    human_result = await client.post(
        f"/api/v1/operations/tasks/{unsafe_evidence.json()['id']}/items/revision-evidence:result",
        headers=headers("security_admin"),
        json={"status": "SUCCEEDED", "evidenceRefs": ["s3://tenant/evidence.json"]},
    )
    assert human_result.status_code == 403
    invalid_reference = await client.post(
        f"/api/v1/operations/tasks/{unsafe_evidence.json()['id']}/items/revision-evidence:result",
        headers=headers("system_service", user_id=SERVICE),
        json={"status": "SUCCEEDED", "evidenceRefs": ["file:///tmp/evidence.json"]},
    )
    assert invalid_reference.status_code == 422

    created = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("content_editor", idempotency_key="tenant-isolation-operation"),
        json={
            "operationKey": "works.revision.validate",
            "resourceId": "revision-1",
            "parameters": {},
        },
    )
    assert created.status_code == 201
    other_tenant = "00000000-0000-7000-8000-000000009999"
    hidden = await client.get(
        f"/api/v1/operations/tasks/{created.json()['id']}",
        headers=headers("content_editor", tenant_id=other_tenant),
    )
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_requester_can_cancel_queued_task_but_cannot_delete_it(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("publisher", idempotency_key="evidence-export-cancel"),
        json={
            "operationKey": "task_runs.evidence.export",
            "resourceId": "run-1",
            "parameters": {"format": "json", "redact": True},
        },
    )
    task_id = created.json()["id"]
    canceled = await client.post(
        f"/api/v1/operations/tasks/{task_id}:cancel",
        headers=headers("publisher"),
        json={"reason": "export no longer required"},
    )
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["status"] == "CANCELED"
    assert canceled.json()["items"][0]["status"] == "CANCELED"
    still_listed = await client.get(
        "/api/v1/operations/tasks?status=CANCELED", headers=headers("publisher")
    )
    assert [task["id"] for task in still_listed.json()] == [task_id]


@pytest.mark.asyncio
async def test_feature_mapping_context_and_separation_of_duties_approval(
    client: httpx.AsyncClient,
) -> None:
    standard = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("content_editor", idempotency_key="mapped-watermark-1"),
        json={
            "featureId": "assets-01",
            "operationKey": "watermarks.preview.render",
            "resourceId": "media-1",
            "parameters": {
                "ruleVersionId": "rule-1",
                "pageParameters": {
                    "watermarkTemplate": "品牌角标",
                    "watermarkPosition": "右下角",
                    "watermarkOpacity": 65,
                    "previewOnly": True,
                },
            },
            "context": {"source": "web", "mode": "assets", "reason": "preview"},
        },
    )
    assert standard.status_code == 201, standard.text
    assert standard.json()["featureId"] == "assets-01"
    assert standard.json()["parameters"]["pageParameters"]["watermarkOpacity"] == 65
    assert standard.json()["context"]["source"] == "web"
    assert standard.json()["status"] == "QUEUED"

    mismatched = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("security_admin", idempotency_key="mapping-mismatch-1"),
        json={
            "featureId": "assets-01",
            "operationKey": "devices.capabilities.refresh",
            "resourceId": "device-1",
        },
    )
    assert mismatched.status_code == 422
    blocked = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("security_admin", idempotency_key="blocked-feature-1"),
        json={
            "featureId": "collection-01",
            "operationKey": "media.derivative.generate",
            "resourceId": "external-link",
        },
    )
    assert blocked.status_code == 403

    creator_id = USER
    approval = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("publisher", user_id=creator_id, idempotency_key="approval-feature-1"),
        json={
            "featureId": "product-management-05",
            "operationKey": "publish_plans.snapshot.validate",
            "resourceId": "snapshot-1",
            "parameters": {"strict": True},
            "context": {"source": "web", "reason": "authorized preflight"},
        },
    )
    assert approval.status_code == 201, approval.text
    task_id = approval.json()["id"]
    assert approval.json()["status"] == "PENDING_APPROVAL"

    premature_result = await client.post(
        f"/api/v1/operations/tasks/{task_id}/items/snapshot-1:result",
        headers=headers("system_service", user_id=SERVICE),
        json={"status": "SUCCEEDED"},
    )
    assert premature_result.status_code == 409

    self_approval = await client.post(
        f"/api/v1/operations/tasks/{task_id}:approve",
        headers=headers("approver", user_id=creator_id),
        json={"reason": "self approval is forbidden"},
    )
    assert self_approval.status_code == 403
    no_mfa = await client.post(
        f"/api/v1/operations/tasks/{task_id}:approve",
        headers=headers("approver", user_id=SERVICE, mfa=False),
        json={"reason": "missing MFA"},
    )
    assert no_mfa.status_code == 403
    approved = await client.post(
        f"/api/v1/operations/tasks/{task_id}:approve",
        headers=headers("approver", user_id=SERVICE),
        json={"reason": "scope and authorization reviewed"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "QUEUED"
    assert approved.json()["approvalDecision"] == "APPROVED"

    completed = await client.post(
        f"/api/v1/operations/tasks/{task_id}/items/snapshot-1:result",
        headers=headers("system_service", user_id=SERVICE),
        json={"status": "SUCCEEDED"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "SUCCEEDED"
