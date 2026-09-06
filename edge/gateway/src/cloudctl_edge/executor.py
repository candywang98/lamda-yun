from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractContextManager, asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Protocol

from cloudctl_automation_sdk import (
    APP_LIFECYCLE_CAPABILITY,
    FILE_PUSH_CAPABILITY,
    INPUT_SWIPE_CAPABILITY,
    INPUT_TAP_CAPABILITY,
    INPUT_TEXT_CAPABILITY,
    SCREENSHOT_CAPABILITY,
    UI_DUMP_CAPABILITY,
    UI_SELECTORS_CAPABILITY,
    AutomationContext,
    AutomationPackage,
    CapabilityDenied,
    LifecycleRunner,
    ReconcileResult,
    SwipeDirection,
    require_capability,
    validate_input_text,
    validate_locator_name,
    validate_swipe,
)
from cloudctl_edge_protocol import edge_control_pb2 as pb
from cloudctl_lamda_driver import ApkPart, InstallOptions, Locator
from cloudctl_lamda_driver.protocols import DeviceDriver
from google.protobuf.json_format import MessageToDict, ParseDict

from .cache import ArtifactCache, ArtifactError
from .runner import EventSink, HardwareBlockedError
from .spool import EdgeSpool


class ExecutorError(RuntimeError):
    pass


class ArtifactSource(Protocol):
    def open(self, artifact: pb.ArtifactRef) -> BinaryIO: ...


class DeviceSessionFactory(Protocol):
    def __call__(self, command: pb.StartCommand) -> AbstractContextManager[DeviceDriver]: ...


DeliverySink = Callable[[pb.ArtifactDeliveryEvent], Awaitable[None]]


class LocalArtifactSource:
    """Read-only staging source with canonical object-key containment checks."""

    def __init__(self, root: Path):
        self._root = root.resolve()

    def open(self, artifact: pb.ArtifactRef) -> BinaryIO:
        candidate = (self._root / artifact.object_key).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise ArtifactError("artifact object key escapes the staging root") from exc
        if not candidate.is_file():
            raise FileNotFoundError(artifact.object_key)
        return candidate.open("rb")


