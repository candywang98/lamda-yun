from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "companion_freezer_probe.py"
SPEC = importlib.util.spec_from_file_location("companion_freezer_probe", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

PACKAGE = "com.company.cloudctl.companion"
MEMBERSHIP = "6:freezer:/\n0::/uid_10269/pid_661\n"


def stat(start: str = "123456", pid: str = "661") -> str:
    return f"{pid} (app name (worker)) S " + "0 " * 18 + start + " 0 0\n"


def rows(own: int | None = 0, parent: int | None = 1, frozen: int | None = 1) -> list:
    return [
        {
            "path": "/sys/fs/cgroup/uid_10269/pid_661",
            "freeze": own,
            "frozen": frozen,
            "populated": 1,
        },
        {"path": "/sys/fs/cgroup/uid_10269", "freeze": parent, "frozen": parent, "populated": 1},
    ]


def test_parent_freeze_is_not_negated_by_child_zero() -> None:
    result = probe.classify([rows(), rows()])
    assert result["state"] == "FROZEN_OBSERVED"
    assert result["requestingPaths"] == ["/sys/fs/cgroup/uid_10269"]
    assert result["policyOwner"] == "UNKNOWN"


def test_unfrozen_only_describes_sampled_instants() -> None:
    result = probe.classify([rows(parent=0, frozen=0), rows(parent=0, frozen=0)])
    assert result["state"] == "NOT_FROZEN_AT_SAMPLES"
    assert result["freezeObserved"] is False


def test_transition_retains_freeze_observation_without_continuity_claim() -> None:
    result = probe.classify([rows(), rows(parent=0, frozen=0)])
    assert result["state"] == "TRANSITION_OBSERVED"
    assert result["freezeObserved"] is True
    assert result["requestingPaths"] == []


@pytest.mark.parametrize(
    "samples",
    [
        [],
        [[], []],
        [rows()],
        [rows(), rows()[:1]],
        [rows(own=None), rows(own=None)],
        [rows(frozen=None), rows(frozen=None)],
        [rows(parent=None), rows(parent=None)],
    ],
)
def test_incomplete_or_denied_reads_are_unknown(samples: list) -> None:
    assert probe.classify(samples)["state"] == "UNKNOWN"


def test_requested_but_not_fully_frozen_is_transition() -> None:
    assert probe.classify([rows(frozen=0), rows(frozen=0)])["state"] == "TRANSITION_OBSERVED"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "populated 1\n",
        "frozen bad",
        "frozen 1\nfrozen 0",
        "frozen 2",
        "frozen 0\nfrozen",
        "frozen 0\nfrozen 1 extra",
    ],
)
def test_invalid_events_never_mean_unfrozen(value: str) -> None:
    assert probe.event_bit(value) is None


def test_event_parser_allows_unrelated_fields() -> None:
    assert probe.event_bit("populated 1\nfrozen 1\n") == 1
    assert probe.event_bit("populated 1\nfrozen 0\n") == 0


@pytest.mark.parametrize(
    "membership",
    [
        "",
        "6:freezer:/",
        "0::/uid_1\n0::/uid_2",
        "0::/uid_1/../pid_2",
        "0::/uid_1/./pid_2",
        "0::/uid_1;reboot",
        "0::relative",
        "0::" + "/nested" * 17,
    ],
)
def test_membership_rejects_unsupported_or_unsafe_paths(membership: str) -> None:
    with pytest.raises(ValueError):
        probe.unified_path(membership)


def test_process_identity_handles_spaces_and_parentheses() -> None:
    assert probe.process_start(stat(), "661") == "123456"
    with pytest.raises(ValueError):
        probe.process_start(stat(), "662")


class FakeReader:
    serial = "device-1"

    def __init__(self, *, changed: str | None = None) -> None:
        self.reads: list = []
        self.calls: list = []
        self.changed = changed

    def read(self, *arguments: str) -> str:
        self.calls.append(arguments)
        if arguments[0] == "pidof":
            return "662" if self.changed == "pid" and len(self.calls) > 4 else "661"
        path = arguments[1]
        if path.endswith("/boot_id"):
            if self.changed == "boot" and len(self.calls) > 4:
                return "00000000-0000-4000-8000-000000000002"
            return "00000000-0000-4000-8000-000000000001"
        if path.endswith("/stat"):
            return stat(
                "654321" if self.changed == "start" and len(self.calls) > 4 else "123456",
                "662" if self.changed == "pid" and len(self.calls) > 4 else "661",
            )
        if path.endswith("/cgroup"):
            if self.changed == "cgroup" and len(self.calls) > 4:
                return "0::/uid_10269/other"
            return MEMBERSHIP
        if path.endswith("/cgroup.freeze"):
            return "0" if "/pid_661/" in path else "1"
        if path.endswith("/cgroup.events"):
            return "populated 1\nfrozen 1\n"
        raise AssertionError(f"unexpected command {arguments}")


