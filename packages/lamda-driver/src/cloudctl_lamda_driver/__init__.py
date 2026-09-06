"""Stable DeviceDriver boundary around the optional LAMDA SDK."""

from .driver import LamdaDriver
from .errors import DeviceDriverError, DriverErrorCode, map_exception
from .protocols import (
    ApkPart,
    DeviceDriver,
    InstallOptions,
    InstallResult,
    Locator,
    LocatorCandidate,
)
from .readonly_probe import CommandExecutor, CommandOutput, ReadOnlyAdbProbe, ReadOnlyProbeError
from .session import LamdaSession
from .sidecar import LamdaSidecarBackend, SidecarRuntimeInfo, probe_sidecar_runtime

__all__ = [
    "ApkPart",
    "DeviceDriver",
    "DeviceDriverError",
    "DriverErrorCode",
    "InstallOptions",
    "InstallResult",
    "LamdaDriver",
    "LamdaSession",
    "LamdaSidecarBackend",
    "Locator",
    "LocatorCandidate",
    "CommandOutput",
    "CommandExecutor",
    "ReadOnlyAdbProbe",
    "ReadOnlyProbeError",
    "SidecarRuntimeInfo",
    "map_exception",
    "probe_sidecar_runtime",
]
