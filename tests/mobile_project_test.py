from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_companion_has_separate_package_and_required_visible_controls() -> None:
    build = (ROOT / "mobile/companion/app/build.gradle.kts").read_text(encoding="utf-8")
    activity = next((ROOT / "mobile/companion/app/src/main/java").rglob("MainActivity.kt"))
    source = activity.read_text(encoding="utf-8")
    assert 'applicationId = "com.company.cloudctl.companion"' in build
    for label in ("Device enrollment", "Stop automation", "Device health", "Permissions"):
        assert label in source
    assert "65000" not in source
    assert "blocked_hardware" in (ROOT / "mobile/companion/VERIFICATION.md").read_text()


def test_dpc_is_separate_and_device_owner_gated() -> None:
    build = (ROOT / "mobile/dpc/app/build.gradle.kts").read_text(encoding="utf-8")
    controller = next((ROOT / "mobile/dpc/app/src/main/java").rglob("PolicyController.kt"))
    source = controller.read_text(encoding="utf-8")
    assert 'applicationId = "com.company.cloudctl.dpc"' in build
    assert "isDeviceOwnerApp" in source
    assert "DISALLOW_DEBUGGING_FEATURES" in source
    assert "blocked_hardware" in (ROOT / "mobile/dpc/VERIFICATION.md").read_text()


def test_mobile_projects_never_embed_dynamic_script_execution() -> None:
    prohibited = ("Runtime.getRuntime().exec", "ProcessBuilder", "DexClassLoader", "WebView")
    for source in (ROOT / "mobile").rglob("*.kt"):
        content = source.read_text(encoding="utf-8")
        assert not any(term in content for term in prohibited), source


def test_companion_uses_typed_task_delivery_and_confirmation_contracts() -> None:
    source_root = ROOT / "mobile/companion/app/src/main/java"
    models = next(source_root.rglob("Models.kt")).read_text(encoding="utf-8")
    client = next(source_root.rglob("CloudTaskClient.kt")).read_text(encoding="utf-8")
    repository = next(source_root.rglob("CompanionRepository.kt")).read_text(encoding="utf-8")
    activity = next(source_root.rglob("MainActivity.kt")).read_text(encoding="utf-8")

    for contract in (
        "AuthorizedTaskStatus",
        "AuthorizedTaskState",
        "ArtifactDeliveryStatus",
        "ArtifactDeliveryState",
        "ArtifactKind",
        "ConfirmationRiskLevel",
    ):
        assert contract in models
    assert "val currentTask: String?" not in models
    assert '"/companion/v2/tasks/claim"' in client
    assert '"/companion/v2/tasks/$taskId/heartbeat"' in client
    assert '"/companion/v2/devices/heartbeat"' in client
    service_kt = next(source_root.rglob("CompanionSyncService.kt")).read_text(encoding="utf-8")
    assert "batteryOptimizationIgnored" in service_kt
    manifest_xml = (ROOT / "mobile/companion/app/src/main/AndroidManifest.xml").read_text(
        encoding="utf-8"
    )
    assert "REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" in manifest_xml
    assert "USER_UNLOCKED" in manifest_xml
    assert '"Authorization" to "Bearer' in client
    assert "runtimeStatusStore.snapshot()" in repository
    assert "task = runtime.task" in repository
    assert "logs = runtime.logs" in repository
    for label in ("Authorized task", "Artifact delivery", "Cancellable", "Risk"):
        assert label in activity


def test_companion_requests_notifications_and_refreshes_periodically() -> None:
    source_root = ROOT / "mobile/companion/app/src/main/java"
    activity = next(source_root.rglob("MainActivity.kt")).read_text(encoding="utf-8")
    view_model = next(source_root.rglob("CompanionViewModel.kt")).read_text(encoding="utf-8")
    repository = next(source_root.rglob("CompanionRepository.kt")).read_text(encoding="utf-8")

    assert "ActivityResultContracts.RequestPermission" in activity
    assert "POST_NOTIFICATIONS" in activity
    assert "delay(" in view_model
    assert "isActive" in view_model
    assert "permissions = permissionState()" in repository
    assert "fun refreshLocalStatus()" in repository
    assert "health = healthCollector.collect()" in repository
    assert "refreshLocal = ::refreshLocalStatus" in repository
    assert "ServiceState.Healthy" not in repository


def test_companion_release_never_uses_the_public_update_test_key() -> None:
    source_root = ROOT / "mobile/companion/app/src/main/java"
    build = (ROOT / "mobile/companion/app/build.gradle.kts").read_text(encoding="utf-8")
    activity = next(source_root.rglob("MainActivity.kt")).read_text(encoding="utf-8")
    repository = next(source_root.rglob("CompanionRepository.kt")).read_text(encoding="utf-8")

    assert "verifyReleaseUpdatePublicKey" in build
    assert "CLOUDCTL_APP_UPDATE_PUBLIC_KEY" in build
    assert "The public RFC 8032 test key cannot be used" in build
    assert "if (canEmergencyStop)" in activity
    assert 'error("Device is not enrolled")' in repository


def test_dpc_handles_provisioning_and_exposes_managed_install_kiosk_contract() -> None:
    source_root = ROOT / "mobile/dpc/app/src/main/java"
    receiver = next(source_root.rglob("CloudCtlDeviceAdminReceiver.kt")).read_text(encoding="utf-8")
    controller = next(source_root.rglob("PolicyController.kt")).read_text(encoding="utf-8")

    assert "onProfileProvisioningComplete" in receiver
    assert "ManagedInstallRequest" in controller
    assert "prepareManagedInstall" in controller
    assert "activateKiosk" in controller
    assert "isLockTaskPermitted" in controller
