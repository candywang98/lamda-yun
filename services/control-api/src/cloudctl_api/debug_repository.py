"""Tenant-scoped persistence for debug sessions and evidence indexes."""

from __future__ import annotations

from typing import cast

from cloudctl_domain import Actor, NotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import DebugEvidenceRow, DebugSessionRow


class DebugRepository:
    def __init__(self, session: AsyncSession, actor: Actor) -> None:
        self.db_session = session
        self.actor = actor
        self.tenant_id = str(actor.tenant_id)

    def add(self, row: object) -> None:
        self.db_session.add(row)

    async def session(self, session_id: str, *, for_update: bool = False) -> DebugSessionRow:
        statement = select(DebugSessionRow).where(
            DebugSessionRow.id == session_id,
            DebugSessionRow.tenant_id == self.tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = await self.db_session.scalar(statement)
        if row is None:
            raise NotFoundError("debug session was not found")
        return row

    async def session_by_launch_hash(
        self, launch_code_hash: str, *, for_update: bool = False
    ) -> DebugSessionRow:
        statement = select(DebugSessionRow).where(
            DebugSessionRow.tenant_id == self.tenant_id,
            DebugSessionRow.launch_code_hash == launch_code_hash,
        )
        if for_update:
            statement = statement.with_for_update()
        row = await self.db_session.scalar(statement)
        if row is None:
            raise NotFoundError("debug launch code was not found")
        return row

    async def evidence_by_hash(self, session_id: str, sha256: str) -> DebugEvidenceRow | None:
        return cast(
            DebugEvidenceRow | None,
            await self.db_session.scalar(
                select(DebugEvidenceRow).where(
                    DebugEvidenceRow.tenant_id == self.tenant_id,
                    DebugEvidenceRow.session_id == session_id,
                    DebugEvidenceRow.sha256 == sha256,
                )
            ),
        )

    async def evidence(self, session_id: str) -> list[DebugEvidenceRow]:
        rows = await self.db_session.scalars(
            select(DebugEvidenceRow)
            .where(
                DebugEvidenceRow.tenant_id == self.tenant_id,
                DebugEvidenceRow.session_id == session_id,
            )
            .order_by(DebugEvidenceRow.id)
        )
        return list(rows)