class SafeRunnerExecutor:
    """Allowlisted command executor; it exposes no arbitrary process or script surface."""

    def __init__(
        self,
        *,
        cache: ArtifactCache,
        artifact_source: ArtifactSource,
        session_factory: DeviceSessionFactory,
        spool: EdgeSpool,
        delivery_sink: DeliverySink | None = None,
        automation_registry: Mapping[str, AutomationPackage] | None = None,
        locator_registry: Mapping[str, Locator] | None = None,
        allowed_packages: Mapping[str, frozenset[str]] | None = None,
    ) -> None:
        self._cache = cache
        self._artifact_source = artifact_source
        self._session_factory = session_factory
        self._spool = spool
        self._delivery_sink = delivery_sink
        self._automation_registry = dict(automation_registry or {})
        self._locator_registry = dict(locator_registry or {})
        self._allowed_packages = allowed_packages

    async def execute(
        self,
        command: pb.StartCommand,
        cancel_event: asyncio.Event,
        event_sink: EventSink,
    ) -> None:
        handlers = {
            "COLLECT_HEALTH": self._collect_health,
            "PREFETCH_ARTIFACTS": self._prefetch,
            "PUSH_MEDIA": self._push_media,
            "INSTALL_APK": self._install_apk,
            "RUN_AUTOMATION": self._run_automation,
            "STOP_AUTOMATION": self._stop_automation,
        }
        handler = handlers.get(command.command_type)
        if handler is None:
            raise ExecutorError("command type is not on the executor allowlist")
        self._check_canceled(cancel_event)
        await handler(command, cancel_event, event_sink)

    async def _prefetch(
        self, command: pb.StartCommand, cancel_event: asyncio.Event, _event_sink: EventSink
    ) -> None:
        for artifact in command.artifacts:
            self._check_canceled(cancel_event)
            await self._fetch(command, artifact)
            await self._emit_delivery(command, artifact, "DELIVERED", artifact.size)

    async def _push_media(
        self, command: pb.StartCommand, cancel_event: asyncio.Event, _event_sink: EventSink
    ) -> None:
        payload = self._payload(command)
        destinations = payload.get("destinations")
        async with self._device(command) as driver:
            for artifact in command.artifacts:
                self._check_canceled(cancel_event)
                path = await self._fetch(command, artifact)
                remote_path = payload.get("remotePath")
                if isinstance(destinations, dict):
                    remote_path = destinations.get(artifact.object_key)
                if not isinstance(remote_path, str):
                    raise ExecutorError("PUSH_MEDIA requires a remotePath for every artifact")
                self._validate_remote_path(remote_path)
                with path.open("rb") as source:
                    await asyncio.to_thread(driver.push_file, source, remote_path, artifact.sha256)
                await self._emit_delivery(command, artifact, "DELIVERED", artifact.size)

    async def _install_apk(
        self, command: pb.StartCommand, cancel_event: asyncio.Event, _event_sink: EventSink
    ) -> None:
        payload = self._payload(command)
        package_name = self._required_string(payload, "packageName")
        self._require_package_allowed(command.device_id, package_name)
        signer_sha256 = self._required_digest(payload, "signerSha256")
        version_name = self._required_string(payload, "versionName")
        version_code = self._required_positive_int(payload, "versionCode")
        parts: list[ApkPart] = []
        for artifact in command.artifacts:
            self._check_canceled(cancel_event)
            if artifact.package_name and artifact.package_name != package_name:
                raise ExecutorError("APK artifact package does not match the approved command")
            path = await self._fetch(command, artifact)
            parts.append(
                ApkPart(
                    path=path,
                    sha256=artifact.sha256,
                    size=artifact.size,
                    split_name=artifact.split_name or None,
                )
            )
        options = InstallOptions(
            package_name=package_name,
            version_name=version_name,
            version_code=version_code,
            signer_sha256=signer_sha256,
            allow_downgrade=bool(payload.get("allowDowngrade", False)),
            user_confirmation_allowed=bool(payload.get("userConfirmationAllowed", True)),
        )
        async with self._device(command) as driver:
            self._check_canceled(cancel_event)
            await asyncio.to_thread(driver.install_apk_session, parts, options)
        for artifact in command.artifacts:
            await self._emit_delivery(command, artifact, "DELIVERED", artifact.size)

    async def _collect_health(
        self, command: pb.StartCommand, cancel_event: asyncio.Event, event_sink: EventSink
    ) -> None:
        async with self._device(command) as driver:
            self._check_canceled(cancel_event)
            capabilities = dict(await asyncio.to_thread(driver.get_capabilities))
        health = self._spool.get_device_health(command.device_id) or {}
        health.update(
            {
                "device_id": command.device_id,
                "state": "HEALTHY",
                "lamda_state": "HEALTHY",
                "capabilities": capabilities,
            }
        )
        self._spool.put_device_health(command.device_id, health)
        event = pb.TaskEvent(
            command_id=command.command_id,
            task_run_id=command.task_run_id,
            step="collect_health",
            state="SUCCEEDED",
        )
        event.occurred_at.FromDatetime(datetime.now(UTC))
        ParseDict({"capabilities": capabilities}, event.attributes)
        await event_sink(event)

    async def _stop_automation(
        self, command: pb.StartCommand, cancel_event: asyncio.Event, _event_sink: EventSink
    ) -> None:
        package_name = self._required_string(self._payload(command), "packageName")
        self._require_package_allowed(command.device_id, package_name)
        async with self._device(command) as driver:
            self._check_canceled(cancel_event)
            await asyncio.to_thread(driver.stop_app, package_name)
        health = self._spool.get_device_health(command.device_id) or {}
        health["automation_stopped"] = True
        self._spool.put_device_health(command.device_id, health)

    async def _run_automation(
        self, command: pb.StartCommand, cancel_event: asyncio.Event, event_sink: EventSink
    ) -> None:
        payload = self._payload(command)
        automation_name = self._required_string(payload, "automationName")
        package = self._automation_registry.get(automation_name)
        if package is None:
            raise ExecutorError("automation package is not in the pre-registered allowlist")
        parameters = payload.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ExecutorError("automation parameters must be an object")
        context = AutomationContext(
            tenant_id=self._required_string(payload, "tenantId"),
            target_id=self._required_string(payload, "targetId"),
            snapshot_sha256=self._required_digest(payload, "snapshotSha256"),
            commit_intent_id=self._required_string(payload, "commitIntentId"),
            parameters=parameters,
        )
        for artifact in command.artifacts:
            self._check_canceled(cancel_event)
            await self._fetch(command, artifact)
        async with self._device(command) as driver:
            adapter = _AutomationDriverAdapter(
                driver=driver,
                cache=self._cache,
                locators=self._locator_registry,
            )
            result = await LifecycleRunner(package, adapter).run(context)
        if result is not ReconcileResult.SUCCEEDED:
            raise ExecutorError(f"automation reconciliation ended in {result.value}")
        event = pb.TaskEvent(
            command_id=command.command_id,
            task_run_id=command.task_run_id,
            step="reconcile",
            state="SUCCEEDED",
        )
        event.occurred_at.FromDatetime(datetime.now(UTC))
        await event_sink(event)

    async def _fetch(self, command: pb.StartCommand, artifact: pb.ArtifactRef) -> Path:
        self._validate_artifact(artifact)
        try:
            path = await asyncio.to_thread(self._cache.get, artifact.sha256)
        except FileNotFoundError:
            await self._emit_delivery(command, artifact, "DOWNLOADING", 0)
            try:
                source = await asyncio.to_thread(self._artifact_source.open, artifact)
                try:
                    path = await asyncio.to_thread(
                        self._cache.put,
                        source,
                        expected_sha256=artifact.sha256,
                        expected_size=artifact.size,
                    )
                finally:
                    source.close()
            except Exception:
                await self._emit_delivery(
                    command, artifact, "FAILED", 0, error_code="EDGE_ARTIFACT_VERIFY_FAILED"
                )
                raise
        await self._emit_delivery(command, artifact, "VERIFIED", artifact.size)
        return path

    async def _emit_delivery(
        self,
        command: pb.StartCommand,
        artifact: pb.ArtifactRef,
        state: str,
        bytes_received: int,
        *,
        error_code: str = "",
    ) -> None:
        event = pb.ArtifactDeliveryEvent(
            command_id=command.command_id,
            task_run_id=command.task_run_id,
            device_id=command.device_id,
            artifact=artifact,
            state=state,
            bytes_received=bytes_received,
            error_code=error_code,
        )
        event.occurred_at.FromDatetime(datetime.now(UTC))
        self._spool.put_artifact_delivery(event)
        if self._delivery_sink is not None:
            await self._delivery_sink(event)

    @asynccontextmanager
    async def _device(self, command: pb.StartCommand) -> AsyncIterator[DeviceDriver]:
        context = self._session_factory(command)
        try:
            driver = await asyncio.to_thread(context.__enter__)
        except HardwareBlockedError:
            raise
        except FileNotFoundError as exc:
            raise HardwareBlockedError(
                "authorized device profile or certificate is unavailable"
            ) from exc
        try:
            yield driver
        finally:
            await asyncio.to_thread(context.__exit__, None, None, None)

    def _require_package_allowed(self, device_id: str, package_name: str) -> None:
        if self._allowed_packages is None:
            return
        allowed = self._allowed_packages.get(device_id, frozenset())
        if package_name not in allowed:
            raise ExecutorError("package is not approved by the device profile")

    @staticmethod
    def _payload(command: pb.StartCommand) -> dict[str, object]:
        value = MessageToDict(command.payload)
        if not isinstance(value, dict):
            raise ExecutorError("command payload must be an object")
        return value

    @staticmethod
    def _required_string(payload: Mapping[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value or len(value) > 512:
            raise ExecutorError(f"{key} is required")
        return value

    @classmethod
    def _required_digest(cls, payload: Mapping[str, object], key: str) -> str:
        value = cls._required_string(payload, key).lower()
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ExecutorError(f"{key} must be a SHA256 digest")
        return value

    @staticmethod
    def _required_positive_int(payload: Mapping[str, object], key: str) -> int:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float) or int(value) != value:
            raise ExecutorError(f"{key} must be an integer")
        result = int(value)
        if result < 1:
            raise ExecutorError(f"{key} must be positive")
        return result

    @staticmethod
    def _validate_artifact(artifact: pb.ArtifactRef) -> None:
        key_parts = artifact.object_key.replace("\\", "/").split("/")
        if any(part in {"", ".", ".."} for part in key_parts):
            raise ArtifactError("artifact object key is not canonical")
        digest = artifact.sha256.lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ArtifactError("artifact SHA256 is invalid")
        if artifact.size < 0:
            raise ArtifactError("artifact size is invalid")

    @staticmethod
    def _validate_remote_path(remote_path: str) -> None:
        if not remote_path.startswith("/") or any(
            part in {"", ".", ".."} for part in remote_path.split("/")[1:]
        ):
            raise ExecutorError("remote path must be absolute, canonical and traversal-free")

    @staticmethod
    def _check_canceled(cancel_event: asyncio.Event) -> None:
        if cancel_event.is_set():
            raise asyncio.CancelledError


class _AutomationDriverAdapter:
    def __init__(
        self,
        *,
        driver: DeviceDriver,
        cache: ArtifactCache,
        locators: Mapping[str, Locator],
    ) -> None:
        self._driver = driver
        self._cache = cache
        self._locators = locators
        capability_map = driver.get_capabilities()
        self.capabilities = frozenset(
            name for name, enabled in capability_map.items() if enabled is True
        )

    async def observe(self, locator: str) -> dict[str, object] | None:
        require_capability(self.capabilities, UI_SELECTORS_CAPABILITY)
        resolved = self._locator(locator)
        try:
            element = await asyncio.to_thread(self._driver.selector, resolved)
        except LookupError:
            return None
        return {
            "exists": await asyncio.to_thread(element.exists),
            "text": await asyncio.to_thread(element.text),
        }

    async def select(self, locator: str) -> None:
        # Backward-compatible alias. It must never bypass the input.tap gate.
        await self.tap(locator)

    async def tap(self, locator: str) -> None:
        require_capability(self.capabilities, INPUT_TAP_CAPABILITY)
        await asyncio.to_thread(self._driver.tap, self._locator(locator))

    async def input_text(self, locator: str, text: str, *, replace: bool = True) -> None:
        require_capability(self.capabilities, INPUT_TEXT_CAPABILITY)
        validated_text = validate_input_text(text)
        await asyncio.to_thread(
            self._driver.input_text,
            self._locator(locator),
            validated_text,
            replace=replace,
        )

    async def swipe(
        self,
        locator: str,
        direction: SwipeDirection,
        *,
        steps: int = 32,
    ) -> None:
        require_capability(self.capabilities, INPUT_SWIPE_CAPABILITY)
        validated_direction, validated_steps = validate_swipe(direction, steps)
        await asyncio.to_thread(
            self._driver.swipe,
            self._locator(locator),
            validated_direction.value,
            steps=validated_steps,
        )

    async def push_file(self, artifact_ref: str, destination: str) -> None:
        require_capability(self.capabilities, FILE_PUSH_CAPABILITY)
        SafeRunnerExecutor._validate_remote_path(destination)
        path = await asyncio.to_thread(self._cache.get, artifact_ref)
        with path.open("rb") as source:
            await asyncio.to_thread(self._driver.push_file, source, destination, artifact_ref)

    async def screenshot(self, label: str) -> str:
        require_capability(self.capabilities, SCREENSHOT_CAPABILITY)
        del label
        payload = await asyncio.to_thread(self._driver.screenshot)
        return hashlib.sha256(payload).hexdigest()

    async def dump_ui(self, label: str) -> str:
        require_capability(self.capabilities, UI_DUMP_CAPABILITY)
        del label
        payload = await asyncio.to_thread(self._driver.dump_ui)
        return hashlib.sha256(payload.encode()).hexdigest()

    async def app_start(self, package_name: str) -> None:
        require_capability(self.capabilities, APP_LIFECYCLE_CAPABILITY)
        await asyncio.to_thread(self._driver.start_app, package_name)

    async def register_watcher(
        self,
        name: str,
        locator: str,
        callback: Callable[[], Awaitable[None]],
    ) -> None:
        del name, locator, callback
        raise CapabilityDenied("watchers are not enabled by this Edge runtime profile")

    async def clear_watchers(self) -> None:
        return None

    def _locator(self, name: str) -> Locator:
        validate_locator_name(name)
        try:
            return self._locators[name]
        except KeyError as exc:
            raise CapabilityDenied("locator is not in the signed runtime registry") from exc
