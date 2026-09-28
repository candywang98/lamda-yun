from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "three_device_preflight.py"
PACKAGE = "com.company.cloudctl.companion"
SERVICE = f"{PACKAGE}/{PACKAGE}.automation.CloudCtlAccessibilityService"
SERIALS = ["b0644fb5", "APH0219624006517", "15faee1d"]


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("three_device_preflight", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


preflight = load_module()


def package_dump(
    *,
    version_code: int,
    version_name: str,
    enabled: int | str,
    stopped: bool,
    hidden: bool = False,
    suspended: bool = False,
    debuggable: bool = False,
) -> str:
    flags = " DEBUGGABLE" if debuggable else ""
    return (
        f"Package [{PACKAGE}]\n"
        f"  versionCode={version_code} minSdk=26 targetSdk=35\n"
        f"  versionName={version_name}\n"
        f"  pkgFlags=[ HAS_CODE{flags} ]\n"
        f"  User 0: installed=true hidden={str(hidden).lower()} "
        f"suspended={str(suspended).lower()} "
        f"stopped={str(stopped).lower()} notLaunched=false enabled={enabled}\n"
    )


def accessibility(*, bound: str, enabled: str, crashed: str) -> str:
    return (
        f"Bound services:{bound}\n"
        f"Enabled services:{enabled}\n"
        f"Crashed services:{crashed}\n"
        "Account-like untrusted tail: secret@example.test token=do-not-emit\n"
    )


class FakeExecutor:
    def __init__(self, outputs: dict[tuple[str, ...], preflight.CommandResult]) -> None:
        self.outputs = outputs
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def __call__(self, argv: Sequence[str], timeout: float) -> preflight.CommandResult:
        call = tuple(argv)
        self.calls.append((call, timeout))
        args = call[1:]
        if args not in self.outputs:
            raise AssertionError(f"unexpected command: {args}")
        return self.outputs[args]


def result(stdout: str = "", returncode: int = 0, error: str | None = None):
    return preflight.CommandResult(stdout=stdout, returncode=returncode, error=error)


def base_outputs() -> dict[tuple[str, ...], preflight.CommandResult]:
    outputs = {
        ("devices",): result(
            "List of devices attached\n"
            "b0644fb5\tdevice\n"
            "APH0219624006517\tdevice\n"
            "15faee1d\tdevice\n"
            "GBGDU19830002425\tdevice\n"
        )
    }
    properties = {
        "b0644fb5": ("OnePlus", "LE2100", "34"),
        "APH0219624006517": ("HUAWEI", "VOG-AL10", "29"),
        "15faee1d": ("OnePlus", "GM1900", "30"),
    }
    for serial, values in properties.items():
        for name, value in zip(
            ("ro.product.manufacturer", "ro.product.model", "ro.build.version.sdk"),
            values,
            strict=True,
        ):
            outputs[("-s", serial, "shell", "getprop", name)] = result(f"{value}\n")
    return outputs


def add_device_outputs(
    outputs: dict[tuple[str, ...], preflight.CommandResult],
    serial: str,
    *,
    package: preflight.CommandResult,
    disabled: preflight.CommandResult,
    pidof: preflight.CommandResult,
    accessibility_dump: preflight.CommandResult,
) -> None:
    outputs[("-s", serial, "shell", "dumpsys", "package", PACKAGE)] = package
    outputs[("-s", serial, "shell", "pm", "list", "packages", "-d", PACKAGE)] = disabled
    outputs[("-s", serial, "shell", "pidof", PACKAGE)] = pidof
    outputs[("-s", serial, "shell", "dumpsys", "accessibility")] = accessibility_dump


def observed_outputs() -> dict[tuple[str, ...], preflight.CommandResult]:
    outputs = base_outputs()
    add_device_outputs(
        outputs,
        "b0644fb5",
        package=result(
            package_dump(
                version_code=3,
                version_name="0.1.0-business-acceptance.3",
                enabled=0,
                stopped=False,
            )
        ),
        disabled=result(),
        pidof=result(returncode=1),
        accessibility_dump=result(
            accessibility(bound="{}", enabled=f"{{{SERVICE}}}", crashed=f"{{{SERVICE}}}")
        ),
    )
    add_device_outputs(
        outputs,
        "APH0219624006517",
        package=result(
            package_dump(
                version_code=1,
                version_name="0.1.0",
                enabled=0,
                stopped=False,
                debuggable=True,
            )
        ),
        disabled=result(),
        pidof=result("28411\n"),
        accessibility_dump=result(
            accessibility(
                bound=(
                    "{Service[label=CloudCtl structured aut…, "
                    "feedbackType[FEEDBACK_GENERIC], capabilities=33]}"
                ),
                enabled=f"{{{SERVICE}}}",
                crashed="{}",
            )
        ),
    )
    add_device_outputs(
        outputs,
        "15faee1d",
        package=result(package_dump(version_code=1, version_name="0.1.0", enabled=2, stopped=True)),
        disabled=result(f"package:{PACKAGE}\n"),
        pidof=result(returncode=1),
        accessibility_dump=result(accessibility(bound="{}", enabled="{}", crashed="{}")),
    )
    return outputs


def ready_outputs() -> dict[tuple[str, ...], preflight.CommandResult]:
    outputs = base_outputs()
    for index, serial in enumerate(SERIALS, start=1):
        add_device_outputs(
            outputs,
            serial,
            package=result(
                package_dump(
                    version_code=index,
                    version_name=f"0.1.{index}",
                    enabled=0,
                    stopped=False,
                )
            ),
            disabled=result(),
            pidof=result(f"{28000 + index}\n"),
            accessibility_dump=result(
                accessibility(bound=f"{{{SERVICE}}}", enabled=f"{{{SERVICE}}}", crashed="{}")
            ),
        )
    return outputs


def test_observed_three_device_forms_fail_closed_without_raw_output() -> None:
    executor = FakeExecutor(observed_outputs())

    report = preflight.run_preflight(
        adb="/known/adb",
        serials=SERIALS,
        timeout_seconds=4,
        executor=executor,
    )

    assert report["localPreflight"] == {"state": "UNKNOWN", "ready": False}
    assert set(report) == {
        "schemaVersion",
        "diagnosticScope",
        "package",
        "localPreflight",
        "cloudAccountReadiness",
        "devices",
    }
    assert report["cloudAccountReadiness"] == {
        "state": "UNKNOWN_NOT_CHECKED",
        "ready": False,
        "reasons": ["CLOUD_BINDING_ACCOUNT_AND_TASK_STATE_NOT_CHECKED"],
    }
    by_serial = {device["serial"]: device for device in report["devices"]}

    oneplus_9r = by_serial["b0644fb5"]
    assert oneplus_9r["package"]["versionCode"] == 3
    assert oneplus_9r["package"]["versionName"] == "0.1.0-business-acceptance.3"
    assert oneplus_9r["package"]["disabled"] is False
    assert oneplus_9r["process"]["state"] == "NOT_RUNNING"
    assert oneplus_9r["accessibility"] == {
        "enabled": "YES",
        "binding": "NOT_BOUND",
        "crashed": "YES",
    }
    assert set(oneplus_9r["localBusinessPrerequisites"]["reasons"]) == {
        "PROCESS_NOT_RUNNING",
        "ACCESSIBILITY_NOT_BOUND",
        "ACCESSIBILITY_SERVICE_CRASHED",
    }

    huawei = by_serial["APH0219624006517"]
    assert huawei["package"]["debuggable"] is True
    assert huawei["process"]["state"] == "RUNNING"
    assert huawei["accessibility"]["binding"] == "AMBIGUOUS_LABEL_ONLY"
    assert huawei["localBusinessPrerequisites"] == {
        "state": "UNKNOWN",
        "ready": False,
        "reasons": ["ACCESSIBILITY_BINDING_IDENTITY_AMBIGUOUS"],
    }

    oneplus_7 = by_serial["15faee1d"]
    assert oneplus_7["package"]["enabledState"] == 2
    assert oneplus_7["package"]["disabled"] is True
    assert oneplus_7["package"]["stopped"] is True
    assert "PACKAGE_DISABLED" in oneplus_7["localBusinessPrerequisites"]["reasons"]

    encoded = json.dumps(report, ensure_ascii=False)
    assert "secret@example.test" not in encoded
    assert "do-not-emit" not in encoded
    assert "CloudCtl structured" not in encoded
    assert "GBGDU19830002425" not in encoded
    assert "stdout" not in encoded
    assert "stderr" not in encoded
    assert all(timeout == 4 for _, timeout in executor.calls)


def test_exact_component_binding_allows_local_pass_but_not_cloud_claim() -> None:
    report = preflight.run_preflight(
        adb="/known/adb",
        serials=SERIALS,
        executor=FakeExecutor(ready_outputs()),
    )

    assert report["localPreflight"] == {"state": "READY", "ready": True}
    assert all(device["localBusinessPrerequisites"]["ready"] for device in report["devices"])
    assert report["cloudAccountReadiness"]["ready"] is False
    assert report["diagnosticScope"]["businessAcceptance"] is False
    assert report["diagnosticScope"]["mutatingOperations"] == []


def test_unavailable_adb_states_do_not_trigger_device_commands() -> None:
    outputs = {
        ("devices",): result(
            "List of devices attached\nb0644fb5\tunauthorized\nAPH0219624006517\toffline\n"
        )
    }
    executor = FakeExecutor(outputs)

    report = preflight.run_preflight(adb="/known/adb", serials=SERIALS, executor=executor)

    assert [device["adbAuthorization"]["state"] for device in report["devices"]] == [
        "UNAUTHORIZED",
        "OFFLINE",
        "NOT_FOUND",
    ]
    assert report["localPreflight"] == {"state": "UNKNOWN", "ready": False}
    assert [call[0][1:] for call in executor.calls] == [("devices",)]


def test_enumeration_timeout_is_unknown_and_fails_closed() -> None:
    executor = FakeExecutor({("devices",): result(returncode=None, error="TIMEOUT")})

    report = preflight.run_preflight(adb="/known/adb", serials=SERIALS, executor=executor)

    assert report["localPreflight"] == {"state": "UNKNOWN", "ready": False}
    assert {device["adbAuthorization"]["state"] for device in report["devices"]} == {"UNKNOWN"}
    assert len(executor.calls) == 1


@pytest.mark.parametrize(
    ("bound", "expected"),
    [
        (f"{{{SERVICE}}}", "BOUND"),
        ("{}", "NOT_BOUND"),
        ("{Service[label=CloudCtl structured automation]}", "AMBIGUOUS_LABEL_ONLY"),
        ("{Service[label=Unrelated accessibility service]}", "NOT_BOUND"),
    ],
)
def test_accessibility_requires_definitive_component_identity(bound: str, expected: str) -> None:
    parsed = preflight.parse_accessibility(
        result(accessibility(bound=bound, enabled=f"{{{SERVICE}}}", crashed="{}")),
        PACKAGE,
    )

    assert parsed["binding"] == expected


def test_accessibility_sections_do_not_absorb_later_component_text() -> None:
    dump = (
        "Bound services:{}\n"
        "Enabled services:{}\n"
        "Crashed services:{}\n"
        f"Other diagnostics:{{{SERVICE}}}\n"
    )

    parsed = preflight.parse_accessibility(result(dump), PACKAGE)

    assert parsed == {"enabled": "NO", "binding": "NOT_BOUND", "crashed": "NO"}


def test_accessibility_component_match_rejects_longer_class_name() -> None:
    other_service = f"{SERVICE}Other"

    parsed = preflight.parse_accessibility(
        result(
            accessibility(
                bound=f"{{{other_service}}}",
                enabled=f"{{{other_service}}}",
                crashed=f"{{{other_service}}}",
            )
        ),
        PACKAGE,
    )

    assert parsed == {"enabled": "NO", "binding": "NOT_BOUND", "crashed": "NO"}


def test_accessibility_uses_only_user_zero_scope() -> None:
    dump = (
        "User state[attributes:{id=10, currentUser=false}]\n"
        f"  Bound services:{{{SERVICE}}}\n"
        f"  Enabled services:{{{SERVICE}}}\n"
        "  Crashed services:{}\n"
        "User state[attributes:{id=0, currentUser=true}]\n"
        "  Bound services:{}\n"
        "  Enabled services:{}\n"
        "  Crashed services:{}\n"
    )

    parsed = preflight.parse_accessibility(result(dump), PACKAGE)

    assert parsed == {"enabled": "NO", "binding": "NOT_BOUND", "crashed": "NO"}


def test_disabled_listing_is_definitive_even_if_enabled_field_is_unknown() -> None:
    dump = package_dump(version_code=3, version_name="0.1.0", enabled=0, stopped=False)
    dump = dump.replace("enabled=0", "enabled=unknown")

    parsed = preflight.parse_package(PACKAGE, result(dump), result(f"package:{PACKAGE}\n"))

    assert parsed["disabled"] is True


def test_unknown_enabled_enum_fails_closed() -> None:
    package = preflight.parse_package(
        PACKAGE,
        result(package_dump(version_code=3, version_name="0.1.0", enabled=99, stopped=False)),
        result(),
    )

    readiness = preflight.local_readiness(
        package,
        {"state": "RUNNING"},
        {"enabled": "YES", "binding": "BOUND", "crashed": "NO"},
    )

    assert package["enabledState"] == 99
    assert package["disabled"] is None
    assert readiness == {
        "state": "UNKNOWN",
        "ready": False,
        "reasons": ["PACKAGE_DISABLED_STATE_UNKNOWN"],
    }


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("hidden", "PACKAGE_HIDDEN"),
        ("suspended", "PACKAGE_SUSPENDED"),
    ],
)
def test_hidden_or_suspended_package_is_not_ready(field: str, reason: str) -> None:
    package = preflight.parse_package(
        PACKAGE,
        result(
            package_dump(
                version_code=3,
                version_name="0.1.0",
                enabled=0,
                stopped=False,
                **{field: True},
            )
        ),
        result(),
    )

    readiness = preflight.local_readiness(
        package,
        {"state": "RUNNING"},
        {"enabled": "YES", "binding": "BOUND", "crashed": "NO"},
    )

    assert package[field] is True
    assert readiness == {"state": "NOT_READY", "ready": False, "reasons": [reason]}


