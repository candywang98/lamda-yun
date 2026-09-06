from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any, BinaryIO, TypeVar, cast

from .apk import ApkSessionInstaller
from .errors import DeviceDriverError, DriverErrorCode, map_exception
from .locator import LocatorResolver
from .protocols import ApkPart, DisplaySpec, Element, InstallOptions, InstallResult, Locator

_MAX_INPUT_TEXT_LENGTH = 4096
_SWIPE_DIRECTIONS = frozenset({"UP", "DOWN", "LEFT", "RIGHT"})

T = TypeVar("T")


class LamdaDriver:
    def __init__(
        self,
        backend: Any,
        guard: Callable[[], None],
        *,
        on_locator_degraded: Callable[[str, str], None] | None = None,
    ) -> None:
        self._backend = backend
        self._guard = guard
        self._locators = LocatorResolver(on_locator_degraded)
        self._installer = ApkSessionInstaller(backend, guard)

    def get_capabilities(self) -> Mapping[str, object]:
        return cast(Mapping[str, object], self._call(self._backend.capabilities))

    def start_app(self, package: str) -> None:
        self._require_capability("app.lifecycle")
        self._call(self._backend.start_app, package)

    def stop_app(self, package: str) -> None:
        self._require_capability("app.lifecycle")
        self._call(self._backend.stop_app, package)

    def selector(self, locator: Locator) -> Element:
        self._require_capability("ui.selectors")
        self._guard()
        return self._locators.resolve(self._backend, locator)

    def tap(self, locator: Locator) -> None:
        self._require_capability("input.tap")
        element = self.selector(locator)
        self._call(self._backend.tap, element)

    def input_text(self, locator: Locator, text: str, *, replace: bool = True) -> None:
        self._require_capability("input.text")
        if len(text) > _MAX_INPUT_TEXT_LENGTH or "\x00" in text:
            raise DeviceDriverError(
                DriverErrorCode.CAPABILITY_DENIED,
                "input text is outside the approved bounds",
                retryable=False,
            )
        element = self.selector(locator)
        self._call(self._backend.input_text, element, text, replace)

    def swipe(self, locator: Locator, direction: str, *, steps: int = 32) -> None:
        self._require_capability("input.swipe")
        if direction not in _SWIPE_DIRECTIONS:
            raise DeviceDriverError(
                DriverErrorCode.CAPABILITY_DENIED,
                "swipe direction is outside the approved set",
                retryable=False,
            )
        if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 200:
            raise DeviceDriverError(
                DriverErrorCode.CAPABILITY_DENIED,
                "swipe steps are outside the approved bounds",
                retryable=False,
            )
        element = self.selector(locator)
        self._call(self._backend.swipe, element, direction, steps)

    def screenshot(self) -> bytes:
        self._require_capability("screenshot")
        return bytes(self._call(self._backend.screenshot))

    def dump_ui(self) -> str:
        self._require_capability("ui.dump")
        return str(self._call(self._backend.dump_ui))

    def push_file(self, source: BinaryIO, remote_path: str, sha256: str) -> None:
        self._require_capability("file.push")
        if not remote_path.startswith("/") or ".." in remote_path.split("/"):
            raise DeviceDriverError(
                DriverErrorCode.CAPABILITY_DENIED,
                "remote path must be absolute and traversal-free",
                retryable=False,
            )
        payload = source.read()
        if hashlib.sha256(payload).hexdigest() != sha256.lower():
            raise DeviceDriverError(
                DriverErrorCode.IO_FAILED, "file SHA256 mismatch", retryable=False
            )
        source.seek(0)
        self._call(self._backend.push_file, source, remote_path, sha256.lower())

    def install_apk_session(
        self, artifacts: Sequence[ApkPart], options: InstallOptions
    ) -> InstallResult:
        return self._installer.install(artifacts, options)

    def create_virtual_display(self, spec: DisplaySpec) -> LamdaDriver:
        capabilities = self.get_capabilities()
        if not capabilities.get("virtual_display", False):
            raise DeviceDriverError(
                DriverErrorCode.CAPABILITY_DENIED,
                "virtual display is not enabled in this device profile",
                retryable=False,
            )
        backend = self._call(
            self._backend.create_virtual_display, spec.width, spec.height, spec.density_dpi
        )
        return LamdaDriver(backend, self._guard)

    def _require_capability(self, capability: str) -> None:
        if self.get_capabilities().get(capability) is not True:
            raise DeviceDriverError(
                DriverErrorCode.CAPABILITY_DENIED,
                f"device profile does not grant {capability}",
                retryable=False,
            )

    def _call(self, operation: Callable[..., T], *args: object) -> T:
        self._guard()
        try:
            return operation(*args)
        except Exception as exc:
            raise map_exception(exc) from exc
