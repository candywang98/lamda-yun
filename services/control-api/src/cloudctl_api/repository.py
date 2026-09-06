"""Tenant-scoped repositories. Methods never commit implicitly."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, TypeVar, cast

from cloudctl_domain import Actor, DomainEvent, NotFoundError, Role, canonical_hash, new_uuid7
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import (
    AuditEventRow,
    AutomationVersionRow,
    CommitIntentRow,
    ContentItemRow,
    ContentRevisionRow,
    DeviceLeaseRow,
    DeviceRow,
    EdgeRow,
    MediaAssetRow,
    OutboxEventRow,
    PublishPlanRow,
    PublishSnapshotRow,
    PublishTargetRow,
    TenantRow,
    UserRow,
)

RowT = TypeVar("RowT")


class ControlRepository:
    def __init__(self, session: AsyncSession, actor: Actor) -> None:
        self.session = session
        self.actor = actor
        self.tenant_id = str(actor.tenant_id)

    async def _one_for_tenant(
        self,
        statement: Select[tuple[RowT]],
        resource: str,
        resource_id: str,
    ) -> RowT:
        row = await self.session.scalar(statement)
        if row is None:
            raise NotFoundError(f"{resource} was not found")
        return row

    def add(self, row: object) -> None:
        self.session.add(row)

    async def flush(self) -> None:
        await self.session.flush()

    async def tenant(self, tenant_id: str) -> TenantRow | None:
        return await self.session.get(TenantRow, tenant_id)

    async def user(self, user_id: str) -> UserRow:
        return await self._one_for_tenant(
            select(UserRow).where(UserRow.id == user_id, UserRow.tenant_id == self.tenant_id),
            "user",
            user_id,
        )

    async def edge(self, edge_id: str) -> EdgeRow:
        return await self._one_for_tenant(
            select(EdgeRow).where(EdgeRow.id == edge_id, EdgeRow.tenant_id == self.tenant_id),
            "edge",
            edge_id,
        )

    async def device(self, device_id: str, *, for_update: bool = False) -> DeviceRow:
        statement = select(DeviceRow).where(
            DeviceRow.id == device_id, DeviceRow.tenant_id == self.tenant_id
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._one_for_tenant(statement, "device", device_id)

    async def devices(self) -> list[DeviceRow]:
        result = await self.session.scalars(
            select(DeviceRow).where(DeviceRow.tenant_id == self.tenant_id).order_by(DeviceRow.id)
        )
        return list(result)

    async def media_by_hash(self, sha256: str) -> MediaAssetRow | None:
        return cast(
            MediaAssetRow | None,
            await self.session.scalar(
                select(MediaAssetRow).where(
                    MediaAssetRow.tenant_id == self.tenant_id, MediaAssetRow.sha256 == sha256
                )
            ),
        )

    async def content(self, content_id: str) -> ContentItemRow:
        return await self._one_for_tenant(
            select(ContentItemRow).where(
                ContentItemRow.id == content_id,
                ContentItemRow.tenant_id == self.tenant_id,
            ),
            "content",
            content_id,
        )

    async def content_revision(self, revision_id: str) -> ContentRevisionRow:
        return await self._one_for_tenant(
            select(ContentRevisionRow).where(
                ContentRevisionRow.id == revision_id,
                ContentRevisionRow.tenant_id == self.tenant_id,
            ),
            "content revision",
            revision_id,
        )

    async def next_revision_no(self, content_id: str) -> int:
        rows = await self.session.scalars(
            select(ContentRevisionRow.revision_no).where(
                ContentRevisionRow.content_id == content_id,
                ContentRevisionRow.tenant_id == self.tenant_id,
            )
        )
        values = list(rows)
        return max(values, default=0) + 1

    async def latest_revision(self, content_id: str) -> ContentRevisionRow:
        revision = await self.session.scalar(
            select(ContentRevisionRow)
            .where(
                ContentRevisionRow.content_id == content_id,
                ContentRevisionRow.tenant_id == self.tenant_id,
            )
            .order_by(ContentRevisionRow.revision_no.desc())
        )
        if revision is None:
            raise NotFoundError("content revision was not found")
        return revision

    async def contents(self) -> list[ContentItemRow]:
        result = await self.session.scalars(
            select(ContentItemRow)
            .where(ContentItemRow.tenant_id == self.tenant_id)
            .order_by(ContentItemRow.id)
        )
        return list(result)

    async def automation_version(self, version_id: str) -> AutomationVersionRow:
        return await self._one_for_tenant(
            select(AutomationVersionRow).where(
                AutomationVersionRow.id == version_id,
                AutomationVersionRow.tenant_id == self.tenant_id,
            ),
            "automation package version",
            version_id,
        )

    async def plan_by_idempotency(self, key: str) -> PublishPlanRow | None:
        return cast(
            PublishPlanRow | None,
            await self.session.scalar(
                select(PublishPlanRow).where(
                    PublishPlanRow.tenant_id == self.tenant_id,
                    PublishPlanRow.idempotency_key == key,
                )
            ),
        )

    async def plan(self, plan_id: str, *, for_update: bool = False) -> PublishPlanRow:
        statement = select(PublishPlanRow).where(
            PublishPlanRow.id == plan_id, PublishPlanRow.tenant_id == self.tenant_id
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._one_for_tenant(statement, "publish plan", plan_id)

    async def snapshot_for_plan(self, plan_id: str) -> PublishSnapshotRow | None:
        return cast(
            PublishSnapshotRow | None,
            await self.session.scalar(
                select(PublishSnapshotRow).where(
                    PublishSnapshotRow.plan_id == plan_id,
                    PublishSnapshotRow.tenant_id == self.tenant_id,
                )
            ),
        )

    async def targets_for_plan(self, plan_id: str) -> list[PublishTargetRow]:
        result = await self.session.scalars(
            select(PublishTargetRow).where(
                PublishTargetRow.plan_id == plan_id,
                PublishTargetRow.tenant_id == self.tenant_id,
            )
        )
        return list(result)

    async def target(self, target_id: str, *, for_update: bool = False) -> PublishTargetRow:
        statement = select(PublishTargetRow).where(
            PublishTargetRow.id == target_id, PublishTargetRow.tenant_id == self.tenant_id
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._one_for_tenant(statement, "publish target", target_id)

    async def lease_for_device(self, device_id: str) -> DeviceLeaseRow | None:
        return cast(
            DeviceLeaseRow | None,
            await self.session.scalar(
                select(DeviceLeaseRow)
                .where(
                    DeviceLeaseRow.device_id == device_id,
                    DeviceLeaseRow.tenant_id == self.tenant_id,
                )
                .with_for_update()
            ),
        )

    async def intent_for_target(self, target_id: str) -> CommitIntentRow | None:
        return cast(
            CommitIntentRow | None,
            await self.session.scalar(
                select(CommitIntentRow).where(
                    CommitIntentRow.target_id == target_id,
                    CommitIntentRow.tenant_id == self.tenant_id,
                    CommitIntentRow.attempt_no == 1,
                )
            ),
        )

    async def events(self, after_id: str | None, limit: int = 100) -> list[OutboxEventRow]:
        statement = select(OutboxEventRow).where(OutboxEventRow.tenant_id == self.tenant_id)
        if after_id:
            statement = statement.where(OutboxEventRow.id > after_id)
        result = await self.session.scalars(statement.order_by(OutboxEventRow.id).limit(limit))
        return list(result)

    async def audit_events(self, limit: int = 100) -> list[AuditEventRow]:
        result = await self.session.scalars(
            select(AuditEventRow)
            .where(AuditEventRow.tenant_id == self.tenant_id)
            .order_by(AuditEventRow.id.desc())
            .limit(limit)
        )
        return list(result)

    def emit(self, event: DomainEvent) -> None:
        self.add(
            OutboxEventRow(
                id=str(event.id),
                tenant_id=str(event.tenant_id),
                aggregate_type=event.aggregate_type,
                aggregate_id=str(event.aggregate_id),
                event_type=event.event_type,
                payload=event.payload,
                occurred_at=event.occurred_at,
                published_at=None,
                claimed_at=None,
                claim_owner=None,
                attempts=0,
                last_error=None,
            )
        )

    def audit(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        before: Any = None,
        after: Any = None,
        result: str = "SUCCEEDED",
        metadata: dict[str, Any] | None = None,
        workflow_id: str | None = None,
        device_id: str | None = None,
        edge_id: str | None = None,
    ) -> None:
        safe_metadata = metadata or {}
        self.add(
            AuditEventRow(
                id=str(new_uuid7()),
                tenant_id=self.tenant_id,
                actor_type=("service" if Role.SYSTEM_SERVICE in self.actor.roles else "user"),
                actor_id=str(self.actor.user_id),
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                request_id=self.actor.request_id,
                workflow_id=workflow_id,
                device_id=device_id,
                edge_id=edge_id,
                before_hash=canonical_hash(before) if before is not None else None,
                after_hash=canonical_hash(after) if after is not None else None,
                result=result,
                metadata_json=safe_metadata,
                occurred_at=datetime.now(UTC),
            )
        )

    @staticmethod
    def new_id() -> str:
        return str(new_uuid7())

    def event(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> DomainEvent:
        return DomainEvent(
            tenant_id=uuid.UUID(self.tenant_id),
            aggregate_type=aggregate_type,
            aggregate_id=uuid.UUID(aggregate_id),
            event_type=event_type,
            payload=payload,
        )
