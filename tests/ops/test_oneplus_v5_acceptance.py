from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from zoneinfo import ZoneInfo

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "artifacts"
    / "three-device-20260928"
    / "install-oneplus-v5.py"
)
CLOUD_SCRIPT = SCRIPT.with_name("oneplus-v5-cloud.py")


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("install_oneplus_v5", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


acceptance = load_module()


def load_cloud_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("oneplus_v5_cloud", CLOUD_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cloud_helper = load_cloud_module()


def candidate() -> dict[str, Any]:
    return {
        "sha256": acceptance.EXPECTED_V5_APK,
        "package": acceptance.PACKAGE,
        "versionCode": 5,
        "versionName": "0.1.0-business-acceptance.5",
        "signerSha256": acceptance.EXPECTED_SIGNER,
        "sourceRevision": acceptance.EXPECTED_SOURCE_REVISION,
        "sourceDirty": False,
    }


def cloud(*, maintenance: bool, version: int) -> dict[str, Any]:
    zeros = {
        "activeLeases": 0,
        "unfinishedTasks": 0,
        "enabledSchedules": 0,
        "activePreviews": 0,
        "activeDebugSessions": 0,
    }
    return {
        "device": {
            "maintenance": maintenance,
            "version": version,
            "tenantMatchesExpected": True,
            "activeBindingMatchesExpected": True,
        },
        "identity": {
            "retained": True,
            "activeBindingCount": 1,
            "accountBindingCount": 1,
            "boundAccountCount": 1,
        },
        "occupancy": {
            "global": dict(zeros),
            "targetDevice": dict(zeros),
            "globalIdle": True,
            "targetIdle": True,
        },
        "counts": dict(acceptance.EXPECTED_COUNTS),
        "imConfig": {
            "httpStatus": 200,
            "receiveOnly": True,
            "mode": "NOTIFICATION",
            "enabled": True,
        },
    }


def device(*, code: int = 4, name: str = "0.1.0-business-acceptance.4") -> dict[str, Any]:
    return {
        "serial": acceptance.SERIAL,
        "adbState": "device",
        "model": acceptance.MODEL,
        "currentUser": "0",
        "versionCode": code,
        "versionName": name,
    }


def observation(*, deferrals: int, heartbeats: int, healthy: bool = True) -> dict[str, Any]:
    return {
        "maintenanceDeferralCount": deferrals,
        "heartbeatCount": heartbeats,
        "allRuntimeSamplesHealthy": healthy,
        "cloudGatePassed": True,
    }


def services_dump(
    *,
    foreground: str = "true",
    foreground_id: int = 1001,
    target_connection: str | None = ".automation.CloudCtlAccessibilityService",
    target_user: int = 0,
    unrelated_foreground: bool = False,
) -> str:
    connection = (
        "      ConnectionRecord{d5fd097 u0 CR FGSA CAPS "
        f"{acceptance.PACKAGE}/{target_connection}:@6de8f16 flags=0x2101001}}\n"
        if target_connection is not None
        else ""
    )
    unrelated = (
        "  * ServiceRecord{aaaa111 u0 com.example.other/.OtherService}\n"
        "    app=ProcessRecord{bbbb222 9999:com.example.other/u0a777}\n"
        "    isForeground=true foregroundId=9000 types=1\n"
        if unrelated_foreground
        else ""
    )
    return (
        "  * ServiceRecord{965785e u0 "
        f"{acceptance.PACKAGE}/.service.CompanionSyncService}}\n"
        f"    app=ProcessRecord{{f240284 23518:{acceptance.PACKAGE}/u0a269}}\n"
        f"    isForeground={foreground} foregroundId={foreground_id} types=40000000\n"
        "    startRequested=true delayedStop=false stopIfKilled=false\n"
        "  * ServiceRecord{f8ef4c8 u"
        f"{target_user} {acceptance.PACKAGE}/.automation.CloudCtlAccessibilityService}}\n"
        f"    app=ProcessRecord{{f240284 23518:{acceptance.PACKAGE}/u0a269}}\n"
        f"{connection}"
        f"{unrelated}"
    )


def accessibility_dump(*, enabled_component: str | None = None, crashed: str = "{}") -> str:
    enabled = enabled_component or acceptance.ACCESSIBILITY_COMPONENT
    return (
        "User state[\n"
        "  attributes:{id=0}\n"
        "]\n"
        "Bound services:{Service[label=CloudCtl structured automation]}\n"
        f"Enabled services:{{{{{enabled}}}}}\n"
        f"Crashed services:{crashed}\n"
    )


class FakeOperations:
    def __init__(
        self,
        *,
        fail_at: str | None = None,
        maintenance_proven: bool = True,
        prepare_ack_then_fail: bool = False,
    ) -> None:
        self.fail_at = fail_at
        self.maintenance_proven = maintenance_proven
        self.prepare_ack_then_fail = prepare_ack_then_fail
        self.calls: list[str] = []
        self.released_lock: dict[str, Any] | None = None
        self.lock = {"fencing": 27, "owner_token": "private-exact-token"}
        self.owned = False

    def step(self, name: str, value: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(name)
        if self.fail_at == name:
            raise acceptance.AcceptanceError(f"failed at {name}")
        return value

    def candidate_preflight(self) -> dict[str, Any]:
        return self.step("candidate", candidate())

    def acquire_lock(self) -> dict[str, Any]:
        return self.step("acquire", self.lock)

    def locked_preflight(self) -> dict[str, Any]:
        return self.step("preflight", {"ready": True})

    def prepare_maintenance(self) -> dict[str, Any]:
        self.calls.append("prepare")
        if self.fail_at == "prepare":
            raise acceptance.AcceptanceError("prepare response uncertain")
        self.owned = True
        if self.prepare_ack_then_fail:
            raise acceptance.AcceptanceError("post-ack snapshot failed")
        return cloud(maintenance=True, version=11)

    def install_once(self) -> dict[str, Any]:
        return self.step("install", {"attempts": 1})

    def observe_maintenance(self) -> dict[str, Any]:
        result = observation(
            deferrals=2 if self.maintenance_proven else 1,
            heartbeats=3,
        )
        return self.step("observe-maintenance", result)

    def finish_maintenance(self) -> dict[str, Any]:
        value = self.step("finish", cloud(maintenance=False, version=12))
        self.owned = False
        return value

    def observe_post_maintenance(self) -> dict[str, Any]:
        return self.step("observe-post", observation(deferrals=0, heartbeats=3))

    def final_verify(self) -> dict[str, Any]:
        return self.step("final", {"ready": True})

    def cleanup_maintenance(self) -> dict[str, Any]:
        value = self.step("cleanup", {"changed": True})
        self.owned = False
        return value

    def maintenance_owned(self) -> bool:
        return self.owned

    def release_lock(self, lock: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("release")
        self.released_lock = lock
        if self.fail_at == "release":
            raise acceptance.AcceptanceError("release failed")
        return {"state": "FREE", "released_fencing": lock["fencing"]}


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("sha256", "0" * 64),
        ("package", "com.example.wrong"),
        ("versionCode", 6),
        ("versionName", "0.1.0-business-acceptance.4"),
        ("signerSha256", "f" * 64),
        ("sourceRevision", "deadbee"),
        ("sourceDirty", True),
    ],
)
def test_candidate_identity_is_exact(field: str, wrong: Any) -> None:
    observed = candidate()
    observed[field] = wrong

    with pytest.raises(acceptance.AcceptanceError, match="candidate identity mismatch"):
        acceptance.validate_candidate(observed)


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("serial", "15faee1d"),
        ("adbState", "offline"),
        ("model", "GM1900"),
        ("currentUser", "10"),
        ("versionCode", 3),
        ("versionName", "0.1.0-business-acceptance.3"),
    ],
)
def test_device_source_v4_gate_rejects_wrong_identity(field: str, wrong: Any) -> None:
    observed = device()
    observed[field] = wrong

    with pytest.raises(acceptance.AcceptanceError, match="device/package identity mismatch"):
        acceptance.validate_device_identity(
            observed,
            version_code=4,
            version_name="0.1.0-business-acceptance.4",
        )


