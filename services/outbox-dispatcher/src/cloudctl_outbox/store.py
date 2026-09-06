"""Outbox claiming and completion repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cloudctl_api.db import Database, OutboxEventRow
from sqlalchemy import or_, select


class OutboxStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def claim(
        self,
        owner: str,
        *,
        batch_size: int = 100,
        claim_ttl: timedelta = timedelta(minutes=2),
    ) -> list[OutboxEventRow]:
        now = datetime.now(UTC)
        stale_before = now - claim_ttl
        async with self.database.unit_of_work() as session:
            result = await session.scalars(
                select(OutboxEventRow)
                .where(
                    OutboxEventRow.published_at.is_(None),
                    or_(
                        OutboxEventRow.claimed_at.is_(None),
                        OutboxEventRow.claimed_at < stale_before,
                    ),
                )
                .order_by(OutboxEventRow.occurred_at, OutboxEventRow.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            rows = list(result)
            for row in rows:
                row.claimed_at = now
                row.claim_owner = owner
                row.attempts += 1
            return [self._detached(row) for row in rows]

    async def mark_published(self, event_id: str, owner: str) -> bool:
        async with self.database.unit_of_work() as session:
            row = await session.get(OutboxEventRow, event_id, with_for_update=True)
            if row is None or row.published_at is not None or row.claim_owner != owner:
                return False
            row.published_at = datetime.now(UTC)
            row.claimed_at = None
            row.claim_owner = None
            row.last_error = None
            return True

    async def mark_failed(self, event_id: str, owner: str, error: str) -> bool:
        async with self.database.unit_of_work() as session:
            row = await session.get(OutboxEventRow, event_id, with_for_update=True)
            if row is None or row.published_at is not None or row.claim_owner != owner:
                return False
            row.claimed_at = None
            row.claim_owner = None
            row.last_error = error[:2000]
            return True

    @staticmethod
    def _detached(row: OutboxEventRow) -> OutboxEventRow:
        return OutboxEventRow(
            id=row.id,
            tenant_id=row.tenant_id,
            aggregate_type=row.aggregate_type,
            aggregate_id=row.aggregate_id,
            event_type=row.event_type,
            payload=dict(row.payload),
            occurred_at=row.occurred_at,
            published_at=row.published_at,
            claimed_at=row.claimed_at,
            claim_owner=row.claim_owner,
            attempts=row.attempts,
            last_error=row.last_error,
        )
