from __future__ import annotations

import asyncio
import hashlib
import sys
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from google.protobuf.json_format import ParseDict

ROOT = Path(__file__).parents[1]
for source in (
    "packages/edge-protocol/src",
    "packages/lamda-driver/src",
    "packages/automation-sdk/src",
    "edge/gateway/src",
):
    sys.path.insert(0, str(ROOT / source))

from cloudctl_automation_sdk import CapabilityDenied, ReconcileResult, SwipeDirection
from cloudctl_edge.cache import ArtifactCache
from cloudctl_edge.executor import LocalArtifactSource, SafeRunnerExecutor, _AutomationDriverAdapter
from cloudctl_edge.runner import HardwareBlockedError, RunnerSupervisor
from cloudctl_edge.scheduler import CommandScheduler
from cloudctl_edge.spool import EdgeSpool
from cloudctl_edge_protocol import edge_control_pb2 as pb
from cloudctl_lamda_driver import InstallResult, Locator, LocatorCandidate


class FakeDriver:
    def __init__(self, capabilities: dict[str, bool] | None = None) -> None:
        self.files: dict[str, bytes] = {}
        self.installed: list[str] = []
        self.stopped: list[str] = []
        self.started: list[str] = []
        self.taps: list[str] = []
        self.text_inputs: list[tuple[str, str, bool]] = []
        self.swipes: list[tuple[str, str, int]] = []
        self._capabilities = capabilities

    def get_capabilities(self):
        if self._capabilities is not None:
            return self._capabilities
        return {
            "ui_automation": True,
            "fixture": True,
            "ui.selectors": True,
            "app.lifecycle": True,
            "file.push": True,
            "screenshot": True,
            "ui.dump": True,
            "input.tap": True,
            "input.text": True,
            "input.swipe": True,
            "evidence.capture": True,
        }

    def start_app(self, package: str) -> None:
        self.started.append(package)

    def selector(self, locator: Locator):
        return FakeElement(locator.name)

    def tap(self, locator: Locator) -> None:
        self.taps.append(locator.name)

    def input_text(self, locator: Locator, text: str, *, replace: bool = True) -> None:
        self.text_inputs.append((locator.name, text, replace))

    def swipe(self, locator: Locator, direction: str, *, steps: int = 32) -> None:
        self.swipes.append((locator.name, direction, steps))

    def screenshot(self) -> bytes:
        return b"fixture screenshot"

    def dump_ui(self) -> str:
        return "<hierarchy />"

    def push_file(self, source, remote_path: str, sha256: str) -> None:
        payload = source.read()
        assert hashlib.sha256(payload).hexdigest() == sha256
        self.files[remote_path] = payload

    def install_apk_session(self, artifacts, options):
        assert all(part.path.is_file() for part in artifacts)
        self.installed.append(options.package_name)
        return InstallResult(
            package_name=options.package_name,
            version_name=options.version_name,
            version_code=options.version_code,
            state="SUCCEEDED",
            session_id="fixture-session",
        )

    def stop_app(self, package: str) -> None:
        self.stopped.append(package)


class FakeElement:
    def __init__(self, name: str) -> None:
        self._name = name

    def exists(self) -> bool:
        return True

    def text(self) -> str:
        return "published" if self._name == "publish_success" else "ready"


class PublishAutomation:
    def __init__(self) -> None:
        self.stages: list[str] = []

    async def validate(self, context) -> None:
        self.stages.append("validate")

    async def preflight(self, driver, context) -> None:
        self.stages.append("preflight")
        await driver.app_start("com.company.approved")
        assert await driver.observe("content") is not None

    async def prepare(self, driver, context) -> None:
        self.stages.append("prepare")
        await driver.input_text("content", "approved body", replace=True)
        await driver.swipe("content", SwipeDirection.UP, steps=32)

    async def before_commit(self, driver, context) -> None:
        self.stages.append("before_commit")
        await driver.screenshot("before-commit")

    async def commit_once(self, driver, context) -> None:
        self.stages.append("commit_once")
        await driver.tap("publish")

    async def reconcile(self, driver, context) -> ReconcileResult:
        self.stages.append("reconcile")
        return (
            ReconcileResult.SUCCEEDED
            if await driver.observe("publish_success") is not None
            else ReconcileResult.UNKNOWN
        )

    async def cleanup(self, driver, context) -> None:
        self.stages.append("cleanup")


def command(command_type: str, *, payload: dict[str, object] | None = None) -> pb.StartCommand:
    value = pb.StartCommand(
        command_id=f"command-{command_type.lower()}",
        task_run_id=f"task-{command_type.lower()}",
        device_id="device-a",
        lease_id="lease-a",
        fencing_token=1,
        command_type=command_type,
    )
    value.deadline.FromDatetime(datetime.now(UTC) + timedelta(minutes=1))
    ParseDict(payload or {}, value.payload)
    return value