def test_collect_is_readonly_and_does_not_claim_business_acceptance() -> None:
    reader = FakeReader()
    report = probe.collect(reader, PACKAGE)
    assert report["state"] == "FROZEN_OBSERVED"
    assert report["atomicSnapshot"] is False
    assert report["businessAcceptance"] is False
    assert report["identityMatchesAtChecks"] is True
    assert report["mutatingOperations"] == []
    assert {args[0] for args in reader.calls} == {"pidof", "cat"}


@pytest.mark.parametrize("changed", ["pid", "start", "cgroup", "boot"])
def test_process_restart_reuse_or_movement_invalidates_attribution(changed: str) -> None:
    report = probe.collect(FakeReader(changed=changed), PACKAGE)
    assert report["state"] == "PROCESS_CHANGED"
    assert report["identityMatchesAtChecks"] is False
    assert report["requestingPaths"] == []


@pytest.mark.parametrize("package", ["bad;reboot", "bad package", "-a", "../package"])
def test_package_validation_precedes_adb(package: str) -> None:
    reader = FakeReader()
    with pytest.raises(ValueError):
        probe.collect(reader, package)
    assert reader.calls == []


@pytest.mark.parametrize("serial", ["-a", "device;reboot", "device 1", "device/1", ""])
def test_serial_validation_precedes_adb(serial: str) -> None:
    reader = FakeReader()
    reader.serial = serial
    with pytest.raises(ValueError):
        probe.collect(reader, PACKAGE)
    assert reader.calls == []


def test_timeout_is_bounded_and_does_not_leak_output() -> None:
    reader = probe.AdbReader("/known/adb", "device-1", 3)
    with patch.object(probe.subprocess, "run", side_effect=subprocess.TimeoutExpired("adb", 3)):
        assert reader.read("pidof", PACKAGE) == ""
    assert reader.reads[0]["error"] == "TIMEOUT"


def test_subprocess_uses_exact_device_and_no_shell() -> None:
    reader = probe.AdbReader("/known/adb", "device-1", 3)
    response = subprocess.CompletedProcess([], 1, stdout="not trusted", stderr="not recorded")
    with patch.object(probe.subprocess, "run", return_value=response) as run:
        assert reader.read("pidof", PACKAGE) == ""
    assert run.call_args.args[0] == ["/known/adb", "-s", "device-1", "shell", "pidof", PACKAGE]
    assert run.call_args.kwargs["timeout"] == 3
    assert "shell" not in run.call_args.kwargs
    assert "not recorded" not in str(reader.reads)


def test_empty_group_during_move_away_and_return_does_not_mean_process_unfrozen() -> None:
    class MovedReader(FakeReader):
        def read(self, *arguments: str) -> str:
            result = super().read(*arguments)
            if arguments[-1].endswith("/cgroup.events"):
                return "populated 0\nfrozen 0\n"
            if arguments[-1].endswith("/cgroup.freeze"):
                return "0"
            return result

    report = probe.collect(MovedReader(), PACKAGE)
    assert report["state"] == "UNKNOWN"
    assert report["identityMatchesAtChecks"] is True


@pytest.mark.parametrize("field", ["/boot_id", "/stat", "/cgroup"])
def test_late_identity_read_failure_never_leaves_definitive_state(field: str) -> None:
    class FailedReader(FakeReader):
        def read(self, *arguments: str) -> str:
            result = super().read(*arguments)
            return "" if len(self.calls) > 4 and arguments[-1].endswith(field) else result

    report = probe.collect(FailedReader(), PACKAGE)
    assert report["state"] == "UNKNOWN"
    assert report["identityMatchesAtChecks"] is None


def test_default_cli_never_discovers_or_executes_adb(capsys: pytest.CaptureFixture) -> None:
    with (
        patch("sys.argv", [str(SCRIPT), "--serial", "device-1"]),
        patch.object(probe.shutil, "which", side_effect=AssertionError("must not locate adb")),
        patch.object(probe.subprocess, "run", side_effect=AssertionError("must not execute adb")),
    ):
        probe.main()
    assert '"executed": false' in capsys.readouterr().out
