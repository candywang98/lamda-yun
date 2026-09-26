from __future__ import annotations

import base64
import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.apk_policy import canonical_analysis_payload
from cloudctl_api.builtin_recipes import builtin_recipe_package
from cloudctl_api.schemas import ApkAnalysisReport
from cloudctl_api.settings import Settings
from cloudctl_automation_sdk import package_signature_payload, validate_manifest
from cloudctl_automation_sdk.recipe import canonical_recipe_bytes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

TENANT = "00000000-0000-7000-8000-000000000111"
CREATOR = "00000000-0000-7000-8000-000000000222"
APPROVER = "00000000-0000-7000-8000-000000000333"
SERVICE = "00000000-0000-7000-8000-000000000444"
AUTOMATION_KEY_ID = "test-automation-1"
AUTOMATION_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
APK_ANALYSIS_KEY_ID = "test-apk-analyzer-1"
APK_ANALYSIS_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(reversed(range(32))))


def automation_public_key() -> str:
    raw = AUTOMATION_PRIVATE_KEY.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def apk_analysis_public_key() -> str:
    raw = APK_ANALYSIS_PRIVATE_KEY.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def headers(user: str, roles: str, *, mfa: bool = True) -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT,
        "X-User-Id": user,
        "X-Roles": roles,
        "X-MFA": str(mfa).lower(),
        "X-Request-Id": str(uuid.uuid4()),
    }


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        Settings(
            env="test",
            repository_mode="memory",
            dev_auth_bypass=True,
            automation_signing_public_keys={AUTOMATION_KEY_ID: automation_public_key()},
            apk_analysis_public_keys={APK_ANALYSIS_KEY_ID: apk_analysis_public_key()},
        )
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
            yield value


def automation_manifest() -> dict:
    return {
        "apiVersion": "cloudctl.example/v1",
        "kind": "AutomationPackage",
        "metadata": {"name": "authorized-publisher", "version": "1.0.0"},
        "spec": {
            "entrypoint": "src.entrypoint:run",
            "runtime": {"python": ">=3.12,<3.13", "lamda": ">=10.6,<11", "android": ">=10,<=17"},
            "targets": [{"packageName": "com.example.target", "versions": ">=1,<2"}],
            "capabilities": {
                "required": ["ui.selectors", "screenshot", "ui.dump"],
                "optional": [],
                "forbidden": [
                    "shell.arbitrary",
                    "frida",
                    "mitm",
                    "proxy.mutate",
                    "adb.remote",
                ],
            },
            "parametersSchema": "schemas/parameters.json",
            "locators": ["locators/app.yaml"],
            "submitPolicy": {"mode": "commit-intent-single-shot"},
            "signature": {"algorithm": "Ed25519", "keyId": AUTOMATION_KEY_ID},
        },
    }


