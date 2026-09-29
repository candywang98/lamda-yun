"""Single-use, data-preserving OnePlus v5 maintenance-recovery acceptance."""

from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

REPO = Path(__file__).resolve().parents[2]
PRIVATE_ROOT = Path.home() / "CloudCtlExternal/acceptance/20260928-v5"
APK = PRIVATE_ROOT / "cloudctl-business-acceptance-v5.apk"
SERIAL = "b0644fb5"
DEVICE_ID = "4aabc387-6e4b-4b59-a525-b1c119ec7f5b"
PACKAGE = "com.company.cloudctl.companion"
MODEL = "LE2100"
ACCESSIBILITY_COMPONENT = f"{PACKAGE}/{PACKAGE}.automation.CloudCtlAccessibilityService"
SYNC_SERVICE = f"{PACKAGE}.service.CompanionSyncService"
JAVA = Path.home() / "CloudCtlExternal/jdks/temurin-17/Contents/Home"
TOOLS = Path.home() / "CloudCtlExternal/android-sdk/build-tools/35.0.0"
EXPECTED_V4_APK = "cff3b03a72f56781a73d2713bd68a968f1d47a6c21f27c528629f72f6e9fcf70"
EXPECTED_V5_APK = "8b40b9284be9f6f7aca812792ff9315d9376803b9c6ec3d1ad9190241e0e5b0f"
EXPECTED_SIGNER = "67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796"
EXPECTED_SOURCE_REVISION = "a3eb419"
EXPECTED_COUNTS = {
    "mobileTasks": 379,
    "outgoingMessages": 23,
    "deviceOrders": 14,
    "deviceReceipts": 6,
}
SETTINGS = (
    "enabled_accessibility_services",
    "accessibility_enabled",
    "enabled_notification_listeners",
    "default_input_method",
)
MAINTENANCE_TIMEOUT_SECONDS = 180
POST_MAINTENANCE_TIMEOUT_SECONDS = 150
POLL_SECONDS = 10
APPROVED_LOG_MESSAGES = {
    "Heartbeat successful": "heartbeat",
    "claim deferred while device is in maintenance": "maintenanceDeferral",
}
OCCUPANCY_FIELDS = {
    "activeLeases",
    "unfinishedTasks",
    "enabledSchedules",
    "activePreviews",
    "activeDebugSessions",
}


class AcceptanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    returncode: int


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_command(apk: Path = APK) -> tuple[str, ...]:
    return ("adb", "-s", SERIAL, "install", "-r", str(apk))


def validate_candidate(snapshot: dict[str, Any]) -> None:
    expected = {
        "sha256": EXPECTED_V5_APK,
        "package": PACKAGE,
        "versionCode": 5,
        "versionName": "0.1.0-business-acceptance.5",
        "signerSha256": EXPECTED_SIGNER,
        "sourceRevision": EXPECTED_SOURCE_REVISION,
        "sourceDirty": False,
    }
    if snapshot != expected:
        raise AcceptanceError("candidate identity mismatch")


def validate_cloud(snapshot: dict[str, Any], *, maintenance: bool, version: int) -> None:
    device = snapshot.get("device", {})
    identity = snapshot.get("identity", {})
    occupancy = snapshot.get("occupancy", {})
    if device.get("maintenance") is not maintenance or device.get("version") != version:
        raise AcceptanceError("maintenance state/version mismatch")
    if not device.get("tenantMatchesExpected") or not device.get("activeBindingMatchesExpected"):
        raise AcceptanceError("tenant or active binding drift")
    if identity != {
        "retained": True,
        "activeBindingCount": 1,
        "accountBindingCount": 1,
        "boundAccountCount": 1,
    }:
        raise AcceptanceError("binding/account identity drift")
    if not occupancy.get("globalIdle") or not occupancy.get("targetIdle"):
        raise AcceptanceError("cloud occupancy is not idle")
    for scope in ("global", "targetDevice"):
        values = occupancy.get(scope)
        if not isinstance(values, dict) or set(values) != OCCUPANCY_FIELDS:
            raise AcceptanceError("cloud occupancy map is incomplete")
        if any(value != 0 for value in values.values()):
            raise AcceptanceError("cloud occupancy count is non-zero")
    if snapshot.get("counts") != EXPECTED_COUNTS:
        raise AcceptanceError("business aggregate count drift")
    if snapshot.get("imConfig") != {
        "httpStatus": 200,
        "receiveOnly": True,
        "mode": "NOTIFICATION",
        "enabled": True,
    }:
        raise AcceptanceError("receive-only configuration drift")