def test_cloud_gate_rejects_stale_maintenance_expected_version() -> None:
    with pytest.raises(acceptance.AcceptanceError, match="maintenance state/version mismatch"):
        acceptance.validate_cloud(
            cloud(maintenance=False, version=9), maintenance=False, version=10
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda item: item["occupancy"]["global"].__setitem__("activeLeases", 1), "occupancy"),
        (lambda item: item["occupancy"].__setitem__("targetIdle", False), "occupancy"),
        (lambda item: item["identity"].__setitem__("retained", False), "identity"),
        (lambda item: item["device"].__setitem__("tenantMatchesExpected", False), "tenant"),
        (lambda item: item["counts"].__setitem__("mobileTasks", 380), "aggregate"),
        (lambda item: item["imConfig"].__setitem__("receiveOnly", False), "receive-only"),
    ],
)
def test_cloud_gate_fails_closed_for_occupancy_identity_and_count_drift(
    mutate: Any, message: str
) -> None:
    observed = cloud(maintenance=False, version=10)
    mutate(observed)

    with pytest.raises(acceptance.AcceptanceError, match=message):
        acceptance.validate_cloud(observed, maintenance=False, version=10)


@pytest.mark.parametrize("scope", ["global", "targetDevice"])
@pytest.mark.parametrize(
    "field",
    [
        "activeLeases",
        "unfinishedTasks",
        "enabledSchedules",
        "activePreviews",
        "activeDebugSessions",
    ],
)
def test_every_occupancy_dimension_must_be_zero(scope: str, field: str) -> None:
    observed = cloud(maintenance=False, version=10)
    observed["occupancy"][scope][field] = 1

    with pytest.raises(acceptance.AcceptanceError, match="occupancy"):
        acceptance.validate_cloud(observed, maintenance=False, version=10)


