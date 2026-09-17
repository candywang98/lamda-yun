"""U10 apk-release/v1: release registry, ring rollout and install preemption.

Acceptance map (frozen task card U10):
- group 1 (错签名/降级/数据 schema 不兼容/下载哈希不匹配 → 4xx + code):
  test_wrong_signature_artifact_is_rejected, test_release_record_*,
  test_upgrade_gates_reject_downgrade_and_old_data_schema,
  test_retire_keeps_pins_and_download_hash_verification
- group 2 (不同设备不同旧版 + 能力路由):
  test_per_device_versions_are_independent,
  test_ring_gating_and_capability_routing
- group 3 (不可覆盖 409 / retire 不破坏 pin):
  test_release_record_fields_immutability_and_tenant_scoping,
  test_retire_keeps_pins_and_download_hash_verification
- group 4 (RUNNING/PAUSED/RECONCILING 抢占 409):
  test_busy_device_preemption_rejected
- group 5 (跨租户 404):
  test_release_record_fields_immutability_and_tenant_scoping
- WIRE2 (U11 seam wiring, :report-installed):
  test_install_receipt_advances_target_and_replays_idempotently,
  test_install_receipt_is_scoped_to_the_bound_device,
  test_failed_receipt_is_recorded_without_advancing,
  test_signature_mismatch_receipt_is_recorded_but_never_success,
  test_install_receipt_identity_mismatch_is_rejected
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.apk_policy import canonical_analysis_payload
from cloudctl_api.db import AuditEventRow, DeviceRow, MobileTaskRow
from cloudctl_api.schemas import ApkAnalysisReport
from cloudctl_api.settings import Settings
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from sqlalchemy import select
from test_backend_control_api import (
    APK_ANALYSIS_KEY_ID,
    APK_ANALYSIS_PRIVATE_KEY,
    AUTOMATION_KEY_ID,
    CREATOR,
    apk_analysis_public_key,
    automation_public_key,
    headers,
)
from test_platform_tasks import PROBE, _enroll, bind, create_account, identity

SECURITY = headers(CREATOR, "security_admin")
PACKAGE = "com.example.target"


@pytest.fixture
async def api():
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
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


def artifact_request(
    *,
    sha256: str | None = None,
    version_code: int = 83201,
    package: str = PACKAGE,
) -> dict:
    sha256 = sha256 or ("c" * 64)
    report = {
        "keyId": APK_ANALYSIS_KEY_ID,
        "analyzer": "cloudctl-apk-analyzer",
        "analyzerVersion": "1.0.0",
        "analyzedAt": datetime.now(UTC).isoformat(),
        "artifactSha256": sha256,
        "packageName": package,
        "versionName": f"0.{version_code}",
        "versionCode": version_code,
        "signatureDigest": "d" * 64,
        "minSdk": 26,
        "targetSdk": 35,
        "abis": ["arm64-v8a"],
        "permissions": ["android.permission.INTERNET"],
        "sbomSha256": "e" * 64,
        "debuggable": False,
        "usesCleartextTraffic": False,
        "verdict": "CLEAN",
        "findings": [],
    }
    validated = ApkAnalysisReport.model_validate(report).model_dump(
        mode="json", by_alias=True
    )
    signature = APK_ANALYSIS_PRIVATE_KEY.sign(canonical_analysis_payload(validated))
    return {
        "sha256": validated["artifactSha256"],
        "packageName": validated["packageName"],
        "versionName": validated["versionName"],
        "versionCode": validated["versionCode"],
        "signatureDigest": validated["signatureDigest"],
        "minSdk": validated["minSdk"],
        "targetSdk": validated["targetSdk"],
        "abis": validated["abis"],
        "permissions": validated["permissions"],
        "sbomRef": f"oci://registry.example/sbom/{package}:{version_code}",
        "sbomSha256": validated["sbomSha256"],
        "sourceRef": f"s3://tenant/apk/{package}-{version_code}.apk",
        "analysisReport": validated,
        "analysisSignature": base64.b64encode(signature).decode("ascii"),
    }


async def register_artifact(client: httpx.AsyncClient, **kwargs) -> dict:
    response = await client.post(
        "/api/v1/apk-artifacts", headers=SECURITY, json=artifact_request(**kwargs)
    )
    assert response.status_code == 201, response.text
    return response.json()


def release_payload(artifact_id: str, **overrides) -> dict:
    body = {
        "artifactId": artifact_id,
        "ring": "all",
        "minCapability": {},
        "dataSchema": {"minCompatible": 1, "current": 2},
        "requiresUserConfirmation": True,
    }
    body.update(overrides)
    return body


async def create_release(client: httpx.AsyncClient, artifact_id: str, **overrides) -> dict:
    response = await client.post(
        "/api/v1/apk-releases", headers=SECURITY, json=release_payload(artifact_id, **overrides)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def assign(client: httpx.AsyncClient, release_id: str, device_ids: list[str]):
    return await client.post(
        f"/api/v1/apk-releases/{release_id}:assign",
        headers=SECURITY,
        json={"targetDeviceIds": device_ids},
    )


async def create_device(
    client: httpx.AsyncClient, name: str, *, labels: list[str] | None = None
) -> str:
    body = {"logicalName": name, "androidVersion": "14", "companionVersion": "1.0.0"}
    if labels:
        body["labels"] = list(labels)
    response = await client.post("/api/v1/mobile/devices", headers=identity(), json=body)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def patch_device(
    app: FastAPI,
    device_id: str,
    *,
    target_app_versions: dict[str, str] | None = None,
    capabilities: dict | None = None,
) -> None:
    async with app.state.database.unit_of_work() as session:
        device = await session.get(DeviceRow, device_id)
        assert device is not None
        if target_app_versions is not None:
            merged = dict(device.target_app_versions or {})
            merged.update(target_app_versions)
            device.target_app_versions = merged
        if capabilities is not None:
            merged = dict(device.capabilities or {})
            merged.update(capabilities)
            device.capabilities = merged


async def create_probe_task(client: httpx.AsyncClient, device_id: str, suffix: str) -> str:
    account = await create_account(client, f"account-{suffix}")
    await bind(client, account, device_id)
    response = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": f"u10-{suffix}-{uuid.uuid4()}"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["items"][0]["taskId"])


async def claim_probe(client: httpx.AsyncClient, auth: dict) -> dict:
    response = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert response.status_code == 200, response.text
    return response.json()


def install_receipt(
    *,
    candidate_id: str,
    release_id: str,
    package: str = PACKAGE,
    version_code: int = 83201,
    outcome: str = "INSTALLED",
    installed_version_code: int | None = None,
    signature_matched: bool | None = None,
    message: str | None = None,
) -> dict:
    """WIRE2: mirrors the device-side ApkInstallReceipt.toWireJson() field set."""
    return {
        "candidateId": candidate_id,
        "releaseId": release_id,
        "packageName": package,
        "attemptedVersionCode": version_code,
        "outcome": outcome,
        "installedVersionCode": installed_version_code,
        "signatureMatched": signature_matched,
        "message": message,
        "completedAt": "2026-09-17T00:00:00Z",
    }


async def report_installed(client: httpx.AsyncClient, auth: dict, candidate_id: str, body: dict):
    return await client.post(
        f"/companion/v2/apk/candidates/{candidate_id}:report-installed",
        headers=auth,
        json=body,
    )


async def set_task_state(
    app: FastAPI, task_id: str, *, status: str, business_state: str
) -> None:
    async with app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, task_id)
        assert task is not None
        task.status = status
        task.business_state = business_state


async def test_wrong_signature_artifact_is_rejected(api):
    client, _ = api
    request = artifact_request()
    wrong_key = Ed25519PrivateKey.generate()
    request["analysisSignature"] = base64.b64encode(
        wrong_key.sign(canonical_analysis_payload(request["analysisReport"]))
    ).decode("ascii")
    response = await client.post("/api/v1/apk-artifacts", headers=SECURITY, json=request)
    assert response.status_code == 422
    problem = response.json()
    assert problem["code"] == "VALIDATION_ERROR"
    assert "signature verification failed" in problem["detail"]


async def test_release_record_fields_immutability_and_tenant_scoping(api):
    client, app = api
    artifact = await register_artifact(client)
    release = await create_release(client, artifact["id"], minCapability={"sdkInt": 26})
    assert release["packageName"] == PACKAGE
    assert release["versionCode"] == 83201
    assert release["versionName"] == "0.83201"
    assert release["sha256"] == artifact["sha256"]
    assert release["signatureDigest"] == artifact["signature_digest"]
    assert release["minCapability"] == {"sdkInt": 26}
    assert release["dataSchema"] == {"minCompatible": 1, "current": 2}
    assert release["requiresUserConfirmation"] is True
    assert release["status"] == "ACTIVE"
    assert release["ring"] == "all"
    # The artifact record itself carries the admission evidence chain.
    assert artifact["scan_status"] == "CLEAN"
    assert artifact["policy_decision"]["decision"] == "ACCEPT"

    duplicate = await client.post(
        "/api/v1/apk-releases",
        headers=SECURITY,
        json=release_payload(artifact["id"], ring="canary"),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "APK_RELEASE_EXISTS"

    device = await create_device(client, "immutable")
    other_tenant = SECURITY | {"X-Tenant-Id": str(uuid.uuid4())}
    assert (await client.get("/api/v1/apk-releases", headers=other_tenant)).json() == {
        "items": []
    }
    assert (
        await client.get(f"/api/v1/apk-releases/{release['id']}", headers=other_tenant)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/apk-releases/{release['id']}:assign",
            headers=other_tenant,
            json={"targetDeviceIds": [device]},
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/apk-releases/{release['id']}:retire",
            headers=other_tenant,
            json={"reason": "cross tenant"},
        )
    ).status_code == 404
    assert (
        await client.post(
            "/api/v1/apk-releases",
            headers=other_tenant,
            json=release_payload(artifact["id"]),
        )
    ).status_code == 404

    publisher = headers(CREATOR, "publisher")
    assert (
        await client.post(
            "/api/v1/apk-releases", headers=publisher, json=release_payload(artifact["id"])
        )
    ).status_code == 403
    assert (
        await client.get("/api/v1/apk-releases", headers=SECURITY)
    ).json()["items"] == [release]
    async with app.state.database.unit_of_work() as session:
        audits = list(
            await session.scalars(
                select(AuditEventRow).where(AuditEventRow.action == "apk.release.published")
            )
        )
        assert len(audits) == 1
        assert audits[0].actor_id == CREATOR
        assert audits[0].resource_id == release["id"]


async def test_ring_gating_and_capability_routing(api):
    client, app = api
    artifact = await register_artifact(client)
    release = await create_release(
        client,
        artifact["id"],
        ring="canary",
        minCapability={"sdkInt": 31, "abis": ["arm64-v8a"]},
    )
    canary = await create_device(client, "ring-canary", labels=["ring:canary"])
    plain = await create_device(client, "ring-plain")
    weak = await create_device(client, "ring-weak", labels=["ring:canary"])
    wrong_abi = await create_device(client, "ring-abi", labels=["ring:canary"])
    await patch_device(
        app, canary, capabilities={"sdkInt": 32, "abis": ["arm64-v8a", "armeabi-v7a"]}
    )
    await patch_device(app, weak, capabilities={"sdkInt": 30, "abis": ["arm64-v8a"]})
    await patch_device(app, wrong_abi, capabilities={"sdkInt": 32, "abis": ["armeabi-v7a"]})

    assigned = await assign(client, release["id"], [canary])
    assert assigned.status_code == 200, assigned.text
    assert [t["deviceId"] for t in assigned.json()["targets"]] == [canary]
    assert assigned.json()["targets"][0]["status"] == "OFFERED"
    assert assigned.json()["targets"][0]["requiresUserConfirmation"] is True

    ring_miss = await assign(client, release["id"], [plain])
    assert ring_miss.status_code == 422
    assert ring_miss.json()["code"] == "APK_RING_MISMATCH"

    capability_miss = await assign(client, release["id"], [weak])
    assert capability_miss.status_code == 422
    assert capability_miss.json()["code"] == "APK_CAPABILITY_INSUFFICIENT"

    abi_miss = await assign(client, release["id"], [wrong_abi])
    assert abi_miss.status_code == 422
    assert abi_miss.json()["code"] == "APK_CAPABILITY_INSUFFICIENT"

    # Rejected devices never receive a candidate (capability routing).
    auth = await _enroll(client, plain, "ring-plain-instance")
    assert (await client.get("/companion/v2/apk/candidates", headers=auth)).json() == {
        "items": []
    }
    # An "all" ring release still reaches a canary-labeled device.
    broad_device = await create_device(client, "ring-broad", labels=["ring:canary"])
    await patch_device(
        app, broad_device, capabilities={"sdkInt": 32, "abis": ["arm64-v8a"]}
    )
    broad_artifact = await register_artifact(client, sha256="1" * 64)
    broad = await create_release(client, broad_artifact["id"], ring="all")
    assert (await assign(client, broad["id"], [broad_device])).status_code == 200
    # A second OFFERED candidate for the same device + package is refused.
    conflicting = await register_artifact(client, sha256="6" * 64, version_code=83202)
    conflicting_release = await create_release(client, conflicting["id"])
    clash = await assign(client, conflicting_release["id"], [broad_device])
    assert clash.status_code == 409
    assert clash.json()["code"] == "APK_CANDIDATE_EXISTS"


async def test_per_device_versions_are_independent(api):
    client, app = api
    artifact = await register_artifact(client, sha256="2" * 64, version_code=83201)
    release = await create_release(client, artifact["id"])
    newer = await create_device(client, "ver-newer")
    older = await create_device(client, "ver-older")
    await patch_device(app, newer, target_app_versions={PACKAGE: "83200"})
    await patch_device(app, older, target_app_versions={PACKAGE: "83100"})
    assigned = await assign(client, release["id"], [newer, older])
    assert assigned.status_code == 200, assigned.text
    # Each device keeps its own installed version; nothing is force-flattened.
    async with app.state.database.unit_of_work() as session:
        rows = {
            row.id: row.target_app_versions
            for row in await session.scalars(select(DeviceRow))
            if row.id in {newer, older}
        }
        assert rows[newer][PACKAGE] == "83200"
        assert rows[older][PACKAGE] == "83100"
    # Both devices see their own candidate; versions differ per device pin.
    for device in (newer, older):
        auth = await _enroll(client, device, f"{device}-instance")
        items = (await client.get("/companion/v2/apk/candidates", headers=auth)).json()[
            "items"
        ]
        assert [item["versionCode"] for item in items] == [83201]


async def test_upgrade_gates_reject_downgrade_and_old_data_schema(api):
    client, app = api
    artifact = await register_artifact(client, sha256="3" * 64, version_code=83201)
    release = await create_release(
        client, artifact["id"], dataSchema={"minCompatible": 2, "current": 3}
    )
    same = await create_device(client, "gate-same")
    legacy = await create_device(client, "gate-legacy")
    modern = await create_device(client, "gate-modern")
    await patch_device(app, same, target_app_versions={PACKAGE: "83201"})
    await patch_device(
        app,
        legacy,
        target_app_versions={PACKAGE: "83200"},
        capabilities={"dataSchemaVersions": {PACKAGE: 1}},
    )
    await patch_device(
        app,
        modern,
        target_app_versions={PACKAGE: "83200"},
        capabilities={"dataSchemaVersions": {PACKAGE: 2}},
    )

    downgrade = await assign(client, release["id"], [same])
    assert downgrade.status_code == 422
    assert downgrade.json()["code"] == "APK_VERSION_DOWNGRADE"

    schema = await assign(client, release["id"], [legacy])
    assert schema.status_code == 422
    assert schema.json()["code"] == "APK_SCHEMA_INCOMPATIBLE"

    assert (await assign(client, release["id"], [modern])).status_code == 200
    # A device that reports no data schema version stays eligible.
    unreported = await create_device(client, "gate-unreported")
    assert (await assign(client, release["id"], [unreported])).status_code == 200
    # Invalid compatibility window is rejected at release creation.
    bad_window = await client.post(
        "/api/v1/apk-releases",
        headers=SECURITY,
        json={
            "artifactId": artifact["id"],
            "dataSchema": {"minCompatible": 3, "current": 2},
        },
    )
    assert bad_window.status_code == 422


async def test_busy_device_preemption_rejected(api):
    client, app = api
    artifact = await register_artifact(client, sha256="4" * 64)
    release = await create_release(client, artifact["id"])
    device = await create_device(client, "busy")
    task_id = await create_probe_task(client, device, "busy")
    auth = await _enroll(client, device, "busy-instance")

    claimed = await claim_probe(client, auth)
    assert claimed["taskId"] == task_id
    busy = await assign(client, release["id"], [device])
    assert busy.status_code == 409
    assert busy.json()["code"] == "APK_DEVICE_BUSY"
    assert "PAUSED_WAITING_USER" in busy.json()["detail"]

    for business_state in ("PAUSED_WAITING_USER", "RECONCILING"):
        await set_task_state(
            app, task_id, status="RUNNING", business_state=business_state
        )
        blocked = await assign(client, release["id"], [device])
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "APK_DEVICE_BUSY"

    await set_task_state(app, task_id, status="SUCCEEDED", business_state="SUCCEEDED")
    settled = await assign(client, release["id"], [device])
    assert settled.status_code == 200, settled.text
    items = (await client.get("/companion/v2/apk/candidates", headers=auth)).json()[
        "items"
    ]
    assert [item["candidateId"] for item in items] == [
        settled.json()["targets"][0]["id"]
    ]


async def test_retire_keeps_pins_and_download_hash_verification(api):
    client, app = api
    artifact = await register_artifact(client, sha256="5" * 64, version_code=83202)
    release = await create_release(client, artifact["id"])
    holder = await create_device(client, "pin-holder")
    outsider = await create_device(client, "pin-outsider")
    assigned = await assign(client, release["id"], [holder])
    candidate_id = assigned.json()["targets"][0]["id"]

    auth = await _enroll(client, holder, "pin-holder-instance")
    outsider_auth = await _enroll(client, outsider, "pin-outsider-instance")
    items = (await client.get("/companion/v2/apk/candidates", headers=auth)).json()[
        "items"
    ]
    assert len(items) == 1
    candidate = items[0]
    assert candidate["candidateId"] == candidate_id
    assert candidate["sha256"] == artifact["sha256"]
    assert candidate["signatureDigest"] == artifact["signature_digest"]
    assert candidate["sourceRef"] == artifact["source_ref"]
    assert candidate["requiresUserConfirmation"] is True
    assert candidate["releaseStatus"] == "ACTIVE"
    # Device isolation: another device never sees this candidate.
    assert (
        await client.get("/companion/v2/apk/candidates", headers=outsider_auth)
    ).json() == {"items": []}

    retired = await client.post(
        f"/api/v1/apk-releases/{release['id']}:retire",
        headers=SECURITY,
        json={"reason": "superseded rollout"},
    )
    assert retired.status_code == 200, retired.text
    assert retired.json()["status"] == "RETIRED"
    assert retired.json()["retiredAt"] is not None
    assert (
        await client.post(
            f"/api/v1/apk-releases/{release['id']}:retire",
            headers=SECURITY,
            json={"reason": "again"},
        )
    ).status_code == 409
    assert (await assign(client, release["id"], [outsider])).status_code == 409

    # Retire never broke the pinned candidate on the holding device.
    items = (await client.get("/companion/v2/apk/candidates", headers=auth)).json()[
        "items"
    ]
    assert len(items) == 1
    assert items[0]["releaseStatus"] == "RETIRED"
    assert items[0]["status"] == "OFFERED"

    mismatch = await client.post(
        f"/companion/v2/apk/candidates/{candidate_id}:report-downloaded",
        headers=auth,
        json={"sha256": "0" * 64},
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "APK_DOWNLOAD_HASH_MISMATCH"
    items = (await client.get("/companion/v2/apk/candidates", headers=auth)).json()[
        "items"
    ]
    assert items[0]["status"] == "OFFERED"

    confirmed = await client.post(
        f"/companion/v2/apk/candidates/{candidate_id}:report-downloaded",
        headers=auth,
        json={"sha256": artifact["sha256"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "DOWNLOADED"
    assert confirmed.json()["sha256"] == artifact["sha256"]
    replay = await client.post(
        f"/companion/v2/apk/candidates/{candidate_id}:report-downloaded",
        headers=auth,
        json={"sha256": artifact["sha256"]},
    )
    assert replay.status_code == 200
    # Cross-device candidate access is a plain 404.
    assert (
        await client.post(
            f"/companion/v2/apk/candidates/{candidate_id}:report-downloaded",
            headers=outsider_auth,
            json={"sha256": artifact["sha256"]},
        )
    ).status_code == 404
    async with app.state.database.unit_of_work() as session:
        audits = list(
            await session.scalars(
                select(AuditEventRow).where(AuditEventRow.action == "apk.release.retired")
            )
        )
        assert len(audits) == 1
        assert audits[0].metadata_json["reason"] == "superseded rollout"


# ---------------------------------------------------------------------------
# WIRE2: :report-installed (U11 receipt seam)
# ---------------------------------------------------------------------------


async def _prepared_candidate(api, *, sha256: str = "7" * 64, version_code: int = 83201):
    """register -> release -> assign -> enroll -> report-downloaded."""
    client, _ = api
    artifact = await register_artifact(client, sha256=sha256, version_code=version_code)
    release = await create_release(client, artifact["id"])
    device = await create_device(client, "receipt-device")
    assigned = await assign(client, release["id"], [device])
    assert assigned.status_code == 200, assigned.text
    candidate_id = assigned.json()["targets"][0]["id"]
    auth = await _enroll(client, device, "receipt-device-instance")
    confirmed = await client.post(
        f"/companion/v2/apk/candidates/{candidate_id}:report-downloaded",
        headers=auth,
        json={"sha256": artifact["sha256"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    return auth, candidate_id, release, artifact


async def test_install_receipt_advances_target_and_replays_idempotently(api):
    client, app = api
    auth, candidate_id, release, artifact = await _prepared_candidate(api)

    receipt = install_receipt(
        candidate_id=candidate_id,
        release_id=release["id"],
        version_code=release["versionCode"],
        installed_version_code=release["versionCode"],
        signature_matched=True,
        message="installed",
    )
    accepted = await report_installed(client, auth, candidate_id, receipt)
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["candidateId"] == candidate_id
    assert body["status"] == "INSTALLED"
    assert body["outcome"] == "INSTALLED"
    assert body["receivedAt"] is not None

    # The INSTALLED terminal state is no longer offered to the device.
    items = (await client.get("/companion/v2/apk/candidates", headers=auth)).json()["items"]
    assert [item["candidateId"] for item in items if item["candidateId"] == candidate_id] == []

    # Idempotent replay of the same receipt: 200, same view, no extra audit.
    replay = await report_installed(client, auth, candidate_id, receipt)
    assert replay.status_code == 200
    assert replay.json()["status"] == "INSTALLED"

    async with app.state.database.unit_of_work() as session:
        installed = list(
            await session.scalars(
                select(AuditEventRow).where(AuditEventRow.action == "apk.release.installed")
            )
        )
        assert len(installed) == 1
        assert installed[0].resource_id == candidate_id
        assert installed[0].metadata_json["receipt"]["outcome"] == "INSTALLED"
        assert installed[0].metadata_json["receipt"]["signatureMatched"] is True


async def test_install_receipt_is_scoped_to_the_bound_device(api):
    client, _ = api
    auth, candidate_id, release, artifact = await _prepared_candidate(api, sha256="8" * 64)
    outsider = await create_device(client, "receipt-outsider")
    outsider_auth = await _enroll(client, outsider, "receipt-outsider-instance")

    receipt = install_receipt(
        candidate_id=candidate_id,
        release_id=release["id"],
        version_code=release["versionCode"],
    )
    # Another device's binding never sees this candidate.
    assert (
        await report_installed(client, outsider_auth, candidate_id, receipt)
    ).status_code == 404
    # Neither does an unknown candidate id.
    assert (
        await report_installed(client, auth, str(uuid.uuid4()), receipt)
    ).status_code == 404
    # The owner still advances normally afterwards.
    accepted = await report_installed(client, auth, candidate_id, receipt)
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "INSTALLED"


async def test_failed_receipt_is_recorded_without_advancing(api):
    client, app = api
    auth, candidate_id, release, artifact = await _prepared_candidate(api, sha256="9" * 64)

    failed = install_receipt(
        candidate_id=candidate_id,
        release_id=release["id"],
        version_code=release["versionCode"],
        outcome="FAILED",
        installed_version_code=None,
        message="STATUS_FAILURE_STORAGE",
    )
    recorded = await report_installed(client, auth, candidate_id, failed)
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["status"] == "DOWNLOADED"
    assert recorded.json()["outcome"] == "FAILED"

    # The candidate stays retryable: still listed for the device.
    items = (await client.get("/companion/v2/apk/candidates", headers=auth)).json()["items"]
    assert [item["candidateId"] for item in items] == [candidate_id]
    assert items[0]["status"] == "DOWNLOADED"

    async with app.state.database.unit_of_work() as session:
        receipts = list(
            await session.scalars(
                select(AuditEventRow).where(
                    AuditEventRow.action == "apk.release.install_receipt"
                )
            )
        )
        assert len(receipts) == 1
        assert receipts[0].metadata_json["receipt"]["outcome"] == "FAILED"
        assert receipts[0].metadata_json["receipt"]["message"] == "STATUS_FAILURE_STORAGE"

    # A later successful retry still advances (failure never wedges the pin).
    success = install_receipt(
        candidate_id=candidate_id,
        release_id=release["id"],
        version_code=release["versionCode"],
        installed_version_code=release["versionCode"],
        signature_matched=True,
    )
    accepted = await report_installed(client, auth, candidate_id, success)
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "INSTALLED"


async def test_signature_mismatch_receipt_is_recorded_but_never_success(api):
    client, app = api
    auth, candidate_id, release, artifact = await _prepared_candidate(api, sha256="a" * 64)

    mismatch = install_receipt(
        candidate_id=candidate_id,
        release_id=release["id"],
        version_code=release["versionCode"],
        installed_version_code=release["versionCode"],
        signature_matched=False,
        message="installer signature does not match release",
    )
    recorded = await report_installed(client, auth, candidate_id, mismatch)
    assert recorded.status_code == 200, recorded.text
    # Recorded in the audit trail ...
    async with app.state.database.unit_of_work() as session:
        receipts = list(
            await session.scalars(
                select(AuditEventRow).where(
                    AuditEventRow.action == "apk.release.install_receipt"
                )
            )
        )
        assert len(receipts) == 1
        assert receipts[0].metadata_json["receipt"]["signatureMatched"] is False
    # ... but never counted as an install success.
    assert recorded.json()["status"] == "DOWNLOADED"
    items = (await client.get("/companion/v2/apk/candidates", headers=auth)).json()["items"]
    assert items[0]["status"] == "DOWNLOADED"

    # A receipt with an unknown signature verdict (null) still counts.
    unverifiable = install_receipt(
        candidate_id=candidate_id,
        release_id=release["id"],
        version_code=release["versionCode"],
        installed_version_code=release["versionCode"],
        signature_matched=None,
    )
    accepted = await report_installed(client, auth, candidate_id, unverifiable)
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "INSTALLED"


async def test_install_receipt_identity_mismatch_is_rejected(api):
    client, app = api
    auth, candidate_id, release, artifact = await _prepared_candidate(api, sha256="b" * 64)

    wrong_release = install_receipt(
        candidate_id=candidate_id,
        release_id=str(uuid.uuid4()),
        version_code=release["versionCode"],
    )
    rejected = await report_installed(client, auth, candidate_id, wrong_release)
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "APK_RECEIPT_MISMATCH"

    wrong_version = install_receipt(
        candidate_id=candidate_id,
        release_id=release["id"],
        version_code=release["versionCode"] + 1,
    )
    assert (
        await report_installed(client, auth, candidate_id, wrong_version)
    ).status_code == 422

    unknown_outcome = install_receipt(
        candidate_id=candidate_id,
        release_id=release["id"],
        version_code=release["versionCode"],
        outcome="MAYBE",
    )
    assert (
        await report_installed(client, auth, candidate_id, unknown_outcome)
    ).status_code == 422

    naive_completed_at = install_receipt(
        candidate_id=candidate_id,
        release_id=release["id"],
        version_code=release["versionCode"],
    ) | {"completedAt": "not-an-instant"}
    assert (
        await report_installed(client, auth, candidate_id, naive_completed_at)
    ).status_code == 422

    # Nothing was mutated by the rejected attempts.
    items = (await client.get("/companion/v2/apk/candidates", headers=auth)).json()["items"]
    assert items[0]["status"] == "DOWNLOADED"
    async with app.state.database.unit_of_work() as session:
        receipts = list(
            await session.scalars(
                select(AuditEventRow).where(
                    AuditEventRow.action.in_(
                        ("apk.release.installed", "apk.release.install_receipt")
                    )
                )
            )
        )
        assert receipts == []
