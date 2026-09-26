from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib.metadata
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TextIO

from .adapter import LamdaSdkBackend
from .errors import DeviceDriverError, DriverErrorCode, map_exception
from .sidecar import SIDECAR_PROTOCOL_VERSION

BackendFactory = Callable[..., LamdaSdkBackend]


class _ServerState:
    def __init__(self, backend_factory: BackendFactory):
        self._backend_factory = backend_factory
        self._backends: dict[int, LamdaSdkBackend] = {}
        self._elements: dict[int, Any] = {}
        self._next_backend_handle = 1
        self._next_element_handle = 1
        self._artifact_root: Path | None = None

    def dispatch(self, operation: str, arguments: Mapping[str, object]) -> object:
        if operation == "connect":
            return self._connect(arguments)
        if operation == "close":
            self.close_all()
            return {"closed": True}
        backend = self._backend(arguments)
        if operation == "acquire_lock":
            backend.acquire_lock(_integer(arguments, "leaseSeconds"))
            return None
        if operation == "refresh_lock":
            backend.refresh_lock(_integer(arguments, "leaseSeconds"))
            return None
        if operation == "release_lock":
            backend.release_lock()
            return None
        if operation == "close_backend":
            backend.close()
            self._backends.pop(_integer(arguments, "backendHandle"), None)
            return None
        if operation == "identity":
            return backend.identity()
        if operation == "capabilities":
            return dict(backend.capabilities())
        if operation == "start_app":
            backend.start_app(_string(arguments, "package"))
            return None
        if operation == "stop_app":
            backend.stop_app(_string(arguments, "package"))
            return None
        if operation == "select":
            element = backend.select(
                _mapping(arguments, "attributes"),
                _number(arguments, "timeoutSeconds"),
            )
            handle = self._next_element_handle
            self._next_element_handle += 1
            self._elements[handle] = element
            return {"elementHandle": handle}
        if operation == "element_exists":
            return _element_value(self._element(arguments), "exists", bool)
        if operation == "element_text":
            return _element_value(self._element(arguments), "text", str)
        if operation == "tap":
            backend.tap(self._element(arguments))
            return None
        if operation == "input_text":
            backend.input_text(
                self._element(arguments),
                _string(arguments, "text"),
                _boolean(arguments, "replace"),
            )
            return None
        if operation == "swipe":
            backend.swipe(
                self._element(arguments),
                _string(arguments, "direction"),
                _integer(arguments, "steps"),
            )
            return None
        if operation == "screenshot":
            return {"base64": base64.b64encode(backend.screenshot()).decode("ascii")}
        if operation == "dump_ui":
            return backend.dump_ui()
        if operation == "push_file":
            digest = _digest(arguments, "sha256")
            with self._artifact(digest, _integer(arguments, "size")).open("rb") as source:
                backend.push_file(source, _string(arguments, "remotePath"), digest)
            return None
        if operation == "create_virtual_display":
            display = backend.create_virtual_display(
                _integer(arguments, "width"),
                _integer(arguments, "height"),
                _integer(arguments, "densityDpi"),
            )
            handle = self._next_backend_handle
            self._next_backend_handle += 1
            self._backends[handle] = LamdaSdkBackend(display)
            return {"backendHandle": handle}
        if operation == "register_watcher":
            backend.register_watcher(
                _string(arguments, "name"),
                _mapping(arguments, "attributes"),
            )
            return None
        if operation == "remove_watcher":
            backend.remove_watcher(_string(arguments, "name"))
            return None
        if operation == "create_install_session":
            return backend.create_install_session(_mapping(arguments, "options"))
        if operation == "write_install_part":
            digest = _digest(arguments, "sha256")
            size = _integer(arguments, "size")
            split_name = arguments.get("splitName")
            if split_name is not None and not isinstance(split_name, str):
                raise ValueError("splitName must be a string or null")
            with self._artifact(digest, size).open("rb") as source:
                backend.write_install_part(
                    _string(arguments, "sessionId"), split_name, source, size, digest
                )
            return None
        if operation == "commit_install_session":
            backend.commit_install_session(_string(arguments, "sessionId"))
            return None
        if operation == "install_session_state":
            return dict(backend.install_session_state(_string(arguments, "sessionId")))
        if operation == "installed_app":
            return dict(backend.installed_app(_string(arguments, "packageName")))
        raise PermissionError("sidecar operation is not on the allowlist")

    def close_all(self) -> None:
        for backend in reversed(tuple(self._backends.values())):
            with contextlib.suppress(Exception):
                backend.close()
        self._backends.clear()
        self._elements.clear()

    def _connect(self, arguments: Mapping[str, object]) -> object:
        if self._backends:
            raise PermissionError("sidecar already has an active device connection")
        certificate_path = Path(_string(arguments, "certificatePath"))
        if not certificate_path.is_absolute() or not certificate_path.is_file():
            raise DeviceDriverError(
                DriverErrorCode.CERTIFICATE_REJECTED,
                "device service certificate is unavailable",
                retryable=False,
            )
        artifact_root = Path(_string(arguments, "artifactRoot"))
        if not artifact_root.is_absolute() or not artifact_root.is_dir():
            raise DeviceDriverError(
                DriverErrorCode.IO_FAILED,
                "Edge artifact cache is unavailable to the LAMDA sidecar",
                retryable=False,
            )
        self._artifact_root = artifact_root.resolve()
        backend = self._backend_factory(
            host=_string(arguments, "host"),
            port=_integer(arguments, "port"),
            certificate_path=certificate_path,
        )
        self._backends[0] = backend
        return {"backendHandle": 0}

    def _artifact(self, digest: str, size: int) -> Path:
        root = self._artifact_root
        if root is None:
            raise DeviceDriverError(
                DriverErrorCode.IO_FAILED,
                "Edge artifact cache is not configured",
                retryable=False,
            )
        candidate = root / digest[:2] / digest
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise DeviceDriverError(
                DriverErrorCode.IO_FAILED,
                "verified artifact is unavailable to the LAMDA sidecar",
                retryable=False,
            ) from exc
        if candidate.is_symlink() or not resolved.is_file() or resolved.stat().st_size != size:
            raise DeviceDriverError(
                DriverErrorCode.IO_FAILED,
                "verified artifact metadata does not match the sidecar request",
                retryable=False,
            )
        digest_value = _hash_file(resolved)
        if digest_value != digest:
            raise DeviceDriverError(
                DriverErrorCode.IO_FAILED,
                "verified artifact digest changed before device delivery",
                retryable=False,
            )
        return resolved

    def _backend(self, arguments: Mapping[str, object]) -> LamdaSdkBackend:
        handle = _integer(arguments, "backendHandle")
        try:
            return self._backends[handle]
        except KeyError as exc:
            raise ConnectionError("LAMDA backend handle is unavailable") from exc

    def _element(self, arguments: Mapping[str, object]) -> Any:
        handle = _integer(arguments, "element")
        try:
            return self._elements[handle]
        except KeyError as exc:
            raise LookupError("LAMDA element handle is unavailable") from exc


