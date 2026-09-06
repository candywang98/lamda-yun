from __future__ import annotations

import os
from pathlib import Path

import pytest
from cloudctl_edge_hub.session import EdgeHub, SessionError
from cloudctl_edge_hub.sqlite_hub_store import SqliteHubStore
from cloudctl_edge_protocol import edge_control_pb2 as pb


@pytest.mark.asyncio
async def test_sqlite_store_replays_pending_messages_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "state" / "hub.db"
    first_hub = EdgeHub(SqliteHubStore(path))
    first = await first_hub.queue(
        "edge-a", pb.CloudToEdge(cancel=pb.CancelCommand(command_id="one", reason="test"))
    )
    second = await first_hub.queue(
        "edge-a", pb.CloudToEdge(cancel=pb.CancelCommand(command_id="two", reason="test"))
    )
    assert (first.sequence, second.sequence) == (1, 2)

    restarted = EdgeHub(SqliteHubStore(path))
    stream = restarted.open("edge-a", last_cloud_sequence_acked=1)
    hello = await anext(stream)
    replay = await anext(stream)
    await stream.aclose()
    assert hello.hello.last_edge_sequence_acked == 0
    assert replay.sequence == 2
    assert replay.cancel.command_id == "two"

    store = SqliteHubStore(path)
    assert [message.sequence for message in await store.replay_cloud("edge-a", 0)] == [2]
    assert await store.last_cloud_sequence("edge-a") == 2


@pytest.mark.asyncio
async def test_sqlite_store_persists_edge_sequence_and_rejects_ack_rollback(
    tmp_path: Path,
) -> None:
    path = tmp_path / "hub.db"
    store = SqliteHubStore(path)
    await store.append_cloud("edge-a", pb.CloudToEdge(cancel=pb.CancelCommand(command_id="one")))
    await store.append_cloud("edge-a", pb.CloudToEdge(cancel=pb.CancelCommand(command_id="two")))
    await store.acknowledge_cloud("edge-a", 1)
    assert await store.record_edge(
        "edge-a",
        pb.EdgeToCloud(
            sequence=1,
            command_ack=pb.CommandAck(command_id="one", state="ACCEPTED"),
        ),
    )

    restarted = SqliteHubStore(path)
    assert await restarted.last_cloud_sequence("edge-a") == 2
    assert await restarted.last_edge_sequence("edge-a") == 1
    with pytest.raises(SessionError, match="behind durable watermark"):
        await restarted.acknowledge_cloud("edge-a", 0)

    third = await restarted.append_cloud(
        "edge-a", pb.CloudToEdge(cancel=pb.CancelCommand(command_id="three"))
    )
    assert third.sequence == 3


@pytest.mark.asyncio
async def test_sqlite_store_bootstraps_sequence_from_preexisting_edge_ack(
    tmp_path: Path,
) -> None:
    store = SqliteHubStore(tmp_path / "hub.db")
    hub = EdgeHub(store)

    stream = hub.open("edge-upgraded", last_cloud_sequence_acked=41)
    hello = await anext(stream)
    await stream.aclose()

    assert hello.WhichOneof("body") == "hello"
    assert await store.last_cloud_sequence("edge-upgraded") == 41
    next_message = await hub.queue(
        "edge-upgraded",
        pb.CloudToEdge(cancel=pb.CancelCommand(command_id="after-upgrade")),
    )
    assert next_message.sequence == 42
    with pytest.raises(SessionError, match="never emitted"):
        await store.acknowledge_cloud("edge-upgraded", 43)


def test_sqlite_store_uses_private_state_permissions(tmp_path: Path) -> None:
    path = tmp_path / "private" / "hub.db"
    SqliteHubStore(path)
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission semantics required")
def test_sqlite_store_refuses_insecure_existing_directory_without_changing_it(
    tmp_path: Path,
) -> None:
    state_directory = tmp_path / "shared"
    state_directory.mkdir(mode=0o755)
    os.chmod(state_directory, 0o755)  # noqa: S103 - deliberately insecure fixture

    with pytest.raises(SessionError, match="group or other access"):
        SqliteHubStore(state_directory / "hub.db")

    assert state_directory.stat().st_mode & 0o777 == 0o755


def test_sqlite_store_requires_absolute_path() -> None:
    with pytest.raises(SessionError, match="absolute"):
        SqliteHubStore("relative/hub.db")