@pytest.mark.parametrize("scope", ["global", "targetDevice"])
def test_occupancy_map_must_contain_all_five_fields(scope: str) -> None:
    observed = cloud(maintenance=False, version=10)
    observed["occupancy"][scope].pop("activeDebugSessions")

    with pytest.raises(acceptance.AcceptanceError, match="map is incomplete"):
        acceptance.validate_cloud(observed, maintenance=False, version=10)


def test_successful_window_uses_one_install_and_exact_release_identity() -> None:
    operations = FakeOperations()

    result = acceptance.execute_window(operations)

    assert result["status"] == "PROVEN"
    assert operations.calls == [
        "candidate",
        "acquire",
        "preflight",
        "prepare",
        "install",
        "observe-maintenance",
        "finish",
        "observe-post",
        "final",
        "release",
    ]
    assert operations.released_lock is operations.lock
    assert operations.released_lock == {
        "fencing": 27,
        "owner_token": "private-exact-token",
    }


@pytest.mark.parametrize("failure", ["install", "observe-maintenance", "finish"])
def test_partial_prepare_install_or_observation_failure_cleans_up_and_releases(
    failure: str,
) -> None:
    operations = FakeOperations(fail_at=failure)

    result = acceptance.execute_window(operations)

    assert result["status"] == "FAILED"
    assert "cleanup" in operations.calls
    assert operations.calls[-1] == "release"
    assert result["lockReleased"] is True


def test_external_competing_prepare_at_version11_is_not_owned_or_cleared() -> None:
    operations = FakeOperations(fail_at="prepare")

    result = acceptance.execute_window(operations)

    assert result["status"] == "FAILED"
    assert operations.maintenance_owned() is False
    assert "cleanup" not in operations.calls
    assert operations.calls[-1] == "release"


def test_uncertain_prepare_transport_failure_remains_unknown_and_is_not_cleared() -> None:
    operations = FakeOperations(fail_at="prepare")

    result = acceptance.execute_window(operations)

    assert result["failure"]["message"] == "prepare response uncertain"
    assert "cleanup" not in operations.calls
    assert result["lockReleased"] is True


def test_acknowledged_prepare_then_snapshot_failure_is_owned_and_cleaned() -> None:
    operations = FakeOperations(prepare_ack_then_fail=True)

    result = acceptance.execute_window(operations)

    assert result["status"] == "FAILED"
    assert operations.calls == [
        "candidate",
        "acquire",
        "preflight",
        "prepare",
        "cleanup",
        "release",
    ]
    assert result["maintenanceCleanup"] == {"changed": True}
    assert result["lockReleased"] is True


def test_candidate_or_locked_preflight_failure_does_not_claim_maintenance() -> None:
    candidate_failure = FakeOperations(fail_at="candidate")
    preflight_failure = FakeOperations(fail_at="preflight")

    candidate_result = acceptance.execute_window(candidate_failure)
    preflight_result = acceptance.execute_window(preflight_failure)

    assert candidate_result["status"] == "FAILED"
    assert candidate_failure.calls == ["candidate"]
    assert preflight_result["status"] == "FAILED"
    assert preflight_failure.calls == ["candidate", "acquire", "preflight", "release"]


def test_timing_threshold_miss_is_not_proven_but_still_exits_maintenance() -> None:
    operations = FakeOperations(maintenance_proven=False)

    result = acceptance.execute_window(operations)

    assert result["status"] == "NOT_PROVEN"
    assert result["maintenanceRecovery"] == "NOT_PROVEN"
    assert result["postMaintenancePresence"] == "PROVEN"
    assert "finish" in operations.calls
    assert "cleanup" not in operations.calls
    assert result["lockReleased"] is True