@pytest.mark.parametrize(
    "package_text",
    [
        "",
        "versionCode=3\nversionName=0.1.0\n",
        "User 0: installed=true stopped=false enabled=0\nversionName=bad/account\n",
    ],
)
def test_incomplete_package_evidence_never_becomes_ready(package_text: str) -> None:
    package = preflight.parse_package(PACKAGE, result(package_text), result())
    readiness = preflight.local_readiness(
        package,
        {"state": "RUNNING"},
        {"enabled": "YES", "binding": "BOUND", "crashed": "NO"},
    )

    assert readiness["ready"] is False
    assert readiness["state"] == "UNKNOWN"


def test_pidof_exit_one_empty_is_not_running_but_other_shapes_are_unknown() -> None:
    assert preflight.parse_process(result(returncode=1)) == {"state": "NOT_RUNNING"}
    assert preflight.parse_process(result("123 456\n")) == {"state": "RUNNING"}
    assert preflight.parse_process(result("not-a-pid\n")) == {"state": "UNKNOWN"}
    assert preflight.parse_process(result(returncode=2)) == {"state": "UNKNOWN"}


@pytest.mark.parametrize(
    ("serials", "package", "message"),
    [
        (SERIALS[:2], PACKAGE, "exactly three"),
        ([SERIALS[0], SERIALS[0], SERIALS[2]], PACKAGE, "unique"),
        ([SERIALS[0], "-s", SERIALS[2]], PACKAGE, "serial"),
        (SERIALS, "bad;package", "package"),
    ],
)
def test_inputs_must_be_exact_unique_and_safe(
    serials: list[str], package: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        preflight.validate_inputs(serials, package)


@pytest.mark.parametrize("timeout", [0, -1, 30.1])
def test_timeout_is_bounded(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout"):
        preflight.run_preflight(
            adb="/known/adb",
            serials=SERIALS,
            timeout_seconds=timeout,
            executor=FakeExecutor({}),
        )


def test_subprocess_execution_is_bounded_and_never_uses_a_shell() -> None:
    completed = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="untrusted output", stderr="credential=never-emit"
    )
    with patch.object(preflight.subprocess, "run", return_value=completed) as run:
        response = preflight.execute(["/known/adb", "devices"], 3.5)

    assert response == preflight.CommandResult(stdout="untrusted output", returncode=1)
    assert run.call_args.args[0] == ["/known/adb", "devices"]
    assert run.call_args.kwargs["timeout"] == 3.5
    assert "shell" not in run.call_args.kwargs
    assert "credential" not in repr(response)


def test_only_allowlisted_read_commands_are_issued() -> None:
    executor = FakeExecutor(ready_outputs())

    preflight.run_preflight(adb="/known/adb", serials=SERIALS, executor=executor)

    arguments = [call[0][1:] for call in executor.calls]
    assert arguments[0] == ("devices",)
    for command in arguments[1:]:
        assert command[0] == "-s"
        assert command[2] == "shell"
        assert command[3:] in {
            ("getprop", "ro.product.manufacturer"),
            ("getprop", "ro.product.model"),
            ("getprop", "ro.build.version.sdk"),
            ("dumpsys", "package", PACKAGE),
            ("pm", "list", "packages", "-d", PACKAGE),
            ("pidof", PACKAGE),
            ("dumpsys", "accessibility"),
        }
    flattened = " ".join(" ".join(command) for command in arguments)
    forbidden_commands = (
        " install ",
        " uninstall ",
        " push ",
        " pull ",
        " force-stop ",
        " settings put ",
    )
    for forbidden in forbidden_commands:
        assert forbidden not in f" {flattened} "


def test_cli_reports_missing_adb_without_attempting_discovery_or_devices(capsys) -> None:
    argv = [item for serial in SERIALS for item in ("--serial", serial)]
    with (
        patch.object(preflight.shutil, "which", return_value=None),
        patch.object(preflight.subprocess, "run", side_effect=AssertionError("must not run")),
    ):
        exit_code = preflight.main(argv)

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert report == {
        "schemaVersion": 1,
        "localPreflight": {"state": "UNKNOWN", "ready": False},
        "reason": "ADB_EXECUTABLE_NOT_FOUND",
    }
