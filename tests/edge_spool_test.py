from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
for source in ("packages/edge-protocol/src", "edge/gateway/src"):
    sys.path.insert(0, str(ROOT / source))

from cloudctl_edge.cache import ArtifactCache, ArtifactError
from cloudctl_edge.evidence import EvidenceQueue
from cloudctl_edge.spool import EdgeSpool, SpoolError, StaleFencingToken
from cloudctl_edge_protocol import edge_control_pb2 as pb


def command(command_id: str, token: int, lease: str = "lease-a") -> pb.StartCommand:
    value = pb.StartCommand(
        command_id=command_id,
        task_run_id="task-a",
        device_id="device-a",
        lease_id=lease,
        fencing_token=token,
        command_type="COLLECT_HEALTH",
    )
    value.deadline.FromDatetime(datetime.now(UTC) + timedelta(minutes=1))
    return value


def debug_grant(session_id: str = "debug-a") -> pb.DebugSessionGrant:
    value = pb.DebugSessionGrant(
        session_id=session_id,
        device_id="device-a",
        capabilities=["view.frame", "input.tap"],
        lease_id="lease-a",
        fencing_token=9,
        relay_token="x" * 48,
    )
    value.expires_at.FromDatetime(datetime.now(UTC) + timedelta(minutes=5))
    return value


def test_spool_uses_wal_persists_before_ack_and_rejects_stale_fence(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")
    assert spool.journal_mode() == "wal"
    first = command("cmd-1", 4)
    assert spool.accept_command(first).inserted is True
    assert spool.accept_command(first).inserted is False
    conflicting = pb.StartCommand()
    conflicting.CopyFrom(first)
    conflicting.command_type = "RUN_AUTOMATION"
    with pytest.raises(SpoolError, match="reused with different content"):
        spool.accept_command(conflicting)
    assert spool.accept_command(command("cmd-2", 5, "lease-b")).inserted is True
    with pytest.raises(StaleFencingToken):
        spool.accept_command(command("cmd-3", 4))
    with pytest.raises(StaleFencingToken):
        spool.assert_current_fence("device-a", "lease-a", 4)


def test_outbound_sequence_replay_and_ack(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")
    one = spool.enqueue_edge_message(
        pb.EdgeToCloud(command_ack=pb.CommandAck(command_id="one", state="RECEIVED"))
    )
    two = spool.enqueue_edge_message(
        pb.EdgeToCloud(command_ack=pb.CommandAck(command_id="two", state="RECEIVED"))
    )
    assert [message.sequence for message in spool.replay_edge_messages()] == [one, two]
    spool.acknowledge_edge_sequence(one)
    assert [message.sequence for message in spool.replay_edge_messages()] == [two]
    with pytest.raises(SpoolError):
        spool.acknowledge_edge_sequence(99)


def test_cloud_sequence_and_receipt_ack_are_persisted_together(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")
    edge_sequence = spool.record_cloud_with_edge_message(
        1,
        pb.EdgeToCloud(command_ack=pb.CommandAck(command_id="one", state="RECEIVED")),
        priority=0,
    )
    assert spool.last_cloud_sequence() == 1
    assert [message.sequence for message in spool.replay_edge_messages()] == [edge_sequence]
    with pytest.raises(SpoolError, match="expected 2"):
        spool.record_cloud_with_edge_message(
            3,
            pb.EdgeToCloud(command_ack=pb.CommandAck(command_id="three", state="RECEIVED")),
        )


def test_debug_grant_survives_reopen_and_revoke_removes_it(tmp_path: Path) -> None:
    path = tmp_path / "spool.sqlite3"
    grant = debug_grant()
    spool = EdgeSpool(path)
    spool.put_debug_grant(grant)
    spool.close()

    reopened = EdgeSpool(path)
    restored = reopened.active_debug_grants()
    assert len(restored) == 1
    assert restored[0].SerializeToString(deterministic=True) == grant.SerializeToString(
        deterministic=True
    )

    reopened.revoke_debug_grant(grant.session_id)
    assert reopened.active_debug_grants() == []
    reopened.close()

    after_revoke = EdgeSpool(path)
    assert after_revoke.active_debug_grants() == []
    after_revoke.close()


def test_debug_grant_is_idempotent_but_rejects_conflicting_payload(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")
    grant = debug_grant()

    spool.put_debug_grant(grant)
    spool.put_debug_grant(grant)
    assert [value.session_id for value in spool.active_debug_grants()] == [grant.session_id]

    conflicting = pb.DebugSessionGrant()
    conflicting.CopyFrom(grant)
    conflicting.capabilities.append("view.layout")
    with pytest.raises(SpoolError, match="reused with different grant content"):
        spool.put_debug_grant(conflicting)


def test_artifact_cache_and_evidence_verify_hashes(tmp_path: Path) -> None:
    payload = b"approved artifact"
    digest = hashlib.sha256(payload).hexdigest()
    cache = ArtifactCache(tmp_path / "cache", max_bytes=1024)
    path = cache.put(BytesIO(payload), expected_sha256=digest, expected_size=len(payload))
    assert cache.get(digest) == path
    path.write_bytes(b"tampered")
    with pytest.raises(ArtifactError, match="corrupted"):
        cache.get(digest)

    spool = EdgeSpool(tmp_path / "spool.sqlite3")
    queue = EvidenceQueue(tmp_path / "evidence", spool)
    record = queue.capture(command_id="cmd-1", kind="commit", source=BytesIO(b"evidence"))
    assert record.priority == 0
    assert spool.pending_evidence()[0].sha256 == hashlib.sha256(b"evidence").hexdigest()
