"""Tenant-scoped persistence for catalog-backed operation tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from cloudctl_domain import Actor, NotFoundError
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from .db import (
    AuditEventRow,
    OperationFeatureConfigDraftRow,
    OperationItemRow,
    OperationTaskRow,
)


class OperationRepository:
    def __init__(self, session: AsyncSession, actor: Actor) -> None:
        self.session = session
        self.actor = actor
        self.tenant_id = str(actor.tenant_id)

    def add(self, row: object) -> None:
        self.session.add(row)

    async def task_by_idempotency(self, key: str) -> OperationTaskRow | None:
        return cast(
            OperationTaskRow | None,
            await self.session.scalar(
                select(OperationTaskRow).where(
                    OperationTaskRow.tenant_id == self.tenant_id,
                    OperationTaskRow.idempotency_key == key,
                )
            ),
        )

    async def feature_config_draft(self, feature_id: str) -> OperationFeatureConfigDraftRow | None:
        return cast(
            OperationFeatureConfigDraftRow | None,
            await self.session.scalar(
                select(OperationFeatureConfigDraftRow).where(
                    OperationFeatureConfigDraftRow.tenant_id == self.tenant_id,
                    OperationFeatureConfigDraftRow.feature_id == feature_id,
                )
            ),
        )

    async def update_feature_config_draft(
        self,
        row_id: str,
        *,
        expected_version: int,
        configuration: dict[str, Any],
        configuration_sha256: str,
        updated_by: str,
        updated_at: datetime,
    ) -> bool:
        result = cast(
            CursorResult[Any],
            await self.session.execute(
                update(OperationFeatureConfigDraftRow)
                .where(
                    OperationFeatureConfigDraftRow.id == row_id,
                    OperationFeatureConfigDraftRow.tenant_id == self.tenant_id,
                    OperationFeatureConfigDraftRow.version == expected_version,
                )
                .values(
                    configuration_json=configuration,
                    configuration_sha256=configuration_sha256,
                    version=expected_version + 1,
                    updated_by=updated_by,
                    updated_at=updated_at,
                )
            ),
        )
        return result.rowcount == 1

    async def task(self, task_id: str, *, for_update: bool = False) -> OperationTaskRow:
        statement = select(OperationTaskRow).where(
            OperationTaskRow.id == task_id,
            OperationTaskRow.tenant_id == self.tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = await self.session.scalar(statement)
        if row is None:
            raise NotFoundError("operation task was not found")
        return row

    async def tasks(
        self,
        *,
        module: str | None,
        status: str | None,
        after_id: str | None,
        allowed_operation_keys: list[str],
        limit: int,
    ) -> list[OperationTaskRow]:
        statement = select(OperationTaskRow).where(
            OperationTaskRow.tenant_id == self.tenant_id,
            OperationTaskRow.operation_key.in_(allowed_operation_keys),
        )
        if module:
            statement = statement.where(OperationTaskRow.module == module)
        if status:
            statement = statement.where(OperationTaskRow.status == status)
        if after_id:
            statement = statement.where(OperationTaskRow.id > after_id)
        result = await self.session.scalars(statement.order_by(OperationTaskRow.id).limit(limit))
        return list(result)

    async def items(self, task_id: str, *, for_update: bool = False) -> list[OperationItemRow]:
        statement = select(OperationItemRow).where(
            OperationItemRow.task_id == task_id,
            OperationItemRow.tenant_id == self.tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.scalars(statement.order_by(OperationItemRow.resource_id))
        return list(result)

    async def item(
        self, task_id: str, resource_id: str, *, for_update: bool = False
    ) -> OperationItemRow:
        statement = select(OperationItemRow).where(
            OperationItemRow.task_id == task_id,
            OperationItemRow.resource_id == resource_id,
            OperationItemRow.tenant_id == self.tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = await self.session.scalar(statement)
        if row is None:
            raise NotFoundError("operation item was not found")
        return row

    async def audit_events(self, task_id: str) -> list[AuditEventRow]:
        result = await self.session.scalars(
            select(AuditEventRow)
            .where(
                AuditEventRow.tenant_id == self.tenant_id,
                AuditEventRow.resource_type == "operation_task",
                AuditEventRow.resource_id == task_id,
            )
            .order_by(AuditEventRow.id)
        )
        return list(result)
