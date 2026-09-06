from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "packages/lamda-driver/src"))

from cloudctl_lamda_driver.apk import ApkSessionInstaller
from cloudctl_lamda_driver.driver import LamdaDriver
from cloudctl_lamda_driver.errors import DeviceDriverError, DriverErrorCode, map_exception
from cloudctl_lamda_driver.locator import LocatorResolver
from cloudctl_lamda_driver.protocols import ApkPart, InstallOptions, Locator, LocatorCandidate
from cloudctl_lamda_driver.session import LamdaSession
from cloudctl_lamda_driver.watcher import WatcherDefinition, WatcherManager


def test_lamda_import_is_confined_to_driver_package() -> None:
    offenders: list[Path] = []
    for path in ROOT.rglob("*.py"):
        if ".venv" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports_lamda = any(
            isinstance(node, (ast.Import, ast.ImportFrom))
            and (
                any(
                    alias.name == "lamda" or alias.name.startswith("lamda.") for alias in node.names
                )
                if isinstance(node, ast.Import)
                else node.module is not None
                and (node.module == "lamda" or node.module.startswith("lamda."))
            )
            for node in ast.walk(tree)
        )
        if imports_lamda and "packages/lamda-driver" not in path.as_posix():
            offenders.append(path)
    assert offenders == []


class FakeFence:
    def verify(self, *, device_id: str, lease_id: str, fencing_token: int) -> None:
        assert (device_id, lease_id, fencing_token) == ("device-a", "lease-a", 7)


class FakeBackend:
    def __init__(self) -> None:
        self.acquired: list[int] = []
        self.refreshed: list[int] = []
        self.released = 0
        self.closed = 0

    def acquire_lock(self, seconds: int) -> None:
        self.acquired.append(seconds)

    def refresh_lock(self, seconds: int) -> None:
        self.refreshed.append(seconds)

    def release_lock(self) -> None:
        self.released += 1

    def close(self) -> None:
        self.closed += 1

    def identity(self) -> str:
        return "device-a"

    def capabilities(self):
        return {"ui_automation": True, "virtual_display": False}


def test_session_uses_sixty_second_lock_and_releases(tmp_path: Path) -> None:
    certificate = tmp_path / "device.pem"
    certificate.write_text("fixture", encoding="utf-8")
    backend = FakeBackend()

    def factory(**kwargs):
        return backend

    with LamdaSession(
        device_id="device-a",
        host="10.0.0.20",
        certificate_path=certificate,
        lease_id="lease-a",
        fencing_token=7,
        fencing_verifier=FakeFence(),
        backend_factory=factory,
    ) as driver:
        assert driver.get_capabilities()["ui_automation"] is True
        assert backend.acquired == [60]
        assert LamdaSession.REFRESH_SECONDS == 20
    assert backend.released == 1
    assert backend.closed == 1


class Element:
    def __init__(self, exists: bool = True):
        self._exists = exists

    def exists(self) -> bool:
        return self._exists

    def text(self) -> str:
        return "ready"


class Selector:
    def select(self, attributes, timeout_seconds):
        if attributes.get("resourceId") == "missing":
            raise LookupError("missing")
        return Element()


def test_locator_fallback_emits_degraded_signal() -> None:
    degraded: list[tuple[str, str]] = []
    locator = Locator(
        name="submit",
        primary=LocatorCandidate("resource_id", {"resourceId": "missing"}),
        fallbacks=(LocatorCandidate("text", {"text": "Submit"}),),
    )
    element = LocatorResolver(lambda name, strategy: degraded.append((name, strategy))).resolve(
        Selector(), locator
    )
    assert element.exists()
    assert degraded == [("submit", "text")]


class Watchers:
    def __init__(self) -> None:
        self.registered: list[str] = []
        self.removed: list[str] = []

    def register_watcher(self, name, attributes) -> None:
        self.registered.append(name)

    def remove_watcher(self, name) -> None:
        self.removed.append(name)


def test_watchers_are_cleaned_and_cannot_handle_captcha() -> None:
    backend = Watchers()
    manager = WatcherManager(backend, app_version="2.0", automation_version="1.4")
    definition = WatcherDefinition("permission", "permission_prompt", {"text": "Allow"})
    with manager.task_scope([definition]):
        assert backend.registered == ["2.0:1.4:permission"]
    assert backend.removed == backend.registered
    with pytest.raises(PermissionError):
        with manager.task_scope(
            [WatcherDefinition("captcha", "permission_prompt", {"text": "Verify"})]
        ):
            pass