@pytest.mark.asyncio
async def test_executor_prefetches_pushes_and_installs_verified_artifacts(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    media = b"approved media"
    apk = b"approved apk"
    (staging / "approved").mkdir(parents=True)
    (staging / "approved/media.bin").write_bytes(media)
    (staging / "approved/app.apk").write_bytes(apk)
    driver = FakeDriver()

    @contextmanager
    def sessions(_command: pb.StartCommand):
        yield driver

    deliveries: list[pb.ArtifactDeliveryEvent] = []

    async def delivery_sink(event: pb.ArtifactDeliveryEvent) -> None:
        deliveries.append(event)

    executor = SafeRunnerExecutor(
        cache=ArtifactCache(tmp_path / "cache"),
        artifact_source=LocalArtifactSource(staging),
        session_factory=sessions,
        delivery_sink=delivery_sink,
        spool=EdgeSpool(tmp_path / "spool.sqlite3"),
    )

    push = command("PUSH_MEDIA", payload={"remotePath": "/sdcard/Download/media.bin"})
    push.artifacts.add(
        object_key="approved/media.bin",
        sha256=hashlib.sha256(media).hexdigest(),
        size=len(media),
        kind="MEDIA",
        file_name="media.bin",
    )
    await executor.execute(push, asyncio.Event(), lambda _event: asyncio.sleep(0))
    assert driver.files["/sdcard/Download/media.bin"] == media

    install = command(
        "INSTALL_APK",
        payload={
            "packageName": "com.company.approved",
            "versionName": "1.2.3",
            "versionCode": 12,
            "signerSha256": "a" * 64,
        },
    )
    install.artifacts.add(
        object_key="approved/app.apk",
        sha256=hashlib.sha256(apk).hexdigest(),
        size=len(apk),
        kind="APK",
        file_name="app.apk",
        package_name="com.company.approved",
    )
    await executor.execute(install, asyncio.Event(), lambda _event: asyncio.sleep(0))
    assert driver.installed == ["com.company.approved"]
    assert [event.state for event in deliveries].count("VERIFIED") == 2
    assert [event.state for event in deliveries].count("DELIVERED") == 2


@pytest.mark.asyncio
async def test_missing_device_profile_is_persisted_as_blocked_hardware(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")

    @contextmanager
    def no_hardware(_command: pb.StartCommand):
        raise HardwareBlockedError("authorized hardware profile is unavailable")
        yield

    executor = SafeRunnerExecutor(
        cache=ArtifactCache(tmp_path / "cache"),
        artifact_source=LocalArtifactSource(tmp_path / "staging"),
        session_factory=no_hardware,
        spool=spool,
    )
    events: list[pb.TaskEvent] = []

    async def sink(event: pb.TaskEvent) -> None:
        events.append(event)

    supervisor = RunnerSupervisor(spool, executor, sink)
    scheduler = CommandScheduler(spool, supervisor)
    collect = command("COLLECT_HEALTH")
    assert scheduler.receive(collect).state == "RECEIVED"
    assert (await scheduler.dispatch(collect)).state == "STARTED"
    await supervisor.wait("device-a")
    assert spool.command_state(collect.command_id) == "BLOCKED_HARDWARE"
    assert events[-1].state == "BLOCKED_HARDWARE"


@pytest.mark.asyncio
async def test_executor_runs_python_sdk_lifecycle_through_scoped_input(tmp_path: Path) -> None:
    driver = FakeDriver()
    package = PublishAutomation()

    @contextmanager
    def sessions(_command: pb.StartCommand):
        yield driver

    locators = {
        name: Locator(
            name=name,
            primary=LocatorCandidate("resource_id", {"resourceId": f"com.target:id/{name}"}),
        )
        for name in ("content", "publish", "publish_success")
    }
    executor = SafeRunnerExecutor(
        cache=ArtifactCache(tmp_path / "cache"),
        artifact_source=LocalArtifactSource(tmp_path / "staging"),
        session_factory=sessions,
        spool=EdgeSpool(tmp_path / "spool.sqlite3"),
        automation_registry={"publish.py": package},
        locator_registry=locators,
    )
    run = command(
        "RUN_AUTOMATION",
        payload={
            "automationName": "publish.py",
            "tenantId": "tenant-a",
            "targetId": "target-a",
            "snapshotSha256": "a" * 64,
            "commitIntentId": "intent-a",
            "parameters": {"body": "approved body"},
        },
    )
    events: list[pb.TaskEvent] = []

    async def sink(event: pb.TaskEvent) -> None:
        events.append(event)

    await executor.execute(run, asyncio.Event(), sink)

    assert package.stages == [
        "validate",
        "preflight",
        "prepare",
        "before_commit",
        "commit_once",
        "reconcile",
        "cleanup",
    ]
    assert driver.started == ["com.company.approved"]
    assert driver.text_inputs == [("content", "approved body", True)]
    assert driver.swipes == [("content", "UP", 32)]
    assert driver.taps == ["publish"]
    assert events[-1].state == "SUCCEEDED"


@pytest.mark.asyncio
async def test_legacy_select_cannot_bypass_input_tap_capability(tmp_path: Path) -> None:
    driver = FakeDriver({"ui.selectors": True, "input.tap": False})
    locator = Locator(
        name="publish",
        primary=LocatorCandidate("resource_id", {"resourceId": "com.target:id/publish"}),
    )
    adapter = _AutomationDriverAdapter(
        driver=driver,
        cache=ArtifactCache(tmp_path / "cache"),
        locators={"publish": locator},
    )

    with pytest.raises(CapabilityDenied, match="input.tap"):
        await adapter.select("publish")
    assert driver.taps == []


@pytest.mark.asyncio
async def test_adapter_denies_unauthorized_reads_and_writes_before_device_io(
    tmp_path: Path,
) -> None:
    driver = FakeDriver({})
    locator = Locator(
        name="content",
        primary=LocatorCandidate("resource_id", {"resourceId": "com.target:id/content"}),
    )
    adapter = _AutomationDriverAdapter(
        driver=driver,
        cache=ArtifactCache(tmp_path / "cache"),
        locators={"content": locator},
    )

    operations = (
        adapter.observe("content"),
        adapter.push_file("a" * 64, "/sdcard/Download/file.bin"),
        adapter.screenshot("shot"),
        adapter.dump_ui("layout"),
        adapter.app_start("com.company.approved"),
    )
    for operation in operations:
        with pytest.raises(CapabilityDenied):
            await operation
    assert driver.started == []
    assert driver.files == {}
