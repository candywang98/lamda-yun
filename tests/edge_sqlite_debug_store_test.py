from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from cloudctl_edge_hub.debug_delivery import DebugDeliveryRecord
from cloudctl_edge_hub.session import SessionError
from cloudctl_edge_hub.sqlite_debug_store import SqliteDebugDeliveryStore


@pytest.mark.asyncio
async def test_sqlite_debug_store_round_trip_and_update(tmp_path) -> None:
    store = SqliteDebugDeliveryStore(tmp_path / "debug.db")
    record = DebugDeliveryRecord(
        session_id="s1",
        edge_id="e1",
        device_id="d1",
        capabilities=("input.tap", "view.frame"),
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
        state="PENDING",
        lease_id="lease-1",
        fencing_token=2,
        relay_token_digest="a" * 64,
    )
    await store.create(record)
    assert await store.get("s1") == record
    await store.update("s1", state="QUEUED", cloud_sequence=9)
    updated = await store.get("s1")
    assert updated is not None and updated.state == "QUEUED" and updated.cloud_sequence == 9


@pytest.mark.asyncio
async def test_sqlite_debug_store_rejects_conflicting_replay(tmp_path) -> None:
    store = SqliteDebugDeliveryStore(tmp_path / "debug.db")
    record = DebugDeliveryRecord(
        session_id="s1",
        edge_id="e1",
        device_id="d1",
        capabilities=("input.tap",),
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
        state="PENDING",
    )
    await store.create(record)
    with pytest.raises(SessionError, match="different input"):
        await store.create(replace(record, device_id="d2"))
