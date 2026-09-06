from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "packages/edge-protocol/src"))

from cloudctl_edge_protocol import edge_control_pb2 as pb


def test_edge_contract_has_required_stream_and_fencing_fields() -> None:
    service = pb.DESCRIPTOR.services_by_name["EdgeControl"]
    connect = service.methods_by_name["Connect"]
    assert connect.client_streaming is True
    assert connect.server_streaming is True
    start = pb.StartCommand.DESCRIPTOR.fields_by_name
    assert start["lease_id"].number == 4
    assert start["fencing_token"].number == 5
    assert start["deadline"].number == 6
    assert "shell" not in start


def test_envelopes_use_sequence_and_oneof_body() -> None:
    assert pb.EdgeToCloud.DESCRIPTOR.fields_by_name["sequence"].number == 1
    assert pb.CloudToEdge.DESCRIPTOR.fields_by_name["sequence"].number == 1
    assert pb.EdgeToCloud.DESCRIPTOR.oneofs_by_name["body"] is not None
    assert pb.CloudToEdge.DESCRIPTOR.oneofs_by_name["body"] is not None


def test_edge_contract_exposes_companion_operations_fields() -> None:
    edge_body = pb.EdgeToCloud.DESCRIPTOR.fields_by_name
    assert edge_body["confirmation_required"].number == 15
    assert edge_body["operator_action"].number == 16
    assert edge_body["artifact_delivery"].number == 17
    assert pb.CloudToEdge.DESCRIPTOR.fields_by_name["confirmation_resolution"].number == 15

    health = pb.DeviceHealth.DESCRIPTOR.fields_by_name
    assert {
        name: health[name].number
        for name in (
            "battery_percent",
            "charging",
            "network_type",
            "temperature_celsius",
            "free_storage_bytes",
            "companion_version",
            "current_task_run_id",
            "current_task_state",
            "automation_stopped",
        )
    } == {
        "battery_percent": 7,
        "charging": 8,
        "network_type": 9,
        "temperature_celsius": 10,
        "free_storage_bytes": 11,
        "companion_version": 12,
        "current_task_run_id": 13,
        "current_task_state": 14,
        "automation_stopped": 15,
    }

    artifact = pb.ArtifactRef.DESCRIPTOR.fields_by_name
    assert {
        name: artifact[name].number
        for name in (
            "kind",
            "content_type",
            "file_name",
            "split_name",
            "package_name",
        )
    } == {
        "kind": 4,
        "content_type": 5,
        "file_name": 6,
        "split_name": 7,
        "package_name": 8,
    }
