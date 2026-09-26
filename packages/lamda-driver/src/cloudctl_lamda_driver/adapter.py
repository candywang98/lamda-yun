from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO

from .errors import DeviceDriverError, DriverErrorCode, map_exception


class LamdaSdkBackend:
    """The only module that imports and translates the third-party lamda SDK."""

    def __init__(self, device: Any):
        self._device = device

    @classmethod
    def connect(cls, *, host: str, port: int, certificate_path: Path) -> LamdaSdkBackend:
        try:
            from lamda.client import Device  # type: ignore[import-untyped]

            device = Device(host, port=port, certificate=str(certificate_path))
            return cls(device)
        except ImportError as exc:
            raise DeviceDriverError(
                DriverErrorCode.CONNECTION_FAILED,
                "LAMDA SDK dependency is unavailable",
                retryable=False,
            ) from exc
        except Exception as exc:
            raise map_exception(exc) from exc

    def acquire_lock(self, lease_seconds: int) -> None:
        self._call_private("_acquire_lock", leaseTime=lease_seconds)

    def refresh_lock(self, lease_seconds: int) -> None:
        self._call_private("_refresh_lock", leaseTime=lease_seconds)

    def release_lock(self) -> None:
        self._call_private("_release_lock")

    def close(self) -> None:
        close = getattr(self._device, "close", None)
        if callable(close):
            close()

    def identity(self) -> str:
        info = self._device.device_info()
        return str(getattr(info, "serial", getattr(info, "device_id", "")))

    def capabilities(self) -> Mapping[str, object]:
        info = self._device.device_info()
        return {
            "ui_automation": True,
            "ui.selectors": True,
            "app.lifecycle": True,
            "file.push": True,
            "screenshot": True,
            "ui.dump": True,
            "view.frame": True,
            "view.layout": True,
            "input.tap": True,
            "input.text": True,
            "input.swipe": True,
            "evidence.capture": True,
            "silent_install": bool(getattr(info, "root", False)),
            "virtual_display": hasattr(self._device, "create_virtual_display"),
            "remote_stream_h264": bool(getattr(info, "h264", False)),
        }

    def start_app(self, package: str) -> None:
        self._device.application.start(package)

    def stop_app(self, package: str) -> None:
        self._device.application.stop(package)

    def select(self, attributes: Mapping[str, object], timeout_seconds: float) -> Any:
        element = self._device(**dict(attributes))
        if not element.wait(timeout=timeout_seconds):
            raise LookupError("element was not found before timeout")
        return element

    def tap(self, element: Any) -> None:
        element.click()

    def input_text(self, element: Any, text: str, replace: bool) -> None:
        if replace:
            element.clear_text_field()
        element.set_text(text)

    def swipe(self, element: Any, direction: str, steps: int) -> None:
        from lamda.client import Direction  # pyright: ignore[reportMissingImports]

        directions = {
            "UP": Direction.DIR_UP,
            "DOWN": Direction.DIR_DOWN,
            "LEFT": Direction.DIR_LEFT,
            "RIGHT": Direction.DIR_RIGHT,
        }
        element.swipe(direction=directions[direction], step=steps)

    def screenshot(self) -> bytes:
        payload = self._device.screenshot(format="raw")
        return bytes(payload)

    def dump_ui(self) -> str:
        return str(self._device.dump_hierarchy())

    def push_file(self, source: BinaryIO, remote_path: str, _sha256: str) -> None:
        self._device.push_file(source, remote_path)

    def create_virtual_display(self, width: int, height: int, density_dpi: int) -> Any:
        return self._device.create_virtual_display(width=width, height=height, density=density_dpi)

    def register_watcher(self, name: str, attributes: Mapping[str, object]) -> None:
        self._device.watcher(name).when(**dict(attributes)).click()

    def remove_watcher(self, name: str) -> None:
        self._device.watcher(name).remove()

    def create_install_session(self, options: Mapping[str, object]) -> str:
        return str(self._device.application.create_install_session(**dict(options)))

    def write_install_part(
        self,
        session_id: str,
        split_name: str | None,
        source: BinaryIO,
        size: int,
        _sha256: str,
    ) -> None:
        self._device.application.write_install_session(session_id, split_name, source, size)

    def commit_install_session(self, session_id: str) -> None:
        self._device.application.commit_install_session(session_id)

    def install_session_state(self, session_id: str) -> Mapping[str, object]:
        state = self._device.application.install_session_state(session_id)
        return dict(state)

    def installed_app(self, package_name: str) -> Mapping[str, object]:
        app = self._device.application.info(package_name)
        return {
            "package_name": package_name,
            "version_name": str(app.version_name),
            "version_code": int(app.version_code),
            "signer_sha256": str(app.signer_sha256),
        }

    def _call_private(self, name: str, **kwargs: object) -> None:
        method = getattr(self._device, name, None)
        if not callable(method):
            raise RuntimeError(f"locked LAMDA version does not expose required method {name}")
        method(**kwargs)
