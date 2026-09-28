#!/usr/bin/env python3
"""Read-only ADB preflight for exactly three explicitly named Companion devices."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_PACKAGE = "com.company.cloudctl.companion"
SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{3,127}$")
PACKAGE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
SAFE_TEXT_PATTERN = re.compile(r"^[A-Za-z0-9 ._()+-]{1,80}$")
SAFE_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._+-]{1,128}$")
KNOWN_ENABLED_STATES = {0, 1, 2, 3, 4}
DISABLED_ENABLED_STATES = {2, 3, 4}
USER_STATE_PATTERN = re.compile(r"(?mi)^[ \t]*User state\[(?P<header>[^\n]*)\][ \t]*:?[ \t]*$")


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str = ""
    returncode: int | None = 0
    error: str | None = None


Executor = Callable[[Sequence[str], float], CommandResult]


def execute(argv: Sequence[str], timeout_seconds: float) -> CommandResult:
    """Execute one fixed-argv read operation while discarding untrusted stderr."""
    try:
        completed = subprocess.run(  # noqa: S603 - argv comes from the fixed allowlist below
            list(argv),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(returncode=None, error="TIMEOUT")
    except OSError:
        return CommandResult(returncode=None, error="ADB_UNAVAILABLE")
    return CommandResult(stdout=completed.stdout, returncode=completed.returncode)


class AdbReader:
    """Expose only the ADB reads approved for this preflight."""

    def __init__(self, adb: str, timeout_seconds: float, executor: Executor = execute) -> None:
        self._adb = adb
        self._timeout_seconds = timeout_seconds
        self._executor = executor

    def devices(self) -> CommandResult:
        return self._run("devices")

    def property(self, serial: str, name: str) -> CommandResult:
        if name not in {
            "ro.product.manufacturer",
            "ro.product.model",
            "ro.build.version.sdk",
        }:
            raise ValueError("getprop name is not allowlisted")
        return self._shell(serial, "getprop", name)

    def package(self, serial: str, package: str) -> CommandResult:
        return self._shell(serial, "dumpsys", "package", package)

    def disabled_packages(self, serial: str, package: str) -> CommandResult:
        return self._shell(serial, "pm", "list", "packages", "-d", package)

    def pidof(self, serial: str, package: str) -> CommandResult:
        return self._shell(serial, "pidof", package)

    def accessibility(self, serial: str) -> CommandResult:
        return self._shell(serial, "dumpsys", "accessibility")

    def _shell(self, serial: str, *arguments: str) -> CommandResult:
        return self._run("-s", serial, "shell", *arguments)

    def _run(self, *arguments: str) -> CommandResult:
        return self._executor((self._adb, *arguments), self._timeout_seconds)


def validate_inputs(serials: Sequence[str], package: str) -> None:
    if len(serials) != 3:
        raise ValueError("exactly three --serial values are required")
    if len(set(serials)) != 3:
        raise ValueError("--serial values must be unique")
    if any(not SERIAL_PATTERN.fullmatch(serial) for serial in serials):
        raise ValueError("serial contains unsupported characters")
    if not PACKAGE_PATTERN.fullmatch(package):
        raise ValueError("package is invalid")


def parse_enumeration(result: CommandResult, serials: Sequence[str]) -> dict[str, str]:
    if result.error or result.returncode != 0:
        return dict.fromkeys(serials, "UNKNOWN")
    observed: dict[str, list[str]] = {serial: [] for serial in serials}
    requested = set(serials)
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] in requested:
            observed[fields[0]].append(fields[1])
    states: dict[str, str] = {}
    mapping = {
        "device": "AUTHORIZED",
        "unauthorized": "UNAUTHORIZED",
        "offline": "OFFLINE",
    }
    for serial in serials:
        values = observed[serial]
        if not values:
            states[serial] = "NOT_FOUND"
        elif len(values) != 1:
            states[serial] = "UNKNOWN"
        else:
            states[serial] = mapping.get(values[0], "UNKNOWN")
    return states


def _safe_text(result: CommandResult, *, numeric: bool = False) -> str | int | None:
    if result.error or result.returncode != 0:
        return None
    value = result.stdout.strip()
    if numeric:
        return int(value) if value.isdigit() else None
    return value if SAFE_TEXT_PATTERN.fullmatch(value) else None


def parse_package(package: str, dump: CommandResult, disabled: CommandResult) -> dict[str, Any]:
    result: dict[str, Any] = {
        "state": "UNKNOWN",
        "versionCode": None,
        "versionName": None,
        "debuggable": None,
        "enabledState": None,
        "disabled": None,
        "hidden": None,
        "suspended": None,
        "stopped": None,
    }
    if dump.error or dump.returncode != 0:
        return result
    text = dump.stdout
    if re.search(r"(?:unable to find package|package .* was not found)", text, re.IGNORECASE):
        result.update(state="NOT_INSTALLED", debuggable=False, disabled=False, stopped=None)
        return result

    version_code = re.search(r"\bversionCode=(\d+)\b", text)
    version_name = re.search(r"\bversionName=([^\s]+)", text)
    user_line = re.search(r"(?m)^\s*User 0:\s*(.+)$", text)
    installed: bool | None = None
    enabled_state: int | None = None
    hidden: bool | None = None
    suspended: bool | None = None
    stopped: bool | None = None
    if user_line:
        fields = dict(
            re.findall(
                r"\b(installed|hidden|suspended|stopped|enabled)=([^\s]+)",
                user_line.group(1),
            )
        )
        installed = _parse_bool(fields.get("installed"))
        hidden = _parse_bool(fields.get("hidden"))
        suspended = _parse_bool(fields.get("suspended"))
        stopped = _parse_bool(fields.get("stopped"))
        enabled_state = int(fields["enabled"]) if fields.get("enabled", "").isdigit() else None

    disabled_listed: bool | None = None
    if not disabled.error and disabled.returncode == 0:
        disabled_listed = any(
            line.strip() == f"package:{package}" for line in disabled.stdout.splitlines()
        )
    disabled_by_state = None
    if enabled_state in KNOWN_ENABLED_STATES:
        disabled_by_state = enabled_state in DISABLED_ENABLED_STATES
    if disabled_listed is True or disabled_by_state is True:
        disabled_value = True
    elif disabled_listed is False and disabled_by_state is False:
        disabled_value = False
    else:
        disabled_value = None
    safe_version_name = version_name.group(1) if version_name else None
    if safe_version_name is not None and not SAFE_VERSION_PATTERN.fullmatch(safe_version_name):
        safe_version_name = None

    package_state = (
        "INSTALLED" if installed is True else "NOT_INSTALLED" if installed is False else "UNKNOWN"
    )
    result.update(
        state=package_state,
        versionCode=int(version_code.group(1)) if version_code else None,
        versionName=safe_version_name,
        debuggable=bool(re.search(r"\b(?:pkgFlags|flags)=\[[^\]]*\bDEBUGGABLE\b", text)),
        enabledState=enabled_state,
        disabled=disabled_value,
        hidden=hidden,
        suspended=suspended,
        stopped=stopped,
    )
    return result


def _parse_bool(value: str | None) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def parse_process(result: CommandResult) -> dict[str, str]:
    if result.error:
        return {"state": "UNKNOWN"}
    value = result.stdout.strip()
    if result.returncode == 1 and not value:
        return {"state": "NOT_RUNNING"}
    pids = value.split()
    if result.returncode == 0 and pids and all(pid.isdigit() and int(pid) > 0 for pid in pids):
        return {"state": "RUNNING"}
    return {"state": "UNKNOWN"}


def _section(text: str, heading: str) -> str | None:
    matches = list(re.finditer(rf"(?m)^[ \t]*{re.escape(heading)}:[ \t]*(.*)$", text))
    if len(matches) != 1:
        return None
    match = matches[0]
    lines = [match.group(1)]
    for line in text[match.end() :].splitlines():
        if re.match(r"^[ \t]*[A-Z][A-Za-z0-9 ()/_-]*:[ \t]*", line):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _has_component(section: str, package: str) -> bool:
    component_class = f"{package}.automation.CloudCtlAccessibilityService"
    components = (
        f"{package}/{component_class}",
        f"{package}/.automation.CloudCtlAccessibilityService",
    )
    component_pattern = "|".join(re.escape(component) for component in components)
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9_.$])(?:{component_pattern})(?![A-Za-z0-9_.$])",
            section,
        )
    )


def _user_zero_accessibility_scope(text: str) -> str | None:
    matches = list(USER_STATE_PATTERN.finditer(text))
    if not matches:
        return text
    user_zero_matches = [
        (index, match)
        for index, match in enumerate(matches)
        if re.search(r"\b(?:id|userId)\s*=\s*0\b", match.group("header"), re.IGNORECASE)
    ]
    if len(user_zero_matches) != 1:
        return None
    index, match = user_zero_matches[0]
    end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
    return text[match.end() : end]


def _is_empty_section(section: str) -> bool:
    return not section or section in {"{}", "[]"}


def _has_cloudctl_label(section: str) -> bool:
    return bool(re.search(r"\bService\s*\[\s*label=[^\]\n]*\bcloudctl\b", section, re.IGNORECASE))


def parse_accessibility(result: CommandResult, package: str) -> dict[str, str]:
    unknown = {"enabled": "UNKNOWN", "binding": "UNKNOWN", "crashed": "UNKNOWN"}
    if result.error or result.returncode != 0:
        return unknown
    user_zero_scope = _user_zero_accessibility_scope(result.stdout)
    if user_zero_scope is None:
        return unknown
    bound = _section(user_zero_scope, "Bound services")
    enabled = _section(user_zero_scope, "Enabled services")
    crashed = _section(user_zero_scope, "Crashed services")
    if bound is None or enabled is None or crashed is None:
        return unknown

    if _has_component(bound, package):
        binding_state = "BOUND"
    elif _is_empty_section(bound):
        binding_state = "NOT_BOUND"
    elif _has_cloudctl_label(bound):
        binding_state = "AMBIGUOUS_LABEL_ONLY"
    else:
        binding_state = "NOT_BOUND"
    return {
        "enabled": "YES" if _has_component(enabled, package) else "NO",
        "binding": binding_state,
        "crashed": "YES" if _has_component(crashed, package) else "NO",
    }


def local_readiness(
    package: dict[str, Any], process: dict[str, str], accessibility: dict[str, str]
) -> dict[str, Any]:
    reasons: list[str] = []
    unknown = False

    if package["state"] == "NOT_INSTALLED":
        reasons.append("PACKAGE_NOT_INSTALLED")
    elif package["state"] == "UNKNOWN":
        reasons.append("PACKAGE_STATE_UNKNOWN")
        unknown = True
    if package["state"] == "INSTALLED":
        if package["versionCode"] is None or package["versionName"] is None:
            reasons.append("PACKAGE_VERSION_UNKNOWN")
            unknown = True
        if package["disabled"] is True:
            reasons.append("PACKAGE_DISABLED")
        elif package["disabled"] is None:
            reasons.append("PACKAGE_DISABLED_STATE_UNKNOWN")
            unknown = True
        if package["hidden"] is True:
            reasons.append("PACKAGE_HIDDEN")
        elif package["hidden"] is None:
            reasons.append("PACKAGE_HIDDEN_STATE_UNKNOWN")
            unknown = True
        if package["suspended"] is True:
            reasons.append("PACKAGE_SUSPENDED")
        elif package["suspended"] is None:
            reasons.append("PACKAGE_SUSPENDED_STATE_UNKNOWN")
            unknown = True
        if package["stopped"] is True:
            reasons.append("PACKAGE_STOPPED")
        elif package["stopped"] is None:
            reasons.append("PACKAGE_STOPPED_STATE_UNKNOWN")
            unknown = True

    if process["state"] == "NOT_RUNNING":
        reasons.append("PROCESS_NOT_RUNNING")
    elif process["state"] == "UNKNOWN":
        reasons.append("PROCESS_STATE_UNKNOWN")
        unknown = True

    if accessibility["enabled"] == "NO":
        reasons.append("ACCESSIBILITY_NOT_ENABLED")
    elif accessibility["enabled"] == "UNKNOWN":
        reasons.append("ACCESSIBILITY_ENABLED_UNKNOWN")
        unknown = True
    if accessibility["binding"] == "NOT_BOUND":
        reasons.append("ACCESSIBILITY_NOT_BOUND")
    elif accessibility["binding"] == "AMBIGUOUS_LABEL_ONLY":
        reasons.append("ACCESSIBILITY_BINDING_IDENTITY_AMBIGUOUS")
        unknown = True
    elif accessibility["binding"] == "UNKNOWN":
        reasons.append("ACCESSIBILITY_BINDING_UNKNOWN")
        unknown = True
    if accessibility["crashed"] == "YES":
        reasons.append("ACCESSIBILITY_SERVICE_CRASHED")
    elif accessibility["crashed"] == "UNKNOWN":
        reasons.append("ACCESSIBILITY_CRASH_STATE_UNKNOWN")
        unknown = True

    state = "UNKNOWN" if unknown else "NOT_READY" if reasons else "READY"
    return {"state": state, "ready": state == "READY", "reasons": reasons}


def collect_device(reader: AdbReader, serial: str, package_name: str) -> dict[str, Any]:
    package = parse_package(
        package_name,
        reader.package(serial, package_name),
        reader.disabled_packages(serial, package_name),
    )
    process = parse_process(reader.pidof(serial, package_name))
    accessibility = parse_accessibility(reader.accessibility(serial), package_name)
    return {
        "serial": serial,
        "adbAuthorization": {"state": "AUTHORIZED", "ready": True},
        "properties": {
            "manufacturer": _safe_text(reader.property(serial, "ro.product.manufacturer")),
            "model": _safe_text(reader.property(serial, "ro.product.model")),
            "sdk": _safe_text(reader.property(serial, "ro.build.version.sdk"), numeric=True),
        },
        "package": package,
        "process": process,
        "accessibility": accessibility,
        "localBusinessPrerequisites": local_readiness(package, process, accessibility),
    }


def unavailable_device(serial: str, adb_state: str) -> dict[str, Any]:
    return {
        "serial": serial,
        "adbAuthorization": {"state": adb_state, "ready": False},
        "properties": {"manufacturer": None, "model": None, "sdk": None},
        "package": {
            "state": "UNKNOWN",
            "versionCode": None,
            "versionName": None,
            "debuggable": None,
            "enabledState": None,
            "disabled": None,
            "hidden": None,
            "suspended": None,
            "stopped": None,
        },
        "process": {"state": "UNKNOWN"},
        "accessibility": {"enabled": "UNKNOWN", "binding": "UNKNOWN", "crashed": "UNKNOWN"},
        "localBusinessPrerequisites": {
            "state": "UNKNOWN",
            "ready": False,
            "reasons": [f"LOCAL_CHECKS_NOT_RUN_ADB_{adb_state}"],
        },
    }


def run_preflight(
    *,
    adb: str,
    serials: Sequence[str],
    package: str = DEFAULT_PACKAGE,
    timeout_seconds: float = 5.0,
    executor: Executor = execute,
) -> dict[str, Any]:
    validate_inputs(serials, package)
    if not 0 < timeout_seconds <= 30:
        raise ValueError("timeout must be greater than 0 and at most 30 seconds")
    reader = AdbReader(adb, timeout_seconds, executor)
    enumeration = parse_enumeration(reader.devices(), serials)
    devices = [
        collect_device(reader, serial, package)
        if enumeration[serial] == "AUTHORIZED"
        else unavailable_device(serial, enumeration[serial])
        for serial in serials
    ]
    local_states = {device["localBusinessPrerequisites"]["state"] for device in devices}
    local_state = (
        "READY"
        if local_states == {"READY"}
        else "UNKNOWN"
        if "UNKNOWN" in local_states
        else "NOT_READY"
    )
    return {
        "schemaVersion": 1,
        "diagnosticScope": {
            "transport": "ADB_READ_ONLY",
            "businessAcceptance": False,
            "mutatingOperations": [],
        },
        "package": package,
        "localPreflight": {"state": local_state, "ready": local_state == "READY"},
        "cloudAccountReadiness": {
            "state": "UNKNOWN_NOT_CHECKED",
            "ready": False,
            "reasons": ["CLOUD_BINDING_ACCOUNT_AND_TASK_STATE_NOT_CHECKED"],
        },
        "devices": devices,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--serial",
        action="append",
        required=True,
        help="exact device serial; repeat exactly three times",
    )
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_inputs(args.serial, args.package)
        if not 0 < args.timeout <= 30:
            raise ValueError("--timeout must be greater than 0 and at most 30 seconds")
    except ValueError as error:
        parser.error(str(error))
    adb = shutil.which("adb")
    if adb is None:
        print(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "localPreflight": {"state": "UNKNOWN", "ready": False},
                    "reason": "ADB_EXECUTABLE_NOT_FOUND",
                },
                sort_keys=True,
            )
        )
        return 1
    report = run_preflight(
        adb=adb,
        serials=args.serial,
        package=args.package,
        timeout_seconds=args.timeout,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["localPreflight"]["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
