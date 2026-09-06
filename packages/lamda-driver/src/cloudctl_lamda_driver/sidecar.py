from __future__ import annotations

import base64
import json
import os
import subprocess
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TextIO, cast

from .errors import DeviceDriverError, DriverErrorCode

SIDECAR_PROTOCOL_VERSION = 1
EXPECTED_LAMDA_SDK_VERSION = "10.8"
_SIDECAR_MODULE = "cloudctl_lamda_driver.sidecar_server"


@dataclass(frozen=True, slots=True)
class SidecarRuntimeInfo:
    protocol_version: int
    sdk_version: str
    python_version: str


class _JsonLineTransport:
    def __init__(self, process: subprocess.Popen[str]):
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise ValueError("sidecar process must expose text pipes")
        self._process = process
        self._stdin = cast(TextIO, process.stdin)
        self._stdout = cast(TextIO, process.stdout)
        self._stderr = cast(TextIO, process.stderr)
        self._request_id = 0
        self._lock = threading.Lock()
        self._stderr_tail = ""
        self._stderr_thread = threading.Thread(
            target=self._capture_stderr,
            name="lamda-sidecar-stderr",
            daemon=True,
        )
        self._stderr_thread.start()

    @classmethod
    def start(cls, python_executable: Path) -> _JsonLineTransport:
        if not python_executable.is_absolute() or not python_executable.is_file():
            raise DeviceDriverError(
                DriverErrorCode.CONNECTION_FAILED,
                "LAMDA sidecar Python runtime is unavailable",
                retryable=False,
            )
        package_src = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONNOUSERSITE": "1",
                "PYTHONUTF8": "1",
                "PYTHONPATH": str(package_src),
            }
        )
        try:
            process = subprocess.Popen(  # noqa: S603 - executable is an operator setting
                build_sidecar_command(python_executable),
                cwd=package_src,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise DeviceDriverError(
                DriverErrorCode.CONNECTION_FAILED,
                "LAMDA sidecar process could not be started",
                retryable=False,
            ) from exc
        return cls(process)

    def call(self, operation: str, arguments: Mapping[str, object] | None = None) -> object:
        with self._lock:
            if self._process.poll() is not None:
                raise DeviceDriverError(
                    DriverErrorCode.CONNECTION_FAILED,
                    "LAMDA sidecar process is not running",
                    retryable=True,
                )
            self._request_id += 1
            request_id = self._request_id
            request = {
                "id": request_id,
                "op": operation,
                "args": dict(arguments or {}),
            }
            try:
                self._stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
                self._stdin.flush()
                line = self._stdout.readline()
            except (BrokenPipeError, OSError) as exc:
                raise DeviceDriverError(
                    DriverErrorCode.CONNECTION_FAILED,
                    "LAMDA sidecar IPC failed",
                    retryable=True,
                ) from exc
            if not line:
                raise DeviceDriverError(
                    DriverErrorCode.CONNECTION_FAILED,
                    "LAMDA sidecar exited without a response",
                    retryable=True,
                )
            return _decode_response(line, request_id)

    def terminate(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
        for stream in (self._stdin, self._stdout, self._stderr):
            stream.close()

    def _capture_stderr(self) -> None:
        for line in self._stderr:
            self._stderr_tail = (self._stderr_tail + line)[-4096:]


class _RemoteElement:
    def __init__(self, backend: LamdaSidecarBackend, handle: int):
        self._backend = backend
        self.handle = handle

    def click(self) -> None:
        self._backend.tap(self)

    def text(self) -> str:
        return str(self._backend._call("element_text", element=self.handle))

    def exists(self) -> bool:
        return bool(self._backend._call("element_exists", element=self.handle))


class LamdaSidecarBackend:
    """LAMDA backend proxy hosted in a dependency-isolated Python process."""

    def __init__(
        self,
        transport: _JsonLineTransport,
        runtime_info: SidecarRuntimeInfo,
        *,
        backend_handle: int = 0,
        owns_transport: bool = True,
    ) -> None:
        self._transport = transport
        self._runtime_info = runtime_info
        self._backend_handle = backend_handle
        self._owns_transport = owns_transport
        self._closed = False

    @classmethod
    def connect(
        cls,
        *,
        host: str,
        port: int,
        certificate_path: Path,
        python_executable: Path,
        artifact_cache_root: Path,
    ) -> LamdaSidecarBackend:
        if not certificate_path.is_absolute() or not certificate_path.is_file():
            raise DeviceDriverError(
                DriverErrorCode.CERTIFICATE_REJECTED,
                "device service certificate is unavailable",
                retryable=False,
            )
        if not artifact_cache_root.is_absolute() or not artifact_cache_root.is_dir():
            raise DeviceDriverError(
                DriverErrorCode.IO_FAILED,
                "Edge artifact cache is unavailable to the LAMDA sidecar",
                retryable=False,
            )
        transport = _JsonLineTransport.start(python_executable)
        try:
            runtime_info = _read_runtime_info(transport.call("hello"))
            result = transport.call(
                "connect",
                {
                    "host": host,
                    "port": port,
                    "certificatePath": str(certificate_path.resolve()),
                    "artifactRoot": str(artifact_cache_root.resolve()),
                },
            )
            backend_handle = _required_int(result, "backendHandle")
            return cls(transport, runtime_info, backend_handle=backend_handle)
        except Exception:
            transport.terminate()
            raise

    @property
    def runtime_info(self) -> SidecarRuntimeInfo:
        return self._runtime_info

    def acquire_lock(self, lease_seconds: int) -> None:
        self._call("acquire_lock", leaseSeconds=lease_seconds)

    def refresh_lock(self, lease_seconds: int) -> None:
        self._call("refresh_lock", leaseSeconds=lease_seconds)

    def release_lock(self) -> None:
        self._call("release_lock")

    def close(self) -> None:
        if self._closed:
            return
        if self._owns_transport:
            try:
                self._transport.call("close")
            except DeviceDriverError:
                pass
            finally:
                self._transport.terminate()
        else:
            self._call("close_backend")
        self._closed = True

    def identity(self) -> str:
        return str(self._call("identity"))

    def capabilities(self) -> Mapping[str, object]:
        return _required_mapping(self._call("capabilities"))

    def start_app(self, package: str) -> None:
        self._call("start_app", package=package)

    def stop_app(self, package: str) -> None:
        self._call("stop_app", package=package)

    def select(self, attributes: Mapping[str, object], timeout_seconds: float) -> _RemoteElement:
        result = self._call(
            "select",
            attributes=dict(attributes),
            timeoutSeconds=timeout_seconds,
        )
        return _RemoteElement(self, _required_int(result, "elementHandle"))

    def tap(self, element: object) -> None:
        self._call("tap", element=self._element_handle(element))

    def input_text(self, element: object, text: str, replace: bool) -> None:
        self._call(
            "input_text",
            element=self._element_handle(element),
            text=text,
            replace=replace,
        )

    def swipe(self, element: object, direction: str, steps: int) -> None:
        self._call(
            "swipe",
            element=self._element_handle(element),
            direction=direction,
            steps=steps,
        )

    def screenshot(self) -> bytes:
        result = _required_mapping(self._call("screenshot"))
        payload = result.get("base64")
        if not isinstance(payload, str):
            raise _protocol_error()
        try:
            return base64.b64decode(payload, validate=True)
        except ValueError as exc:
            raise _protocol_error() from exc

    def dump_ui(self) -> str:
        return str(self._call("dump_ui"))

    def push_file(self, source: BinaryIO, remote_path: str, sha256: str) -> None:
        self._call(
            "push_file",
            remotePath=remote_path,
            sha256=sha256,
            size=_remaining_size(source),
        )

    def create_virtual_display(
        self, width: int, height: int, density_dpi: int
    ) -> LamdaSidecarBackend:
        result = self._call(
            "create_virtual_display",
            width=width,
            height=height,
            densityDpi=density_dpi,
        )
        handle = _required_int(result, "backendHandle")
        return LamdaSidecarBackend(
            self._transport,
            self._runtime_info,
            backend_handle=handle,
            owns_transport=False,
        )

    def register_watcher(self, name: str, attributes: Mapping[str, object]) -> None:
        self._call("register_watcher", name=name, attributes=dict(attributes))

    def remove_watcher(self, name: str) -> None:
        self._call("remove_watcher", name=name)

    def create_install_session(self, options: Mapping[str, object]) -> str:
        return str(self._call("create_install_session", options=dict(options)))

    def write_install_part(
        self,
        session_id: str,
        split_name: str | None,
        source: BinaryIO,
        size: int,
        sha256: str,
    ) -> None:
        if _remaining_size(source) != size:
            raise DeviceDriverError(
                DriverErrorCode.IO_FAILED,
                "APK part size changed before sidecar delivery",
                retryable=False,
            )
        self._call(
            "write_install_part",
            sessionId=session_id,
            splitName=split_name,
            sha256=sha256,
            size=size,
        )

    def commit_install_session(self, session_id: str) -> None:
        self._call("commit_install_session", sessionId=session_id)

    def install_session_state(self, session_id: str) -> Mapping[str, object]:
        return _required_mapping(self._call("install_session_state", sessionId=session_id))

    def installed_app(self, package_name: str) -> Mapping[str, object]:
        return _required_mapping(self._call("installed_app", packageName=package_name))

    def _call(self, operation: str, **arguments: object) -> object:
        if self._closed:
            raise DeviceDriverError(
                DriverErrorCode.CONNECTION_FAILED,
                "LAMDA sidecar backend is closed",
                retryable=False,
            )
        return self._transport.call(
            operation,
            {"backendHandle": self._backend_handle, **arguments},
        )

    def _element_handle(self, element: object) -> int:
        if not isinstance(element, _RemoteElement) or element._backend is not self:
            raise DeviceDriverError(
                DriverErrorCode.CAPABILITY_DENIED,
                "element handle does not belong to this LAMDA backend",
                retryable=False,
            )
        return element.handle


def build_sidecar_command(python_executable: Path) -> list[str]:
    return [str(python_executable), "-s", "-m", _SIDECAR_MODULE]


def probe_sidecar_runtime(python_executable: Path) -> SidecarRuntimeInfo:
    transport = _JsonLineTransport.start(python_executable)
    try:
        info = _read_runtime_info(transport.call("hello"))
        transport.call("close")
        return info
    finally:
        transport.terminate()


def _read_runtime_info(value: object) -> SidecarRuntimeInfo:
    mapping = _required_mapping(value)
    protocol_version = _required_int(mapping, "protocolVersion")
    if protocol_version != SIDECAR_PROTOCOL_VERSION:
        raise DeviceDriverError(
            DriverErrorCode.CONNECTION_FAILED,
            "LAMDA sidecar protocol version is incompatible",
            retryable=False,
        )
    sdk_version = mapping.get("sdkVersion")
    python_version = mapping.get("pythonVersion")
    if not isinstance(sdk_version, str) or not isinstance(python_version, str):
        raise _protocol_error()
    if sdk_version != EXPECTED_LAMDA_SDK_VERSION:
        raise DeviceDriverError(
            DriverErrorCode.CONNECTION_FAILED,
            "LAMDA sidecar SDK version is incompatible",
            retryable=False,
        )
    if python_version.split(".")[:2] != ["3", "12"]:
        raise DeviceDriverError(
            DriverErrorCode.CONNECTION_FAILED,
            "LAMDA sidecar must run on Python 3.12",
            retryable=False,
        )
    return SidecarRuntimeInfo(protocol_version, sdk_version, python_version)


def _decode_response(line: str, request_id: int) -> object:
    try:
        response = json.loads(line)
    except json.JSONDecodeError as exc:
        raise _protocol_error() from exc
    if not isinstance(response, dict) or response.get("id") != request_id:
        raise _protocol_error()
    if response.get("ok") is True:
        return response.get("result")
    error = response.get("error")
    if not isinstance(error, dict):
        raise _protocol_error()
    raw_code = error.get("code")
    detail = error.get("detail")
    retryable = error.get("retryable")
    reconcile_required = error.get("reconcileRequired", False)
    try:
        code = DriverErrorCode(str(raw_code))
    except ValueError:
        code = DriverErrorCode.UNKNOWN
    if not isinstance(detail, str) or not isinstance(retryable, bool):
        raise _protocol_error()
    return _raise_remote_error(code, detail, retryable, bool(reconcile_required))


def _raise_remote_error(
    code: DriverErrorCode, detail: str, retryable: bool, reconcile_required: bool
) -> object:
    raise DeviceDriverError(
        code,
        detail,
        retryable=retryable,
        reconcile_required=reconcile_required,
    )


def _required_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise _protocol_error()
    return cast(Mapping[str, object], value)


def _required_int(value: object, key: str) -> int:
    mapping = _required_mapping(value)
    result = mapping.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise _protocol_error()
    return result


def _protocol_error() -> DeviceDriverError:
    return DeviceDriverError(
        DriverErrorCode.CONNECTION_FAILED,
        "LAMDA sidecar returned an invalid protocol response",
        retryable=False,
    )


def _remaining_size(source: BinaryIO) -> int:
    try:
        position = source.tell()
        source.seek(0, 2)
        size = source.tell()
        source.seek(position)
    except (AttributeError, OSError) as exc:
        raise DeviceDriverError(
            DriverErrorCode.IO_FAILED,
            "artifact source must be a seekable verified cache file",
            retryable=False,
        ) from exc
    if size < position:
        raise DeviceDriverError(
            DriverErrorCode.IO_FAILED,
            "artifact source position is invalid",
            retryable=False,
        )
    return size - position
