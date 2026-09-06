from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable


class Element(Protocol):
    def click(self) -> None: ...
    def text(self) -> str: ...
    def exists(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class LocatorCandidate:
    strategy: str
    attributes: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class Locator:
    name: str
    primary: LocatorCandidate
    fallbacks: tuple[LocatorCandidate, ...] = ()
    timeout_seconds: float = 10.0
    assertions: tuple[str, ...] = ("exists",)
    diagnostics: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ApkPart:
    path: Path
    sha256: str
    size: int
    split_name: str | None = None


@dataclass(frozen=True, slots=True)
class InstallOptions:
    package_name: str
    version_name: str
    version_code: int
    signer_sha256: str
    allow_downgrade: bool = False
    user_confirmation_allowed: bool = True


@dataclass(frozen=True, slots=True)
class InstallResult:
    package_name: str
    version_name: str
    version_code: int
    state: str
    session_id: str


@dataclass(frozen=True, slots=True)
class DisplaySpec:
    width: int
    height: int
    density_dpi: int


@runtime_checkable
class DeviceDriver(Protocol):
    def get_capabilities(self) -> Mapping[str, object]: ...
    def start_app(self, package: str) -> None: ...
    def stop_app(self, package: str) -> None: ...
    def selector(self, locator: Locator) -> Element: ...
    def tap(self, locator: Locator) -> None: ...
    def input_text(self, locator: Locator, text: str, *, replace: bool = True) -> None: ...
    def swipe(self, locator: Locator, direction: str, *, steps: int = 32) -> None: ...
    def screenshot(self) -> bytes: ...
    def dump_ui(self) -> str: ...
    def push_file(self, source: BinaryIO, remote_path: str, sha256: str) -> None: ...
    def install_apk_session(
        self, artifacts: Sequence[ApkPart], options: InstallOptions
    ) -> InstallResult: ...
    def create_virtual_display(self, spec: DisplaySpec) -> DeviceDriver: ...