def signed_automation_request() -> dict:
    manifest = automation_manifest()
    artifact_sha256 = "a" * 64
    sbom_sha256 = "b" * 64
    sbom_ref = "s3://tenant/sbom.json"
    signature = AUTOMATION_PRIVATE_KEY.sign(
        package_signature_payload(
            artifact_sha256=artifact_sha256,
            manifest=validate_manifest(manifest).model_dump(mode="json", by_alias=True),
            sbom_ref=sbom_ref,
            sbom_sha256=sbom_sha256,
        )
    )
    return {
        "artifactSha256": artifact_sha256,
        "manifest": manifest,
        "sbomRef": sbom_ref,
        "sbomSha256": sbom_sha256,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def signed_recipe_package(*, version: str = "1.0.1") -> dict:
    package = {
        "apiVersion": "cloudctl.recipe/v1",
        "kind": "LocalRecipePackage",
        "manifest": {
            "id": "recipe-device-probe-signed",
            "version": version,
            "hash": "0" * 64,
            "signingKeyId": AUTOMATION_KEY_ID,
            "minEngineVersion": 1,
            "platform": "companion",
            "app": "com.company.cloudctl.companion",
            "commandTypes": ["device.probe_capabilities.v1"],
        },
        "graph": {
            "startStateId": "probe",
            "maxIterations": 8,
            "maxDurationMs": 30000,
            "states": [
                {"stateId": "probe", "action": "log", "onSuccess": "SUCCEEDED", "terminal": True}
            ],
        },
        "signature": {"algorithm": "Ed25519", "keyId": AUTOMATION_KEY_ID, "digest": "pending"},
    }
    package["manifest"]["hash"] = hashlib.sha256(canonical_recipe_bytes(package)).hexdigest()
    payload = package_signature_payload(
        artifact_sha256=package["manifest"]["hash"],
        manifest=package["manifest"],
        sbom_ref="recipe://local",
        sbom_sha256=package["manifest"]["hash"],
    )
    package["signature"]["digest"] = base64.b64encode(AUTOMATION_PRIVATE_KEY.sign(payload)).decode(
        "ascii"
    )
    return package


def signed_apk_request(*, findings: list[dict] | None = None) -> dict:
    report = {
        "keyId": APK_ANALYSIS_KEY_ID,
        "analyzer": "cloudctl-apk-analyzer",
        "analyzerVersion": "1.0.0",
        "analyzedAt": datetime.now(UTC).isoformat(),
        "artifactSha256": "c" * 64,
        "packageName": "com.example.target",
        "versionName": "8.32.1",
        "versionCode": 83201,
        "signatureDigest": "d" * 64,
        "minSdk": 26,
        "targetSdk": 35,
        "abis": ["arm64-v8a"],
        "permissions": ["android.permission.INTERNET"],
        "sbomSha256": "e" * 64,
        "debuggable": False,
        "usesCleartextTraffic": False,
        "verdict": "CLEAN",
        "findings": findings or [],
    }
    report = ApkAnalysisReport.model_validate(report).model_dump(mode="json", by_alias=True)
    signature = APK_ANALYSIS_PRIVATE_KEY.sign(canonical_analysis_payload(report))
    return {
        "sha256": report["artifactSha256"],
        "packageName": report["packageName"],
        "versionName": report["versionName"],
        "versionCode": report["versionCode"],
        "signatureDigest": report["signatureDigest"],
        "minSdk": report["minSdk"],
        "targetSdk": report["targetSdk"],
        "abis": report["abis"],
        "permissions": report["permissions"],
        "sbomRef": "oci://registry.example/sbom/com.example.target:83201",
        "sbomSha256": report["sbomSha256"],
        "sourceRef": "s3://tenant/apk/com.example.target-83201.apk",
        "analysisReport": report,
        "analysisSignature": base64.b64encode(signature).decode("ascii"),
    }


async def qualify_automation(
    client: httpx.AsyncClient, headers_value: dict[str, str], version_id: str
) -> None:
    stages = (
        (5, 0, 0, 0),
        (25, 20, 20, 0),
        (100, 100, 99, 1),
    )
    for percentage, sample_size, success_count, failure_count in stages:
        response = await client.post(
            f"/api/v1/automation-packages/{version_id}:promote",
            headers=headers_value,
            json={
                "targetPercentage": percentage,
                "evidence": {
                    "sampleSize": sample_size,
                    "successCount": success_count,
                    "failureCount": failure_count,
                    "safetyViolations": 0,
                    "p95DurationMs": 1200,
                },
            },
        )
        assert response.status_code == 200, response.text


async def bootstrap(client: httpx.AsyncClient) -> dict[str, str]:
    security = headers(CREATOR, "security_admin")
    edge = (
        await client.post(
            "/api/v1/edges",
            headers=security,
            json={"logicalName": "edge-a", "certificateFingerprint": "ab" * 32},
        )
    ).json()
    device = (
        await client.post(
            "/api/v1/devices",
            headers=security,
            json={
                "edgeId": edge["id"],
                "logicalName": "device-a",
                "androidVersion": "14",
                "lamdaVersion": "10.8",
                "labels": ["stable"],
            },
        )
    ).json()
    account = (
        await client.post(
            "/api/v1/accounts",
            headers=security,
            json={
                "platform": "authorized-platform-adapter",
                "externalSubjectRef": "authorized:test-account",
                "displayLabel": "Authorized test account",
                "secretRef": "vault://cloudctl/test-account",
                "authorizationBasis": "integration test authorization fixture",
            },
        )
    ).json()
    binding = await client.post(
        f"/api/v1/accounts/{account['id']}/bindings",
        headers=security,
        json={
            "deviceId": device["id"],
            "confirmationNote": "authorized integration test binding",
        },
    )
    assert binding.status_code == 201, binding.text
    content = (
        await client.post(
            "/api/v1/content",
            headers=headers(CREATOR, "content_editor"),
            json={"title": "Launch", "payload": {"caption": "authorized content"}},
        )
    ).json()
    automation = (
        await client.post(
            "/api/v1/automation-packages",
            headers=security,
            json=signed_automation_request(),
        )
    ).json()
    await qualify_automation(client, security, automation["id"])
    return {
        "device_id": device["id"],
        "account_id": account["id"],
        "revision_id": content["revision"]["id"],
        "automation_id": automation["id"],
    }


@pytest.mark.asyncio
async def test_health_probes(client: httpx.AsyncClient) -> None:
    live = await client.get("/health/live")
    ready = await client.get("/health/ready")
    compatibility = await client.get("/healthz")

    assert live.json() == {"status": "ok"}
    expected = {"status": "ok", "repositoryMode": "memory"}
    assert ready.json() == expected
    assert compatibility.json() == expected


@pytest.mark.asyncio
async def test_media_references_include_publish_plan(client: httpx.AsyncClient) -> None:
    refs = await bootstrap(client)
    media = await client.post(
        "/api/v1/media/assets:register",
        headers=headers(CREATOR, "content_editor"),
        json={
            "sha256": "f" * 64,
            "objectKey": "reference/publish.jpg",
            "contentType": "image/jpeg",
            "sizeBytes": 32,
        },
    )
    assert media.status_code == 201, media.text
    media_id = media.json()["id"]
    content = await client.post(
        "/api/v1/content",
        headers=headers(CREATOR, "content_editor"),
        json={
            "title": "Publish reference",
            "payload": {
                "kind": "post",
                "body": "reference body",
                "mediaAssetIds": [media_id],
                "targetApp": "douyin",
                "draftState": "草稿",
            },
        },
    )
    assert content.status_code == 201, content.text
    revision_id = content.json()["revision"]["id"]
    plan = await client.post(
        "/api/v1/publish-plans",
        headers=headers(CREATOR, "publisher") | {"Idempotency-Key": "media-reference-plan"},
        json={
            "contentRevisionId": revision_id,
            "platform": "authorized-platform-adapter",
            "targets": [{"accountId": refs["account_id"], "deviceId": refs["device_id"]}],
            "schedule": {"mode": "NOW"},
            "execution": {"maxConcurrency": 1},
            "approvalPolicy": "NONE",
            "automationPackageVersionId": refs["automation_id"],
        },
    )
    assert plan.status_code == 201, plan.text
    references = await client.get(
        f"/api/v1/media/assets/{media_id}/references",
        headers=headers(CREATOR, "viewer"),
    )
    assert references.status_code == 200, references.text
    assert references.json()["publishPlanReferences"] == [
        {
            "publishPlanId": plan.json()["id"],
            "state": "DRAFT",
            "platform": "authorized-platform-adapter",
        }
    ]
    assert references.json()["contentReferences"][0]["revisionNo"] == 1


@pytest.mark.asyncio
async def test_product_archive_is_protected_by_publish_plan_reference(
    client: httpx.AsyncClient,
) -> None:
    refs = await bootstrap(client)
    product = await client.post(
        "/api/v1/products",
        headers=headers(CREATOR, "content_editor"),
        json={
            "spuCode": "ARCHIVE-GUARD-1",
            "title": "Archive guarded product",
            "category": "test",
            "price": "10",
            "stock": 1,
        },
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]
    plan = await client.post(
        "/api/v1/publish-plans",
        headers=headers(CREATOR, "publisher") | {"Idempotency-Key": "archive-guard-plan"},
        json={
            "contentRevisionId": refs["revision_id"],
            "productId": product_id,
            "platform": "authorized-platform-adapter",
            "targets": [{"accountId": refs["account_id"], "deviceId": refs["device_id"]}],
            "schedule": {"mode": "NOW"},
            "execution": {"maxConcurrency": 1},
            "approvalPolicy": "NONE",
            "automationPackageVersionId": refs["automation_id"],
        },
    )
    assert plan.status_code == 201, plan.text
    blocked = await client.post(
        f"/api/v1/products/{product_id}:archive",
        headers=headers(CREATOR, "content_editor"),
        json={"reason": "must remain available for active plan"},
    )
    assert blocked.status_code == 409, blocked.text
    canceled = await client.post(
        f"/api/v1/publish-plans/{plan.json()['id']}:cancel",
        headers=headers(CREATOR, "publisher"),
    )
    assert canceled.status_code == 200, canceled.text
    archived = await client.post(
        f"/api/v1/products/{product_id}:archive",
        headers=headers(CREATOR, "content_editor"),
        json={"reason": "plan canceled"},
    )
    assert archived.status_code == 200, archived.text
    rejected = await client.post(
        "/api/v1/publish-plans",
        headers=headers(CREATOR, "publisher") | {"Idempotency-Key": "archive-guard-plan-2"},
        json={
            "contentRevisionId": refs["revision_id"],
            "productId": product_id,
            "platform": "authorized-platform-adapter",
            "targets": [{"accountId": refs["account_id"], "deviceId": refs["device_id"]}],
            "schedule": {"mode": "NOW"},
            "execution": {"maxConcurrency": 1},
            "approvalPolicy": "NONE",
            "automationPackageVersionId": refs["automation_id"],
        },
    )
    assert rejected.status_code == 409, rejected.text


@pytest.mark.asyncio
async def test_automation_registry_rejects_tampering_and_rollout_skips(
    client: httpx.AsyncClient,
) -> None:
    security = headers(CREATOR, "security_admin")
    tampered = signed_automation_request()
    tampered["artifactSha256"] = "f" * 64
    rejected = await client.post("/api/v1/automation-packages", headers=security, json=tampered)
    assert rejected.status_code == 422
    assert "signature verification failed" in rejected.json()["detail"]

    registered = await client.post(
        "/api/v1/automation-packages", headers=security, json=signed_automation_request()
    )
    assert registered.status_code == 201, registered.text
    skipped = await client.post(
        f"/api/v1/automation-packages/{registered.json()['id']}:promote",
        headers=security,
        json={
            "targetPercentage": 25,
            "evidence": {
                "sampleSize": 20,
                "successCount": 20,
                "failureCount": 0,
                "safetyViolations": 0,
                "p95DurationMs": 1000,
            },
        },
    )
    assert skipped.status_code == 422
    assert "advance from 0% to 5%" in skipped.json()["detail"]


@pytest.mark.asyncio
async def test_apk_registry_derives_clean_status_from_signed_policy_report(
    client: httpx.AsyncClient,
) -> None:
    security = headers(CREATOR, "security_admin")
    admitted = await client.post(
        "/api/v1/apk-artifacts", headers=security, json=signed_apk_request()
    )
    assert admitted.status_code == 201, admitted.text
    assert admitted.json()["scan_status"] == "CLEAN"
    assert admitted.json()["policy_decision"]["decision"] == "ACCEPT"

    unsafe = signed_apk_request(
        findings=[{"ruleId": "MOB-999", "severity": "CRITICAL", "title": "Blocking finding"}]
    )
    rejected = await client.post("/api/v1/apk-artifacts", headers=security, json=unsafe)
    assert rejected.status_code == 422
    assert "HIGH or CRITICAL" in rejected.json()["detail"]


@pytest.mark.asyncio
async def test_browser_preflight_allows_configured_dev_origins_and_identity_headers(
    client: httpx.AsyncClient,
) -> None:
    response = await client.options(
        "/api/v1/operations/catalog",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,X-Tenant-Id,X-User-Id,X-Roles,X-MFA",
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    allowed = response.headers["access-control-allow-headers"].lower()
    for header in ("authorization", "x-tenant-id", "x-user-id", "x-roles", "x-mfa"):
        assert header in allowed


@pytest.mark.asyncio
async def test_publish_idempotency_approval_fencing_and_commit_intent(
    client: httpx.AsyncClient,
) -> None:
    refs = await bootstrap(client)
    creator_headers = headers(CREATOR, "publisher") | {"Idempotency-Key": "plan-key-1"}
    request = {
        "contentRevisionId": refs["revision_id"],
        "platform": "authorized-platform-adapter",
        "targets": [{"accountId": refs["account_id"], "deviceId": refs["device_id"]}],
        "schedule": {"mode": "NOW"},
        "execution": {"maxConcurrency": 1},
        "approvalPolicy": "BEFORE_START",
        "automationPackageVersionId": refs["automation_id"],
    }
    first = await client.post("/api/v1/publish-plans", headers=creator_headers, json=request)
    replay = await client.post("/api/v1/publish-plans", headers=creator_headers, json=request)
    assert first.status_code == 201, first.text
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert first.json()["id"] == replay.json()["id"]

    plan_id = first.json()["id"]
    submitted = await client.post(
        f"/api/v1/publish-plans/{plan_id}:submit", headers=headers(CREATOR, "publisher")
    )
    assert submitted.status_code == 200, submitted.text
    snapshot_hash = submitted.json()["snapshot"]["payload_sha256"]

    self_approval = await client.post(
        f"/api/v1/publish-plans/{plan_id}:approve",
        headers=headers(CREATOR, "approver"),
        json={"decision": "APPROVED"},
    )
    assert self_approval.status_code == 403
    no_mfa = await client.post(
        f"/api/v1/publish-plans/{plan_id}:approve",
        headers=headers(APPROVER, "approver", mfa=False),
        json={"decision": "APPROVED"},
    )
    assert no_mfa.status_code == 403
    approved = await client.post(
        f"/api/v1/publish-plans/{plan_id}:approve",
        headers=headers(APPROVER, "approver"),
        json={"decision": "APPROVED"},
    )
    assert approved.status_code == 200, approved.text

    current = await client.get(
        f"/api/v1/publish-plans/{plan_id}", headers=headers(CREATOR, "publisher")
    )
    assert current.json()["snapshot"]["payload_sha256"] == snapshot_hash
    target_id = current.json()["publishTargets"][0]["id"]
    for state in ("QUEUED", "RUNNING"):
        response = await client.post(
            f"/api/v1/publish-targets/{target_id}:state",
            headers=headers(SERVICE, "system_service"),
            json={"state": state},
        )
        assert response.status_code == 200, response.text

    lease1 = await client.post(
        f"/api/v1/devices/{refs['device_id']}/leases",
        headers=headers(SERVICE, "system_service"),
        json={"ownerWorkflowId": f"publish-target/{target_id}", "ttlSeconds": 60},
    )
    assert lease1.status_code == 201, lease1.text
    await client.delete(
        f"/api/v1/devices/{refs['device_id']}/leases/{lease1.json()['lease_id']}",
        headers=headers(SERVICE, "system_service"),
    )
    lease2 = await client.post(
        f"/api/v1/devices/{refs['device_id']}/leases",
        headers=headers(SERVICE, "system_service"),
        json={"ownerWorkflowId": f"publish-target/{target_id}", "ttlSeconds": 60},
    )
    assert lease2.json()["fencing_token"] > lease1.json()["fencing_token"]

    stale_intent = await client.post(
        f"/api/v1/publish-targets/{target_id}/commit-intents",
        headers=headers(SERVICE, "system_service"),
        json={
            "fencingToken": lease1.json()["fencing_token"],
            "beforeCommitEvidenceId": str(uuid.uuid4()),
        },
    )
    assert stale_intent.status_code == 409
    evidence_id = str(uuid.uuid4())
    intent = await client.post(
        f"/api/v1/publish-targets/{target_id}/commit-intents",
        headers=headers(SERVICE, "system_service"),
        json={
            "fencingToken": lease2.json()["fencing_token"],
            "beforeCommitEvidenceId": evidence_id,
        },
    )
    duplicate = await client.post(
        f"/api/v1/publish-targets/{target_id}/commit-intents",
        headers=headers(SERVICE, "system_service"),
        json={
            "fencingToken": lease2.json()["fencing_token"],
            "beforeCommitEvidenceId": evidence_id,
        },
    )
    assert intent.status_code == 201, intent.text
    assert duplicate.json()["id"] == intent.json()["id"]


@pytest.mark.asyncio
async def test_tenant_isolation_and_problem_details(client: httpx.AsyncClient) -> None:
    refs = await bootstrap(client)
    other = headers(CREATOR, "device_operator") | {
        "X-Tenant-Id": "00000000-0000-7000-8000-000000000999"
    }
    response = await client.post(
        f"/api/v1/devices/{refs['device_id']}:maintenance",
        headers=other,
        json={"enabled": True, "reason": "test"},
    )
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["correlation_id"] == other["X-Request-Id"]


@pytest.mark.asyncio
async def test_recipe_catalog_requires_signature_and_manual_device_publish(
    client: httpx.AsyncClient,
) -> None:
    refs = await bootstrap(client)
    publisher = headers(CREATOR, "publisher")
    developer = headers(CREATOR, "automation_developer")
    builtin = builtin_recipe_package("device.probe_capabilities.v1")
    denied = await client.post("/api/v1/recipes", headers=publisher, json=signed_recipe_package())
    assert denied.status_code == 403
    unsigned = await client.post("/api/v1/recipes", headers=developer, json=builtin)
    assert unsigned.status_code == 422
    tampered = signed_recipe_package()
    tampered["graph"]["maxIterations"] = 7
    rejected = await client.post("/api/v1/recipes", headers=developer, json=tampered)
    assert rejected.status_code == 422
    registered = await client.post(
        "/api/v1/recipes", headers=developer, json=signed_recipe_package()
    )
    assert registered.status_code == 201, registered.text
    version_id = registered.json()["versionId"]
    assert registered.json()["artifactSha256"] == signed_recipe_package()["manifest"]["hash"]
    skipped = await client.post(
        f"/api/v1/automation-packages/{version_id}:promote",
        headers=headers(CREATOR, "security_admin"),
        json={
            "targetPercentage": 5,
            "evidence": {
                "sampleSize": 0,
                "successCount": 0,
                "failureCount": 0,
                "safetyViolations": 0,
                "p95DurationMs": 0,
            },
        },
    )
    assert skipped.status_code == 422
    published = await client.post(
        f"/api/v1/recipes/{version_id}:publish",
        headers=developer,
        json={
            "targetDeviceIds": [refs["device_id"]],
            "idempotencyKey": "publish-oneplus-probe-1",
        },
    )
    assert published.status_code == 200, published.text
    assert published.json()["deployments"][0]["status"] == "PUBLISHED"
    replay = await client.post(
        f"/api/v1/recipes/{version_id}:publish",
        headers=developer,
        json={
            "targetDeviceIds": [refs["device_id"]],
            "idempotencyKey": "publish-oneplus-probe-1",
        },
    )
    assert replay.json()["deployments"][0]["id"] == published.json()["deployments"][0]["id"]
    enrollment = await client.post(
        "/api/v1/mobile/enrollments",
        headers=headers(CREATOR, "device_operator"),
        json={"deviceId": refs["device_id"], "ttlSeconds": 600},
    )
    assert enrollment.status_code == 201, enrollment.text
    companion = await client.post(
        "/companion/v2/enroll",
        json={
            "code": enrollment.json()["code"],
            "appInstanceId": "recipe-catalog-instance",
            "companionVersion": "1.0.0",
        },
    )
    assert companion.status_code == 201, companion.text
    token = companion.json()["bindingToken"]
    active = await client.get(
        "/companion/v2/recipes/active",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert active.status_code == 200, active.text
    assert active.json()["items"][0]["versionId"] == version_id
    download = await client.get(
        f"/companion/v2/recipes/{version_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert download.status_code == 200, download.text
    assert download.headers["x-content-sha256"] == signed_recipe_package()["manifest"]["hash"]
    revoked = await client.post(
        f"/api/v1/recipes/{version_id}:revoke",
        headers=developer,
        json={
            "targetDeviceIds": [refs["device_id"]],
            "idempotencyKey": "revoke-oneplus-probe-1",
        },
    )
    assert revoked.status_code == 200, revoked.text
    empty = await client.get(
        "/companion/v2/recipes/active",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert empty.json()["items"] == []
    missing = await client.get(
        f"/companion/v2/recipes/{version_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing.status_code == 404
