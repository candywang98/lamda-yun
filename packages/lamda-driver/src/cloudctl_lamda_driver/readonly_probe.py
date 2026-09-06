"""Strictly allowlisted ADB diagnostics for provisioning a LAMDA device."""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{4,128}$")
PACKAGE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")


class ReadOnlyProbeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CommandOutput:
    stdout: bytes
    stderr: bytes = b""
    returncode: int = 0


CommandExecutor = Callable[[Sequence[str], float], CommandOutput]


def _execute(argv: Sequence[str], timeout_seconds: float) -> CommandOutput:
    completed = subprocess.run(  # noqa: S603 - argv is an internal allowlist, never a shell
        list(argv),
        check=False,
        capture_output=True,
        timeout=timeout_seconds,
    )
    return CommandOutput(completed.stdout, completed.stderr, completed.returncode)


class ReadOnlyAdbProbe:
    """Expose only non-mutating provisioning diagnostics through the driver boundary."""

    def __init__(
        self,
        *,
        adb_path: Path,
        serial: str,
        executor: CommandExecutor = _execute,
        timeout_seconds: float = 20.0,
    ) -> None:
        if not adb_path.is_absolute() or not adb_path.is_file():
            raise ValueError("adb_path must be an existing absolute file")
        if not SERIAL_PATTERN.fullmatch(serial):
            raise ValueError("serial contains unsupported characters")
        self._adb_path = str(adb_path)
        self._serial = serial
        self._executor = executor
        self._timeout_seconds = timeout_seconds
        self._operations: list[str] = []

    @property
    def serial_hash(self) -> str:
        return hashlib.sha256(self._serial.encode("utf-8")).hexdigest()

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(self._operations)

    def inventory(self, target_package: str) -> dict[str, Any]:
        if not PACKAGE_PATTERN.fullmatch(target_package):
            raise ValueError("target package is invalid")
        devices = self._text("devices.list", "devices", "-l")
        device_line = next(
            (line for line in devices.splitlines() if line.startswith(f"{self._serial} ")),
            "",
        )
        if " device " not in f" {device_line} ":
            raise ReadOnlyProbeError("authorized device is not in adb device state")
        model = self._property("ro.product.model")
        android_version = self._property("ro.build.version.release")
        sdk_level = self._property("ro.build.version.sdk")
        device_name = self._property("ro.product.device")
        package_dump = self._text(
            "target.package.inspect",
            "-s",
            self._serial,
            "shell",
            "dumpsys",
            "package",
            target_package,
        )
        version_name = self._match(package_dump, r"\bversionName=([^\s]+)")
        version_code = self._match(package_dump, r"\bversionCode=(\d+)")
        packages = self._text(
            "lamda.package.detect", "-s", self._serial, "shell", "pm", "list", "packages"
        )
        sockets = self._text("lamda.port.detect", "-s", self._serial, "shell", "ss", "-ltn")
        lamda_packages = sorted(
            line.removeprefix("package:")
            for line in packages.splitlines()
            if "lamda" in line.lower()
        )
        return {
            "serialHash": self.serial_hash,
            "model": model,
            "device": device_name,
            "androidVersion": android_version,
            "sdkLevel": sdk_level,
            "targetPackage": target_package,
            "targetVersionName": version_name,
            "targetVersionCode": version_code,
            "lamdaPackages": lamda_packages,
            "lamdaPortListening": any(":65000" in line for line in sockets.splitlines()),
            "lamdaVersion": "UNAVAILABLE",
            "transport": "ADB_READ_ONLY_DIAGNOSTIC",
        }

    def screenshot(self) -> bytes:
        payload = self._bytes(
            "screenshot.capture", "-s", self._serial, "exec-out", "screencap", "-p"
        )
        if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ReadOnlyProbeError("device screenshot did not return PNG data")
        return payload

    def dump_ui(self) -> str:
        payload = self._text(
            "ui.dump",
            "-s",
            self._serial,
            "exec-out",
            "uiautomator",
            "dump",
            "/dev/tty",
        )
        start = payload.find("<?xml")
        if start < 0 or "<hierarchy" not in payload[start:]:
            raise ReadOnlyProbeError("device UI dump did not return a hierarchy")
        return payload[start:]

    def _property(self, name: str) -> str:
        return self._text(f"inventory.{name}", "-s", self._serial, "shell", "getprop", name).strip()

    def _match(self, value: str, pattern: str) -> str:
        match = re.search(pattern, value)
        return match.group(1) if match else "UNAVAILABLE"

    def _text(self, operation: str, *args: str) -> str:
        return self._bytes(operation, *args).decode("utf-8", errors="replace")

    def _bytes(self, operation: str, *args: str) -> bytes:
        result = self._executor((self._adb_path, *args), self._timeout_seconds)
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ReadOnlyProbeError(f"{operation} failed: {detail or result.returncode}")
        self._operations.append(operation)
        return result.stdout
