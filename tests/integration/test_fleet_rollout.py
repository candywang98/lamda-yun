"""U12 fleet rollout rehearsal: canary rings, dual-version pinning, retreat paths.

This is the *drill layer* over the release stack that U10 (release API),
U11 (device-side install) and WIRE2 (:report-installed receipt loop) merged.
Every test below is a scripted rehearsal step; the operator-facing twin of
each step lives in ``docs/runbooks/fleet-rollout.md`` (section numbers are
cross-referenced in the acceptance map).

Acceptance map (frozen task card U12):

1. 灰度模型 1 canary → 小批(early) → 其余(all)，当前环失败停止扩散：
   test_ring_drill_canary_early_all_records_full_evidence
   test_canary_failure_stops_ring_expansion_and_rollback_restores
2. 双版本共存 + 任务按能力/版本路由 + 暂停任务持有旧版不被清理：
   test_dual_version_coexistence_routes_by_capability_and_version
   test_held_artifacts_of_paused_and_unknown_tasks_survive_withdrawal
3. 演练场景（证书/制品撤回、数据 schema 兼容、失败回退=更高 versionCode
   恢复包、人工安装门）：
   test_mid_rollout_retire_and_schema_containment
   test_canary_failure_stops_ring_expansion_and_rollback_restores
   test_manual_install_gate_blocks_until_user_confirmation
4. runbook：docs/runbooks/fleet-rollout.md（与上述场景一一对应）。
5. P14 Recipe 生命周期只回归受影响路径（版本固定读取）：
   test_recipe_version_pin_read_regression

Evidence rules asserted throughout: every rehearsal step must leave audit
rows carrying BOTH version kinds (APK versionCode + Recipe revision), the
file sha256 (via ``after_hash`` recomputation and the receipt payloads), the
install receipt payload and the concrete device ids.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.apk_policy import canonical_analysis_payload
from cloudctl_api.db import AuditEventRow, DeviceRow, MobileTaskRow
from cloudctl_api.schemas import ApkAnalysisReport
from cloudctl_api.settings import Settings
from cloudctl_automation_sdk import package_signature_payload
from cloudctl_automation_sdk.recipe import canonical_recipe_bytes
from cloudctl_domain import canonical_hash
from fastapi import FastAPI
from sqlalchemy import select
from test_backend_control_api import (
    APK_ANALYSIS_KEY_ID,
    APK_ANALYSIS_PRIVATE_KEY,
    AUTOMATION_KEY_ID,
    AUTOMATION_PRIVATE_KEY,
    CREATOR,
    apk_analysis_public_key,
    automation_public_key,
    headers,
)
from test_p14_recipe_versions import isolated_postgres, pg_url  # noqa: F401
from test_platform_tasks import PROBE, _enroll, bind, create_account, identity

SECURITY = headers(CREATOR, "security_admin")
DEVELOPER = headers(CREATOR, "automation_developer")
PACKAGE = "com.example.target"
BASE_CAPS = {"sdkInt": 32, "abis": ["arm64-v8a"]}


@pytest.fixture(params=["sqlite", "postgres"])
async def api(request):
    """Dual-run rehearsal stage (memory-sqlite + isolated PostgreSQL)."""
    settings = Settings(
        env="test",
        repository_mode="memory",
        dev_auth_bypass=True,
        automation_signing_public_keys={AUTOMATION_KEY_ID: automation_public_key()},
        apk_analysis_public_keys={APK_ANALYSIS_KEY_ID: apk_analysis_public_key()},
    )
    if request.param == "postgres":
        settings = settings.model_copy(
            update={
                "repository_mode": "postgresql",
                "database_url": request.getfixturevalue("pg_url"),
            }
        )
    app = create_app(settings)
    await app.state.database.create_schema()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


# ---------------------------------------------------------------------------
# Rehearsal kit: artifacts, releases, fleets, device install driver
# ---------------------------------------------------------------------------


def artifact_request(*, sha256: str, version_code: int, package: str = PACKAGE) -> dict:
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
    validated = ApkAnalysisReport.model_validate(report).model_dump(mode="json", by_alias=True)
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


async def register_artifact(
    client: httpx.AsyncClient, *, sha256: str, version_code: int
) -> dict:
    response = await client.post(
        "/api/v1/apk-artifacts",
        headers=SECURITY,
        json=artifact_request(sha256=sha256, version_code=version_code),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_release(
    client: httpx.AsyncClient,
    artifact_id: str,
    *,
    ring: str = "all",
    min_capability: dict | None = None,
    data_schema: dict | None = None,
    requires_user_confirmation: bool = True,
) -> dict:
    body = {
        "artifactId": artifact_id,
        "ring": ring,
        "minCapability": min_capability or {},
        "dataSchema": data_schema or {"minCompatible": 1, "current": 2},
        "requiresUserConfirmation": requires_user_confirmation,
    }
    response = await client.post("/api/v1/apk-releases", headers=SECURITY, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def assign_release(
    client: httpx.AsyncClient, release_id: str, devices: list[str]
) -> httpx.Response:
    return await client.post(
        f"/api/v1/apk-releases/{release_id}:assign",
        headers=SECURITY,
        json={"targetDeviceIds": devices},
    )


async def publish_wave(
    client: httpx.AsyncClient,
    *,
    sha256: str,
    version_code: int,
    ring: str,
    devices: list[str],
    **release_kwargs,
) -> dict:
    """One rehearsal wave: register artifact → release → assign ring devices."""
    artifact = await register_artifact(client, sha256=sha256, version_code=version_code)
    release = await create_release(client, artifact["id"], ring=ring, **release_kwargs)
    assigned = await assign_release(client, release["id"], devices)
    assert assigned.status_code == 200, assigned.text
    return release


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


async def ring_fleet(
    api, *, canary: int = 1, early: int = 2, plain: int = 2, caps: dict | None = None
) -> dict[str, list[str]]:
    """Register the rehearsal fleet with ring labels and base capabilities."""
    client, app = api
    fleet: dict[str, list[str]] = {}
    for ring, count, labels in (
        ("canary", canary, ["ring:canary"]),
        ("early", early, ["ring:early"]),
        ("plain", plain, None),
    ):
        fleet[ring] = []
        for index in range(count):
            device = await create_device(client, f"u12-{ring}-{index}", labels=labels)
            await patch_device(app, device, capabilities=dict(caps or BASE_CAPS))
            fleet[ring].append(device)
    return fleet


async def enroll_fleet(api, fleet: dict[str, list[str]]) -> dict[str, dict[str, str]]:
    client, _ = api
    auths: dict[str, dict[str, str]] = {}
    for devices in fleet.values():
        for device in devices:
            auths[device] = await _enroll(client, device, f"u12-{device[:8]}-instance")
    return auths


async def candidates_of(client: httpx.AsyncClient, auth: dict) -> list[dict]:
    return (await client.get("/companion/v2/apk/candidates", headers=auth)).json()["items"]


def install_receipt(
    *,
    candidate_id: str,
    release_id: str,
    version_code: int,
    outcome: str = "INSTALLED",
    installed_version_code: int | None = None,
    signature_matched: bool | None = None,
    message: str | None = None,
) -> dict:
    """WIRE2 wire shape (device-side ApkInstallReceipt.toWireJson)."""
    return {
        "candidateId": candidate_id,
        "releaseId": release_id,
        "packageName": PACKAGE,
        "attemptedVersionCode": version_code,
        "outcome": outcome,
        "installedVersionCode": installed_version_code,
        "signatureMatched": signature_matched,
        "message": message,
        "completedAt": "2026-09-17T00:00:00Z",
    }


async def device_installs(
    api,
    auth: dict,
    device_id: str,
    release: dict,
    *,
    outcome: str = "INSTALLED",
    signature_matched: bool = True,
    message: str | None = None,
    advance_device_version: bool = True,
) -> dict:
    """Drive the U11 device half: pull candidate → download+hash → receipt.

    Mirrors ApkUpdateCoordinator: only an INSTALLED receipt with a non-false
    signatureMatched advances; the device then reports its new version via
    the status path (modelled here by patching target_app_versions).
    """
    client, app = api
    candidate = next(
        item
        for item in await candidates_of(client, auth)
        if item["releaseId"] == release["id"]
    )
    downloaded = await client.post(
        f"/companion/v2/apk/candidates/{candidate['candidateId']}:report-downloaded",
        headers=auth,
        json={"sha256": candidate["sha256"]},
    )
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.json()["sha256"] == release["sha256"]
    receipt = install_receipt(
        candidate_id=candidate["candidateId"],
        release_id=release["id"],
        version_code=release["versionCode"],
        outcome=outcome,
        installed_version_code=release["versionCode"] if outcome == "INSTALLED" else None,
        signature_matched=signature_matched,
        message=message,
    )
    reported = await client.post(
        f"/companion/v2/apk/candidates/{candidate['candidateId']}:report-installed",
        headers=auth,
        json=receipt,
    )
    assert reported.status_code == 200, reported.text
    if outcome == "INSTALLED" and signature_matched is not False and advance_device_version:
        await patch_device(
            app, device_id, target_app_versions={PACKAGE: str(release["versionCode"])}
        )
    return {"candidate": candidate, "receipt": receipt, "response": reported.json()}


async def audit_rows(app: FastAPI, *actions: str) -> list[AuditEventRow]:
    async with app.state.database.unit_of_work() as session:
        return list(
            await session.scalars(select(AuditEventRow).where(AuditEventRow.action.in_(actions)))
        )


def download_evidence_hash(release: dict) -> str:
    """``apk.release.downloaded`` rows hash exactly this after-payload."""
    return canonical_hash({"releaseId": release["id"], "sha256": release["sha256"]})


# ---------------------------------------------------------------------------
# Recipe rehearsal kit (P14 pin-read regression surface)
# ---------------------------------------------------------------------------


def recipe_package(version: str) -> dict:
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
    package["signature"]["digest"] = base64.b64encode(
        AUTOMATION_PRIVATE_KEY.sign(
            package_signature_payload(
                artifact_sha256=package["manifest"]["hash"],
                manifest=package["manifest"],
                sbom_ref="recipe://local",
                sbom_sha256=package["manifest"]["hash"],
            )
        )
    ).decode()
    return package


async def register_recipe(client: httpx.AsyncClient, version: str) -> str:
    response = await client.post(
        "/api/v1/recipes", headers=DEVELOPER, json=recipe_package(version)
    )
    assert response.status_code == 201, response.text
    return str(response.json()["versionId"])


async def recipe_change(
    client: httpx.AsyncClient,
    version_id: str,
    devices: list[str],
    action: str = "publish",
    *,
    key: str | None = None,
    expected: str | None = None,
) -> httpx.Response:
    body = {
        "targetDeviceIds": devices,
        "idempotencyKey": "u12-key-" + (key or str(uuid.uuid4())),
    }
    if expected is not None:
        body["expectedCurrentVersionId"] = expected
    return await client.post(
        f"/api/v1/recipes/{version_id}:{action}", headers=DEVELOPER, json=body
    )


# ---------------------------------------------------------------------------
# Task rehearsal kit
# ---------------------------------------------------------------------------


async def create_probe_task(client: httpx.AsyncClient, device_id: str, suffix: str) -> str:
    account = await create_account(client, f"u12-account-{suffix}")
    await bind(client, account, device_id)
    response = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": f"u12-{suffix}-{uuid.uuid4()}"},
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


async def set_task_state(
    app: FastAPI, task_id: str, *, status: str, business_state: str
) -> None:
    async with app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, task_id)
        assert task is not None
        task.status = status
        task.business_state = business_state


async def expire_lease(app: FastAPI, task_id: str) -> None:
    async with app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, task_id)
        assert task is not None
        task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)


# ---------------------------------------------------------------------------
# Scenario 1 (runbook §3): the happy-path ring drill canary → early → all
# with a complete evidence trail.
# ---------------------------------------------------------------------------


async def test_ring_drill_canary_early_all_records_full_evidence(api):
    client, app = api
    fleet = await ring_fleet(api, canary=1, early=2, plain=2)
    canary, early, plain = fleet["canary"], fleet["early"], fleet["plain"]
    everyone = canary + early + plain
    auths = await enroll_fleet(api, fleet)

    # Recipe revision baseline for the whole fleet (P14 pin-read surface).
    recipe_v1 = await register_recipe(client, "1")
    assert (await recipe_change(client, recipe_v1, everyone, key="v1")).status_code == 200

    # Wave 1 — canary ring (1 device). Install preemption is forbidden while
    # the device is busy (U10 409): the drill settles the live task first.
    wave1 = await publish_wave(
        client, sha256="1" * 64, version_code=83210, ring="canary", devices=canary
    )
    task_id = await create_probe_task(client, canary[0], "drill-canary")
    canary_auth = auths[canary[0]]
    claimed = await claim_probe(client, canary_auth)
    assert claimed["command"]["recipe"]["versionId"] == recipe_v1
    busy = await assign_release(client, wave1["id"], canary)
    assert busy.status_code == 409
    assert busy.json()["code"] == "APK_DEVICE_BUSY"
    await set_task_state(app, task_id, status="SUCCEEDED", business_state="SUCCEEDED")

    done = await device_installs(api, canary_auth, canary[0], wave1)
    assert done["response"]["status"] == "INSTALLED"
    # Ring stop gate (runbook §3): canary is 100% INSTALLED → early may proceed.

    # Wave 2 — early ring (small batch), one of them settling a pinned task
    # before the fleet-wide wave.
    early_task = await create_probe_task(client, early[0], "drill-early")
    early_auth = auths[early[0]]
    assert (
        await claim_probe(client, early_auth)
    )["command"]["recipe"]["versionId"] == recipe_v1
    await set_task_state(app, early_task, status="SUCCEEDED", business_state="SUCCEEDED")
    wave2 = await publish_wave(
        client, sha256="2" * 64, version_code=83211, ring="early", devices=early
    )
    for device in early:
        finished = await device_installs(api, auths[device], device, wave2)
        assert finished["response"]["status"] == "INSTALLED"

    # Recipe revision progresses alongside the APK waves (canary only).
    recipe_v2 = await register_recipe(client, "2")
    assert (await recipe_change(client, recipe_v2, canary, key="v2")).status_code == 200

    # Wave 3 — remaining rings converge on the final build.
    wave3 = await publish_wave(
        client, sha256="3" * 64, version_code=83212, ring="all", devices=everyone
    )
    for device in everyone:
        finished = await device_installs(api, auths[device], device, wave3)
        assert finished["response"]["status"] == "INSTALLED"

    # Per-device version bookkeeping: the fleet converged on the final build.
    async with app.state.database.unit_of_work() as session:
        rows = {
            row.id: row.target_app_versions
            for row in await session.scalars(select(DeviceRow))
            if row.id in set(everyone)
        }
    assert all(rows[device][PACKAGE] == "83212" for device in everyone)

    # Evidence trail (runbook §6): each install left an audit row carrying
    # the APK versionCode + full receipt + concrete device id; each download
    # row's after-hash pins the file sha256; the recipe side recorded its
    # revision on every pinned claim (两类版本号).
    installed = await audit_rows(app, "apk.release.installed")
    downloaded = await audit_rows(app, "apk.release.downloaded")
    published = await audit_rows(app, "apk.release.published")
    assigned = await audit_rows(app, "apk.release.assigned")
    pinned = await audit_rows(app, "recipe.task.pinned")
    recipe_published = await audit_rows(app, "recipe.version.published")

    expected_installed_devices = sorted(everyone + early + canary)
    assert sorted(row.device_id for row in installed) == expected_installed_devices
    for row in installed:
        receipt = row.metadata_json["receipt"]
        assert receipt["attemptedVersionCode"] in {83210, 83211, 83212}
        assert receipt["installedVersionCode"] == receipt["attemptedVersionCode"]
        assert receipt["signatureMatched"] is True
        assert receipt["packageName"] == PACKAGE

    wave_hashes = {
        download_evidence_hash(wave) for wave in (wave1, wave2, wave3)
    }
    assert sorted(row.device_id for row in downloaded) == expected_installed_devices
    for row in downloaded:
        assert row.after_hash in wave_hashes

    assert len(published) == 3
    for wave in (wave1, wave2, wave3):
        row = next(item for item in published if item.resource_id == wave["id"])
        # The published view (versionCode + sha256 evidence chain) is hashed
        # into the audit row verbatim.
        assert row.after_hash == canonical_hash(wave)
    assign_map = {row.resource_id: row for row in assigned}
    for wave, devices in (
        (wave1, canary),
        (wave2, early),
        (wave3, everyone),
    ):
        assert sorted(assign_map[wave["id"]].metadata_json["device_ids"]) == sorted(devices)

    assert {row.metadata_json["recipe"]["versionId"] for row in pinned} == {recipe_v1}
    assert all(row.device_id in set(everyone) for row in pinned)
    assert {row.metadata_json["version_id"] for row in recipe_published} == {
        recipe_v1,
        recipe_v2,
    }
    releases = (await client.get("/api/v1/apk-releases", headers=SECURITY)).json()["items"]
    assert sorted(item["versionCode"] for item in releases) == [83210, 83211, 83212]


# ---------------------------------------------------------------------------
# Scenario 2 (runbook §4): canary failure stops the ring expansion; a higher
# versionCode rollback package restores the old business capability.
# ---------------------------------------------------------------------------


async def test_canary_failure_stops_ring_expansion_and_rollback_restores(api):
    client, app = api
    fleet = await ring_fleet(api, canary=1, early=2, plain=1)
    canary, early, plain = fleet["canary"], fleet["early"], fleet["plain"]
    bystanders = early + plain
    auths = await enroll_fleet(api, fleet)
    canary_auth = auths[canary[0]]

    recipe_v1 = await register_recipe(client, "1")
    assert (
        await recipe_change(client, recipe_v1, canary + early, key="v1")
    ).status_code == 200

    bad = await publish_wave(
        client, sha256="4" * 64, version_code=83301, ring="canary", devices=canary
    )

    # Containment A — single-flight per device+package: while the canary
    # holds an OFFERED candidate, no other release may pile onto it.
    other = await register_artifact(client, sha256="5" * 64, version_code=83302)
    other_release = await create_release(client, other["id"], ring="canary")
    clash = await assign_release(client, other_release["id"], canary)
    assert clash.status_code == 409
    assert clash.json()["code"] == "APK_CANDIDATE_EXISTS"

    # Containment B — the canary release cannot even be aimed at later rings.
    ring_miss = await assign_release(client, bad["id"], early)
    assert ring_miss.status_code == 422
    assert ring_miss.json()["code"] == "APK_RING_MISMATCH"

    # The canary downloads fine but the installer fails (storage full).
    failed = await device_installs(
        api,
        canary_auth,
        canary[0],
        bad,
        outcome="FAILED",
        signature_matched=None,
        message="STATUS_FAILURE_STORAGE",
    )
    assert failed["response"]["status"] == "DOWNLOADED"
    assert failed["response"]["outcome"] == "FAILED"
    # Stop rule (runbook §4): canary < 100% INSTALLED → the early/all waves
    # are never assigned. Bystander devices never saw a candidate.
    for device in bystanders:
        assert await candidates_of(client, auths[device]) == []

    # Old business keeps running on the not-yet-upgraded fleet.
    bystander_task = await create_probe_task(client, early[0], "fail-bystander")
    assert (await claim_probe(client, auths[early[0]]))["taskId"] == bystander_task
    await set_task_state(app, bystander_task, status="SUCCEEDED", business_state="SUCCEEDED")

    # Retreat (runbook §4): retire the bad wave, then ship a HIGHER
    # versionCode package that restores the old logic (低 versionCode 降级
    # 不可承诺 — U11 acceptance).
    retired = await client.post(
        f"/api/v1/apk-releases/{bad['id']}:retire",
        headers=SECURITY,
        json={"reason": "canary install failure drill: stop ring expansion"},
    )
    assert retired.status_code == 200
    assert retired.json()["status"] == "RETIRED"
    assert (await assign_release(client, bad["id"], early)).status_code == 409
    # The failed candidate pin survives the retire (retryable by design) and
    # stays visible with its RETIRED release status.
    stale = await candidates_of(client, canary_auth)
    assert [item["status"] for item in stale] == ["DOWNLOADED"]
    assert stale[0]["releaseStatus"] == "RETIRED"

    rollback = await publish_wave(
        client, sha256="6" * 64, version_code=83400, ring="canary", devices=canary
    )
    restored = await device_installs(api, canary_auth, canary[0], rollback)
    assert restored["response"]["status"] == "INSTALLED"

    # The canary is back on the old business capability: it claims work again
    # with the pinned recipe revision.
    recovery_task = await create_probe_task(client, canary[0], "fail-recovery")
    recovered = await claim_probe(client, canary_auth)
    assert recovered["taskId"] == recovery_task
    assert recovered["command"]["recipe"]["versionId"] == recipe_v1
    await set_task_state(app, recovery_task, status="SUCCEEDED", business_state="SUCCEEDED")

    # Evidence: the FAILED receipt is recorded without ever counting as an
    # install; the rollback install is a normal INSTALLED receipt.
    receipts = await audit_rows(app, "apk.release.install_receipt")
    assert [row.metadata_json["receipt"]["outcome"] for row in receipts] == ["FAILED"]
    assert receipts[0].metadata_json["receipt"]["message"] == "STATUS_FAILURE_STORAGE"
    assert receipts[0].device_id == canary[0]
    installed = await audit_rows(app, "apk.release.installed")
    assert [row.device_id for row in installed] == [canary[0]]
    assert installed[0].metadata_json["receipt"]["attemptedVersionCode"] == 83400
    retired_audit = await audit_rows(app, "apk.release.retired")
    assert (
        retired_audit[0].metadata_json["reason"]
        == "canary install failure drill: stop ring expansion"
    )


# ---------------------------------------------------------------------------
# Scenario 3 (runbook §5): dual-version coexistence with capability/version
# routing.
# ---------------------------------------------------------------------------


async def test_dual_version_coexistence_routes_by_capability_and_version(api):
    client, app = api
    fleet = await ring_fleet(api, canary=2, early=0, plain=2)
    canary, plain = fleet["canary"], fleet["plain"]
    weak = await create_device(client, "u12-weak", labels=["ring:canary"])
    await patch_device(app, weak, capabilities={"sdkInt": 30, "abis": ["arm64-v8a"]})
    everyone = canary + plain + [weak]
    auths = await enroll_fleet(api, {"canary": canary, "plain": plain, "weak": [weak]})

    recipe_v1 = await register_recipe(client, "1")
    assert (await recipe_change(client, recipe_v1, everyone, key="v1")).status_code == 200

    # Generation 1 is the fleet baseline (ring=all).
    gen1 = await publish_wave(
        client, sha256="7" * 64, version_code=83201, ring="all", devices=everyone
    )
    for device in everyone:
        finished = await device_installs(api, auths[device], device, gen1)
        assert finished["response"]["status"] == "INSTALLED"

    # Generation 2 ships to the canary ring only, with a capability gate.
    gen2 = await publish_wave(
        client,
        sha256="8" * 64,
        version_code=83202,
        ring="canary",
        devices=canary,
        min_capability={"sdkInt": 31},
    )
    upgraded = await device_installs(api, auths[canary[0]], canary[0], gen2)
    assert upgraded["response"]["status"] == "INSTALLED"

    # Both generations stay ACTIVE simultaneously (dual-version online).
    releases = (await client.get("/api/v1/apk-releases", headers=SECURITY)).json()["items"]
    active = {item["versionCode"]: item["status"] for item in releases}
    assert active == {83201: "ACTIVE", 83202: "ACTIVE"}

    # Capability routing: the weak canary cannot take generation 2 and keeps
    # running generation 1 — no candidate is ever offered to it.
    denied = await assign_release(client, gen2["id"], [weak])
    assert denied.status_code == 422
    assert denied.json()["code"] == "APK_CAPABILITY_INSUFFICIENT"
    assert await candidates_of(client, auths[weak]) == []

    # Version routing: an old-generation package no longer routes to a device
    # that already upgraded (downgrade refused), while a never-upgraded
    # device still accepts the very same release.
    gen1_again_artifact = await register_artifact(client, sha256="9" * 64, version_code=83201)
    gen1_again = await create_release(client, gen1_again_artifact["id"], ring="all")
    downgrade = await assign_release(client, gen1_again["id"], [canary[0]])
    assert downgrade.status_code == 422
    assert downgrade.json()["code"] == "APK_VERSION_DOWNGRADE"
    fresh = await create_device(client, "u12-coexist-fresh")
    await patch_device(app, fresh, capabilities=dict(BASE_CAPS))
    assert (await assign_release(client, gen1_again["id"], [fresh])).status_code == 200

    # Tasks keep routing to both generations during coexistence: the old-APK
    # device and the upgraded device claim the same probe with the same
    # pinned recipe revision.
    old_task = await create_probe_task(client, plain[0], "coexist-old")
    new_task = await create_probe_task(client, canary[0], "coexist-new")
    for device, task in ((plain[0], old_task), (canary[0], new_task)):
        claimed = await claim_probe(client, auths[device])
        assert claimed["taskId"] == task
        assert claimed["command"]["recipe"]["versionId"] == recipe_v1
        await set_task_state(app, task, status="SUCCEEDED", business_state="SUCCEEDED")


# ---------------------------------------------------------------------------
# Scenario 4 (runbook §4): mid-rollout certificate/artifact withdrawal
# (retire) and data schema containment — later rings never receive the waves
# they are not compatible with.
# ---------------------------------------------------------------------------


async def test_mid_rollout_retire_and_schema_containment(api):
    client, app = api
    fleet = await ring_fleet(api, canary=1, early=2, plain=0)
    canary, early = fleet["canary"], fleet["early"]
    legacy = early[1]
    await patch_device(
        app,
        legacy,
        capabilities={"dataSchemaVersions": {PACKAGE: 1}},
    )
    auths = await enroll_fleet(api, fleet)

    recipe_v1 = await register_recipe(client, "1")
    assert (
        await recipe_change(client, recipe_v1, canary + early, key="v1")
    ).status_code == 200

    wave1 = await publish_wave(
        client, sha256="a" * 64, version_code=83501, ring="canary", devices=canary
    )
    finished = await device_installs(api, auths[canary[0]], canary[0], wave1)
    assert finished["response"]["status"] == "INSTALLED"

    # Certificate withdrawal mid-rollout: the wave is retired before any
    # later ring saw it. New assignments are refused everywhere.
    retired = await client.post(
        f"/api/v1/apk-releases/{wave1['id']}:retire",
        headers=SECURITY,
        json={"reason": "signing certificate withdrawn during drill"},
    )
    assert retired.status_code == 200
    assert (await assign_release(client, wave1["id"], early)).status_code == 409
    for device in early:
        assert await candidates_of(client, auths[device]) == []

    # The already-installed canary is untouched and keeps working.
    survivor_task = await create_probe_task(client, canary[0], "retire-survivor")
    assert (await claim_probe(client, auths[canary[0]]))["taskId"] == survivor_task
    await set_task_state(app, survivor_task, status="SUCCEEDED", business_state="SUCCEEDED")

    # The next wave carries a data schema window; the legacy-schema device is
    # excluded (stays on its old APK), the modern one proceeds.
    wave2 = await publish_wave(
        client,
        sha256="b" * 64,
        version_code=83502,
        ring="early",
        devices=[early[0]],
        data_schema={"minCompatible": 2, "current": 3},
    )
    legacy_blocked = await assign_release(client, wave2["id"], [legacy])
    assert legacy_blocked.status_code == 422
    assert legacy_blocked.json()["code"] == "APK_SCHEMA_INCOMPATIBLE"
    assert await candidates_of(client, auths[legacy]) == []
    modern = await device_installs(api, auths[early[0]], early[0], wave2)
    assert modern["response"]["status"] == "INSTALLED"

    # The schema-excluded device keeps its old business capability.
    legacy_task = await create_probe_task(client, legacy, "schema-legacy")
    assert (await claim_probe(client, auths[legacy]))["taskId"] == legacy_task
    await set_task_state(app, legacy_task, status="SUCCEEDED", business_state="SUCCEEDED")


# ---------------------------------------------------------------------------
# Scenario 5 (runbook §3.4): the manual install gate
# (requiresUserConfirmation).
# ---------------------------------------------------------------------------


async def test_manual_install_gate_blocks_until_user_confirmation(api):
    client, app = api
    fleet = await ring_fleet(api, canary=1, early=0, plain=1)
    canary, plain = fleet["canary"], fleet["plain"]
    auths = await enroll_fleet(api, fleet)

    gated = await publish_wave(
        client, sha256="d" * 64, version_code=83601, ring="canary", devices=canary
    )
    ungated = await publish_wave(
        client,
        sha256="e" * 64,
        version_code=83602,
        ring="all",
        devices=plain,
        requires_user_confirmation=False,
    )

    # The gate requirement is surfaced to the device with the candidate.
    offered = await candidates_of(client, auths[canary[0]])
    assert [item["requiresUserConfirmation"] for item in offered] == [True]
    plain_offered = await candidates_of(client, auths[plain[0]])
    assert [item["requiresUserConfirmation"] for item in plain_offered] == [False]

    # Unconfirmed: the device does not download; nothing advances.
    assert [item["status"] for item in offered] == ["OFFERED"]

    # The user declines: a terminal USER_DECLINED receipt is recorded as
    # evidence, but the target never advances (stays retryable at OFFERED).
    declined = install_receipt(
        candidate_id=offered[0]["candidateId"],
        release_id=gated["id"],
        version_code=gated["versionCode"],
        outcome="USER_DECLINED",
        message="owner declined the install",
    )
    recorded = await client.post(
        f"/companion/v2/apk/candidates/{offered[0]['candidateId']}:report-installed",
        headers=auths[canary[0]],
        json=declined,
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["status"] == "OFFERED"
    receipts = await audit_rows(app, "apk.release.install_receipt")
    assert [row.metadata_json["receipt"]["outcome"] for row in receipts] == ["USER_DECLINED"]
    assert await audit_rows(app, "apk.release.installed") == []

    # After the owner confirms, the very same candidate proceeds normally.
    confirmed = await device_installs(api, auths[canary[0]], canary[0], gated)
    assert confirmed["response"]["status"] == "INSTALLED"
    assert await candidates_of(client, auths[canary[0]]) == []

    # The ungated release on the plain device installs without the manual
    # gate (the field is a requirement statement, not a silent-install
    # promise — the device still reports download + receipt).
    plain_done = await device_installs(api, auths[plain[0]], plain[0], ungated)
    assert plain_done["response"]["status"] == "INSTALLED"
    installed = await audit_rows(app, "apk.release.installed")
    assert sorted(row.device_id for row in installed) == sorted(canary + plain)


# ---------------------------------------------------------------------------
# Scenario 6 (runbook §5): PAUSED / UNKNOWN tasks keep their artifact pins
# through certificate withdrawal (release retire + recipe revoke).
# ---------------------------------------------------------------------------


async def test_held_artifacts_of_paused_and_unknown_tasks_survive_withdrawal(api):
    client, app = api
    fleet = await ring_fleet(api, canary=0, early=0, plain=2)
    paused_device, unknown_device = fleet["plain"]
    auths = await enroll_fleet(api, fleet)

    recipe_v1 = await register_recipe(client, "1")
    assert (await recipe_change(client, recipe_v1, fleet["plain"], key="v1")).status_code == 200

    # Candidates are pinned while the tasks are still QUEUED (a RUNNING /
    # PAUSED / RECONCILING task would refuse new install preemption).
    release = await publish_wave(
        client, sha256="f" * 64, version_code=83701, ring="all", devices=fleet["plain"]
    )
    paused_task = await create_probe_task(client, paused_device, "hold-paused")
    unknown_task = await create_probe_task(client, unknown_device, "hold-unknown")
    paused_pin = (await claim_probe(client, auths[paused_device]))["command"]["recipe"]
    unknown_pin = (await claim_probe(client, auths[unknown_device]))["command"]["recipe"]
    assert paused_pin["versionId"] == recipe_v1
    assert unknown_pin["versionId"] == recipe_v1

    await set_task_state(
        app, paused_task, status="RUNNING", business_state="PAUSED_WAITING_USER"
    )
    await set_task_state(app, unknown_task, status="UNKNOWN", business_state="UNKNOWN")

    # Withdrawal storm: retire the APK release and revoke the recipe version.
    assert (
        await client.post(
            f"/api/v1/apk-releases/{release['id']}:retire",
            headers=SECURITY,
            json={"reason": "certificate rotation drill"},
        )
    ).status_code == 200
    assert (
        await recipe_change(client, recipe_v1, fleet["plain"], "revoke", key="revoke")
    ).status_code == 200

    # The APK target pins survive the retire (still offered, RETIRED status).
    for device in fleet["plain"]:
        items = await candidates_of(client, auths[device])
        assert [item["status"] for item in items] == ["OFFERED"]
        assert items[0]["releaseStatus"] == "RETIRED"
        assert items[0]["sha256"] == release["sha256"]

    # The recipe version pins survive the revoke: both holders can still
    # download the pinned bytes with a verifiable content hash.
    for device, pin in ((paused_device, paused_pin), (unknown_device, unknown_pin)):
        download = await client.get(
            f"/companion/v2/recipes/{pin['versionId']}", headers=auths[device]
        )
        assert download.status_code == 200, download.text
        assert len(download.headers["x-content-sha256"]) == 64

    # The stored pins were not cleaned by the withdrawal.
    async with app.state.database.unit_of_work() as session:
        stored_paused = await session.get(MobileTaskRow, paused_task)
        stored_unknown = await session.get(MobileTaskRow, unknown_task)
        assert stored_paused.recipe_pin["versionId"] == recipe_v1
        assert stored_unknown.recipe_pin["versionId"] == recipe_v1

    # Withdrawal does stop the spread: a fresh device cannot join the retired
    # release even though the held pins live on.
    outsider = await create_device(client, "u12-hold-outsider")
    assert (await assign_release(client, release["id"], [outsider])).status_code == 409

    # Pin release is tied to the task lifecycle, not to the withdrawal: once
    # the holders settle, the revoked recipe stops resolving.
    await set_task_state(app, paused_task, status="SUCCEEDED", business_state="SUCCEEDED")
    await set_task_state(app, unknown_task, status="FAILED", business_state="FAILED")
    for device, pin in ((paused_device, paused_pin), (unknown_device, unknown_pin)):
        assert (
            await client.get(f"/companion/v2/recipes/{pin['versionId']}", headers=auths[device])
        ).status_code == 404


# ---------------------------------------------------------------------------
# Scenario 7 (P14 regression, runbook §5): version pin reading only — a
# claimed task keeps reading its pinned recipe revision across publishes and
# revokes until the task reaches a terminal state.
# ---------------------------------------------------------------------------


async def test_recipe_version_pin_read_regression(api):
    client, app = api
    fleet = await ring_fleet(api, canary=0, early=0, plain=1)
    device = fleet["plain"][0]
    auth = (await enroll_fleet(api, fleet))[device]

    v1 = await register_recipe(client, "1")
    v2 = await register_recipe(client, "2")
    assert (await recipe_change(client, v1, [device], key="v1")).status_code == 200
    task_id = await create_probe_task(client, device, "pin-regression")
    first = await claim_probe(client, auth)
    assert first["command"]["recipe"]["versionId"] == v1

    # A newer published revision never steals the pinned read...
    assert (await recipe_change(client, v2, [device], key="v2")).status_code == 200
    async with app.state.database.unit_of_work() as session:
        stored = await session.get(MobileTaskRow, task_id)
        assert stored.recipe_pin["versionId"] == v1
    await expire_lease(app, task_id)
    retry = await claim_probe(client, auth)
    assert retry["command"]["recipe"]["versionId"] == v1
    assert retry["attempt"] == 2

    # ...and a revoke does not clean the pin while the task holds it.
    assert (
        await recipe_change(client, v1, [device], "revoke", key="revoke")
    ).status_code == 200
    assert (await client.get(f"/companion/v2/recipes/{v1}", headers=auth)).status_code == 200
    await set_task_state(app, task_id, status="SUCCEEDED", business_state="SUCCEEDED")
    assert (await client.get(f"/companion/v2/recipes/{v1}", headers=auth)).status_code == 404
