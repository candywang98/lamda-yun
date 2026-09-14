"""Application services owning transactions and domain orchestration."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from cloudctl_automation_sdk import (
    RolloutEvidence,
    evaluate_rollout_promotion,
    package_signature_payload,
    validate_manifest,
    validate_recipe_package,
    verify_package_signature,
)
from cloudctl_domain import (
    Actor,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    Permission,
    PublishState,
    Role,
    ValidationError,
    assert_publish_transition,
    canonical_hash,
    require_permissions,
)
from cloudctl_domain.states import TERMINAL_STATES, assert_safe_cancel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .apk_policy import evaluate_apk_policy, verify_analysis_signature
from .db import (
    AccountDeviceBindingRow,
    ApkArtifactRow,
    ApprovalRow,
    AutomationVersionRow,
    ContentGroupMembershipRow,
    ContentGroupRow,
    ContentItemRow,
    ContentRevisionMediaRow,
    ContentRevisionRow,
    Database,
    DeviceLeaseRow,
    DeviceRow,
    EdgeRow,
    MediaAssetRow,
    MediaDerivativeRow,
    MediaGroupMembershipRow,
    MediaGroupRow,
    MediaTagRow,
    MediaUploadRow,
    MobileTaskRow,
    PlatformAccountRow,
    ProductGroupMembershipRow,
    ProductGroupRow,
    ProductMediaRow,
    ProductRow,
    PublishPlanRow,
    PublishSnapshotRow,
    PublishTargetRow,
    RecipeDeploymentActionRow,
    RecipeDeploymentRow,
    TenantRow,
    UserRow,
)
from .media_store import ObjectStore
from .repository import ControlRepository
from .schemas import (
    AccountDeviceBind,
    AccountStatusUpdate,
    ApkArtifactCreate,
    ApprovalRequest,
    AutomationPackageCreate,
    AutomationPromotionRequest,
    ContentArchiveRequest,
    ContentCreate,
    ContentGroupCreate,
    ContentGroupMembershipCreate,
    ContentXianyuDispatchRequest,
    DeviceCreate,
    EdgeCreate,
    MaintenanceRequest,
    MediaCreate,
    MediaDerivativeCreate,
    MediaDerivativeResult,
    MediaGroupUpdate,
    MediaTaxonomyUpdate,
    MediaUploadCreate,
    PlatformAccountCreate,
    ProductArchiveRequest,
    ProductBatchDelete,
    ProductBatchUpdateGroup,
    ProductBatchUpdatePrice,
    ProductCreate,
    ProductFilterRequest,
    ProductImportRequest,
    ProductMediaUpdate,
    ProductUpdate,
    PublishPlanCreate,
    RecipePublishRequest,
    RecipeRollbackRequest,
    RevisionCreate,
    RoleUpdate,
    UserCreate,
)
from .settings import Settings


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _row(row: object, *fields: str) -> dict[str, Any]:
    return {field: getattr(row, field) for field in fields}


class ControlService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        object_store: ObjectStore,
        mobile_task_service: Any | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.object_store = object_store
        self.mobile_task_service = mobile_task_service

    async def create_tenant(self, actor: Actor, name: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.TENANT_ADMIN)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            tenant_id = repository.new_id()
            tenant = TenantRow(id=tenant_id, name=name, created_at=_now())
            repository.add(tenant)
            repository.audit(
                action="tenant.created",
                resource_type="tenant",
                resource_id=tenant_id,
                after={"name": name},
            )
            return _row(tenant, "id", "name", "created_at")

    async def create_user(self, actor: Actor, request: UserCreate) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.TENANT_ADMIN)
        try:
            roles = [Role(role).value for role in request.roles]
        except ValueError as exc:
            raise ValidationError("unknown role") from exc
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            if await repository.tenant(str(actor.tenant_id)) is None:
                repository.add(
                    TenantRow(
                        id=str(actor.tenant_id), name=f"tenant-{actor.tenant_id}", created_at=_now()
                    )
                )
            user_id = repository.new_id()
            user = UserRow(
                id=user_id,
                tenant_id=repository.tenant_id,
                oidc_subject=request.oidc_subject,
                roles=roles,
                disabled=False,
                created_at=_now(),
            )
            repository.add(user)
            repository.audit(
                action="identity.user.created",
                resource_type="user",
                resource_id=user_id,
                after={"roles": roles, "oidc_subject_hash": canonical_hash(request.oidc_subject)},
            )
            return _row(user, "id", "tenant_id", "oidc_subject", "roles", "disabled")

    async def update_user_roles(
        self, actor: Actor, user_id: str, request: RoleUpdate
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.TENANT_ADMIN)
        try:
            roles = [Role(role).value for role in request.roles]
        except ValueError as exc:
            raise ValidationError("unknown role") from exc
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            user = await repository.user(user_id)
            before = {"roles": list(user.roles)}
            user.roles = roles
            repository.audit(
                action="identity.user.roles_updated",
                resource_type="user",
                resource_id=user.id,
                before=before,
                after={"roles": roles},
            )
            repository.emit(
                repository.event(
                    "user", user.id, "identity.user.roles_updated", {"userId": user.id}
                )
            )
            return _row(user, "id", "tenant_id", "oidc_subject", "roles", "disabled")

    async def create_edge(self, actor: Actor, request: EdgeCreate) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            edge = EdgeRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                logical_name=request.logical_name,
                certificate_fingerprint=request.certificate_fingerprint,
                state="REGISTERED",
                last_seen_at=None,
                created_at=_now(),
            )
            repository.add(edge)
            repository.audit(
                action="edge.registered",
                resource_type="edge",
                resource_id=edge.id,
                after={
                    "logical_name": edge.logical_name,
                    "fingerprint": edge.certificate_fingerprint,
                },
            )
            repository.emit(
                repository.event("edge", edge.id, "edge.registered", {"edgeId": edge.id})
            )
            return _row(edge, "id", "logical_name", "state", "certificate_fingerprint")

    async def create_device(self, actor: Actor, request: DeviceCreate) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            await repository.edge(request.edge_id)
            device = DeviceRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                edge_id=request.edge_id,
                logical_name=request.logical_name,
                android_version=request.android_version,
                lamda_version=request.lamda_version,
                target_app_versions=request.target_app_versions,
                capabilities=request.capabilities,
                labels=request.labels,
                state="REGISTERED",
                maintenance=False,
                last_seen_at=None,
                version=0,
                fencing_counter=0,
                created_at=_now(),
            )
            repository.add(device)
            repository.audit(
                action="device.registered",
                resource_type="device",
                resource_id=device.id,
                after={"edge_id": device.edge_id, "logical_name": device.logical_name},
                device_id=device.id,
                edge_id=device.edge_id,
            )
            repository.emit(
                repository.event("device", device.id, "device.registered", {"deviceId": device.id})
            )
            return self._device_view(device)

    async def list_devices(self, actor: Actor) -> list[dict[str, Any]]:
        require_permissions(actor.roles, Permission.DEVICE_READ)
        async with self.database.unit_of_work() as session:
            rows = await ControlRepository(session, actor).devices()
            return [self._device_view(row) for row in rows]

    async def create_platform_account(
        self, actor: Actor, request: PlatformAccountCreate
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        if request.expires_at is not None and _aware(request.expires_at) <= _now():
            raise ValidationError("account authorization expiry must be in the future")
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            existing = await session.scalar(
                select(PlatformAccountRow).where(
                    PlatformAccountRow.tenant_id == repository.tenant_id,
                    PlatformAccountRow.platform == request.platform,
                    PlatformAccountRow.external_subject_ref == request.external_subject_ref,
                )
            )
            if existing is not None:
                raise ConflictError("platform account authorization already exists")
            account = PlatformAccountRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                platform=request.platform,
                external_subject_ref=request.external_subject_ref,
                display_label=request.display_label,
                secret_ref=request.secret_ref,
                authorization_basis=request.authorization_basis,
                status="AUTHORIZED",
                expires_at=request.expires_at,
                last_checked_at=_now(),
                revoked_at=None,
                version=0,
                created_at=_now(),
            )
            repository.add(account)
            repository.audit(
                action="account.authorization.created",
                resource_type="platform_account",
                resource_id=account.id,
                after={
                    "platform": account.platform,
                    "status": account.status,
                    "subject_ref_hash": canonical_hash(account.external_subject_ref),
                    "secret_ref_hash": canonical_hash(account.secret_ref),
                },
            )
            repository.emit(
                repository.event(
                    "platform_account",
                    account.id,
                    "account.authorization.created",
                    {"accountId": account.id, "platform": account.platform},
                )
            )
            return self._account_view(account, [])

    async def list_platform_accounts(self, actor: Actor) -> list[dict[str, Any]]:
        require_permissions(actor.roles, Permission.DEVICE_READ)
        async with self.database.unit_of_work() as session:
            tenant_id = str(actor.tenant_id)
            accounts = list(
                await session.scalars(
                    select(PlatformAccountRow)
                    .where(PlatformAccountRow.tenant_id == tenant_id)
                    .order_by(PlatformAccountRow.id)
                )
            )
            bindings = list(
                await session.scalars(
                    select(AccountDeviceBindingRow)
                    .where(AccountDeviceBindingRow.tenant_id == tenant_id)
                    .order_by(AccountDeviceBindingRow.bound_at.desc())
                )
            )
            by_account: dict[str, list[AccountDeviceBindingRow]] = {}
            for binding in bindings:
                by_account.setdefault(binding.account_id, []).append(binding)
            return [self._account_view(row, by_account.get(row.id, [])) for row in accounts]

    async def get_account_ownership(self, actor: Actor, account_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_READ)
        async with self.database.unit_of_work() as session:
            tenant_id = str(actor.tenant_id)
            account = await self._account(session, tenant_id, account_id)
            bindings = list(
                await session.scalars(
                    select(AccountDeviceBindingRow)
                    .where(
                        AccountDeviceBindingRow.tenant_id == tenant_id,
                        AccountDeviceBindingRow.account_id == account.id,
                    )
                    .order_by(AccountDeviceBindingRow.bound_at.desc())
                )
            )
            tasks = list(
                await session.scalars(
                    select(MobileTaskRow)
                    .where(
                        MobileTaskRow.tenant_id == tenant_id,
                        MobileTaskRow.account_id == account.id,
                    )
                    .order_by(MobileTaskRow.created_at.desc())
                )
            )
            targets = list(
                await session.scalars(
                    select(PublishTargetRow)
                    .where(
                        PublishTargetRow.tenant_id == tenant_id,
                        PublishTargetRow.account_id == account.id,
                    )
                    .order_by(PublishTargetRow.created_at.desc())
                )
            )
            return {
                "account": self._account_view(account, bindings),
                "unbound": not any(row.status == "BOUND" for row in bindings),
                "mobileTasks": [
                    {
                        "taskId": row.id,
                        "status": row.status,
                        "accountId": row.account_id,
                        "bindingVersion": row.binding_version,
                        "deviceId": row.device_id,
                        "deviceIdAtExecution": row.device_id_at_execution,
                        "errorCode": row.error_code,
                    }
                    for row in tasks
                ],
                "publishTargets": [
                    {
                        "id": row.id,
                        "planId": row.plan_id,
                        "accountId": row.account_id,
                        "deviceId": row.device_id,
                        "bindingVersion": row.binding_version,
                        "deviceIdAtExecution": row.device_id_at_execution,
                        "state": row.state,
                    }
                    for row in targets
                ],
            }

    async def bind_account_device(
        self,
        actor: Actor,
        account_id: str,
        request: AccountDeviceBind,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            account = await self._account(
                session, repository.tenant_id, account_id, for_update=True
            )
            device = await repository.device(request.device_id, for_update=True)
            if account.status != "AUTHORIZED":
                raise ConflictError("only an authorized account can be bound")
            if account.expires_at is not None and _aware(account.expires_at) <= _now():
                raise ConflictError("account authorization has expired")
            now = _now()
            same_platform_bound = list(
                await session.scalars(
                    select(AccountDeviceBindingRow)
                    .join(
                        PlatformAccountRow,
                        PlatformAccountRow.id == AccountDeviceBindingRow.account_id,
                    )
                    .where(
                        AccountDeviceBindingRow.tenant_id == repository.tenant_id,
                        AccountDeviceBindingRow.device_id == device.id,
                        AccountDeviceBindingRow.status == "BOUND",
                        PlatformAccountRow.platform == account.platform,
                    )
                    .with_for_update()
                )
            )
            displaced: list[AccountDeviceBindingRow] = []
            for existing in same_platform_bound:
                if existing.account_id == account.id:
                    continue
                existing.status = "UNBOUND"
                existing.unbound_at = now
                displaced.append(existing)
            if displaced:
                await session.flush()
                await self._block_stale_account_work(
                    session,
                    tenant_id=repository.tenant_id,
                    device_id=device.id,
                    account_ids=[row.account_id for row in displaced],
                    reason="ACCOUNT_CHANGED",
                    now=now,
                )
                from .db import TaskScheduleRow

                paused = list(
                    await session.scalars(
                        select(TaskScheduleRow).where(
                            TaskScheduleRow.tenant_id == repository.tenant_id,
                            TaskScheduleRow.account_id.in_([row.account_id for row in displaced]),
                            TaskScheduleRow.enabled.is_(True),
                        )
                    )
                )
                for schedule in paused:
                    schedule.enabled = False
                    schedule.paused_reason = "ACCOUNT_CHANGED"
            binding = await session.scalar(
                select(AccountDeviceBindingRow)
                .where(
                    AccountDeviceBindingRow.tenant_id == repository.tenant_id,
                    AccountDeviceBindingRow.account_id == account.id,
                    AccountDeviceBindingRow.device_id == device.id,
                )
                .with_for_update()
            )
            if binding is None:
                binding = AccountDeviceBindingRow(
                    id=repository.new_id(),
                    tenant_id=repository.tenant_id,
                    account_id=account.id,
                    device_id=device.id,
                    status="BOUND",
                    confirmed_by=str(actor.user_id),
                    confirmation_note=request.confirmation_note,
                    bound_at=now,
                    unbound_at=None,
                    binding_version=1,
                    platform=account.platform,
                    created_at=now,
                )
                repository.add(binding)
            else:
                next_version = binding.binding_version + (1 if binding.status != "BOUND" else 0)
                binding.status = "BOUND"
                binding.confirmed_by = str(actor.user_id)
                binding.confirmation_note = request.confirmation_note
                binding.bound_at = now
                binding.unbound_at = None
                binding.binding_version = next_version or 1
                binding.platform = account.platform
            account.version += 1
            repository.audit(
                action="account.device.bound",
                resource_type="platform_account",
                resource_id=account.id,
                after={
                    "device_id": device.id,
                    "binding_id": binding.id,
                    "binding_version": binding.binding_version,
                    "displaced_account_ids": [row.account_id for row in displaced],
                },
                device_id=device.id,
                edge_id=device.edge_id,
            )
            return self._binding_view(binding)

    async def unbind_account_device(self, actor: Actor, account_id: str, device_id: str) -> None:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            account = await self._account(
                session, repository.tenant_id, account_id, for_update=True
            )
            await repository.device(device_id, for_update=True)
            binding = await session.scalar(
                select(AccountDeviceBindingRow)
                .where(
                    AccountDeviceBindingRow.tenant_id == repository.tenant_id,
                    AccountDeviceBindingRow.account_id == account.id,
                    AccountDeviceBindingRow.device_id == device_id,
                )
                .with_for_update()
            )
            if binding is None or binding.status != "BOUND":
                raise ConflictError("account is not actively bound to this device")
            now = _now()
            binding.status = "UNBOUND"
            binding.unbound_at = now
            account.version += 1
            await self._block_stale_account_work(
                session,
                tenant_id=repository.tenant_id,
                device_id=device_id,
                account_ids=[account.id],
                reason="ACCOUNT_CHANGED",
                now=now,
            )
            repository.audit(
                action="account.device.unbound",
                resource_type="platform_account",
                resource_id=account.id,
                before={"binding_id": binding.id, "status": "BOUND"},
                after={"binding_id": binding.id, "status": "UNBOUND"},
                device_id=device_id,
            )

    async def _block_stale_account_work(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        device_id: str,
        account_ids: list[str],
        reason: str,
        now: datetime,
    ) -> None:
        if not account_ids:
            return
        queued = list(
            await session.scalars(
                select(MobileTaskRow)
                .where(
                    MobileTaskRow.tenant_id == tenant_id,
                    MobileTaskRow.device_id == device_id,
                    MobileTaskRow.status == "QUEUED",
                    MobileTaskRow.account_id.in_(account_ids),
                )
                .with_for_update()
            )
        )
        for task in queued:
            task.status = "FAILED"
            task.business_state = "FAILED"
            task.error_code = reason
            task.detail = "account binding changed before execution"
            task.completed_at = now
            task.lease_id = None
            task.lease_expires_at = None
            from .im_service import settle_reply_delivery

            await settle_reply_delivery(session, task.id, "FAILED")
        open_plans = list(
            await session.scalars(
                select(PublishPlanRow)
                .where(
                    PublishPlanRow.tenant_id == tenant_id,
                    PublishPlanRow.state.in_(
                        {
                            PublishState.DRAFT.value,
                            PublishState.AWAITING_APPROVAL.value,
                            PublishState.SCHEDULED.value,
                            PublishState.QUEUED.value,
                        }
                    ),
                )
                .with_for_update()
            )
        )
        for plan in open_plans:
            targets = list(plan.targets or [])
            if not any(
                isinstance(target, dict)
                and target.get("accountId") in account_ids
                and target.get("deviceId") in {None, device_id}
                for target in targets
            ):
                continue
            current = PublishState(plan.state)
            if current in {
                PublishState.DRAFT,
                PublishState.AWAITING_APPROVAL,
                PublishState.SCHEDULED,
                PublishState.QUEUED,
            }:
                plan.state = PublishState.CANCELED.value
                plan.cancel_requested = True
                plan.version += 1
                plan.execution = {
                    **dict(plan.execution or {}),
                    "pausedReason": reason,
                    "pausedAt": now.isoformat(),
                }

    async def update_account_status(
        self, actor: Actor, account_id: str, request: AccountStatusUpdate
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            account = await self._account(
                session, repository.tenant_id, account_id, for_update=True
            )
            if request.expected_version is not None and request.expected_version != account.version:
                raise ConflictError("account version does not match expectedVersion")
            before = {"status": account.status, "version": account.version}
            account.status = request.status
            account.revoked_at = _now() if request.status == "REVOKED" else None
            account.last_checked_at = _now()
            account.version += 1
            if request.status != "AUTHORIZED":
                bindings = list(
                    await session.scalars(
                        select(AccountDeviceBindingRow)
                        .where(
                            AccountDeviceBindingRow.account_id == account.id,
                            AccountDeviceBindingRow.tenant_id == repository.tenant_id,
                            AccountDeviceBindingRow.status == "BOUND",
                        )
                        .with_for_update()
                    )
                )
                now = _now()
                for binding in bindings:
                    binding.status = "UNBOUND"
                    binding.unbound_at = now
                    await self._block_stale_account_work(
                        session,
                        tenant_id=repository.tenant_id,
                        device_id=binding.device_id,
                        account_ids=[account.id],
                        reason="ACCOUNT_CHANGED",
                        now=now,
                    )
            repository.audit(
                action="account.authorization.status_changed",
                resource_type="platform_account",
                resource_id=account.id,
                before=before,
                after={"status": account.status, "version": account.version},
                metadata={"reason": request.reason},
            )
            return self._account_view(account, [])

    async def set_maintenance(
        self, actor: Actor, device_id: str, request: MaintenanceRequest
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            device = await repository.device(device_id, for_update=True)
            existing_lease = await repository.lease_for_device(device.id)
            now = _now()
            if (
                existing_lease is not None
                and existing_lease.canceled_at is None
                and _aware(existing_lease.expires_at) > now
            ):
                raise ConflictError("device maintenance cannot change while a lease is active")
            if request.expected_version is not None and request.expected_version != device.version:
                raise ConflictError("device version does not match If-Match expectation")
            before = {"maintenance": device.maintenance, "version": device.version}
            device.maintenance = request.enabled
            device.version += 1
            repository.audit(
                action="device.maintenance.changed",
                resource_type="device",
                resource_id=device.id,
                before=before,
                after={"maintenance": device.maintenance, "version": device.version},
                metadata={"reason": request.reason},
                device_id=device.id,
                edge_id=device.edge_id,
            )
            repository.emit(
                repository.event(
                    "device",
                    device.id,
                    "device.maintenance.updated",
                    {"deviceId": device.id, "enabled": device.maintenance},
                )
            )
            return self._device_view(device)

    async def create_media(self, actor: Actor, request: MediaCreate) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            existing = await repository.media_by_hash(request.sha256)
            if existing is not None:
                return self._media_view(existing)
            if request.source_asset_id is not None:
                source = await session.get(MediaAssetRow, request.source_asset_id)
                if source is None or source.tenant_id != repository.tenant_id:
                    raise ValidationError("source asset does not exist in tenant")
            asset = MediaAssetRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                sha256=request.sha256,
                object_key=request.object_key,
                content_type=request.content_type,
                size_bytes=request.size_bytes,
                source_asset_id=request.source_asset_id,
                metadata_json=request.metadata,
                created_at=_now(),
            )
            repository.add(asset)
            repository.audit(
                action="media.registered",
                resource_type="media_asset",
                resource_id=asset.id,
                after={"sha256": asset.sha256, "size_bytes": asset.size_bytes},
            )
            return self._media_view(asset)

    async def list_media_assets(
        self,
        actor: Actor,
        *,
        tag: str | None = None,
        group_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_READ)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            conditions = [MediaAssetRow.tenant_id == repository.tenant_id]
            if tag is not None:
                normalized_tag = tag.strip()
                if not normalized_tag:
                    raise ValidationError("tag cannot be empty")
                conditions.append(
                    MediaAssetRow.id.in_(
                        select(MediaTagRow.media_asset_id).where(
                            MediaTagRow.tenant_id == repository.tenant_id,
                            MediaTagRow.tag == normalized_tag,
                        )
                    )
                )
            if group_id is not None:
                conditions.append(
                    MediaAssetRow.id.in_(
                        select(MediaGroupMembershipRow.media_asset_id).where(
                            MediaGroupMembershipRow.tenant_id == repository.tenant_id,
                            MediaGroupMembershipRow.group_id == group_id,
                        )
                    )
                )
            total = int(
                await session.scalar(
                    select(func.count()).select_from(MediaAssetRow).where(*conditions)
                )
                or 0
            )
            assets = list(
                await session.scalars(
                    select(MediaAssetRow)
                    .where(*conditions)
                    .order_by(MediaAssetRow.created_at.desc(), MediaAssetRow.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            asset_ids = [asset.id for asset in assets]
            tags = (
                list(
                    await session.scalars(
                        select(MediaTagRow).where(
                            MediaTagRow.tenant_id == repository.tenant_id,
                            MediaTagRow.media_asset_id.in_(asset_ids),
                        )
                    )
                )
                if asset_ids
                else []
            )
            memberships = (
                list(
                    await session.scalars(
                        select(MediaGroupMembershipRow).where(
                            MediaGroupMembershipRow.tenant_id == repository.tenant_id,
                            MediaGroupMembershipRow.media_asset_id.in_(asset_ids),
                        )
                    )
                )
                if asset_ids
                else []
            )
            tags_by_asset: dict[str, list[str]] = {}
            for item in tags:
                tags_by_asset.setdefault(item.media_asset_id, []).append(item.tag)
            groups_by_asset: dict[str, list[str]] = {}
            for item in memberships:
                groups_by_asset.setdefault(item.media_asset_id, []).append(item.group_id)
            items = []
            for asset in assets:
                item = self._media_view(asset)
                item["tags"] = sorted(tags_by_asset.get(asset.id, []))
                item["groupIds"] = sorted(groups_by_asset.get(asset.id, []))
                items.append(item)
            return {"items": items, "page": page, "pageSize": page_size, "total": total}

    async def create_product(self, actor: Actor, request: ProductCreate) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            existing = await session.scalar(
                select(ProductRow).where(
                    ProductRow.tenant_id == repository.tenant_id,
                    ProductRow.spu_code == request.spu_code,
                )
            )
            if existing is not None:
                raise ConflictError("product SPU already exists")
            asset_ids = list(dict.fromkeys(request.media_asset_ids))
            assets = (
                list(
                    await session.scalars(
                        select(MediaAssetRow).where(
                            MediaAssetRow.tenant_id == repository.tenant_id,
                            MediaAssetRow.id.in_(asset_ids),
                        )
                    )
                )
                if asset_ids
                else []
            )
            if len(assets) != len(asset_ids):
                raise ValidationError("one or more media assets do not exist in tenant")
            product = ProductRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                spu_code=request.spu_code,
                title=request.title,
                description=request.description,
                category=request.category,
                price=request.price,
                stock=request.stock,
                status="ACTIVE",
                revision=1,
                attributes=dict(request.attributes or {}),
                created_at=_now(),
            )
            repository.add(product)
            await session.flush()
            for order, asset_id in enumerate(asset_ids):
                repository.add(
                    ProductMediaRow(
                        id=repository.new_id(),
                        tenant_id=repository.tenant_id,
                        product_id=product.id,
                        media_asset_id=asset_id,
                        sort_order=order,
                        role="cover" if order == 0 else "detail",
                        created_at=_now(),
                    )
                )
            repository.audit(
                action="product.created",
                resource_type="product",
                resource_id=product.id,
                after={
                    "spu_code": product.spu_code,
                    "revision": product.revision,
                    "media_count": len(asset_ids),
                },
            )
            return self._product_view(product, asset_ids)

    async def update_media_taxonomy(
        self, actor: Actor, asset_id: str, request: MediaTaxonomyUpdate
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            asset = await session.scalar(
                select(MediaAssetRow).where(
                    MediaAssetRow.id == asset_id, MediaAssetRow.tenant_id == repository.tenant_id
                )
            )
            if asset is None:
                raise NotFoundError("media asset was not found")
            tags = list(dict.fromkeys(tag.strip() for tag in request.tags if tag.strip()))
            if any(len(tag) > 80 for tag in tags):
                raise ValidationError("media tags must be at most 80 characters")
            groups = (
                list(
                    await session.scalars(
                        select(MediaGroupRow).where(
                            MediaGroupRow.tenant_id == repository.tenant_id,
                            MediaGroupRow.id.in_(request.group_ids),
                        )
                    )
                )
                if request.group_ids
                else []
            )
            if len(groups) != len(set(request.group_ids)):
                raise ValidationError("one or more media groups do not exist in tenant")
            await session.execute(
                delete(MediaTagRow).where(
                    MediaTagRow.media_asset_id == asset.id,
                    MediaTagRow.tenant_id == repository.tenant_id,
                )
            )
            await session.execute(
                delete(MediaGroupMembershipRow).where(
                    MediaGroupMembershipRow.media_asset_id == asset.id,
                    MediaGroupMembershipRow.tenant_id == repository.tenant_id,
                )
            )
            for tag in tags:
                repository.add(
                    MediaTagRow(
                        id=repository.new_id(),
                        tenant_id=repository.tenant_id,
                        media_asset_id=asset.id,
                        tag=tag,
                        created_at=_now(),
                    )
                )
            for group in groups:
                repository.add(
                    MediaGroupMembershipRow(
                        id=repository.new_id(),
                        tenant_id=repository.tenant_id,
                        group_id=group.id,
                        media_asset_id=asset.id,
                        created_at=_now(),
                    )
                )
            repository.audit(
                action="media.taxonomy_updated",
                resource_type="media_asset",
                resource_id=asset.id,
                after={"tag_count": len(tags), "group_count": len(groups)},
            )
            return {
                "mediaAssetId": asset.id,
                "tags": tags,
                "groupIds": sorted(group.id for group in groups),
            }

    async def create_media_group(self, actor: Actor, request: ContentGroupCreate) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            existing = await session.scalar(
                select(MediaGroupRow).where(
                    MediaGroupRow.tenant_id == repository.tenant_id,
                    MediaGroupRow.name == request.name,
                )
            )
            if existing is not None:
                raise ConflictError("media group already exists")
            group = MediaGroupRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                name=request.name,
                description=request.description,
                created_at=_now(),
            )
            repository.add(group)
            return {
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "mediaAssetIds": [],
            }

    async def list_media_groups(self, actor: Actor) -> list[dict[str, Any]]:
        require_permissions(actor.roles, Permission.CONTENT_READ)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            groups = list(
                await session.scalars(
                    select(MediaGroupRow)
                    .where(MediaGroupRow.tenant_id == repository.tenant_id)
                    .order_by(MediaGroupRow.name)
                )
            )
            memberships = list(
                await session.scalars(
                    select(MediaGroupMembershipRow).where(
                        MediaGroupMembershipRow.tenant_id == repository.tenant_id
                    )
                )
            )
            return [
                {
                    "id": g.id,
                    "name": g.name,
                    "description": g.description,
                    "mediaAssetIds": [m.media_asset_id for m in memberships if m.group_id == g.id],
                }
                for g in groups
            ]

    async def update_media_group(
        self, actor: Actor, group_id: str, request: MediaGroupUpdate
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            group = await session.scalar(
                select(MediaGroupRow)
                .where(
                    MediaGroupRow.id == group_id, MediaGroupRow.tenant_id == repository.tenant_id
                )
                .with_for_update()
            )
            if group is None:
                raise NotFoundError("media group was not found")
            duplicate = await session.scalar(
                select(MediaGroupRow).where(
                    MediaGroupRow.tenant_id == repository.tenant_id,
                    MediaGroupRow.name == request.name,
                    MediaGroupRow.id != group.id,
                )
            )
            if duplicate is not None:
                raise ConflictError("media group already exists")
            group.name = request.name
            group.description = request.description
            ids = list(
                await session.scalars(
                    select(MediaGroupMembershipRow.media_asset_id).where(
                        MediaGroupMembershipRow.group_id == group.id,
                        MediaGroupMembershipRow.tenant_id == repository.tenant_id,
                    )
                )
            )
            repository.audit(
                action="media.group.updated",
                resource_type="media_group",
                resource_id=group.id,
                after={"name": group.name, "member_count": len(ids)},
            )
            return {
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "mediaAssetIds": ids,
            }

    async def delete_media_group(self, actor: Actor, group_id: str) -> None:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            group = await session.scalar(
                select(MediaGroupRow)
                .where(
                    MediaGroupRow.id == group_id, MediaGroupRow.tenant_id == repository.tenant_id
                )
                .with_for_update()
            )
            if group is None:
                raise NotFoundError("media group was not found")
            await session.execute(
                delete(MediaGroupMembershipRow).where(
                    MediaGroupMembershipRow.group_id == group.id,
                    MediaGroupMembershipRow.tenant_id == repository.tenant_id,
                )
            )
            await session.delete(group)
            repository.audit(
                action="media.group.deleted",
                resource_type="media_group",
                resource_id=group.id,
                before={"name": group.name},
            )

    async def get_media_references(self, actor: Actor, asset_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_READ)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            asset = await session.scalar(
                select(MediaAssetRow).where(
                    MediaAssetRow.id == asset_id, MediaAssetRow.tenant_id == repository.tenant_id
                )
            )
            if asset is None:
                raise NotFoundError("media asset was not found")
            product_ids = list(
                await session.scalars(
                    select(ProductMediaRow.product_id).where(
                        ProductMediaRow.media_asset_id == asset_id,
                        ProductMediaRow.tenant_id == repository.tenant_id,
                    )
                )
            )
            refs = list(
                await session.scalars(
                    select(ContentRevisionMediaRow).where(
                        ContentRevisionMediaRow.media_asset_id == asset_id,
                        ContentRevisionMediaRow.tenant_id == repository.tenant_id,
                    )
                )
            )
            revision_ids = [ref.content_revision_id for ref in refs]
            revisions = (
                list(
                    await session.scalars(
                        select(ContentRevisionRow).where(
                            ContentRevisionRow.tenant_id == repository.tenant_id,
                            ContentRevisionRow.id.in_(revision_ids),
                        )
                    )
                )
                if revision_ids
                else []
            )
            revisions_by_id = {revision.id: revision for revision in revisions}
            content_refs = [
                {
                    "contentId": ref.content_id,
                    "revisionId": ref.content_revision_id,
                    "revisionNo": revisions_by_id[ref.content_revision_id].revision_no,
                }
                for ref in refs
                if ref.content_revision_id in revisions_by_id
            ]
            publish_plans = (
                list(
                    await session.scalars(
                        select(PublishPlanRow).where(
                            PublishPlanRow.tenant_id == repository.tenant_id,
                            PublishPlanRow.content_revision_id.in_(revision_ids),
                        )
                    )
                )
                if revision_ids
                else []
            )
            tags = list(
                await session.scalars(
                    select(MediaTagRow.tag).where(
                        MediaTagRow.media_asset_id == asset_id,
                        MediaTagRow.tenant_id == repository.tenant_id,
                    )
                )
            )
            groups = list(
                await session.scalars(
                    select(MediaGroupMembershipRow.group_id).where(
                        MediaGroupMembershipRow.media_asset_id == asset_id,
                        MediaGroupMembershipRow.tenant_id == repository.tenant_id,
                    )
                )
            )
            return {
                "mediaAssetId": asset_id,
                "tags": tags,
                "groupIds": groups,
                "productIds": product_ids,
                "contentReferences": content_refs,
                "publishPlanReferences": [
                    {"publishPlanId": plan.id, "state": plan.state, "platform": plan.platform}
                    for plan in publish_plans
                ],
            }

    async def list_products(self, actor: Actor) -> list[dict[str, Any]]:
        require_permissions(actor.roles, Permission.CONTENT_READ)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            products = list(
                await session.scalars(
                    select(ProductRow)
                    .where(ProductRow.tenant_id == repository.tenant_id)
                    .order_by(ProductRow.created_at.desc())
                )
            )
            result = []
            for product in products:
                media = list(
                    await session.scalars(
                        select(ProductMediaRow)
                        .where(
                            ProductMediaRow.product_id == product.id,
                            ProductMediaRow.tenant_id == repository.tenant_id,
                        )
                        .order_by(ProductMediaRow.sort_order)
                    )
                )
                result.append(
                    self._product_view(product, [row.media_asset_id for row in media], media)
                )
            return result

    async def get_product(self, actor: Actor, product_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_READ)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            product = await session.scalar(
                select(ProductRow).where(
                    ProductRow.id == product_id,
                    ProductRow.tenant_id == repository.tenant_id,
                )
            )
            if product is None:
                raise NotFoundError("product was not found")
            media = list(
                await session.scalars(
                    select(ProductMediaRow)
                    .where(
                        ProductMediaRow.product_id == product.id,
                        ProductMediaRow.tenant_id == repository.tenant_id,
                    )
                    .order_by(ProductMediaRow.sort_order)
                )
            )
            return self._product_view(product, [row.media_asset_id for row in media], media)

    async def update_product(
        self, actor: Actor, product_id: str, request: ProductUpdate
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            product = await session.scalar(
                select(ProductRow)
                .where(ProductRow.id == product_id, ProductRow.tenant_id == repository.tenant_id)
                .with_for_update()
            )
            if product is None:
                raise NotFoundError("product was not found")
            if product.revision != request.expected_revision:
                raise ConflictError("product revision does not match expectedRevision")
            duplicate = await session.scalar(
                select(ProductRow).where(
                    ProductRow.tenant_id == repository.tenant_id,
                    ProductRow.spu_code == request.spu_code,
                    ProductRow.id != product.id,
                )
            )
            if duplicate is not None:
                raise ConflictError("product SPU already exists")
            asset_ids = list(dict.fromkeys(request.media_asset_ids))
            assets = (
                list(
                    await session.scalars(
                        select(MediaAssetRow).where(
                            MediaAssetRow.tenant_id == repository.tenant_id,
                            MediaAssetRow.id.in_(asset_ids),
                        )
                    )
                )
                if asset_ids
                else []
            )
            if len(assets) != len(asset_ids):
                raise ValidationError("one or more media assets do not exist in tenant")
            before = self._product_view(
                product,
                list(
                    await session.scalars(
                        select(ProductMediaRow.media_asset_id).where(
                            ProductMediaRow.product_id == product.id
                        )
                    )
                ),
            )
            product.spu_code = request.spu_code
            product.title = request.title
            product.description = request.description
            product.category = request.category
            product.price = request.price
            product.stock = request.stock
            product.attributes = dict(request.attributes or {})
            product.revision += 1
            await session.execute(
                delete(ProductMediaRow).where(
                    ProductMediaRow.product_id == product.id,
                    ProductMediaRow.tenant_id == repository.tenant_id,
                )
            )
            for order, asset_id in enumerate(asset_ids):
                repository.add(
                    ProductMediaRow(
                        id=repository.new_id(),
                        tenant_id=repository.tenant_id,
                        product_id=product.id,
                        media_asset_id=asset_id,
                        sort_order=order,
                        role="cover" if order == 0 else "detail",
                        created_at=_now(),
                    )
                )
            repository.audit(
                action="product.updated",
                resource_type="product",
                resource_id=product.id,
                before={"revision": before["revision"]},
                after={"revision": product.revision, "media_count": len(asset_ids)},
            )
            return self._product_view(product, asset_ids)

    async def archive_product(
        self, actor: Actor, product_id: str, request: ProductArchiveRequest
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            product = await session.scalar(
                select(ProductRow)
                .where(ProductRow.id == product_id, ProductRow.tenant_id == repository.tenant_id)
                .with_for_update()
            )
            if product is None:
                raise NotFoundError("product was not found")
            if product.status == "ARCHIVED":
                asset_ids = list(
                    await session.scalars(
                        select(ProductMediaRow.media_asset_id)
                        .where(ProductMediaRow.product_id == product.id)
                        .order_by(ProductMediaRow.sort_order)
                    )
                )
                return self._product_view(product, asset_ids)
            active_plan = await session.scalar(
                select(PublishPlanRow.id).where(
                    PublishPlanRow.product_id == product.id,
                    PublishPlanRow.tenant_id == repository.tenant_id,
                    PublishPlanRow.state.not_in([state.value for state in TERMINAL_STATES]),
                )
            )
            if active_plan is not None:
                raise ConflictError("product is referenced by an active publish plan")
            product.status = "ARCHIVED"
            product.revision += 1
            repository.audit(
                action="product.archived",
                resource_type="product",
                resource_id=product.id,
                after={"status": product.status, "revision": product.revision},
                metadata={"reason": request.reason},
            )
            asset_ids = list(
                await session.scalars(
                    select(ProductMediaRow.media_asset_id)
                    .where(ProductMediaRow.product_id == product.id)
                    .order_by(ProductMediaRow.sort_order)
                )
            )
            return self._product_view(product, asset_ids)

    async def update_product_media(
        self, actor: Actor, product_id: str, request: ProductMediaUpdate
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            product = await session.scalar(
                select(ProductRow)
                .where(ProductRow.id == product_id, ProductRow.tenant_id == repository.tenant_id)
                .with_for_update()
            )
            if product is None:
                raise NotFoundError("product was not found")
            if product.revision != request.expected_revision:
                raise ConflictError("product revision does not match expectedRevision")
            ids = [item.media_asset_id for item in request.items]
            if len(ids) != len(set(ids)):
                raise ValidationError("mediaAssetId values must be unique")
            orders = [item.sort_order for item in request.items]
            if sorted(orders) != list(range(len(orders))):
                raise ValidationError("sortOrder values must be contiguous from zero")
            if request.items and sum(item.role == "cover" for item in request.items) != 1:
                raise ValidationError("exactly one cover is required when media is present")
            assets = (
                list(
                    await session.scalars(
                        select(MediaAssetRow).where(
                            MediaAssetRow.tenant_id == repository.tenant_id,
                            MediaAssetRow.id.in_(ids),
                        )
                    )
                )
                if ids
                else []
            )
            if len(assets) != len(ids):
                raise ValidationError("one or more media assets do not exist in tenant")
            await session.execute(
                delete(ProductMediaRow).where(
                    ProductMediaRow.product_id == product.id,
                    ProductMediaRow.tenant_id == repository.tenant_id,
                )
            )
            for item in sorted(request.items, key=lambda value: value.sort_order):
                repository.add(
                    ProductMediaRow(
                        id=repository.new_id(),
                        tenant_id=repository.tenant_id,
                        product_id=product.id,
                        media_asset_id=item.media_asset_id,
                        sort_order=item.sort_order,
                        role=item.role,
                        created_at=_now(),
                    )
                )
            product.revision += 1
            repository.audit(
                action="product.media_updated",
                resource_type="product",
                resource_id=product.id,
                after={"revision": product.revision, "media_count": len(ids)},
            )
            asset_ids = [
                item.media_asset_id
                for item in sorted(request.items, key=lambda value: value.sort_order)
            ]
            return self._product_view(product, asset_ids, request.items)

    async def batch_update_product_price(
        self, actor: Actor, request: ProductBatchUpdatePrice
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            products = list(
                await session.scalars(
                    select(ProductRow).where(
                        ProductRow.id.in_(request.product_ids),
                        ProductRow.tenant_id == repository.tenant_id,
                        ProductRow.status == "ACTIVE",
                    )
                )
            )
            if len(products) != len(request.product_ids):
                raise ValidationError("one or more products do not exist or are archived")
            
            for product in products:
                product.price = request.price
                product.revision += 1
                repository.audit(
                    action="product.price_updated",
                    resource_type="product",
                    resource_id=product.id,
                    after={"revision": product.revision, "price": request.price},
                )
            
            return {"updated_count": len(products), "product_ids": request.product_ids}

    async def batch_update_product_group(
        self, actor: Actor, request: ProductBatchUpdateGroup
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            
            # Verify group exists - 使用ProductGroupRow而不是ContentGroupRow
            group = await session.get(ProductGroupRow, request.group_id)
            if group is None or group.tenant_id != repository.tenant_id:
                raise ValidationError("product group does not exist in tenant")
            
            products = list(
                await session.scalars(
                    select(ProductRow).where(
                        ProductRow.id.in_(request.product_ids),
                        ProductRow.tenant_id == repository.tenant_id,
                        ProductRow.status == "ACTIVE",
                    )
                )
            )
            if len(products) != len(request.product_ids):
                raise ValidationError("one or more products do not exist or are archived")
            
            # Remove existing group memberships - 使用ProductGroupMembershipRow
            await session.execute(
                delete(ProductGroupMembershipRow).where(
                    ProductGroupMembershipRow.product_id.in_(request.product_ids),
                    ProductGroupMembershipRow.tenant_id == repository.tenant_id,
                )
            )
            
            # Add new group memberships - 使用ProductGroupMembershipRow
            for product_id in request.product_ids:
                repository.add(
                    ProductGroupMembershipRow(
                        id=repository.new_id(),
                        tenant_id=repository.tenant_id,
                        group_id=request.group_id,
                        product_id=product_id,
                        added_by=repository.user_id,
                        created_at=_now(),
                    )
                )
            
            return {"updated_count": len(products), "group_id": request.group_id}

    async def batch_delete_products(
        self, actor: Actor, request: ProductBatchDelete
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            products = list(
                await session.scalars(
                    select(ProductRow).where(
                        ProductRow.id.in_(request.product_ids),
                        ProductRow.tenant_id == repository.tenant_id,
                        ProductRow.status == "ACTIVE",
                    )
                )
            )
            if len(products) != len(request.product_ids):
                raise ValidationError("one or more products do not exist or are already archived")
            
            for product in products:
                product.status = "ARCHIVED"
                product.revision += 1
                repository.audit(
                    action="product.archived",
                    resource_type="product",
                    resource_id=product.id,
                    after={"revision": product.revision, "reason": request.reason},
                )
            
            return {"archived_count": len(products), "product_ids": request.product_ids}

    async def import_products(
        self, actor: Actor, request: ProductImportRequest
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            
            if request.group_id:
                group = await session.get(ContentGroupRow, request.group_id)
                if group is None or group.tenant_id != repository.tenant_id:
                    raise ValidationError("content group does not exist in tenant")
            
            imported_ids = []
            skipped_count = 0
            
            for item in request.items:
                # Check if product with same SPU code already exists
                existing = await session.scalar(
                    select(ProductRow).where(
                        ProductRow.spu_code == item.spu_code,
                        ProductRow.tenant_id == repository.tenant_id,
                    )
                )
                
                if existing:
                    skipped_count += 1
                    continue
                
                product_id = repository.new_id()
                product = ProductRow(
                    id=product_id,
                    tenant_id=repository.tenant_id,
                    spu_code=item.spu_code,
                    title=item.title,
                    description=item.description,
                    category=item.category,
                    price=item.price,
                    stock=item.stock,
                    status="ACTIVE",
                    revision=1,
                    attributes={"imageUrls": list(item.image_urls or [])},
                    created_at=_now(),
                )
                repository.add(product)
                
                # Add to group if specified
                group_id = item.group_id or request.group_id
                if group_id:
                    repository.add(
                        ContentGroupMembershipRow(
                            id=repository.new_id(),
                            tenant_id=repository.tenant_id,
                            group_id=group_id,
                            content_id=product_id,
                            created_at=_now(),
                        )
                    )
                
                repository.audit(
                    action="product.imported",
                    resource_type="product",
                    resource_id=product_id,
                    after={"spu_code": item.spu_code, "title": item.title},
                )
                
                imported_ids.append(product_id)
            
            return {
                "imported_count": len(imported_ids),
                "skipped_count": skipped_count,
                "product_ids": imported_ids,
            }

    async def filter_products(
        self, actor: Actor, request: ProductFilterRequest
    ) -> list[dict[str, Any]]:
        require_permissions(actor.roles, Permission.CONTENT_READ)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            
            query = select(ProductRow).where(ProductRow.tenant_id == repository.tenant_id)
            
            if request.status and request.status != "ALL":
                query = query.where(ProductRow.status == request.status)
            
            if request.search:
                search_pattern = f"%{request.search}%"
                query = query.where(
                    (ProductRow.title.ilike(search_pattern))
                    | (ProductRow.spu_code.ilike(search_pattern))
                    | (ProductRow.description.ilike(search_pattern))
                )
            
            if request.category:
                query = query.where(ProductRow.category == request.category)
            
            if request.min_price:
                query = query.where(ProductRow.price >= request.min_price)
            
            if request.max_price:
                query = query.where(ProductRow.price <= request.max_price)
            
            if request.group_id:
                query = query.join(
                    ProductGroupMembershipRow,
                    (ProductGroupMembershipRow.product_id == ProductRow.id)
                    & (ProductGroupMembershipRow.tenant_id == repository.tenant_id)
                    & (ProductGroupMembershipRow.group_id == request.group_id),
                )
            
            products = list(await session.scalars(query.order_by(ProductRow.created_at.desc())))
            
            result = []
            for product in products:
                media = list(
                    await session.scalars(
                        select(ProductMediaRow)
                        .where(
                            ProductMediaRow.product_id == product.id,
                            ProductMediaRow.tenant_id == repository.tenant_id,
                        )
                        .order_by(ProductMediaRow.sort_order)
                    )
                )
                asset_ids = [m.media_asset_id for m in media]
                result.append(self._product_view(product, asset_ids, media))
            
            return result

    async def initiate_media_upload(
        self, actor: Actor, request: MediaUploadCreate
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        if bool(request.source_asset_id) != bool(request.derivative_profile_id):
            raise ValidationError("sourceAssetId and derivativeProfileId must be provided together")
        upload_id = ControlRepository.new_id()
        object_key = f"tenants/{actor.tenant_id}/media/{upload_id}/{request.file_name}"
        expires_at = _now() + timedelta(seconds=self.settings.media_upload_expires_seconds)
        grant = await self.object_store.create_upload(
            object_key,
            content_type=request.content_type,
            size_bytes=request.size_bytes,
            sha256=request.sha256,
            expires_seconds=self.settings.media_upload_expires_seconds,
        )
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            existing = await repository.media_by_hash(request.sha256)
            if existing is not None:
                return {"state": "COMPLETED", "asset": self._media_view(existing)}
            if request.source_asset_id is not None:
                source = await session.get(MediaAssetRow, request.source_asset_id)
                if source is None or source.tenant_id != repository.tenant_id:
                    raise ValidationError("source asset does not exist in tenant")
            upload = MediaUploadRow(
                id=upload_id,
                tenant_id=repository.tenant_id,
                expected_sha256=request.sha256,
                object_key=object_key,
                content_type=request.content_type,
                size_bytes=request.size_bytes,
                source_asset_id=request.source_asset_id,
                derivative_profile_id=request.derivative_profile_id,
                metadata_json=request.metadata,
                state="PENDING",
                created_by=str(actor.user_id),
                expires_at=expires_at,
                completed_at=None,
                created_at=_now(),
            )
            repository.add(upload)
            repository.audit(
                action="media.upload.initiated",
                resource_type="media_upload",
                resource_id=upload.id,
                after={
                    "object_key_hash": canonical_hash(upload.object_key),
                    "sha256": upload.expected_sha256,
                    "size_bytes": upload.size_bytes,
                },
            )
            upload_url = grant.url
            if not upload_url.startswith(("http://", "https://")):
                path = f"/api/v1/media/uploads/{upload.id}/content"
                base = (self.settings.public_base_url or "").rstrip("/")
                upload_url = f"{base}{path}" if base else path
            return {
                "id": upload.id,
                "state": upload.state,
                "objectKey": upload.object_key,
                "uploadUrl": upload_url,
                "uploadHeaders": grant.headers,
                "expiresAt": upload.expires_at,
            }

    async def store_media_upload_content(
        self, upload_id: str, content: bytes, content_type: str
    ) -> None:
        declared_type = content_type.split(";", 1)[0].strip() or "application/octet-stream"
        async with self.database.unit_of_work() as session:
            upload = await session.scalar(select(MediaUploadRow).where(MediaUploadRow.id == upload_id))
            if upload is None:
                raise NotFoundError("media upload does not exist")
            if upload.state == "COMPLETED":
                raise ConflictError("media upload already completed")
            if upload.expires_at is not None and upload.expires_at < _now():
                raise ValidationError("media upload has expired")
            if len(content) != upload.size_bytes:
                raise ValidationError("uploaded object size does not match the declared size")
            digest = hashlib.sha256(content).hexdigest()
            if digest != upload.expected_sha256:
                raise ValidationError("uploaded object SHA256 does not match the declared digest")
            if declared_type != upload.content_type:
                raise ValidationError("uploaded object content type does not match")
            object_key = upload.object_key
            stored_type = upload.content_type
        put = getattr(self.object_store, "put", None)
        if put is None:
            raise ValidationError("object store does not accept direct uploads")
        put(object_key, content, stored_type)

    async def download_media_asset(self, actor: Actor, asset_id: str) -> tuple[bytes, str]:
        require_permissions(actor.roles, Permission.CONTENT_READ)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            asset = await session.scalar(
                select(MediaAssetRow).where(
                    MediaAssetRow.id == asset_id,
                    MediaAssetRow.tenant_id == repository.tenant_id,
                )
            )
            if asset is None:
                raise NotFoundError("media asset was not found")
            object_key = asset.object_key
            content_type = asset.content_type
        stored = await self.object_store.get(object_key)
        if stored is None:
            raise NotFoundError("media object was not found")
        return stored.content, stored.content_type or content_type

    async def complete_media_upload(self, actor: Actor, upload_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        tenant_id = str(actor.tenant_id)
        async with self.database.unit_of_work() as session:
            upload = await session.scalar(
                select(MediaUploadRow).where(
                    MediaUploadRow.id == upload_id, MediaUploadRow.tenant_id == tenant_id
                )
            )
            if upload is None:
                raise ValidationError("media upload does not exist in tenant")
            if upload.state == "COMPLETED":
                asset = await session.scalar(
                    select(MediaAssetRow).where(
                        MediaAssetRow.tenant_id == tenant_id,
                        MediaAssetRow.sha256 == upload.expected_sha256,
                    )
                )
                if asset is None:
                    raise ConflictError("completed upload has no registered asset")
                return self._media_view(asset)
            object_key = upload.object_key
        stored = await self.object_store.head(object_key)
        failure: str | None = None
        if stored is None:
            failure = "uploaded object was not found"
        elif stored.size_bytes != upload.size_bytes:
            failure = "uploaded object size does not match the declared size"
        elif stored.sha256 != upload.expected_sha256:
            failure = "uploaded object SHA256 does not match the declared digest"
        elif stored.content_type != upload.content_type:
            failure = "uploaded object content type does not match"
        result: dict[str, Any] | None = None
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            current = await session.scalar(
                select(MediaUploadRow)
                .where(
                    MediaUploadRow.id == upload_id,
                    MediaUploadRow.tenant_id == repository.tenant_id,
                )
                .with_for_update()
            )
            if current is None:
                raise ValidationError("media upload does not exist in tenant")
            if _aware(current.expires_at) <= _now() and failure is None:
                failure = "media upload authorization expired before completion"
            if failure is not None:
                current.state = "FAILED"
                repository.audit(
                    action="media.upload.validation_failed",
                    resource_type="media_upload",
                    resource_id=current.id,
                    after={"state": current.state},
                    result="FAILED",
                    metadata={"reason": failure},
                )
            else:
                existing = await repository.media_by_hash(current.expected_sha256)
                asset = existing or MediaAssetRow(
                    id=repository.new_id(),
                    tenant_id=repository.tenant_id,
                    sha256=current.expected_sha256,
                    object_key=current.object_key,
                    content_type=current.content_type,
                    size_bytes=current.size_bytes,
                    source_asset_id=current.source_asset_id,
                    metadata_json=current.metadata_json,
                    created_at=_now(),
                )
                if existing is None:
                    repository.add(asset)
                current.state = "COMPLETED"
                current.completed_at = _now()
                repository.audit(
                    action="media.upload.completed",
                    resource_type="media_asset",
                    resource_id=asset.id,
                    after={"sha256": asset.sha256, "upload_id": current.id},
                )
                repository.emit(
                    repository.event(
                        "media_asset",
                        asset.id,
                        "media.asset.ready",
                        {"assetId": asset.id, "sha256": asset.sha256},
                    )
                )
                result = self._media_view(asset)
        if failure is not None:
            raise ConflictError(failure)
        if result is None:
            raise ConflictError("media upload completion did not produce an asset")
        return result

    async def request_media_derivative(
        self, actor: Actor, source_asset_id: str, request: MediaDerivativeCreate
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            source = await session.get(MediaAssetRow, source_asset_id)
            if source is None or source.tenant_id != repository.tenant_id:
                raise ValidationError("source asset does not exist in tenant")
            derivative = MediaDerivativeRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                source_asset_id=source.id,
                profile_id=request.profile_id,
                state="QUEUED",
                output_asset_id=None,
                error_code=None,
                detail=None,
                completed_at=None,
                created_at=_now(),
            )
            repository.add(derivative)
            repository.audit(
                action="media.derivative.requested",
                resource_type="media_derivative",
                resource_id=derivative.id,
                after={"source_asset_id": source.id, "profile_id": derivative.profile_id},
            )
            repository.emit(
                repository.event(
                    "media_derivative",
                    derivative.id,
                    "media.derivative.requested",
                    {"derivativeId": derivative.id, "sourceAssetId": source.id},
                )
            )
            return self._derivative_view(derivative)

    async def record_media_derivative_result(
        self, actor: Actor, derivative_id: str, request: MediaDerivativeResult
    ) -> dict[str, Any]:
        if Role.SYSTEM_SERVICE not in actor.roles:
            raise ForbiddenError("only an authorized service may record derivative results")
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            derivative = await session.scalar(
                select(MediaDerivativeRow)
                .where(
                    MediaDerivativeRow.id == derivative_id,
                    MediaDerivativeRow.tenant_id == repository.tenant_id,
                )
                .with_for_update()
            )
            if derivative is None:
                raise ValidationError("media derivative does not exist in tenant")
            if derivative.state in {"SUCCEEDED", "FAILED"}:
                raise ConflictError("media derivative already has a terminal result")
            if request.status == "SUCCEEDED":
                if request.output_asset_id is None:
                    raise ValidationError("outputAssetId is required for a successful derivative")
                output = await session.get(MediaAssetRow, request.output_asset_id)
                if (
                    output is None
                    or output.tenant_id != repository.tenant_id
                    or output.source_asset_id != derivative.source_asset_id
                ):
                    raise ValidationError(
                        "output asset is not a traceable derivative of the source"
                    )
            derivative.state = request.status
            derivative.output_asset_id = request.output_asset_id
            derivative.error_code = request.error_code
            derivative.detail = request.detail
            derivative.completed_at = _now()
            repository.audit(
                action="media.derivative.result_recorded",
                resource_type="media_derivative",
                resource_id=derivative.id,
                after={"status": derivative.state, "output_asset_id": derivative.output_asset_id},
                result=derivative.state,
            )
            return self._derivative_view(derivative)

    async def create_content(self, actor: Actor, request: ContentCreate) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            await self._assert_payload_media(session, repository.tenant_id, request.payload)
            content = ContentItemRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                title=request.title,
                created_by=str(actor.user_id),
                status="ACTIVE",
                archived_at=None,
                created_at=_now(),
            )
            revision = ContentRevisionRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                content_id=content.id,
                revision_no=1,
                payload=request.payload,
                payload_sha256=canonical_hash(request.payload),
                created_by=str(actor.user_id),
                created_at=_now(),
            )
            repository.add(content)
            repository.add(revision)
            await session.flush()
            for media_id in dict.fromkeys(request.payload.get("mediaAssetIds") or []):
                repository.add(
                    ContentRevisionMediaRow(
                        id=repository.new_id(),
                        tenant_id=repository.tenant_id,
                        content_revision_id=revision.id,
                        content_id=content.id,
                        media_asset_id=media_id,
                        created_at=_now(),
                    )
                )
            group_ids = await self._assign_content_group(
                session, repository, actor, content.id, request.group_id
            )
            repository.audit(
                action="content.created",
                resource_type="content",
                resource_id=content.id,
                after={"revision_id": revision.id, "payload_sha256": revision.payload_sha256},
            )
            repository.emit(
                repository.event(
                    "content", content.id, "content.revision.created", {"revisionId": revision.id}
                )
            )
            return self._content_view(content, revision, group_ids)

    async def add_revision(
        self, actor: Actor, content_id: str, request: RevisionCreate
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            content = await repository.content(content_id)
            if content.status == "ARCHIVED":
                raise ConflictError("archived content cannot receive new revisions")
            await self._assert_payload_media(session, repository.tenant_id, request.payload)
            revision = ContentRevisionRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                content_id=content.id,
                revision_no=await repository.next_revision_no(content.id),
                payload=request.payload,
                payload_sha256=canonical_hash(request.payload),
                created_by=str(actor.user_id),
                created_at=_now(),
            )
            repository.add(revision)
            await session.flush()
            for media_id in dict.fromkeys(request.payload.get("mediaAssetIds") or []):
                repository.add(
                    ContentRevisionMediaRow(
                        id=repository.new_id(),
                        tenant_id=repository.tenant_id,
                        content_revision_id=revision.id,
                        content_id=content.id,
                        media_asset_id=media_id,
                        created_at=_now(),
                    )
                )
            group_ids = await self._assign_content_group(
                session, repository, actor, content.id, request.group_id
            )
            repository.audit(
                action="content.revision.created",
                resource_type="content_revision",
                resource_id=revision.id,
                after={"content_id": content.id, "payload_sha256": revision.payload_sha256},
            )
            repository.emit(
                repository.event(
                    "content", content.id, "content.revision.created", {"revisionId": revision.id}
                )
            )
            return self._content_view(content, revision, group_ids)

    async def get_content(self, actor: Actor, content_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_READ)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            content = await repository.content(content_id)
            revision = await repository.latest_revision(content.id)
            group_ids = await self._content_group_ids(session, repository.tenant_id, content.id)
            return self._content_view(content, revision, group_ids)

    async def list_content(self, actor: Actor) -> list[dict[str, Any]]:
        require_permissions(actor.roles, Permission.CONTENT_READ)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            contents = await repository.contents()
            response = []
            for content in contents:
                revision = await repository.latest_revision(content.id)
                group_ids = await self._content_group_ids(session, repository.tenant_id, content.id)
                payload = revision.payload if isinstance(revision.payload, dict) else {}
                response.append(
                    {
                        "id": content.id,
                        "title": content.title,
                        "status": content.status,
                        "kind": payload.get("kind"),
                        "draftState": payload.get("draftState"),
                        "latestRevision": revision.revision_no,
                        "groupIds": group_ids,
                        "updatedAt": revision.created_at,
                    }
                )
            return response

    async def archive_content(
        self, actor: Actor, content_id: str, request: ContentArchiveRequest
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            content = await repository.content(content_id)
            if content.status == "ARCHIVED":
                return {
                    "id": content.id,
                    "status": content.status,
                    "archivedAt": content.archived_at,
                }
            content.status = "ARCHIVED"
            content.archived_at = _now()
            repository.audit(
                action="content.archived",
                resource_type="content",
                resource_id=content.id,
                after={"status": content.status},
                metadata={"reason": request.reason},
            )
            return {"id": content.id, "status": content.status, "archivedAt": content.archived_at}

    async def dispatch_post_to_xianyu(
        self,
        actor: Actor,
        content_id: str,
        request: ContentXianyuDispatchRequest,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_READ, Permission.DEVICE_MAINTAIN)
        if self.mobile_task_service is None:
            raise ConflictError("mobile task service is not configured")
        from .mobile_schemas import MobileTaskCreate
        from .xianyu_publish import build_text_publish_task

        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            content = await repository.content(content_id)
            if content.status == "ARCHIVED":
                raise ConflictError("archived content cannot be dispatched")
            revision = await repository.latest_revision(content.id)
            payload = revision.payload if isinstance(revision.payload, dict) else {}
            if payload.get("kind") != "product":
                raise ValidationError("only product content can be dispatched to idlefish")
            body = payload.get("body")
            if not isinstance(body, str) or not body.strip():
                raise ValidationError("product body is required")
            media_ids = payload.get("mediaAssetIds") or []
            price = request.listing_price or payload.get("listingPrice")
            if not isinstance(price, str) or not price.strip():
                raise ValidationError("listing price is required")
            device = await repository.device(request.device_id)
            task_body = MobileTaskCreate.model_validate(
                build_text_publish_task(
                    device.id,
                    description=body,
                    price=price,
                    media_asset_ids=media_ids or None,
                    delivery_id=(
                        f"delivery-xianyu-{content.id}-{revision.id}" if media_ids else None
                    ),
                )
            )
            key = idempotency_key or f"post-xianyu:{content.id}:{revision.id}:{device.id}"
        task, created = await self.mobile_task_service.create_task(actor, key, task_body)
        return {
            "contentId": content.id,
            "revisionId": revision.id,
            "revisionNo": revision.revision_no,
            "deviceId": device.id,
            "mobileTask": task,
            "created": created,
            "tapsPublish": False,
        }

    async def create_content_group(
        self, actor: Actor, request: ContentGroupCreate
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            existing = await session.scalar(
                select(ContentGroupRow).where(
                    ContentGroupRow.tenant_id == repository.tenant_id,
                    ContentGroupRow.name == request.name,
                )
            )
            if existing is not None:
                raise ConflictError("content group name already exists")
            group = ContentGroupRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                name=request.name,
                description=request.description,
                created_by=str(actor.user_id),
                created_at=_now(),
            )
            repository.add(group)
            repository.audit(
                action="content.group.created",
                resource_type="content_group",
                resource_id=group.id,
                after={"name": group.name},
            )
            return self._group_view(group, [])

    async def list_content_groups(self, actor: Actor) -> list[dict[str, Any]]:
        require_permissions(actor.roles, Permission.CONTENT_READ)
        async with self.database.unit_of_work() as session:
            tenant_id = str(actor.tenant_id)
            groups = list(
                await session.scalars(
                    select(ContentGroupRow)
                    .where(ContentGroupRow.tenant_id == tenant_id)
                    .order_by(ContentGroupRow.id)
                )
            )
            memberships = list(
                await session.scalars(
                    select(ContentGroupMembershipRow).where(
                        ContentGroupMembershipRow.tenant_id == tenant_id
                    )
                )
            )
            by_group: dict[str, list[str]] = {}
            for membership in memberships:
                by_group.setdefault(membership.group_id, []).append(membership.content_id)
            return [self._group_view(group, by_group.get(group.id, [])) for group in groups]

    async def add_content_group_member(
        self,
        actor: Actor,
        group_id: str,
        request: ContentGroupMembershipCreate,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            group = await self._content_group(session, repository.tenant_id, group_id)
            content = await repository.content(request.content_id)
            existing = await session.scalar(
                select(ContentGroupMembershipRow).where(
                    ContentGroupMembershipRow.group_id == group.id,
                    ContentGroupMembershipRow.content_id == content.id,
                )
            )
            if existing is None:
                existing = ContentGroupMembershipRow(
                    id=repository.new_id(),
                    tenant_id=repository.tenant_id,
                    group_id=group.id,
                    content_id=content.id,
                    added_by=str(actor.user_id),
                    created_at=_now(),
                )
                repository.add(existing)
                repository.audit(
                    action="content.group.member_added",
                    resource_type="content_group",
                    resource_id=group.id,
                    after={"content_id": content.id},
                )
            return _row(existing, "id", "group_id", "content_id", "created_at")

    async def remove_content_group_member(
        self, actor: Actor, group_id: str, content_id: str
    ) -> None:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            await self._content_group(session, repository.tenant_id, group_id)
            membership = await session.scalar(
                select(ContentGroupMembershipRow).where(
                    ContentGroupMembershipRow.tenant_id == repository.tenant_id,
                    ContentGroupMembershipRow.group_id == group_id,
                    ContentGroupMembershipRow.content_id == content_id,
                )
            )
            if membership is None:
                raise ConflictError("content is not a member of this group")
            await session.delete(membership)
            repository.audit(
                action="content.group.member_removed",
                resource_type="content_group",
                resource_id=group_id,
                before={"content_id": content_id},
            )

    async def register_automation(
        self, actor: Actor, request: AutomationPackageCreate
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.AUTOMATION_MANAGE)
        try:
            manifest = validate_manifest(request.manifest)
            normalized_manifest = manifest.model_dump(mode="json", by_alias=True)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        public_key = self.settings.automation_signing_public_keys.get(
            manifest.spec.signature.key_id
        )
        if public_key is None:
            raise ValidationError("automation package uses an untrusted signing key")
        try:
            signature_digest = verify_package_signature(
                public_key_base64=public_key,
                signature_base64=request.signature,
                payload=package_signature_payload(
                    artifact_sha256=request.artifact_sha256,
                    manifest=normalized_manifest,
                    sbom_ref=request.sbom_ref,
                    sbom_sha256=request.sbom_sha256,
                ),
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            row = AutomationVersionRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                name=manifest.metadata.name,
                version=manifest.metadata.version,
                artifact_sha256=request.artifact_sha256,
                manifest=normalized_manifest,
                signature_key_id=manifest.spec.signature.key_id,
                signature_digest=signature_digest,
                sbom_ref=request.sbom_ref,
                sbom_sha256=request.sbom_sha256,
                rollout_percentage=0,
                rollout_evidence=[],
                production_qualified=False,
                created_at=_now(),
            )
            repository.add(row)
            repository.audit(
                action="automation.version.registered",
                resource_type="automation_package_version",
                resource_id=row.id,
                after={
                    "name": row.name,
                    "version": row.version,
                    "sha256": row.artifact_sha256,
                    "signature_key_id": row.signature_key_id,
                    "signature_digest": row.signature_digest,
                    "sbom_sha256": row.sbom_sha256,
                    "rollout_percentage": 0,
                },
            )
            repository.emit(
                repository.event(
                    "automation_package_version",
                    row.id,
                    "automation.package.registered",
                    {
                        "versionId": row.id,
                        "qualified": False,
                        "rolloutPercentage": 0,
                    },
                )
            )
            return self._automation_view(row)

    async def promote_automation(
        self,
        actor: Actor,
        version_id: str,
        request: AutomationPromotionRequest,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.AUTOMATION_MANAGE)
        try:
            evidence = RolloutEvidence(
                sample_size=request.evidence.sample_size,
                success_count=request.evidence.success_count,
                failure_count=request.evidence.failure_count,
                safety_violations=request.evidence.safety_violations,
                p95_duration_ms=request.evidence.p95_duration_ms,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            row = await repository.automation_version(version_id)
            if self._is_local_recipe(row):
                raise ValidationError(
                    "recipe packages cannot use automation promotion; publish to devices instead"
                )
            try:
                decision = evaluate_rollout_promotion(
                    current_percentage=row.rollout_percentage,
                    target_percentage=request.target_percentage,
                    evidence=evidence,
                    max_failure_rate=self.settings.automation_rollout_max_failure_rate,
                )
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            before = {
                "rollout_percentage": row.rollout_percentage,
                "production_qualified": row.production_qualified,
            }
            row.rollout_percentage = request.target_percentage
            row.rollout_evidence = [*row.rollout_evidence, decision]
            row.production_qualified = bool(decision["productionQualified"])
            repository.audit(
                action="automation.version.promoted",
                resource_type="automation_package_version",
                resource_id=row.id,
                before=before,
                after=decision,
            )
            repository.emit(
                repository.event(
                    "automation_package_version",
                    row.id,
                    "automation.package.promoted",
                    {
                        "versionId": row.id,
                        "rolloutPercentage": row.rollout_percentage,
                        "qualified": row.production_qualified,
                    },
                )
            )
            return self._automation_view(row)

    async def register_recipe(self, actor: Actor, package: dict[str, Any]) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.RECIPE_PUBLISH)
        if not isinstance(package, dict):
            raise ValidationError("recipe package must be an object")
        signature = package.get("signature") if isinstance(package.get("signature"), dict) else {}
        key_id = signature.get("keyId")
        digest = signature.get("digest")
        if not isinstance(key_id, str) or not key_id:
            raise ValidationError("recipe package uses an untrusted signing key")
        if digest == "hash-pinned-builtin":
            raise ValidationError("builtin hash-pin is not a published catalog signature")
        public_key = self.settings.automation_signing_public_keys.get(key_id)
        if public_key is None:
            raise ValidationError("recipe package uses an untrusted signing key")
        try:
            parsed = validate_recipe_package(package, public_key_base64=public_key)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        payload_digest = verify_package_signature(
            public_key_base64=public_key,
            signature_base64=parsed.signature.digest,
            payload=package_signature_payload(
                artifact_sha256=parsed.manifest.hash,
                manifest=package["manifest"],
                sbom_ref="recipe://local",
                sbom_sha256=parsed.manifest.hash,
            ),
        )
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            existing = await session.scalar(
                select(AutomationVersionRow).where(
                    AutomationVersionRow.tenant_id == repository.tenant_id,
                    AutomationVersionRow.name == parsed.manifest.id,
                    AutomationVersionRow.version == parsed.manifest.version,
                )
            )
            if existing is not None:
                if existing.artifact_sha256 != parsed.manifest.hash:
                    raise ConflictError("recipe name/version already registered with a different hash")
                return self._recipe_view(existing)
            row = AutomationVersionRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                name=parsed.manifest.id,
                version=parsed.manifest.version,
                artifact_sha256=parsed.manifest.hash,
                manifest=package,
                signature_key_id=parsed.signature.key_id,
                signature_digest=payload_digest,
                sbom_ref="recipe://local",
                sbom_sha256=parsed.manifest.hash,
                rollout_percentage=0,
                rollout_evidence=[],
                production_qualified=False,
                created_at=_now(),
            )
            repository.add(row)
            repository.audit(
                action="recipe.version.registered",
                resource_type="automation_package_version",
                resource_id=row.id,
                after={
                    "name": row.name,
                    "version": row.version,
                    "sha256": row.artifact_sha256,
                    "signature_key_id": row.signature_key_id,
                    "command_types": parsed.manifest.command_types,
                },
            )
            repository.emit(
                repository.event(
                    "automation_package_version",
                    row.id,
                    "recipe.package.registered",
                    {"versionId": row.id, "sha256": row.artifact_sha256},
                )
            )
            return self._recipe_view(row)

    async def list_recipes(self, actor: Actor) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.RECIPE_PUBLISH)
        async with self.database.unit_of_work() as session:
            tenant_id = str(actor.tenant_id)
            rows = list(
                await session.scalars(
                    select(AutomationVersionRow)
                    .where(AutomationVersionRow.tenant_id == tenant_id)
                    .order_by(
                        AutomationVersionRow.created_at.desc(), AutomationVersionRow.id.desc()
                    )
                )
            )
            deployments = list(
                await session.scalars(
                    select(RecipeDeploymentRow)
                    .where(RecipeDeploymentRow.tenant_id == tenant_id)
                    .order_by(RecipeDeploymentRow.created_at, RecipeDeploymentRow.id)
                )
            )
            return {
                "items": [
                    self._recipe_view(
                        row, [item for item in deployments if item.version_id == row.id]
                    )
                    for row in rows
                    if self._is_local_recipe(row)
                ]
            }

    async def publish_recipe(
        self, actor: Actor, version_id: str, request: RecipePublishRequest
    ) -> dict[str, Any]:
        return await self._change_recipe(actor, version_id, request, "publish")

    async def revoke_recipe(
        self, actor: Actor, version_id: str, request: RecipePublishRequest
    ) -> dict[str, Any]:
        return await self._change_recipe(actor, version_id, request, "revoke")

    async def rollback_recipe(
        self, actor: Actor, version_id: str, request: RecipeRollbackRequest
    ) -> dict[str, Any]:
        return await self._change_recipe(actor, version_id, request, "rollback")

    async def _change_recipe(
        self, actor: Actor, version_id: str, request: RecipePublishRequest, action: str
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.RECIPE_PUBLISH)
        device_ids = sorted(set(request.target_device_ids))
        expected = (
            request.expected_current_version_id
            if isinstance(request, RecipeRollbackRequest)
            else None
        )
        fingerprint = canonical_hash(
            {
                "action": action,
                "versionId": version_id,
                "deviceIds": device_ids,
                "expected": expected,
            }
        )
        try:
            async with self.database.unit_of_work() as session:
                repository = ControlRepository(session, actor)
                row = await repository.automation_version(version_id)
                if not self._is_local_recipe(row):
                    raise ValidationError(
                        "automation packages cannot be deployed as device recipes"
                    )
                # Sorted device locks serialize both mapping changes and first claim, and
                # give overlapping multi-device requests a consistent lock order.
                for device_id in device_ids:
                    await repository.device(device_id, for_update=True)
                key = (repository.tenant_id, request.idempotency_key)
                replay = await session.get(RecipeDeploymentActionRow, key)
                if replay is not None:
                    if replay.request_sha256 != fingerprint:
                        raise ConflictError(
                            "idempotency key already used for a different recipe action"
                        )
                    return replay.response
                legacy = await session.scalar(
                    select(RecipeDeploymentRow).where(
                        RecipeDeploymentRow.tenant_id == repository.tenant_id,
                        RecipeDeploymentRow.idempotency_key == request.idempotency_key,
                    )
                )
                if legacy is not None:
                    raise ConflictError("idempotency key belongs to a historical deployment")
                if action != "revoke":
                    # Re-check trust and engine requirements at activation, including rollback.
                    public_key = self.settings.automation_signing_public_keys.get(
                        row.signature_key_id
                    )
                    if public_key is None:
                        raise ValidationError("recipe package uses an untrusted signing key")
                    try:
                        validate_recipe_package(row.manifest, public_key_base64=public_key)
                    except ValueError as exc:
                        raise ValidationError(str(exc)) from exc
                command_types = sorted(set(row.manifest["manifest"]["commandTypes"]))
                changes = []
                for device_id in device_ids:
                    for command_type in command_types:
                        current = await session.scalar(
                            select(RecipeDeploymentRow).where(
                                RecipeDeploymentRow.tenant_id == repository.tenant_id,
                                RecipeDeploymentRow.device_id == device_id,
                                RecipeDeploymentRow.command_type == command_type,
                                RecipeDeploymentRow.status == "PUBLISHED",
                            )
                        )
                        if action == "rollback":
                            if current is None or current.version_id != expected:
                                raise ConflictError("expected current recipe version is stale")
                            if version_id == expected:
                                raise ConflictError(
                                    "rollback target must differ from current version"
                                )
                            history = await session.scalar(
                                select(RecipeDeploymentRow).where(
                                    RecipeDeploymentRow.tenant_id == repository.tenant_id,
                                    RecipeDeploymentRow.device_id == device_id,
                                    RecipeDeploymentRow.command_type == command_type,
                                    RecipeDeploymentRow.version_id == version_id,
                                    RecipeDeploymentRow.status == "REVOKED",
                                )
                            )
                            if history is None:
                                raise ConflictError(
                                    "rollback target has no deployment history for device command"
                                )
                        changes.append((device_id, command_type, current))
                now = _now()
                deployments = []
                before = []
                for device_id, command_type, current in changes:
                    before.append(
                        {
                            "deviceId": device_id,
                            "commandType": command_type,
                            "versionId": current.version_id if current else None,
                        }
                    )
                    if action == "revoke":
                        if current is not None and current.version_id == version_id:
                            current.status = "REVOKED"
                            current.updated_at = now
                            deployments.append(current)
                        continue
                    if current is not None and current.version_id == version_id:
                        deployments.append(current)
                        continue
                    if current is not None:
                        current.status = "REVOKED"
                        current.updated_at = now
                        # Retire before INSERT to satisfy the partial unique index.
                        await session.flush()
                    deployment = RecipeDeploymentRow(
                        id=repository.new_id(),
                        tenant_id=repository.tenant_id,
                        version_id=version_id,
                        device_id=device_id,
                        command_type=command_type,
                        status="PUBLISHED",
                        idempotency_key=request.idempotency_key,
                        previous_version_id=current.version_id if current else None,
                        published_by=str(actor.user_id),
                        created_at=now,
                        updated_at=now,
                    )
                    repository.add(deployment)
                    deployments.append(deployment)
                response = self._recipe_view(row, deployments)
                session.add(
                    RecipeDeploymentActionRow(
                        tenant_id=repository.tenant_id,
                        idempotency_key=request.idempotency_key,
                        request_sha256=fingerprint,
                        action=action,
                        version_id=version_id,
                        actor_id=str(actor.user_id),
                        response=response,
                        created_at=now,
                    )
                )
                repository.audit(
                    action={
                        "publish": "recipe.version.published",
                        "revoke": "recipe.version.revoked",
                        "rollback": "recipe.version.rolled_back",
                    }[action],
                    resource_type="automation_package_version",
                    resource_id=row.id,
                    before={"deployments": before},
                    after={
                        "device_ids": device_ids,
                        "idempotency_key": request.idempotency_key,
                        "expected_current_version_id": expected,
                        "version_id": version_id,
                        "deployments": response["deployments"],
                    },
                    metadata={
                        "device_ids": device_ids,
                        "idempotency_key": request.idempotency_key,
                        "expected_current_version_id": expected,
                        "version_id": version_id,
                    },
                )
                return response
        except IntegrityError as exc:
            # Disjoint device requests can still race on a tenant-wide action key.
            async with self.database.unit_of_work() as session:
                replay = await session.get(
                    RecipeDeploymentActionRow, (str(actor.tenant_id), request.idempotency_key)
                )
                if replay is not None and replay.request_sha256 == fingerprint:
                    return replay.response
            raise ConflictError("concurrent recipe deployment changed; refresh and retry") from exc

    async def get_recipe(self, actor: Actor, version_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.RECIPE_PUBLISH)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            row = await repository.automation_version(version_id)
            if not self._is_local_recipe(row):
                raise NotFoundError("recipe package version was not found")
            deployments = list(
                await session.scalars(
                    select(RecipeDeploymentRow).where(
                        RecipeDeploymentRow.tenant_id == repository.tenant_id,
                        RecipeDeploymentRow.version_id == row.id,
                    )
                )
            )
            return self._recipe_view(row, deployments)

    async def register_apk(self, actor: Actor, request: ApkArtifactCreate) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.APK_MANAGE)
        report = request.analysis_report.model_dump(mode="json", by_alias=True)
        public_key = self.settings.apk_analysis_public_keys.get(request.analysis_report.key_id)
        if public_key is None:
            raise ValidationError("APK report uses an untrusted analysis key")
        expected = {
            "artifactSha256": request.sha256,
            "packageName": request.package_name,
            "versionName": request.version_name,
            "versionCode": request.version_code,
            "signatureDigest": request.signature_digest,
            "minSdk": request.min_sdk,
            "targetSdk": request.target_sdk,
            "abis": request.abis,
            "permissions": request.permissions,
            "sbomSha256": request.sbom_sha256,
        }
        try:
            analysis_signature_digest = verify_analysis_signature(
                public_key_base64=public_key,
                signature_base64=request.analysis_signature,
                report=report,
            )
            policy_decision = evaluate_apk_policy(
                expected=expected,
                report=report,
                source_ref=request.source_ref,
                sbom_ref=request.sbom_ref,
                now=_now(),
                denied_permissions=frozenset(self.settings.apk_denied_permissions),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(str(exc)) from exc
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            row = ApkArtifactRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                sha256=request.sha256.lower(),
                package_name=request.package_name,
                version_name=request.version_name,
                version_code=request.version_code,
                signature_digest=request.signature_digest,
                min_sdk=request.min_sdk,
                target_sdk=request.target_sdk,
                abis=request.abis,
                permissions=request.permissions,
                sbom_ref=request.sbom_ref,
                sbom_sha256=request.sbom_sha256,
                scan_status="CLEAN",
                source_ref=request.source_ref,
                analysis_key_id=request.analysis_report.key_id,
                analysis_signature_digest=analysis_signature_digest,
                analysis_report=report,
                policy_decision=policy_decision,
                created_at=_now(),
            )
            repository.add(row)
            repository.audit(
                action="apk.artifact.registered",
                resource_type="apk_artifact",
                resource_id=row.id,
                after={
                    "package_name": row.package_name,
                    "version_code": row.version_code,
                    "signature_digest": row.signature_digest,
                    "sha256": row.sha256,
                    "sbom_sha256": row.sbom_sha256,
                    "analysis_key_id": row.analysis_key_id,
                    "analysis_signature_digest": row.analysis_signature_digest,
                    "policy_decision": row.policy_decision,
                },
            )
            repository.emit(
                repository.event(
                    "apk_artifact",
                    row.id,
                    "apk.artifact.admitted",
                    {
                        "artifactId": row.id,
                        "sha256": row.sha256,
                        "scanStatus": row.scan_status,
                    },
                )
            )
            return self._apk_view(row)

    async def create_plan(
        self, actor: Actor, idempotency_key: str, request: PublishPlanCreate
    ) -> tuple[dict[str, Any], bool]:
        require_permissions(actor.roles, Permission.PUBLISH_CREATE)
        if not idempotency_key or len(idempotency_key) > 128:
            raise ValidationError("a valid Idempotency-Key header is required")
        request_sha256 = canonical_hash(request.model_dump(mode="json", by_alias=True))
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            existing = await repository.plan_by_idempotency(idempotency_key)
            if existing is not None:
                if existing.request_sha256 != request_sha256:
                    raise ConflictError("Idempotency-Key was already used for a different request")
                return self._plan_view(existing), False
            await repository.content_revision(request.content_revision_id)
            if request.product_id is not None:
                product = await session.scalar(
                    select(ProductRow).where(
                        ProductRow.id == request.product_id,
                        ProductRow.tenant_id == repository.tenant_id,
                    )
                )
                if product is None:
                    raise NotFoundError("product was not found")
                if product.status != "ACTIVE":
                    raise ConflictError("archived product cannot receive a publish plan")
            automation = await repository.automation_version(request.automation_package_version_id)
            if not automation.production_qualified:
                raise ValidationError("automation package version is not production qualified")
            await self._validate_publish_targets(
                session, repository.tenant_id, request.platform, request.targets
            )
            plan = PublishPlanRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                idempotency_key=idempotency_key,
                request_sha256=request_sha256,
                creator_id=str(actor.user_id),
                content_revision_id=request.content_revision_id,
                product_id=request.product_id,
                automation_package_version_id=request.automation_package_version_id,
                platform=request.platform,
                schedule=request.schedule,
                execution=request.execution,
                approval_policy=request.approval_policy,
                targets=request.targets,
                state=PublishState.DRAFT.value,
                cancel_requested=False,
                workflow_id=None,
                version=0,
                created_at=_now(),
            )
            repository.add(plan)
            repository.audit(
                action="publish.plan.created",
                resource_type="publish_plan",
                resource_id=plan.id,
                after=self._plan_view(plan),
            )
            repository.emit(
                repository.event(
                    "publish_plan", plan.id, "publish.plan.created", {"planId": plan.id}
                )
            )
            return self._plan_view(plan), True

    async def submit_plan(self, actor: Actor, plan_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.PUBLISH_CREATE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            plan = await repository.plan(plan_id, for_update=True)
            if plan.product_id is not None:
                product = await session.scalar(
                    select(ProductRow).where(
                        ProductRow.id == plan.product_id,
                        ProductRow.tenant_id == repository.tenant_id,
                    )
                )
                if product is None or product.status != "ACTIVE":
                    raise ConflictError("publish plan references an archived product")
            existing_snapshot = await repository.snapshot_for_plan(plan.id)
            if existing_snapshot is not None:
                return self._submitted_view(
                    plan, existing_snapshot, await repository.targets_for_plan(plan.id)
                )
            if PublishState(plan.state) is not PublishState.DRAFT:
                raise ConflictError("only a DRAFT plan can be submitted")
            revision = await repository.content_revision(plan.content_revision_id)
            automation = await repository.automation_version(plan.automation_package_version_id)
            snapshot_payload = {
                "platform": plan.platform,
                "contentRevision": {
                    "id": revision.id,
                    "payload": revision.payload,
                    "sha256": revision.payload_sha256,
                },
                "automationPackage": {
                    "id": automation.id,
                    "name": automation.name,
                    "version": automation.version,
                    "sha256": automation.artifact_sha256,
                },
                "schedule": plan.schedule,
                "execution": plan.execution,
                "targets": plan.targets,
                "approvalPolicy": plan.approval_policy,
            }
            snapshot = PublishSnapshotRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                plan_id=plan.id,
                content_revision_id=revision.id,
                automation_package_version_id=automation.id,
                payload=snapshot_payload,
                payload_sha256=canonical_hash(snapshot_payload),
                created_at=_now(),
            )
            repository.add(snapshot)
            target_state = (
                PublishState.AWAITING_APPROVAL
                if plan.approval_policy != "NONE"
                else PublishState.SCHEDULED
            )
            assert_publish_transition(PublishState.DRAFT, target_state)
            plan.state = target_state.value
            plan.workflow_id = f"publish-plan/{plan.id}"
            plan.version += 1
            targets: list[PublishTargetRow] = []
            for target_payload in plan.targets:
                account_id = target_payload.get("accountId")
                if not isinstance(account_id, str) or not account_id:
                    raise ValidationError("every target requires accountId")
                device_id = target_payload.get("deviceId")
                frozen_binding_version = None
                if isinstance(device_id, str) and device_id:
                    live_binding = await session.scalar(
                        select(AccountDeviceBindingRow).where(
                            AccountDeviceBindingRow.tenant_id == repository.tenant_id,
                            AccountDeviceBindingRow.account_id == account_id,
                            AccountDeviceBindingRow.device_id == device_id,
                            AccountDeviceBindingRow.status == "BOUND",
                        )
                    )
                    if live_binding is None:
                        raise ConflictError(
                            "publish target account is not bound to the selected device"
                        )
                    frozen_binding_version = live_binding.binding_version
                target = PublishTargetRow(
                    id=repository.new_id(),
                    tenant_id=repository.tenant_id,
                    plan_id=plan.id,
                    snapshot_id=snapshot.id,
                    account_id=account_id,
                    device_id=device_id if isinstance(device_id, str) else None,
                    binding_version=frozen_binding_version,
                    device_id_at_execution=None,
                    state=target_state.value,
                    result_detail=None,
                    cancel_requested=False,
                    created_at=_now(),
                )
                repository.add(target)
                targets.append(target)
            repository.audit(
                action="publish.plan.submitted",
                resource_type="publish_plan",
                resource_id=plan.id,
                after={"snapshot_sha256": snapshot.payload_sha256, "state": plan.state},
                workflow_id=plan.workflow_id,
            )
            repository.emit(
                repository.event(
                    "publish_plan",
                    plan.id,
                    "publish.plan.submitted",
                    {
                        "planId": plan.id,
                        "workflowId": plan.workflow_id,
                        "snapshotId": snapshot.id,
                        "requiresApproval": plan.approval_policy != "NONE",
                    },
                )
            )
            return self._submitted_view(plan, snapshot, targets)

    async def decide_approval(
        self, actor: Actor, plan_id: str, request: ApprovalRequest
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.PUBLISH_APPROVE)
        if not actor.mfa:
            raise ForbiddenError("MFA is required for publish approval")
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            plan = await repository.plan(plan_id, for_update=True)
            if plan.creator_id == str(actor.user_id):
                raise ForbiddenError("creator cannot approve their own publish plan")
            if PublishState(plan.state) is not PublishState.AWAITING_APPROVAL:
                raise ConflictError("plan is not awaiting approval")
            approval = ApprovalRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                plan_id=plan.id,
                creator_id=plan.creator_id,
                approver_id=str(actor.user_id),
                decision=request.decision,
                reason=request.reason,
                created_at=_now(),
            )
            repository.add(approval)
            requested_state = (
                PublishState.SCHEDULED if request.decision == "APPROVED" else PublishState.FAILED
            )
            assert_publish_transition(PublishState.AWAITING_APPROVAL, requested_state)
            plan.state = requested_state.value
            plan.version += 1
            for target in await repository.targets_for_plan(plan.id):
                target.state = requested_state.value
                if requested_state is PublishState.FAILED:
                    target.result_detail = "approval rejected"
            repository.audit(
                action="publish.approval.decided",
                resource_type="publish_plan",
                resource_id=plan.id,
                after={"decision": request.decision, "state": plan.state},
                metadata={"reason": request.reason} if request.reason else {},
                workflow_id=plan.workflow_id,
            )
            repository.emit(
                repository.event(
                    "publish_plan",
                    plan.id,
                    "publish.plan.approval_decided",
                    {"planId": plan.id, "decision": request.decision, "state": plan.state},
                )
            )
            return self._plan_view(plan)

    async def cancel_plan(self, actor: Actor, plan_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.PUBLISH_CREATE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            plan = await repository.plan(plan_id, for_update=True)
            current = PublishState(plan.state)
            targets = await repository.targets_for_plan(plan.id)
            unsafe_states = {
                PublishState.COMMITTING,
                PublishState.RECONCILING,
                PublishState.SUCCEEDED,
                PublishState.UNKNOWN,
            }
            has_unsafe_target = any(
                PublishState(target.state) in unsafe_states for target in targets
            )
            plan.cancel_requested = True
            plan.version += 1
            if not has_unsafe_target:
                assert_safe_cancel(current)
                plan.state = PublishState.CANCELED.value
            for target in targets:
                if PublishState(target.state) not in unsafe_states | {PublishState.FAILED}:
                    target.cancel_requested = True
                    target.state = PublishState.CANCELED.value
            repository.audit(
                action="publish.plan.cancel_requested",
                resource_type="publish_plan",
                resource_id=plan.id,
                after={
                    "state": plan.state,
                    "cancel_requested": True,
                    "deferred": has_unsafe_target,
                },
                workflow_id=plan.workflow_id,
            )
            repository.emit(
                repository.event(
                    "publish_plan",
                    plan.id,
                    "publish.plan.cancel_requested",
                    {"planId": plan.id, "deferred": has_unsafe_target},
                )
            )
            return self._plan_view(plan)

    async def get_plan(self, actor: Actor, plan_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.PUBLISH_READ)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            plan = await repository.plan(plan_id)
            snapshot = await repository.snapshot_for_plan(plan.id)
            targets = await repository.targets_for_plan(plan.id)
            result = self._plan_view(plan)
            result["snapshot"] = self._snapshot_view(snapshot) if snapshot else None
            result["publishTargets"] = [self._target_view(target) for target in targets]
            return result

    async def acquire_lease(
        self, actor: Actor, device_id: str, owner_workflow_id: str, ttl_seconds: int
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            device = await repository.device(device_id, for_update=True)
            if device.maintenance:
                raise ConflictError("device is in maintenance mode")
            existing = await repository.lease_for_device(device.id)
            now = _now()
            if (
                existing is not None
                and existing.canceled_at is None
                and _aware(existing.expires_at) > now
                and existing.owner_workflow_id != owner_workflow_id
            ):
                raise ConflictError("device is leased by another workflow")
            if (
                existing is not None
                and existing.canceled_at is None
                and _aware(existing.expires_at) > now
                and existing.owner_workflow_id == owner_workflow_id
            ):
                return self._lease_view(existing)
            device.fencing_counter += 1
            if existing is not None:
                await session.execute(
                    delete(DeviceLeaseRow).where(DeviceLeaseRow.device_id == device.id)
                )
                await session.flush()
            lease = DeviceLeaseRow(
                device_id=device.id,
                tenant_id=repository.tenant_id,
                lease_id=repository.new_id(),
                owner_workflow_id=owner_workflow_id,
                fencing_token=device.fencing_counter,
                expires_at=now + timedelta(seconds=ttl_seconds),
                canceled_at=None,
                created_at=now,
            )
            repository.add(lease)
            repository.audit(
                action="device.lease.acquired",
                resource_type="device_lease",
                resource_id=lease.lease_id,
                after={
                    "device_id": device.id,
                    "fencing_token": lease.fencing_token,
                    "expires_at": lease.expires_at,
                },
                workflow_id=owner_workflow_id,
                device_id=device.id,
                edge_id=device.edge_id,
            )
            return self._lease_view(lease)

    async def release_lease(self, actor: Actor, device_id: str, lease_id: str) -> None:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            device = await repository.device(device_id)
            lease = await repository.lease_for_device(device_id)
            if lease is None or lease.lease_id != lease_id:
                raise ConflictError("lease does not match the active device lease")
            lease.canceled_at = _now()
            repository.audit(
                action="device.lease.released",
                resource_type="device_lease",
                resource_id=lease.lease_id,
                device_id=device.id,
                edge_id=device.edge_id,
                workflow_id=lease.owner_workflow_id,
            )

    async def create_commit_intent(
        self,
        actor: Actor,
        target_id: str,
        fencing_token: int,
        before_commit_evidence_id: str,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.PUBLISH_CREATE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            target = await repository.target(target_id, for_update=True)
            existing = await repository.intent_for_target(target.id)
            if existing is not None:
                if (
                    existing.fencing_token != fencing_token
                    or existing.before_commit_evidence_id != before_commit_evidence_id
                ):
                    raise ConflictError(
                        "commit intent already exists with different immutable input"
                    )
                return self._intent_view(existing)
            if target.device_id is None:
                raise ConflictError("publish target has no assigned device")
            lease = await repository.lease_for_device(target.device_id)
            if (
                lease is None
                or lease.canceled_at is not None
                or _aware(lease.expires_at) <= _now()
                or lease.fencing_token != fencing_token
            ):
                raise ConflictError("active fencing lease does not match commit intent")
            current = PublishState(target.state)
            if current not in {PublishState.RUNNING, PublishState.WAITING_CONFIRMATION}:
                raise ConflictError(f"cannot create commit intent while target is {current}")
            assert_publish_transition(current, PublishState.COMMITTING)
            from .db import CommitIntentRow

            intent = CommitIntentRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                target_id=target.id,
                attempt_no=1,
                fencing_token=fencing_token,
                before_commit_evidence_id=before_commit_evidence_id,
                created_at=_now(),
            )
            repository.add(intent)
            target.state = PublishState.COMMITTING.value
            repository.audit(
                action="publish.commit_intent.created",
                resource_type="commit_intent",
                resource_id=intent.id,
                after={
                    "target_id": target.id,
                    "fencing_token": fencing_token,
                    "attempt_no": 1,
                    "before_commit_evidence_id": before_commit_evidence_id,
                },
                device_id=target.device_id,
                workflow_id=lease.owner_workflow_id,
            )
            repository.emit(
                repository.event(
                    "publish_target",
                    target.id,
                    "publish.target.commit_intent_created",
                    {"targetId": target.id, "commitIntentId": intent.id},
                )
            )
            return self._intent_view(intent)

    async def update_target_state(
        self, actor: Actor, target_id: str, requested: PublishState, detail: str | None
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.PUBLISH_CREATE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            target = await repository.target(target_id, for_update=True)
            current = PublishState(target.state)
            if requested == current:
                return self._target_view(target)
            assert_publish_transition(current, requested)
            if current is PublishState.COMMITTING and requested is not PublishState.RECONCILING:
                raise ConflictError("COMMITTING can only advance to RECONCILING")
            target.state = requested.value
            target.result_detail = detail
            repository.audit(
                action="publish.target.state_changed",
                resource_type="publish_target",
                resource_id=target.id,
                before={"state": current.value},
                after={"state": requested.value, "detail": detail},
                device_id=target.device_id,
            )
            repository.emit(
                repository.event(
                    "publish_target",
                    target.id,
                    "publish.target.updated",
                    {"targetId": target.id, "state": requested.value, "detail": detail},
                )
            )
            return self._target_view(target)

    async def audit_events(self, actor: Actor, limit: int) -> list[dict[str, Any]]:
        require_permissions(actor.roles, Permission.AUDIT_READ)
        async with self.database.unit_of_work() as session:
            rows = await ControlRepository(session, actor).audit_events(limit)
            return [
                _row(
                    row,
                    "id",
                    "tenant_id",
                    "actor_type",
                    "actor_id",
                    "action",
                    "resource_type",
                    "resource_id",
                    "request_id",
                    "workflow_id",
                    "device_id",
                    "edge_id",
                    "before_hash",
                    "after_hash",
                    "result",
                    "metadata_json",
                    "occurred_at",
                )
                for row in rows
            ]

    async def events(
        self, actor: Actor, after_id: str | None, limit: int = 100
    ) -> list[dict[str, Any]]:
        require_permissions(actor.roles, Permission.PUBLISH_READ)
        async with self.database.unit_of_work() as session:
            rows = await ControlRepository(session, actor).events(after_id, limit)
            return [
                {
                    "id": row.id,
                    "tenantId": row.tenant_id,
                    "type": row.event_type,
                    "aggregateType": row.aggregate_type,
                    "aggregateId": row.aggregate_id,
                    "payload": row.payload,
                    "occurredAt": row.occurred_at,
                }
                for row in rows
            ]

    @staticmethod
    async def _account(
        session: AsyncSession,
        tenant_id: str,
        account_id: str,
        *,
        for_update: bool = False,
    ) -> PlatformAccountRow:
        statement = select(PlatformAccountRow).where(
            PlatformAccountRow.id == account_id,
            PlatformAccountRow.tenant_id == tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        account = await session.scalar(statement)
        if account is None:
            raise NotFoundError("platform account was not found")
        return account

    @staticmethod
    async def _content_group(
        session: AsyncSession, tenant_id: str, group_id: str
    ) -> ContentGroupRow:
        group = await session.scalar(
            select(ContentGroupRow).where(
                ContentGroupRow.id == group_id,
                ContentGroupRow.tenant_id == tenant_id,
            )
        )
        if group is None:
            raise NotFoundError("content group was not found")
        return group

    async def _validate_publish_targets(
        self,
        session: AsyncSession,
        tenant_id: str,
        platform: str,
        targets: list[dict[str, Any]],
    ) -> None:
        now = _now()
        for target in targets:
            account_id = target.get("accountId")
            device_id = target.get("deviceId")
            if not isinstance(account_id, str) or not account_id:
                raise ValidationError("every publish target requires accountId")
            account = await self._account(session, tenant_id, account_id)
            if account.platform != platform:
                raise ValidationError("publish target account platform does not match plan")
            if account.status != "AUTHORIZED":
                raise ConflictError("publish target account is not authorized")
            if account.expires_at is not None and _aware(account.expires_at) <= now:
                raise ConflictError("publish target account authorization has expired")
            if device_id is not None:
                if not isinstance(device_id, str) or not device_id:
                    raise ValidationError("deviceId must be a non-empty string")
                binding = await session.scalar(
                    select(AccountDeviceBindingRow).where(
                        AccountDeviceBindingRow.tenant_id == tenant_id,
                        AccountDeviceBindingRow.account_id == account.id,
                        AccountDeviceBindingRow.device_id == device_id,
                        AccountDeviceBindingRow.status == "BOUND",
                    )
                )
                if binding is None:
                    raise ConflictError(
                        "publish target account is not bound to the selected device"
                    )

    @staticmethod
    def _device_view(row: DeviceRow) -> dict[str, Any]:
        return _row(
            row,
            "id",
            "tenant_id",
            "edge_id",
            "logical_name",
            "android_version",
            "lamda_version",
            "target_app_versions",
            "capabilities",
            "labels",
            "state",
            "maintenance",
            "last_seen_at",
            "version",
        )

    @staticmethod
    def _account_view(
        row: PlatformAccountRow, bindings: list[AccountDeviceBindingRow]
    ) -> dict[str, Any]:
        return {
            "id": row.id,
            "tenantId": row.tenant_id,
            "platform": row.platform,
            "externalSubjectRef": row.external_subject_ref,
            "displayLabel": row.display_label,
            "secretConfigured": True,
            "authorizationBasis": row.authorization_basis,
            "status": row.status,
            "expiresAt": row.expires_at,
            "lastCheckedAt": row.last_checked_at,
            "revokedAt": row.revoked_at,
            "version": row.version,
            "bindings": [ControlService._binding_view(binding) for binding in bindings],
            "createdAt": row.created_at,
        }

    @staticmethod
    def _binding_view(row: AccountDeviceBindingRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "accountId": row.account_id,
            "deviceId": row.device_id,
            "status": row.status,
            "confirmedBy": row.confirmed_by,
            "confirmationNote": row.confirmation_note,
            "boundAt": row.bound_at,
            "unboundAt": row.unbound_at,
            "bindingVersion": row.binding_version,
            "platform": row.platform,
            "historical": row.status != "BOUND",
        }

    @staticmethod
    def _media_view(row: MediaAssetRow) -> dict[str, Any]:
        return _row(
            row,
            "id",
            "sha256",
            "object_key",
            "content_type",
            "size_bytes",
            "source_asset_id",
            "metadata_json",
            "created_at",
        )

    @staticmethod
    def _derivative_view(row: MediaDerivativeRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "sourceAssetId": row.source_asset_id,
            "profileId": row.profile_id,
            "state": row.state,
            "outputAssetId": row.output_asset_id,
            "errorCode": row.error_code,
            "detail": row.detail,
            "completedAt": row.completed_at,
            "createdAt": row.created_at,
        }

    @staticmethod
    def _product_view(
        row: ProductRow,
        media_asset_ids: list[str],
        media_items: list[Any] | None = None,
    ) -> dict[str, Any]:
        media = (
            [
                {
                    "mediaAssetId": item.media_asset_id,
                    "sortOrder": item.sort_order,
                    "role": item.role,
                }
                for item in sorted(media_items, key=lambda value: value.sort_order)
            ]
            if media_items is not None
            else [
                {"mediaAssetId": media_asset_id, "sortOrder": index}
                for index, media_asset_id in enumerate(media_asset_ids)
            ]
        )
        return {
            "id": row.id,
            "spuCode": row.spu_code,
            "title": row.title,
            "description": row.description,
            "category": row.category,
            "price": row.price,
            "stock": row.stock,
            "status": row.status,
            "revision": row.revision,
            "mediaAssetIds": media_asset_ids,
            "media": media,
            "attributes": dict(getattr(row, "attributes", None) or {}),
            "createdAt": row.created_at,
        }

    @staticmethod
    def _group_view(row: ContentGroupRow, content_ids: list[str]) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "contentIds": content_ids,
            "createdAt": row.created_at,
        }

    @staticmethod
    def _content_view(
        content: ContentItemRow,
        revision: ContentRevisionRow,
        group_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = revision.payload if isinstance(revision.payload, dict) else {}
        return {
            "id": content.id,
            "title": content.title,
            "status": content.status,
            "kind": payload.get("kind"),
            "archivedAt": content.archived_at,
            "groupIds": group_ids or [],
            "revision": _row(
                revision,
                "id",
                "revision_no",
                "payload",
                "payload_sha256",
                "created_at",
            ),
        }

    async def _assert_payload_media(
        self, session: AsyncSession, tenant_id: str, payload: dict[str, Any]
    ) -> None:
        media_ids = payload.get("mediaAssetIds") if isinstance(payload, dict) else None
        if not media_ids:
            return
        if not isinstance(media_ids, list):
            raise ValidationError("mediaAssetIds must be an array")
        for asset_id in media_ids:
            asset = await session.get(MediaAssetRow, asset_id)
            if asset is None or asset.tenant_id != tenant_id:
                raise ValidationError("mediaAssetIds must reference tenant media assets")

    async def _content_group_ids(
        self, session: AsyncSession, tenant_id: str, content_id: str
    ) -> list[str]:
        return list(
            await session.scalars(
                select(ContentGroupMembershipRow.group_id).where(
                    ContentGroupMembershipRow.tenant_id == tenant_id,
                    ContentGroupMembershipRow.content_id == content_id,
                )
            )
        )

    async def _assign_content_group(
        self,
        session: AsyncSession,
        repository: ControlRepository,
        actor: Actor,
        content_id: str,
        group_id: str | None,
    ) -> list[str]:
        if group_id:
            group = await self._content_group(session, repository.tenant_id, group_id)
            existing = await session.scalar(
                select(ContentGroupMembershipRow).where(
                    ContentGroupMembershipRow.group_id == group.id,
                    ContentGroupMembershipRow.content_id == content_id,
                )
            )
            if existing is None:
                repository.add(
                    ContentGroupMembershipRow(
                        id=repository.new_id(),
                        tenant_id=repository.tenant_id,
                        group_id=group.id,
                        content_id=content_id,
                        added_by=str(actor.user_id),
                        created_at=_now(),
                    )
                )
                repository.audit(
                    action="content.group.member_added",
                    resource_type="content_group",
                    resource_id=group.id,
                    after={"content_id": content_id},
                )
            other_memberships = list(
                await session.scalars(
                    select(ContentGroupMembershipRow).where(
                        ContentGroupMembershipRow.tenant_id == repository.tenant_id,
                        ContentGroupMembershipRow.content_id == content_id,
                        ContentGroupMembershipRow.group_id != group.id,
                    )
                )
            )
            for membership in other_memberships:
                await session.delete(membership)
        return await self._content_group_ids(session, repository.tenant_id, content_id)

    @staticmethod
    def _is_local_recipe(row: AutomationVersionRow) -> bool:
        manifest = row.manifest if isinstance(row.manifest, dict) else {}
        return manifest.get("kind") == "LocalRecipePackage" or row.sbom_ref == "recipe://local"

    @staticmethod
    def _automation_view(row: AutomationVersionRow) -> dict[str, Any]:
        return _row(
            row,
            "id",
            "name",
            "version",
            "artifact_sha256",
            "manifest",
            "signature_key_id",
            "signature_digest",
            "sbom_ref",
            "sbom_sha256",
            "rollout_percentage",
            "rollout_evidence",
            "production_qualified",
        )

    @staticmethod
    def _recipe_view(
        row: AutomationVersionRow, deployments: list[RecipeDeploymentRow] | None = None
    ) -> dict[str, Any]:
        return {
            "id": row.id,
            "versionId": row.id,
            "name": row.name,
            "version": row.version,
            "artifactSha256": row.artifact_sha256,
            "signingKeyId": row.signature_key_id,
            "createdAt": _aware(row.created_at).isoformat(),
            "package": row.manifest,
            "deployments": [
                {
                    "id": item.id,
                    "deviceId": item.device_id,
                    "commandType": item.command_type,
                    "status": item.status,
                    "previousVersionId": item.previous_version_id,
                    "idempotencyKey": item.idempotency_key,
                    "publishedBy": item.published_by,
                    "createdAt": _aware(item.created_at).isoformat(),
                    "updatedAt": _aware(item.updated_at).isoformat(),
                }
                for item in sorted(
                    deployments or [],
                    key=lambda item: (
                        _aware(item.created_at),
                        item.device_id,
                        item.command_type,
                        item.id,
                    ),
                )
            ],
        }

    @staticmethod
    def _apk_view(row: ApkArtifactRow) -> dict[str, Any]:
        return _row(
            row,
            "id",
            "sha256",
            "package_name",
            "version_name",
            "version_code",
            "signature_digest",
            "min_sdk",
            "target_sdk",
            "abis",
            "permissions",
            "sbom_ref",
            "sbom_sha256",
            "scan_status",
            "source_ref",
            "analysis_key_id",
            "analysis_signature_digest",
            "analysis_report",
            "policy_decision",
        )

    @staticmethod
    def _plan_view(row: PublishPlanRow) -> dict[str, Any]:
        return _row(
            row,
            "id",
            "tenant_id",
            "creator_id",
            "request_sha256",
            "content_revision_id",
            "product_id",
            "automation_package_version_id",
            "platform",
            "schedule",
            "execution",
            "approval_policy",
            "targets",
            "state",
            "cancel_requested",
            "workflow_id",
            "version",
            "created_at",
        )

    @staticmethod
    def _snapshot_view(row: PublishSnapshotRow) -> dict[str, Any]:
        return _row(
            row,
            "id",
            "plan_id",
            "content_revision_id",
            "automation_package_version_id",
            "payload",
            "payload_sha256",
            "created_at",
        )

    @staticmethod
    def _target_view(row: PublishTargetRow) -> dict[str, Any]:
        return _row(
            row,
            "id",
            "plan_id",
            "snapshot_id",
            "account_id",
            "device_id",
            "binding_version",
            "device_id_at_execution",
            "state",
            "result_detail",
            "cancel_requested",
            "created_at",
        )

    @classmethod
    def _submitted_view(
        cls,
        plan: PublishPlanRow,
        snapshot: PublishSnapshotRow,
        targets: list[PublishTargetRow],
    ) -> dict[str, Any]:
        response = cls._plan_view(plan)
        response["snapshot"] = cls._snapshot_view(snapshot)
        response["publishTargets"] = [cls._target_view(target) for target in targets]
        return response

    @staticmethod
    def _lease_view(row: DeviceLeaseRow) -> dict[str, Any]:
        return _row(
            row,
            "device_id",
            "lease_id",
            "owner_workflow_id",
            "fencing_token",
            "expires_at",
            "canceled_at",
            "owner_type",
        )

    @staticmethod
    def _intent_view(row: Any) -> dict[str, Any]:
        return _row(
            row,
            "id",
            "target_id",
            "attempt_no",
            "fencing_token",
            "before_commit_evidence_id",
            "created_at",
        )
