"""Fleet schedule control state (F12 cancel semantics).

A separate additive table instead of new columns on task_schedule: the legacy
schedule table stays byte-compatible with the frozen task-schedule/v1 surface,
while fleet cancel gets an explicit terminal state with audit columns.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...db import Base, TimestampMixin


class FleetScheduleControlRow(Base, TimestampMixin):
    __tablename__ = "fleet_schedule_control"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    # No DB-level FK to task_schedule: that table lives in the legacy SQL
    # migration path, not the alembic chain (see migration 20260917_0027).
    schedule_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # CLOSED vocabulary: ACTIVE | CANCELLED. Cancel is terminal — a cancelled
    # schedule never mints again and is never re-armed via :enable.
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[str] = mapped_column(String(64), nullable=True)
    cancel_reason: Mapped[str] = mapped_column(String(500), nullable=True)

    __table_args__ = (UniqueConstraint("schedule_id"),)