def validate_device_identity(
    snapshot: dict[str, Any], *, version_code: int, version_name: str
) -> None:
    expected = {
        "serial": SERIAL,
        "adbState": "device",
        "model": MODEL,
        "currentUser": "0",
        "versionCode": version_code,
        "versionName": version_name,
    }
    observed = {key: snapshot.get(key) for key in expected}
    if observed != expected:
        raise AcceptanceError("device/package identity mismatch")


def validate_runtime(status: dict[str, Any]) -> None:
    required = {
        "processRunning": True,
        "syncServicePresent": True,
        "syncServiceForeground": True,
        "accessibilityEnabled": True,
        "accessibilityBound": True,
        "accessibilityCrashed": False,
    }
    if any(status.get(key) is not value for key, value in required.items()):
        raise AcceptanceError("required process/service/accessibility state is absent")


def validate_post_install(before: dict[str, Any], after: dict[str, Any]) -> None:
    validate_device_identity(
        after,
        version_code=5,
        version_name="0.1.0-business-acceptance.5",
    )
    for key in ("appId", "uid", "firstInstallTime", "grants", "settings"):
        if after.get(key) != before.get(key):
            raise AcceptanceError(f"installed identity drift: {key}")
    if after.get("installedApkSha256") != EXPECTED_V5_APK:
        raise AcceptanceError("installed v5 APK hash mismatch")
    if after.get("installedSignerSha256") != EXPECTED_SIGNER:
        raise AcceptanceError("installed v5 signer mismatch")


def validate_observation(
    observation: dict[str, Any],
    *,
    require_deferrals: bool,
) -> bool:
    minimum_deferrals = 2 if require_deferrals else 0
    return bool(
        observation.get("heartbeatCount", 0) >= 3
        and observation.get("maintenanceDeferralCount", 0) >= minimum_deferrals
        and observation.get("allRuntimeSamplesHealthy") is True
        and observation.get("cloudGatePassed") is True
    )


