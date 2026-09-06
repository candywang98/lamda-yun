from __future__ import annotations

import asyncio
import json
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import uvicorn
from cloudctl_edge_protocol import edge_control_pb2 as pb
from cloudctl_lamda_driver import (
    DeviceDriverError,
    LamdaSession,
    LamdaSidecarBackend,
    probe_sidecar_runtime,
)

from .adb_debug import AdbDebugError, RestrictedAdbDebugDriver
from .cache import ArtifactCache
from .cert_store import CertificateStore
from .companion_api import CompanionAuthStore, create_companion_app
from .control_stream import EdgeControlStream
from .executor import LocalArtifactSource, SafeRunnerExecutor
from .operator_actions import OperatorActionCoordinator
from .remote_proxy import DebugSessionError, DebugSessionManager, ProxyTarget
from .runner import EventSink, HardwareBlockedError, RunnerSupervisor
from .scheduler import CommandScheduler
from .settings import GatewaySettings, SettingsError
from .spool import EdgeSpool


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    device_id: str
    host: str
    certificate_path: Path
    allowed_packages: frozenset[str]


@dataclass(slots=True)
class GatewayRuntime:
    settings: GatewaySettings
    spool: EdgeSpool
    cache: ArtifactCache
    supervisor: RunnerSupervisor
    scheduler: CommandScheduler
    control_stream: EdgeControlStream
    debug_sessions: DebugSessionManager
    companion_app: Any

    async def run(self) -> None:
        stop_event = asyncio.Event()
        credentials = CertificateStore(self.settings.edge_credentials_dir).read()
        server = uvicorn.Server(
            uvicorn.Config(
                app=self.companion_app,
                host=self.settings.companion_bind_host,
                port=self.settings.companion_bind_port,
                ssl_certfile=str(self.settings.companion_tls_certificate),
                ssl_keyfile=str(self.settings.companion_tls_private_key),
                log_level="info",
            )
        )
        control_task = asyncio.create_task(
            self.control_stream.run_forever(
                endpoint=self.settings.hub_endpoint,
                credentials=credentials,
                stop_event=stop_event,
                tls_server_name=self.settings.hub_tls_server_name,
            ),
            name="edge-control-stream",
        )
        server_task = asyncio.create_task(server.serve(), name="companion-https")
        try:
            done, _pending = await asyncio.wait(
                {control_task, server_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                exception = task.exception()
                if exception is not None:
                    raise exception
        finally:
            stop_event.set()
            server.should_exit = True
            for task in (control_task, server_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(control_task, server_task, return_exceptions=True)
            self.close()

    def close(self) -> None:
        self.cache.close()
        self.spool.close()


class _FenceVerifier:
    def __init__(self, spool: EdgeSpool):
        self._spool = spool

    def verify(self, *, device_id: str, lease_id: str, fencing_token: int) -> None:
        self._spool.assert_current_fence(device_id, lease_id, fencing_token)


class _SessionFactory:
    def __init__(
        self,
        profiles: dict[str, DeviceProfile],
        spool: EdgeSpool,
        sidecar_python: Path,
        artifact_cache_root: Path,
    ):
        self._profiles = profiles
        self._verifier = _FenceVerifier(spool)
        self._backend_factory = partial(
            LamdaSidecarBackend.connect,
            python_executable=sidecar_python,
            artifact_cache_root=artifact_cache_root,
        )

    def __call__(self, command: pb.StartCommand) -> AbstractContextManager[Any]:
        profile = self._profiles.get(command.device_id)
        if profile is None:
            raise HardwareBlockedError("authorized device profile is unavailable")
        if not profile.certificate_path.is_file():
            raise HardwareBlockedError("LAMDA service certificate is unavailable")
        return LamdaSession(
            device_id=command.device_id,
            host=profile.host,
            certificate_path=profile.certificate_path,
            lease_id=command.lease_id,
            fencing_token=command.fencing_token,
            fencing_verifier=self._verifier,
            backend_factory=self._backend_factory,
        )


def compose_gateway(settings: GatewaySettings) -> GatewayRuntime:
    settings.validate_runtime()
    sidecar_python = settings.lamda_sidecar_python
    if sidecar_python is None:
        raise SettingsError("LAMDA sidecar runtime is required")
    try:
        probe_sidecar_runtime(sidecar_python)
    except DeviceDriverError as exc:
        raise SettingsError(exc.detail) from exc
    profiles = _load_device_profiles(settings.device_profiles_path)
    spool = EdgeSpool(settings.state_dir / "edge-spool.sqlite3")
    cache = ArtifactCache(settings.state_dir / "artifact-cache")

    control: EdgeControlStream | None = None

    async def task_event_sink(event: pb.TaskEvent) -> None:
        if control is None:
            raise RuntimeError("Edge control stream composition is incomplete")
        await control.emit_task_event(event)

    class _DeferredExecutor:
        delegate: SafeRunnerExecutor | None = None

        async def execute(
            self,
            command: pb.StartCommand,
            cancel_event: asyncio.Event,
            event_sink: EventSink,
        ) -> None:
            if self.delegate is None:
                raise RuntimeError("Edge executor composition is incomplete")
            await self.delegate.execute(command, cancel_event, event_sink)

    deferred = _DeferredExecutor()
    supervisor = RunnerSupervisor(spool, deferred, task_event_sink)
    scheduler = CommandScheduler(spool, supervisor)
    actions = OperatorActionCoordinator(spool, supervisor)
    debug_sessions = DebugSessionManager()
    debug_driver = (
        RestrictedAdbDebugDriver(
            settings.lab_adb_path,
            device_id=settings.lab_adb_device_id,
        )
        if settings.lab_adb_debug_enabled
        and settings.lab_adb_path is not None
        and settings.lab_adb_device_id is not None
        else None
    )

    def debug_target_resolver(device_id: str) -> ProxyTarget:
        profile = profiles.get(device_id)
        if profile is None:
            raise SettingsError("authorized debug device profile is unavailable")
        # ProxyTarget performs the private/loopback IP and fixed service-port checks.  No
        # caller-provided host or port is accepted here.
        try:
            return ProxyTarget(profile.host)
        except DebugSessionError as exc:
            raise SettingsError("debug target must be a private/loopback device address") from exc

    for grant in spool.active_debug_grants():
        expires_at = grant.expires_at.ToDatetime(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            spool.revoke_debug_grant(grant.session_id)
            continue
        debug_sessions.grant(
            session_id=grant.session_id,
            device_id=grant.device_id,
            expires_at=expires_at,
            capabilities=set(grant.capabilities),
            target=debug_target_resolver(grant.device_id),
            bearer_token=grant.relay_token,
            lease_id=grant.lease_id,
            fencing_token=grant.fencing_token,
        )

    async def debug_frame_handler(frame: pb.DebugRelayFrame) -> None:
        if debug_driver is None or control is None:
            raise RuntimeError("lab ADB debug driver is disabled")
        try:
            response = await debug_driver.handle(frame)
        except AdbDebugError:
            response = pb.DebugRelayFrame(
                session_id=frame.session_id,
                device_id=frame.device_id,
                request_id=frame.request_id,
                capability="debug.ack",
                kind="debug.ack",
                payload=json.dumps(
                    {"state": "FAILED", "errorCode": "LAB_ADB_OPERATION_FAILED"},
                    separators=(",", ":"),
                ).encode("utf-8"),
                end=True,
            )
        await control.emit_debug_frame(response)

    control = EdgeControlStream(
        edge_id=settings.edge_id,
        software_version=settings.software_version,
        spool=spool,
        scheduler=scheduler,
        debug_sessions=debug_sessions,
        debug_target_resolver=debug_target_resolver,
        debug_frame_handler=debug_frame_handler if debug_driver is not None else None,
        operator_actions=actions,
    )

    async def delivery_sink(event: pb.ArtifactDeliveryEvent) -> None:
        spool.enqueue_edge_message(pb.EdgeToCloud(artifact_delivery=event), priority=10)
        control.notify_outbound()

    allowed_packages = {
        device_id: profile.allowed_packages for device_id, profile in profiles.items()
    }
    deferred.delegate = SafeRunnerExecutor(
        cache=cache,
        artifact_source=LocalArtifactSource(settings.artifact_staging_root),
        session_factory=_SessionFactory(
            profiles,
            spool,
            sidecar_python,
            cache.objects_root,
        ),
        spool=spool,
        delivery_sink=delivery_sink,
        allowed_packages=allowed_packages,
    )
    auth = CompanionAuthStore(spool)
    for enrollment in _load_enrollments(settings.enrollment_path):
        auth.issue_enrollment_code(**enrollment)
    app = create_companion_app(
        spool=spool,
        auth_store=auth,
        operator_actions=actions,
        supervisor=supervisor,
        current_version=settings.software_version,
    )
    return GatewayRuntime(
        settings=settings,
        spool=spool,
        cache=cache,
        supervisor=supervisor,
        scheduler=scheduler,
        control_stream=control,
        debug_sessions=debug_sessions,
        companion_app=app,
    )


def _load_device_profiles(path: Path) -> dict[str, DeviceProfile]:
    raw = _load_json(path)
    entries = raw.get("devices") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        raise SettingsError("device profile file must contain a devices array")
    profiles: dict[str, DeviceProfile] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise SettingsError("device profile entries must be objects")
        device_id = _required_json_string(entry, "deviceId")
        if device_id in profiles:
            raise SettingsError("device profile identifiers must be unique")
        packages = entry.get("allowedPackages", [])
        if not isinstance(packages, list) or not all(
            isinstance(package, str) and package for package in packages
        ):
            raise SettingsError("allowedPackages must be a string array")
        profiles[device_id] = DeviceProfile(
            device_id=device_id,
            host=_required_json_string(entry, "host"),
            certificate_path=Path(_required_json_string(entry, "certificatePath")),
            allowed_packages=frozenset(packages),
        )
    return profiles


def _load_enrollments(path: Path) -> list[dict[str, str]]:
    raw = _load_json(path)
    entries = raw.get("enrollments") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        raise SettingsError("enrollment file must contain an enrollments array")
    return [
        {
            "code": _required_json_string(entry, "code"),
            "device_id": _required_json_string(entry, "deviceId"),
            "tenant_name": _required_json_string(entry, "tenantName"),
            "site_name": _required_json_string(entry, "siteName"),
        }
        for entry in entries
        if isinstance(entry, dict)
    ]


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SettingsError(f"invalid JSON configuration: {path}") from exc


def _required_json_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise SettingsError(f"{key} is required")
    return item.strip()
