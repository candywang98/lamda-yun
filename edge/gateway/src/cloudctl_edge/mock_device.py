from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from io import BytesIO
from typing import BinaryIO, Never, Protocol

from cloudctl_lamda_driver.protocols import DisplaySpec, InstallResult, Locator


class MockApkArtifact(Protocol):
    payload: bytes


class MockInstallOptions(Protocol):
    package_name: str
    version_name: str
    version_code: int


@dataclass(frozen=True, slots=True)
class MockElement:
    key: str
    text: str


@dataclass(slots=True)
class MockDevice:
    """Deterministic device fixture; it does not satisfy any real-device acceptance gate."""

    device_id: str = "mock-device-1"
    android_version: str = "14"
    lamda_version: str = "10.8-mock"
    apps: dict[str, str] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)
    elements: dict[str, MockElement] = field(default_factory=dict)
    running_package: str | None = None
    stopped: bool = False
    battery_percent: int = 82
    charging: bool = True
    network_type: str = "WIFI"
    temperature_celsius: float = 32.5
    free_storage_bytes: int = 8 * 1024 * 1024 * 1024
    companion_version: str = "0.1.0-mock"
    current_task_run_id: str = ""
    current_task_state: str = "IDLE"

    def get_capabilities(self) -> Mapping[str, object]:
        return {
            "ui_automation": True,
            "silent_install": False,
            "virtual_display": False,
            "remote_stream_h264": False,
            "fixture": True,
        }

    def start_app(self, package: str) -> None:
        if package not in self.apps:
            raise LookupError(f"package is not installed: {package}")
        self.running_package = package

    def stop_app(self, package: str) -> None:
        if self.running_package == package:
            self.running_package = None

    def selector(self, locator: Locator) -> MockElement:
        candidates = (locator.primary, *locator.fallbacks)
        for candidate in candidates:
            key = str(sorted(candidate.attributes.items()))
            if key in self.elements:
                return self.elements[key]
        raise LookupError("element was not found")

    def screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\nmock-device"

    def dump_ui(self) -> str:
        children = "".join(
            f'<node key="{key}" text="{value.text}" />' for key, value in self.elements.items()
        )
        return f"<hierarchy>{children}</hierarchy>"

    def push_file(self, source: BinaryIO, remote_path: str, sha256: str) -> None:
        payload = source.read()
        if hashlib.sha256(payload).hexdigest() != sha256:
            raise ValueError("file SHA256 mismatch")
        self.files[remote_path] = payload

    def install_apk_session(
        self, artifacts: Sequence[MockApkArtifact], options: MockInstallOptions
    ) -> InstallResult:
        if self.stopped:
            raise RuntimeError("automation was stopped by the operator")
        package_name = options.package_name
        payload = BytesIO()
        for artifact in artifacts:
            payload.write(artifact.payload)
        if not payload.getvalue():
            raise ValueError("APK session is empty")
        self.apps[package_name] = options.version_name
        return InstallResult(
            package_name=package_name,
            version_name=options.version_name,
            version_code=options.version_code,
            state="SUCCEEDED",
            session_id="mock-install-session",
        )

    def create_virtual_display(self, spec: DisplaySpec) -> Never:
        raise PermissionError("Mock profile does not enable virtual displays")

    def emergency_stop(self) -> None:
        self.stopped = True
        self.running_package = None