def run_server(
    input_stream: TextIO,
    output_stream: TextIO,
    *,
    backend_factory: BackendFactory = LamdaSdkBackend.connect,
    sdk_version: str | None = None,
) -> int:
    state = _ServerState(backend_factory)
    version = sdk_version or _installed_sdk_version()
    try:
        for line in input_stream:
            request_id: object = None
            stop = False
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError("request must be an object")
                request_id = request.get("id")
                operation = request.get("op")
                arguments = request.get("args", {})
                if isinstance(request_id, bool) or not isinstance(request_id, int):
                    raise ValueError("request id must be an integer")
                if not isinstance(operation, str) or not isinstance(arguments, dict):
                    raise ValueError("request operation and arguments are invalid")
                if operation == "hello":
                    result: object = {
                        "protocolVersion": SIDECAR_PROTOCOL_VERSION,
                        "sdkVersion": version,
                        "pythonVersion": sys.version.split()[0],
                    }
                else:
                    with contextlib.redirect_stdout(sys.stderr):
                        result = state.dispatch(operation, arguments)
                    stop = operation == "close"
                response = {"id": request_id, "ok": True, "result": _json_value(result)}
            except Exception as exc:
                error = map_exception(exc)
                response = {
                    "id": request_id,
                    "ok": False,
                    "error": {
                        "code": error.code.value,
                        "detail": error.detail,
                        "retryable": error.retryable,
                        "reconcileRequired": error.reconcile_required,
                    },
                }
            output_stream.write(json.dumps(response, separators=(",", ":")) + "\n")
            output_stream.flush()
            if stop:
                return 0
    finally:
        state.close_all()
    return 0


def main() -> int:
    return run_server(sys.stdin, sys.stdout)


def _installed_sdk_version() -> str:
    try:
        return importlib.metadata.version("lamda")
    except importlib.metadata.PackageNotFoundError:
        return "UNAVAILABLE"


def _mapping(arguments: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = arguments.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _string(arguments: Mapping[str, object], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _integer(arguments: Mapping[str, object], key: str) -> int:
    value = arguments.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _number(arguments: Mapping[str, object], key: str) -> float:
    value = arguments.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be a number")
    return float(value)


def _boolean(arguments: Mapping[str, object], key: str) -> bool:
    value = arguments.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _digest(arguments: Mapping[str, object], key: str) -> str:
    value = _string(arguments, key).lower()
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{key} must be a SHA256 digest")
    return value


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _element_value(element: Any, attribute: str, convert: Callable[[object], object]) -> object:
    value = getattr(element, attribute, None)
    if value is None:
        raise AttributeError(f"LAMDA element does not expose {attribute}")
    return convert(value() if callable(value) else value)


def _json_value(value: object) -> object:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