def test_cleanup_or_release_failure_is_prominent() -> None:
    cleanup_failure = FakeOperations(fail_at="cleanup")
    cleanup_failure.fail_at = "install"
    original_step = cleanup_failure.step

    def fail_cleanup(name: str, value: dict[str, Any]) -> dict[str, Any]:
        if name == "cleanup":
            raise acceptance.AcceptanceError("ownership conflict")
        return original_step(name, value)

    cleanup_failure.step = fail_cleanup  # type: ignore[method-assign]
    release_failure = FakeOperations(fail_at="release")

    cleanup_result = acceptance.execute_window(cleanup_failure)
    release_result = acceptance.execute_window(release_failure)

    assert cleanup_result["status"] == "FAILED"
    assert cleanup_result["cleanupFailure"]["message"] == "ownership conflict"
    assert release_result["status"] == "FAILED"
    assert release_result["lockReleased"] is False
    assert release_result["releaseFailure"]["message"] == "release failed"


@pytest.mark.parametrize(
    "release_result",
    [
        {"state": "FREE", "released_fencing": 28},
        {"state": "RELEASED", "released_fencing": 27},
        {"state": "FREE"},
    ],
)
def test_release_acknowledgement_requires_free_state_and_exact_fencing(
    release_result: dict[str, Any],
) -> None:
    operations = FakeOperations()
    operations.release_lock = lambda _lock: release_result  # type: ignore[method-assign]

    result = acceptance.execute_window(operations)

    assert result["status"] == "FAILED"
    assert result["lockReleased"] is False
    assert result["releaseFailure"] == {
        "type": "AcceptanceError",
        "message": "device lock release acknowledgement mismatch",
    }


def test_owned_cleanup_identity_is_independent_of_aggregate_count_drift() -> None:
    snapshot = cloud(maintenance=True, version=11)
    snapshot["counts"]["mobileTasks"] = 999
    snapshot["occupancy"]["global"]["unfinishedTasks"] = 4
    snapshot["occupancy"]["globalIdle"] = False

    cloud_helper.assert_cleanup_identity(snapshot)


def test_owned_cleanup_still_refuses_binding_or_tenant_drift() -> None:
    snapshot = cloud(maintenance=True, version=11)
    snapshot["device"]["activeBindingMatchesExpected"] = False

    with pytest.raises(RuntimeError, match="active binding drift"):
        cloud_helper.assert_cleanup_identity(snapshot)


def test_only_authorized_install_command_is_exposed() -> None:
    expected_apk = (
        Path.home()
        / "CloudCtlExternal"
        / "acceptance"
        / "20260928-v5"
        / "cloudctl-business-acceptance-v5.apk"
    )
    assert acceptance.install_command() == (
        "adb",
        "-s",
        "b0644fb5",
        "install",
        "-r",
        str(expected_apk),
    )
    source = SCRIPT.read_text()
    assert '"am", "start"' not in source
    assert "force-stop" not in source
    assert "clear-data" not in source
    assert "uninstall" not in source


def test_phone_events_use_epoch_exact_process_and_deduplicate_overlapping_windows() -> None:
    raw = "\n".join(
        [
            "1790639999.900 4310 4311 I CompanionSync: Heartbeat successful",
            "1790640000.100 4310 4311 I CompanionSync: Heartbeat successful",
            "1790640000.100 4310 4311 I CompanionSync: Heartbeat successful",
            "1790640001.200 9999 9998 I CompanionSync: "
            "claim deferred while device is in maintenance",
            "1790640002.300 4310 4311 I CompanionSync: "
            "claim deferred while device is in maintenance",
            "1790640003.400 4310 4311 W CompanionSync: task payload must not be retained",
        ]
    )

    events = acceptance.parse_phone_events(
        raw,
        since_epoch=1790640000.0,
        process_id="4310",
    )

    assert events == [
        {"timestamp": "1790640000.100", "processId": "4310", "type": "heartbeat"},
        {
            "timestamp": "1790640002.300",
            "processId": "4310",
            "type": "maintenanceDeferral",
        },
    ]


@pytest.mark.parametrize(
    "line",
    [
        "1790640001.000 4310 1 W CompanionSync: Heartbeat successful",
        "1790640001.000 4310 1 E CompanionSync: Heartbeat successful",
        "1790640001.000 4310 1 I OtherTag: Heartbeat successful",
        "1790640001.000 4310 1 I CompanionSync: prefix Heartbeat successful",
        "1790640001.000 4310 1 I CompanionSync: Heartbeat successful suffix",
        '1790640001.000 4310 1 W CompanionSync: "Heartbeat successful"',
        "nan 4310 1 I CompanionSync: Heartbeat successful",
        "inf 4310 1 I CompanionSync: Heartbeat successful",
        "not-a-time 4310 1 I CompanionSync: Heartbeat successful",
    ],
)
def test_phone_events_reject_nonexact_or_malformed_lines(line: str) -> None:
    assert (
        acceptance.parse_phone_events(
            line,
            since_epoch=1790640000.0,
            process_id="4310",
        )
        == []
    )


