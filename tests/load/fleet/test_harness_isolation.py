"""Transaction-boundary checks for the simulated fleet's database fixture."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

import pytest
from cloudctl_api.db import Database, DeviceLeaseRow, MobileTaskRow
from sqlalchemy.ext.asyncio import AsyncSession

from .harness import FleetLoadApp


class ObserverRollback(Exception):
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["claim", "complete"])
async def test_task_transaction_survives_other_session_rollback(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    async with FleetLoadApp() as harness:
        device_id = await harness.seed_device("isolation")
        version, account_id = await harness.seed_account_and_bind(device_id, "isolation")
        auth = await harness.enroll(device_id, "isolation")
        task_id, _ = await harness.mint_probe(device_id, account_id, version, "isolation")
        database: Database = harness.app.state.database
        service = harness.app.state.mobile_task_service
        lease_id = None
        if operation == "complete":
            claimed = await harness.client.post(
                "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
            )
            assert claimed.status_code == 200, claimed.text
            lease_id = claimed.json()["leaseId"]

        in_task_transaction: ContextVar[bool] = ContextVar("in_task_transaction", default=False)
        flushed = asyncio.Event()
        release_commit = asyncio.Event()
        original_uow = database.unit_of_work
        method_name = "claim" if operation == "claim" else "finish"
        original_method = getattr(service, method_name)

        async def marked_operation(*args: Any, **kwargs: Any) -> Any:
            token = in_task_transaction.set(True)
            try:
                return await original_method(*args, **kwargs)
            finally:
                in_task_transaction.reset(token)

        @asynccontextmanager
        async def held_transaction() -> AsyncIterator[AsyncSession]:
            async with original_uow() as session:
                yield session
                if in_task_transaction.get():
                    await session.flush()
                    flushed.set()
                    await release_commit.wait()

        monkeypatch.setattr(service, method_name, marked_operation)
        monkeypatch.setattr(database, "unit_of_work", held_transaction)
        request = asyncio.create_task(
            harness.client.post(
                "/companion/v2/tasks/claim"
                if operation == "claim"
                else f"/companion/v2/tasks/{task_id}/complete",
                headers=auth,
                json={"leaseSeconds": 60}
                if operation == "claim"
                else {
                    "leaseId": lease_id,
                    "result": {
                        "outcome": "ok",
                        "resultType": "DeviceProbeResult",
                        "schemaVersion": 1,
                    },
                },
            )
        )
        try:
            await asyncio.wait_for(flushed.wait(), timeout=5)
            with pytest.raises(ObserverRollback):
                async with original_uow() as observer:
                    task = await observer.get(MobileTaskRow, task_id)
                    assert task is not None
                    observed_status = task.status
                    lease = await observer.get(DeviceLeaseRow, device_id)
                    observed_lease = lease.lease_id if lease is not None else None
                    raise ObserverRollback
        finally:
            release_commit.set()
            response = await asyncio.wait_for(request, timeout=5)

        assert response.status_code == 200, response.text
        async with original_uow() as observer:
            task = await observer.get(MobileTaskRow, task_id)
            lease = await observer.get(DeviceLeaseRow, device_id)
            assert task is not None
            committed_status = task.status
            committed_lease = lease.lease_id if lease is not None else None

        expected_before = "QUEUED" if operation == "claim" else "CLAIMED"
        expected_after = "CLAIMED" if operation == "claim" else "SUCCEEDED"
        assert (observed_status, committed_status) == (expected_before, expected_after)
        assert observed_lease == lease_id
        assert committed_lease == response.json()["leaseId"]
