from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from cloudctl_edge_protocol import edge_control_pb2 as pb
from google.protobuf.json_format import ParseDict

from .spool import EdgeSpool


class HealthDevice(Protocol):
    device_id: str
    android_version: str
    lamda_version: str
    apps: Mapping[str, str]
    battery_percent: int
    charging: bool
    network_type: str
    temperature_celsius: float
    free_storage_bytes: int
    companion_version: str
    current_task_run_id: str
    current_task_state: str
    stopped: bool

    def get_capabilities(self) -> Mapping[str, object]: ...


@dataclass(slots=True)
class DeviceRegistry:
    edge_id: str
    spool: EdgeSpool
    _devices: dict[str, HealthDevice] = field(default_factory=dict, init=False)

    def register(self, device: HealthDevice) -> None:
        if device.device_id in self._devices:
            raise ValueError("device is already registered")
        self._devices[device.device_id] = device

    def heartbeat(self) -> pb.Heartbeat:
        heartbeat = pb.Heartbeat(edge_id=self.edge_id)
        heartbeat.observed_at.FromDatetime(datetime.now(UTC))
        for device in self._devices.values():
            capabilities = dict(device.get_capabilities())
            health: dict[str, object] = {
                "device_id": device.device_id,
                "state": "ONLINE",
                "android_version": device.android_version,
                "lamda_version": device.lamda_version,
                "app_versions": dict(device.apps),
                "capabilities": capabilities,
                "battery_percent": device.battery_percent,
                "charging": device.charging,
                "network_type": device.network_type,
                "temperature_celsius": device.temperature_celsius,
                "free_storage_bytes": device.free_storage_bytes,
                "companion_version": device.companion_version,
                "current_task_run_id": device.current_task_run_id,
                "current_task_state": device.current_task_state,
                "automation_stopped": device.stopped,
            }
            self.spool.put_device_health(device.device_id, health)
            message = heartbeat.devices.add(
                device_id=device.device_id,
                state="ONLINE",
                android_version=device.android_version,
                lamda_version=device.lamda_version,
                battery_percent=device.battery_percent,
                charging=device.charging,
                network_type=device.network_type,
                temperature_celsius=device.temperature_celsius,
                free_storage_bytes=device.free_storage_bytes,
                companion_version=device.companion_version,
                current_task_run_id=device.current_task_run_id,
                current_task_state=device.current_task_state,
                automation_stopped=device.stopped,
            )
            message.app_versions.update(device.apps)
            ParseDict(capabilities, message.capabilities)
        return heartbeat