def test_device_ahead_of_host_does_not_admit_pre_watermark_event() -> None:
    host_boundary = 1000.0
    device_boundary = 2000.0
    raw = "\n".join(
        [
            "1500.000 4310 1 I CompanionSync: Heartbeat successful",
            "2000.001 4310 1 I CompanionSync: Heartbeat successful",
        ]
    )

    events = acceptance.parse_phone_events(
        raw,
        since_epoch=device_boundary,
        process_id="4310",
    )

    assert host_boundary < 1500.0 < device_boundary
    assert [item["timestamp"] for item in events] == ["2000.001"]


def test_device_behind_host_uses_device_watermark_not_host_epoch() -> None:
    device_boundary = 1000.0
    host_boundary = 2000.0
    raw = "1000.001 4310 1 I CompanionSync: Heartbeat successful"

    events = acceptance.parse_phone_events(
        raw,
        since_epoch=device_boundary,
        process_id="4310",
    )

    assert 1000.001 < host_boundary
    assert [item["timestamp"] for item in events] == ["1000.001"]


def test_logcat_since_argument_is_a_time_not_an_integer_line_count() -> None:
    argument = acceptance.logcat_since_argument(1790640000.1234)

    assert argument == "1790640000.123"
    assert "." in argument


def test_phone_event_epoch_filter_crosses_local_midnight_without_date_assumption() -> None:
    zone = ZoneInfo("Asia/Shanghai")
    before = datetime(2026, 9, 28, 23, 59, 59, 900000, tzinfo=zone).timestamp()
    boundary = datetime(2026, 9, 29, 0, 0, 0, tzinfo=zone).timestamp()
    after = datetime(2026, 9, 29, 0, 0, 0, 100000, tzinfo=zone).timestamp()
    raw = "\n".join(
        [
            f"{before:.3f} 23518 1 I CompanionSync: Heartbeat successful",
            f"{after:.3f} 23518 1 I CompanionSync: Heartbeat successful",
        ]
    )

    events = acceptance.parse_phone_events(
        raw,
        since_epoch=boundary,
        process_id="23518",
    )

    assert events == [{"timestamp": f"{after:.3f}", "processId": "23518", "type": "heartbeat"}]


def test_observed_exact_user0_service_records_are_healthy() -> None:
    service = acceptance.parse_service_health(services_dump(), process_id="23518")
    accessibility = acceptance.parse_accessibility_health(accessibility_dump())

    assert service == {
        "syncServicePresent": True,
        "syncServiceForeground": True,
        "accessibilityBound": True,
    }
    assert accessibility == {
        "accessibilityEnabledFromDump": True,
        "accessibilityCrashed": False,
    }


def test_enabled_but_unbound_target_does_not_borrow_another_service_connection() -> None:
    raw = services_dump(target_connection=None) + (
        "  * ServiceRecord{abc1234 u0 com.example.other/.OtherAccessibilityService}\n"
        "    app=ProcessRecord{def5678 9999:com.example.other/u0a777}\n"
        "      ConnectionRecord{aa11bb2 u0 CR com.example.other/.OtherAccessibilityService:@1}\n"
    )

    result = acceptance.parse_service_health(raw, process_id="23518")

    assert result["accessibilityBound"] is False


def test_suffixed_component_is_not_the_target_binding() -> None:
    result = acceptance.parse_service_health(
        services_dump(target_connection=".automation.CloudCtlAccessibilityServiceSuffix"),
        process_id="23518",
    )

    assert result["accessibilityBound"] is False


@pytest.mark.parametrize(
    ("foreground", "foreground_id"),
    [("false", 1001), ("true", 0)],
)
def test_target_foreground_requires_explicit_true_and_nonzero_id(
    foreground: str, foreground_id: int
) -> None:
    result = acceptance.parse_service_health(
        services_dump(
            foreground=foreground,
            foreground_id=foreground_id,
            unrelated_foreground=True,
        ),
        process_id="23518",
    )

    assert result["syncServicePresent"] is True
    assert result["syncServiceForeground"] is False


def test_other_user_target_record_is_not_user0_binding() -> None:
    result = acceptance.parse_service_health(
        services_dump(target_user=10),
        process_id="23518",
    )

    assert result["accessibilityBound"] is False