def parse_phone_events(
    raw: str,
    *,
    since_epoch: float,
    process_id: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        fields = line.split(None, 5)
        if len(fields) < 6:
            continue
        try:
            timestamp_value = float(fields[0])
        except ValueError:
            continue
        if (
            not math.isfinite(timestamp_value)
            or timestamp_value <= since_epoch
            or fields[1] != process_id
            or fields[3] != "I"
            or fields[4] != "CompanionSync:"
        ):
            continue
        for message, event_type in APPROVED_LOG_MESSAGES.items():
            if fields[5] != message:
                continue
            events.append({"timestamp": fields[0], "processId": fields[1], "type": event_type})
            break
    unique = {(item["timestamp"], item["processId"], item["type"]): item for item in events}
    return [unique[key] for key in sorted(unique)]


def logcat_since_argument(since_epoch: float) -> str:
    if since_epoch <= 0:
        raise AcceptanceError("logcat since epoch must be positive")
    return f"{since_epoch:.3f}"


def _service_blocks(text: str) -> list[list[str]]:
    lines = text.splitlines()
    blocks: list[list[str]] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(?P<indent>\s*)\* ServiceRecord\{", lines[index])
        if match is None:
            index += 1
            continue
        indent = len(match.group("indent"))
        block = [lines[index]]
        index += 1
        while index < len(lines):
            line = lines[index]
            stripped = line.lstrip()
            line_indent = len(line) - len(stripped)
            if stripped.startswith("*") and line_indent <= indent:
                break
            block.append(line)
            index += 1
        blocks.append(block)
    return blocks


def _exact_service_block(text: str, relative_class: str) -> list[str] | None:
    components = (
        f"{PACKAGE}/{relative_class}",
        f"{PACKAGE}/{PACKAGE}{relative_class}",
    )
    component_pattern = "|".join(re.escape(component) for component in components)
    header = re.compile(rf"^\s*\* ServiceRecord\{{[^}}]+\bu0\s+(?:{component_pattern})\}}\s*$")
    matches = [block for block in _service_blocks(text) if header.fullmatch(block[0])]
    return matches[0] if len(matches) == 1 else None


def _service_process_id(block: list[str]) -> str | None:
    matches = []
    pattern = re.compile(
        rf"^\s*app=ProcessRecord\{{[^}}]+\s+(\d+):{re.escape(PACKAGE)}/u0a\d+\}}\s*$"
    )
    for line in block:
        match = pattern.fullmatch(line)
        if match:
            matches.append(match.group(1))
    return matches[0] if len(matches) == 1 else None


def parse_service_health(services: str, *, process_id: str) -> dict[str, bool]:
    sync = _exact_service_block(services, ".service.CompanionSyncService")
    accessibility = _exact_service_block(services, ".automation.CloudCtlAccessibilityService")
    sync_present = sync is not None and _service_process_id(sync) == process_id
    sync_foreground = False
    if sync_present and sync is not None:
        foreground_values = []
        for line in sync:
            match = re.fullmatch(
                r"\s*isForeground=(true|false)\s+foregroundId=(\d+)\b.*",
                line,
            )
            if match:
                foreground_values.append((match.group(1), int(match.group(2))))
        sync_foreground = (
            len(foreground_values) == 1
            and foreground_values[0][0] == "true"
            and foreground_values[0][1] > 0
        )

    accessibility_bound = False
    if accessibility is not None and _service_process_id(accessibility) == process_id:
        exact_components = (
            f"{PACKAGE}/.automation.CloudCtlAccessibilityService",
            f"{PACKAGE}/{PACKAGE}.automation.CloudCtlAccessibilityService",
        )
        component_pattern = "|".join(re.escape(item) for item in exact_components)
        connection = re.compile(
            rf"^\s+ConnectionRecord\{{[^}}]+\bu0\b[^}}]*\s(?:{component_pattern}):@[^}}]+\}}\s*$"
        )
        accessibility_bound = any(connection.fullmatch(line) for line in accessibility)
    return {
        "syncServicePresent": sync_present,
        "syncServiceForeground": sync_foreground,
        "accessibilityBound": accessibility_bound,
    }


def _load_preflight_module() -> Any:
    name = "oneplus_v5_three_device_preflight"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = REPO / "scripts/three_device_preflight.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AcceptanceError("existing accessibility preflight helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def parse_accessibility_health(raw: str) -> dict[str, bool]:
    preflight = _load_preflight_module()
    parsed = preflight.parse_accessibility(
        preflight.CommandResult(stdout=raw, returncode=0), PACKAGE
    )
    return {
        "accessibilityEnabledFromDump": parsed["enabled"] == "YES",
        "accessibilityCrashed": parsed["crashed"] != "NO",
    }


class WindowOperations(Protocol):
    def candidate_preflight(self) -> dict[str, Any]: ...

    def acquire_lock(self) -> dict[str, Any]: ...

    def locked_preflight(self) -> dict[str, Any]: ...

    def prepare_maintenance(self) -> dict[str, Any]: ...

    def install_once(self) -> dict[str, Any]: ...

    def observe_maintenance(self) -> dict[str, Any]: ...

    def finish_maintenance(self) -> dict[str, Any]: ...

    def observe_post_maintenance(self) -> dict[str, Any]: ...

    def final_verify(self) -> dict[str, Any]: ...

    def cleanup_maintenance(self) -> dict[str, Any]: ...

    def maintenance_owned(self) -> bool: ...

    def release_lock(self, lock: dict[str, Any]) -> dict[str, Any]: ...


def execute_window(operations: WindowOperations) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "cloudctl-oneplus-v5-device-acceptance/1",
        "startedAt": utc_now(),
        "status": "RUNNING",
        "stages": [],
        "maintenanceRecovery": "NOT_PROVEN",
        "postMaintenancePresence": "NOT_PROVEN",
    }
    lock: dict[str, Any] | None = None
    maintenance_finished = False
    try:
        result["candidate"] = operations.candidate_preflight()
        result["stages"].append("candidate-validated")
        lock = operations.acquire_lock()
        result["fencing"] = lock["fencing"]
        result["stages"].append("device-lock-acquired")
        result["before"] = operations.locked_preflight()
        result["stages"].append("locked-preflight-passed")
        result["maintenancePrepared"] = operations.prepare_maintenance()
        result["stages"].append("maintenance-entered")
        result["install"] = operations.install_once()
        result["stages"].append("v5-installed")
        maintenance_observation = operations.observe_maintenance()
        result["maintenanceObservation"] = maintenance_observation
        if validate_observation(maintenance_observation, require_deferrals=True):
            result["maintenanceRecovery"] = "PROVEN"
        result["maintenanceFinished"] = operations.finish_maintenance()
        maintenance_finished = True
        result["stages"].append("maintenance-exited")
        post_observation = operations.observe_post_maintenance()
        result["postMaintenanceObservation"] = post_observation
        if validate_observation(post_observation, require_deferrals=False):
            result["postMaintenancePresence"] = "PROVEN"
        result["final"] = operations.final_verify()
        result["stages"].append("final-gates-passed")
        result["status"] = (
            "PROVEN"
            if result["maintenanceRecovery"] == "PROVEN"
            and result["postMaintenancePresence"] == "PROVEN"
            else "NOT_PROVEN"
        )
    except Exception as error:  # noqa: BLE001 - operation result must survive cleanup
        result["status"] = "FAILED"
        result["failure"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if lock is not None and operations.maintenance_owned() and not maintenance_finished:
            try:
                result["maintenanceCleanup"] = operations.cleanup_maintenance()
            except Exception as error:  # noqa: BLE001 - preserve primary failure and conflict
                result["status"] = "FAILED"
                result["cleanupFailure"] = {
                    "type": type(error).__name__,
                    "message": str(error),
                }
        if lock is not None:
            try:
                released = operations.release_lock(lock)
                result["lockReleased"] = released.get("state") == "FREE" and released.get(
                    "released_fencing"
                ) == lock.get("fencing")
                if not result["lockReleased"]:
                    result["status"] = "FAILED"
                    result["releaseFailure"] = {
                        "type": "AcceptanceError",
                        "message": "device lock release acknowledgement mismatch",
                    }
            except Exception as error:  # noqa: BLE001 - report exact release failure
                result["status"] = "FAILED"
                result["lockReleased"] = False
                result["releaseFailure"] = {
                    "type": type(error).__name__,
                    "message": str(error),
                }
        result["finishedAt"] = utc_now()
    return result


class RealOperations:
    def __init__(self) -> None:
        os.umask(0o077)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.run_dir = PRIVATE_ROOT / f"install-window-{stamp}"
        self.run_dir.mkdir(mode=0o700, parents=True)
        self.window_id = f"v5-{uuid.uuid4().hex}"
        self._maintenance_owned = False
        self.before_package: dict[str, Any] | None = None
        self.maintenance_device_watermark: float | None = None
        self.maintenance_server_since_host_epoch: float | None = None
        self.post_device_watermark: float | None = None
        self.post_server_since_host_epoch: float | None = None
        self.post_install_pid: str | None = None

    def execute(
        self,
        args: list[str | Path] | tuple[str, ...],
        *,
        timeout: int = 30,
        input_text: str | None = None,
        binary: bool = False,
    ) -> CommandResult | bytes:
        completed = subprocess.run(  # noqa: S603 - all callers use fixed argv
            [str(arg) for arg in args],
            cwd=REPO,
            input=input_text if not binary else None,
            capture_output=True,
            text=not binary,
            timeout=timeout,
            env={**os.environ, "JAVA_HOME": str(JAVA)},
        )
        if completed.returncode != 0:
            raise AcceptanceError(f"command failed: {args[0]} exit={completed.returncode}")
        if binary:
            return completed.stdout
        return CommandResult(stdout=completed.stdout.strip(), returncode=completed.returncode)

    def adb(self, *args: str, timeout: int = 25) -> str:
        result = self.execute(["adb", "-s", SERIAL, *args], timeout=timeout)
        assert isinstance(result, CommandResult)
        return result.stdout

    def save_private(self, name: str, value: Any) -> None:
        (self.run_dir / name).write_text(
            json.dumps(value, indent=2, default=str, sort_keys=True) + "\n"
        )

    def signer_digest(self, path: Path) -> str:
        result = self.execute([TOOLS / "apksigner", "verify", "--print-certs", path])
        assert isinstance(result, CommandResult)
        digests = re.findall(r"certificate SHA-256 digest: ([a-f0-9]{64})", result.stdout)
        if len(digests) != 1:
            raise AcceptanceError("APK signer output is ambiguous")
        return digests[0]

    def candidate_snapshot(self) -> dict[str, Any]:
        if not APK.is_file():
            raise AcceptanceError("v5 candidate is missing")
        badging = self.execute([TOOLS / "aapt", "dump", "badging", APK])
        assert isinstance(badging, CommandResult)
        package = re.search(
            r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'",
            badging.stdout,
        )
        if package is None:
            raise AcceptanceError("candidate package metadata is missing")
        source_found = False
        dirty_found = False
        with zipfile.ZipFile(APK) as archive:
            for name in archive.namelist():
                if not re.fullmatch(r"classes\d*\.dex", name):
                    continue
                data = archive.read(name)
                source_found = source_found or EXPECTED_SOURCE_REVISION.encode() in data
                dirty_found = dirty_found or f"{EXPECTED_SOURCE_REVISION}-dirty".encode() in data
        return {
            "sha256": hash_file(APK),
            "package": package.group(1),
            "versionCode": int(package.group(2)),
            "versionName": package.group(3),
            "signerSha256": self.signer_digest(APK),
            "sourceRevision": EXPECTED_SOURCE_REVISION if source_found else None,
            "sourceDirty": dirty_found,
        }

    def candidate_preflight(self) -> dict[str, Any]:
        snapshot = self.candidate_snapshot()
        validate_candidate(snapshot)
        self.save_private("candidate.json", snapshot)
        return snapshot

    def lock_command(self, *args: str, input_text: str | None = None) -> dict[str, Any]:
        result = self.execute(
            [sys.executable, REPO / "scripts/device_lock.py", *args],
            input_text=input_text,
        )
        assert isinstance(result, CommandResult)
        return json.loads(result.stdout)

    def acquire_lock(self) -> dict[str, Any]:
        status = self.lock_command("status", SERIAL)
        if status.get("state") != "FREE":
            raise AcceptanceError("shared device lock is not free")
        lock = self.lock_command(
            "acquire",
            SERIAL,
            "--holder",
            "sol-v5-acceptance-20260928",
            "--purpose",
            "Authorized OnePlus v5 maintenance-recovery acceptance",
            "--task-id",
            "three-device-oneplus-v5-maintenance-recovery",
            "--ttl",
            "1800",
        )
        self.save_private("lock-private.json", lock)
        return lock

    def cloud(self, action: str, *extra: str, timeout: int = 75) -> dict[str, Any]:
        script = Path(__file__).with_name("oneplus-v5-cloud.py").read_text()
        result = self.execute(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                "seoul",
                "/home/ubuntu/cloudctl-mobile/releases/order-delivery-557f547/.venv/bin/python",
                "-",
                action,
                *extra,
            ],
            timeout=timeout,
            input_text=script,
        )
        assert isinstance(result, CommandResult)
        return json.loads(result.stdout)

    def package_snapshot(self, installed_name: str) -> dict[str, Any]:
        package_dump = self.adb("shell", "dumpsys", "package", PACKAGE)
        version = re.search(r"^\s+versionCode=(\d+)", package_dump, re.MULTILINE)
        version_name = re.search(r"^\s+versionName=(\S+)", package_dump, re.MULTILINE)
        app_id = re.search(r"^\s+appId=(\d+)", package_dump, re.MULTILINE)
        first_install = re.findall(r"^\s+firstInstallTime=(.+)$", package_dump, re.MULTILINE)
        grants = re.findall(r"^\s+(\S+): granted=(true|false)(.*)$", package_dump, re.MULTILINE)
        uid_line = self.adb("shell", "cmd", "package", "list", "packages", "-U", PACKAGE)
        uid = re.search(r"\buid:(\d+)\b", uid_line)
        if not all((version, version_name, app_id, first_install, grants, uid)):
            raise AcceptanceError("package identity snapshot is incomplete")
        paths = self.adb("shell", "pm", "path", PACKAGE).splitlines()
        if len(paths) != 1 or not paths[0].startswith("package:/data/app/"):
            raise AcceptanceError("installed APK path is ambiguous")
        remote = paths[0].removeprefix("package:")
        if not remote.endswith("/base.apk"):
            raise AcceptanceError("installed APK is not a single base APK")
        destination = self.run_dir / installed_name
        self.adb("pull", remote, str(destination), timeout=90)
        return {
            "serial": SERIAL,
            "adbState": self.adb("get-state"),
            "model": self.adb("shell", "getprop", "ro.product.model"),
            "currentUser": self.adb("shell", "am", "get-current-user"),
            "versionCode": int(version.group(1)),
            "versionName": version_name.group(1),
            "appId": app_id.group(1),
            "uid": uid.group(1),
            "firstInstallTime": first_install,
            "grants": grants,
            "settings": {
                key: self.adb("shell", "settings", "get", "secure", key) for key in SETTINGS
            },
            "installedApkSha256": hash_file(destination),
            "installedSignerSha256": self.signer_digest(destination),
        }

    def runtime_status(self) -> dict[str, Any]:
        pid = self.adb("shell", "pidof", PACKAGE)
        pids = pid.split()
        process_id = pids[0] if len(pids) == 1 and pids[0].isdigit() else None
        services = self.adb("shell", "dumpsys", "activity", "services", PACKAGE)
        accessibility = self.adb("shell", "dumpsys", "accessibility")
        enabled = self.adb("shell", "settings", "get", "secure", "enabled_accessibility_services")
        service_health = (
            parse_service_health(services, process_id=process_id)
            if process_id is not None
            else {
                "syncServicePresent": False,
                "syncServiceForeground": False,
                "accessibilityBound": False,
            }
        )
        accessibility_health = parse_accessibility_health(accessibility)
        return {
            "processRunning": process_id is not None,
            "processId": process_id,
            **service_health,
            "accessibilityEnabled": (
                ACCESSIBILITY_COMPONENT in enabled
                and accessibility_health["accessibilityEnabledFromDump"]
            ),
            "accessibilityCrashed": accessibility_health["accessibilityCrashed"],
        }

    def locked_preflight(self) -> dict[str, Any]:
        candidate = self.candidate_snapshot()
        validate_candidate(candidate)
        package = self.package_snapshot("installed-before-v4.apk")
        validate_device_identity(
            package,
            version_code=4,
            version_name="0.1.0-business-acceptance.4",
        )
        if package["installedApkSha256"] != EXPECTED_V4_APK:
            raise AcceptanceError("installed v4 APK hash mismatch")
        if package["installedSignerSha256"] != EXPECTED_SIGNER:
            raise AcceptanceError("installed v4 signer mismatch")
        runtime = self.runtime_status()
        validate_runtime(runtime)
        cloud = self.cloud("snapshot")
        validate_cloud(cloud, maintenance=False, version=10)
        if cloud.get("capabilities", {}).get("companionVersion") != package["versionName"]:
            raise AcceptanceError("cloud companion version does not match installed v4")
        self.before_package = package
        private = {"candidate": candidate, "package": package, "runtime": runtime, "cloud": cloud}
        self.save_private("locked-preflight-private.json", private)
        return {
            "observedAt": utc_now(),
            "installedVersion": package["versionName"],
            "installedApkSha256": package["installedApkSha256"],
            "runtime": runtime,
            "cloud": cloud,
        }

    def prepare_maintenance(self) -> dict[str, Any]:
        acknowledgement = self.cloud("prepare-cas", self.window_id)
        if acknowledgement != {
            "action": "prepare-cas",
            "windowId": self.window_id,
            "acknowledged": True,
            "expectedResult": {"maintenance": True, "version": 11},
            "acknowledgedAt": acknowledgement.get("acknowledgedAt"),
        }:
            raise AcceptanceError("maintenance CAS acknowledgement is invalid")
        self._maintenance_owned = True
        self.save_private(
            "maintenance-ownership-private.json",
            {
                "windowId": self.window_id,
                "prepareCasAcknowledged": True,
                "acknowledgedAt": acknowledgement["acknowledgedAt"],
                "expectedOwnedState": {"maintenance": True, "version": 11},
            },
        )
        prepared = self.cloud("snapshot")
        validate_cloud(prepared, maintenance=True, version=11)
        self.save_private("cloud-maintenance-private.json", prepared)
        return {"acknowledgement": acknowledgement, "snapshot": prepared}

    def install_once(self) -> dict[str, Any]:
        self.maintenance_server_since_host_epoch = time.time()
        self.maintenance_device_watermark = self.device_epoch()
        started = utc_now()
        result = self.execute(install_command(), timeout=180)
        assert isinstance(result, CommandResult)
        if "Success" not in result.stdout.splitlines():
            raise AcceptanceError("PackageManager did not confirm install success")
        summary = {
            "startedAt": started,
            "finishedAt": utc_now(),
            "attempts": 1,
            "deviceLogWatermarkEpoch": self.maintenance_device_watermark,
            "serverJournalSinceHostEpoch": self.maintenance_server_since_host_epoch,
        }
        self.save_private("install-result-private.json", summary)
        return summary

    def phone_events(self, since_epoch: float, process_id: str) -> list[dict[str, Any]]:
        raw = self.adb(
            "logcat",
            "-d",
            "-v",
            "epoch",
            "-T",
            logcat_since_argument(since_epoch),
            "CompanionSync:I",
            "*:S",
            timeout=30,
        )
        return parse_phone_events(raw, since_epoch=since_epoch, process_id=process_id)

    def device_epoch(self) -> float:
        raw = self.adb("shell", "date", "+%s.%3N").strip()
        try:
            value = float(raw)
        except ValueError as error:
            raise AcceptanceError("device epoch watermark is malformed") from error
        if not math.isfinite(value) or value <= 0:
            raise AcceptanceError("device epoch watermark is invalid")
        return value

    def wait_for_automatic_runtime(self, timeout_seconds: int = 30) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last: dict[str, Any] | None = None
        while True:
            last = self.runtime_status()
            try:
                validate_runtime(last)
                return last
            except AcceptanceError:
                if time.monotonic() >= deadline:
                    raise AcceptanceError(
                        "automatic post-install runtime did not become ready"
                    ) from None
                time.sleep(min(2, max(0.0, deadline - time.monotonic())))

    def observe(
        self,
        *,
        phase: str,
        device_watermark_epoch: float,
        server_since_host_epoch: float,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        samples: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        expected_pid = self.post_install_pid
        if expected_pid is None:
            raise AcceptanceError("post-install process identity is unknown")
        while True:
            status = self.runtime_status()
            samples.append(
                {
                    "observedAt": utc_now(),
                    **status,
                    "exactProcess": status.get("processId") == expected_pid,
                }
            )
            events = self.phone_events(device_watermark_epoch, expected_pid)
            heartbeats = [item for item in events if item["type"] == "heartbeat"]
            deferrals = [item for item in events if item["type"] == "maintenanceDeferral"]
            threshold = len(heartbeats) >= 3 and (phase != "maintenance" or len(deferrals) >= 2)
            if threshold or time.monotonic() >= deadline:
                break
            time.sleep(min(POLL_SECONDS, max(0.0, deadline - time.monotonic())))
        cloud = self.cloud("snapshot")
        expected_maintenance = phase == "maintenance"
        expected_version = 11 if expected_maintenance else 12
        cloud_gate_passed = True
        try:
            validate_cloud(cloud, maintenance=expected_maintenance, version=expected_version)
        except AcceptanceError:
            cloud_gate_passed = False
        journal = self.cloud("journal", str(server_since_host_epoch), str(time.time()), timeout=45)
        observation = {
            "phase": phase,
            "deviceLogWatermarkEpoch": device_watermark_epoch,
            "serverJournalSinceHostEpoch": server_since_host_epoch,
            "finishedAt": utc_now(),
            "heartbeatCount": sum(item["type"] == "heartbeat" for item in events),
            "maintenanceDeferralCount": sum(
                item["type"] == "maintenanceDeferral" for item in events
            ),
            "events": events,
            "runtimeSamples": samples,
            "allRuntimeSamplesHealthy": all(
                (
                    all(
                        sample.get(key) is True
                        for key in (
                            "processRunning",
                            "syncServicePresent",
                            "syncServiceForeground",
                            "accessibilityEnabled",
                            "accessibilityBound",
                            "exactProcess",
                        )
                    )
                    and sample.get("accessibilityCrashed") is False
                )
                for sample in samples
            ),
            "cloudGatePassed": cloud_gate_passed,
            "serverJournal": journal,
        }
        self.save_private(f"{phase}-observation-private.json", observation)
        return observation

    def observe_maintenance(self) -> dict[str, Any]:
        if (
            self.before_package is None
            or self.maintenance_device_watermark is None
            or self.maintenance_server_since_host_epoch is None
        ):
            raise AcceptanceError("install observation started without preflight/install")
        after = self.package_snapshot("installed-after-v5.apk")
        validate_post_install(self.before_package, after)
        runtime = self.wait_for_automatic_runtime()
        self.post_install_pid = runtime["processId"]
        self.save_private("package-after-private.json", after)
        return self.observe(
            phase="maintenance",
            device_watermark_epoch=self.maintenance_device_watermark,
            server_since_host_epoch=self.maintenance_server_since_host_epoch,
            timeout_seconds=MAINTENANCE_TIMEOUT_SECONDS,
        )

    def finish_maintenance(self) -> dict[str, Any]:
        if not self._maintenance_owned:
            raise AcceptanceError("maintenance finish refused without proven ownership")
        finished = self.cloud("finish-owned", self.window_id)
        validate_cloud(finished, maintenance=False, version=12)
        self._maintenance_owned = False
        self.post_server_since_host_epoch = time.time()
        self.post_device_watermark = self.device_epoch()
        self.save_private("cloud-finished-private.json", finished)
        return finished

    def observe_post_maintenance(self) -> dict[str, Any]:
        if self.post_device_watermark is None or self.post_server_since_host_epoch is None:
            raise AcceptanceError("post-maintenance observation has no start time")
        return self.observe(
            phase="postMaintenance",
            device_watermark_epoch=self.post_device_watermark,
            server_since_host_epoch=self.post_server_since_host_epoch,
            timeout_seconds=POST_MAINTENANCE_TIMEOUT_SECONDS,
        )

    def final_verify(self) -> dict[str, Any]:
        if self.before_package is None:
            raise AcceptanceError("final verification has no pre-install snapshot")
        package = self.package_snapshot("installed-final-v5.apk")
        validate_post_install(self.before_package, package)
        runtime = self.runtime_status()
        validate_runtime(runtime)
        cloud = self.cloud("snapshot")
        validate_cloud(cloud, maintenance=False, version=12)
        if cloud.get("capabilities", {}).get("companionVersion") != package["versionName"]:
            raise AcceptanceError("cloud companion version does not match installed v5")
        self.save_private(
            "final-private.json", {"package": package, "runtime": runtime, "cloud": cloud}
        )
        return {
            "observedAt": utc_now(),
            "installedVersion": package["versionName"],
            "installedApkSha256": package["installedApkSha256"],
            "runtime": runtime,
            "cloud": cloud,
        }

    def cleanup_maintenance(self) -> dict[str, Any]:
        if not self._maintenance_owned:
            raise AcceptanceError("maintenance cleanup refused without proven ownership")
        cleanup = self.cloud("finish-owned", self.window_id)
        self._maintenance_owned = False
        self.save_private("cloud-cleanup-private.json", cleanup)
        return cleanup

    def maintenance_owned(self) -> bool:
        return self._maintenance_owned

    def release_lock(self, lock: dict[str, Any]) -> dict[str, Any]:
        released = self.lock_command(
            "release",
            SERIAL,
            "--fencing",
            str(lock["fencing"]),
            "--token-stdin",
            input_text=lock["owner_token"] + "\n",
        )
        self.save_private("lock-released.json", released)
        return released


def main(argv: list[str]) -> int:
    if argv[1:] != ["--approved-controller-window"]:
        raise SystemExit("explicit --approved-controller-window is required")
    operations = RealOperations()
    result = execute_window(operations)
    operations.save_private("run-summary-private.json", result)
    public = {
        **result,
        "privateRunDirectory": str(operations.run_dir),
        "businessTaskCreated": False,
        "manualLaunch": False,
        "privateDatabaseReread": False,
    }
    print(json.dumps(public, indent=2, default=str))
    return 0 if result["status"] in {"PROVEN", "NOT_PROVEN"} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
