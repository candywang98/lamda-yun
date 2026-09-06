from __future__ import annotations

import importlib.util
import json
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest
from cloudctl_lamda_driver import CommandOutput, ReadOnlyAdbProbe, ReadOnlyProbeError

SERIAL = "b0644fb5"
PNG = b"\x89PNG\r\n\x1a\nreadonly-device-screenshot"
UI_XML = b'<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0" />\n'


def script_module() -> ModuleType:
    path = Path("scripts/run-readonly-device-smoke.py")
    spec = importlib.util.spec_from_file_location("run_readonly_device_smoke", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeAdbExecutor:
    def __init__(self, adb_path: Path) -> None:
        self.adb_path = str(adb_path)
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: Sequence[str], timeout_seconds: float) -> CommandOutput:
        call = tuple(argv)
        self.calls.append(call)
        assert call[0] == self.adb_path
        assert timeout_seconds == 20.0
        args = call[1:]
        outputs = {
            ("devices", "-l"): (
                b"List of devices attached\n"
                b"b0644fb5 device product:OnePlus9R model:LE2100 device:lemonade\n"
            ),
            ("-s", SERIAL, "shell", "getprop", "ro.product.model"): b"LE2100\n",
            ("-s", SERIAL, "shell", "getprop", "ro.build.version.release"): b"14\n",
            ("-s", SERIAL, "shell", "getprop", "ro.build.version.sdk"): b"34\n",
            ("-s", SERIAL, "shell", "getprop", "ro.product.device"): b"lemonade\n",
            ("-s", SERIAL, "shell", "dumpsys", "package", "com.android.settings"): (
                b"versionCode=34 minSdk=23 targetSdk=34\nversionName=14\n"
            ),
            ("-s", SERIAL, "shell", "pm", "list", "packages"): (
                b"package:com.android.settings\npackage:com.example.target\n"
            ),
            ("-s", SERIAL, "shell", "ss", "-ltn"): b"State Recv-Q Send-Q Local Address\n",
            ("-s", SERIAL, "exec-out", "screencap", "-p"): PNG,
            ("-s", SERIAL, "exec-out", "uiautomator", "dump", "/dev/tty"): UI_XML,
        }
        if args not in outputs:
            return CommandOutput(b"", f"unexpected command: {args}".encode(), 1)
        return CommandOutput(outputs[args])


def adb_file(tmp_path: Path) -> Path:
    path = tmp_path / "adb.exe"
    path.write_bytes(b"fake adb executable")
    return path


def test_probe_uses_only_the_allowlisted_read_operations(tmp_path: Path) -> None:
    adb_path = adb_file(tmp_path)
    executor = FakeAdbExecutor(adb_path)
    probe = ReadOnlyAdbProbe(adb_path=adb_path, serial=SERIAL, executor=executor)

    inventory = probe.inventory("com.android.settings")
    screenshot = probe.screenshot()
    ui_dump = probe.dump_ui()

    assert inventory["model"] == "LE2100"
    assert inventory["androidVersion"] == "14"
    assert inventory["lamdaPackages"] == []
    assert inventory["lamdaPortListening"] is False
    assert inventory["transport"] == "ADB_READ_ONLY_DIAGNOSTIC"
    assert screenshot == PNG
    assert ui_dump.startswith("<?xml")
    assert probe.operations == (
        "devices.list",
        "inventory.ro.product.model",
        "inventory.ro.build.version.release",
        "inventory.ro.build.version.sdk",
        "inventory.ro.product.device",
        "target.package.inspect",
        "lamda.package.detect",
        "lamda.port.detect",
        "screenshot.capture",
        "ui.dump",
    )
    flattened = " ".join(" ".join(call) for call in executor.calls)
    forbidden_commands = (
        " install ",
        " uninstall ",
        " push ",
        " pull ",
        " input ",
        " tap ",
        " swipe ",
    )
    for forbidden in forbidden_commands:
        assert forbidden not in f" {flattened} "


def test_probe_rejects_invalid_package_and_non_png_capture(tmp_path: Path) -> None:
    adb_path = adb_file(tmp_path)
    executor = FakeAdbExecutor(adb_path)
    probe = ReadOnlyAdbProbe(adb_path=adb_path, serial=SERIAL, executor=executor)

    with pytest.raises(ValueError, match="target package is invalid"):
        probe.inventory("not-a-package")

    def non_png(argv: Sequence[str], timeout_seconds: float) -> CommandOutput:
        del argv, timeout_seconds
        return CommandOutput(b"not a png")

    probe = ReadOnlyAdbProbe(adb_path=adb_path, serial=SERIAL, executor=non_png)
    with pytest.raises(ReadOnlyProbeError, match="did not return PNG"):
        probe.screenshot()


def test_runner_writes_diagnostic_bundle_without_claiming_acceptance(tmp_path: Path) -> None:
    module = script_module()
    adb_path = adb_file(tmp_path)
    executor = FakeAdbExecutor(adb_path)
    output = tmp_path / "oneplus9r-20260831"

    result = module.run_smoke(
        adb_path=adb_path,
        serial=SERIAL,
        target_package="com.android.settings",
        output_dir=output,
        executor=executor,
    )

    assert result["diagnosticOnly"] is True
    assert result["hardwareEvidence"] is False
    assert result["acceptanceStatus"] == "blocked_hardware"
    assert result["acceptanceReady"] is False
    assert len(result["blockers"]) == 3
    assert set(result["evidenceFiles"]) == {
        "inventory.json",
        "screenshot.png",
        "ui.xml",
        "command-audit.json",
    }
    assert (output / "screenshot.png").read_bytes() == PNG
    audit = json.loads((output / "command-audit.json").read_text(encoding="utf-8"))
    assert audit["mutatingOperationsExecuted"] is False
    assert audit["rawCommandArgumentsRecorded"] is False
    assert "install" not in audit["operations"]
    stored = json.loads((output / "run-result.json").read_text(encoding="utf-8"))
    assert stored == result
    for path in output.glob("*.json"):
        assert SERIAL not in path.read_text(encoding="utf-8")


def test_dry_run_plan_never_creates_output(tmp_path: Path) -> None:
    module = script_module()

    value = module.plan(SERIAL, "com.android.settings")

    assert value["mode"] == "dry-run"
    assert value["mutatingOperations"] == []
    assert list(tmp_path.iterdir()) == []