class ApkBackend:
    def __init__(self) -> None:
        self.commits = 0

    def create_install_session(self, options):
        return "session-a"

    def write_install_part(self, session_id, split_name, source, size, sha256):
        assert len(source.read()) == size

    def commit_install_session(self, session_id):
        self.commits += 1
        raise ConnectionError("outcome unknown")

    def install_session_state(self, session_id):
        return {"state": "SUCCEEDED"}

    def installed_app(self, package_name):
        return {}


def test_apk_commit_is_attempted_once_and_requires_reconciliation(tmp_path: Path) -> None:
    apk = tmp_path / "base.apk"
    apk.write_bytes(b"apk")
    backend = ApkBackend()
    installer = ApkSessionInstaller(backend, lambda: None)
    with pytest.raises(DeviceDriverError) as raised:
        installer.install(
            [ApkPart(apk, hashlib.sha256(b"apk").hexdigest(), 3)],
            InstallOptions("com.company.target", "1.0", 1, "a" * 64),
        )
    assert raised.value.code == DriverErrorCode.APK_COMMIT_UNKNOWN
    assert raised.value.reconcile_required is True
    assert backend.commits == 1


def test_error_mapping_is_stable_and_redacted() -> None:
    error = map_exception(PermissionError("private device detail"))
    assert error.code == DriverErrorCode.CAPABILITY_DENIED
    assert "private device detail" not in error.detail


class InputElement:
    def __init__(self) -> None:
        self.clicked = 0
        self.text_values: list[tuple[str, bool]] = []
        self.swipes: list[tuple[str, int]] = []

    def exists(self) -> bool:
        return True

    def text(self) -> str:
        return "ready"


class InputBackend:
    def __init__(self, capabilities: dict[str, bool]) -> None:
        self._capabilities = capabilities
        self.element = InputElement()

    def capabilities(self):
        return self._capabilities

    def select(self, _attributes, _timeout_seconds):
        return self.element

    def tap(self, element: InputElement) -> None:
        assert element is self.element
        element.clicked += 1

    def input_text(self, element: InputElement, text: str, replace: bool) -> None:
        assert element is self.element
        element.text_values.append((text, replace))

    def swipe(self, element: InputElement, direction: str, steps: int) -> None:
        assert element is self.element
        element.swipes.append((direction, steps))


def input_locator() -> Locator:
    return Locator(
        name="content",
        primary=LocatorCandidate("resource_id", {"resourceId": "com.target:id/content"}),
    )


def test_driver_exposes_only_capability_scoped_element_input() -> None:
    backend = InputBackend(
        {
            "ui.selectors": True,
            "input.tap": True,
            "input.text": True,
            "input.swipe": True,
        }
    )
    driver = LamdaDriver(backend, lambda: None)

    driver.tap(input_locator())
    driver.input_text(input_locator(), "approved content", replace=True)
    driver.swipe(input_locator(), "UP", steps=32)

    assert backend.element.clicked == 1
    assert backend.element.text_values == [("approved content", True)]
    assert backend.element.swipes == [("UP", 32)]


def test_driver_rejects_ungranted_or_unbounded_input() -> None:
    backend = InputBackend(
        {
            "ui.selectors": True,
            "input.tap": False,
            "input.text": True,
            "input.swipe": True,
        }
    )
    driver = LamdaDriver(backend, lambda: None)

    with pytest.raises(DeviceDriverError) as tap_error:
        driver.tap(input_locator())
    assert tap_error.value.code == DriverErrorCode.CAPABILITY_DENIED

    with pytest.raises(DeviceDriverError) as text_error:
        driver.input_text(input_locator(), "x" * 4097)
    assert text_error.value.code == DriverErrorCode.CAPABILITY_DENIED

    with pytest.raises(DeviceDriverError) as swipe_error:
        driver.swipe(input_locator(), "DIAGONAL", steps=32)
    assert swipe_error.value.code == DriverErrorCode.CAPABILITY_DENIED
    assert backend.element.clicked == 0
    assert backend.element.text_values == []
    assert backend.element.swipes == []
