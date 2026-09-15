from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from cloudctl_domain import (
    Actor,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    Permission,
    ValidationError,
    require_permissions,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .db import (
    AccountDeviceBindingRow,
    AuditEventRow,
    AutomationVersionRow,
    Database,
    DeviceLeaseRow,
    DevicePreviewRow,
    DeviceRow,
    MediaAssetRow,
    MobileBindingRow,
    MobileEnrollmentRow,
    MobileTaskEventRow,
    MobileTaskRow,
    PlatformAccountRow,
    RecipeDeploymentRow,
)
from .media_store import ObjectStore
from .mobile_schemas import DevicePreviewUpload, MobileDeviceHeartbeat, MobileTaskCreate
from .xianyu_publish import build_text_publish_task

ACTIVE_STATES = ("CLAIMED", "RUNNING")
TERMINAL_BUSINESS_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"})
COMPANION_PACKAGE = "com.company.cloudctl.companion"
XIANYU_PACKAGE = "com.taobao.idlefish"
XHS_PACKAGE = "com.xingin.xhs"
DOUYIN_PACKAGE = "com.ss.android.ugc.aweme"
ALLOWED_PACKAGES = {COMPANION_PACKAGE, XIANYU_PACKAGE, XHS_PACKAGE, DOUYIN_PACKAGE}
RUNNER_TO_BUSINESS = {
    "QUEUED": "QUEUED",
    "CLAIMED": "PREFLIGHT",
    "RUNNING": "RUNNING",
    "SUCCEEDED": "SUCCEEDED",
    "FAILED": "FAILED",
}
PREVIEW_JPEG_MAGIC = b"\xff\xd8\xff"
PREVIEW_MAX_BYTES = 400_000
PREVIEW_CAPTURE_INTERVAL_MS = 2_000


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _digest(kind: str, value: str) -> str:
    return hashlib.sha256(f"cloudctl-mobile:{kind}:{value}".encode()).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class MobileTaskService:
    def __init__(self, database: Database, object_store: ObjectStore | None = None) -> None:
        self.database = database
        self.object_store = object_store

    async def media_manifest(
        self, current: MobileBindingRow, delivery_id: str, asset_ids: list[str]
    ) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            rows = list(
                (
                    await session.execute(
                        select(MediaAssetRow).where(
                            MediaAssetRow.tenant_id == current.tenant_id,
                            MediaAssetRow.id.in_(asset_ids),
                        )
                    )
                ).scalars()
            )
        by_id = {row.id: row for row in rows}
        if len(by_id) != len(asset_ids):
            raise NotFoundError("one or more media assets were not found in tenant")
        return {
            "protocolVersion": "cloudctl.media/v1",
            "deliveryId": delivery_id,
            "items": [
                {
                    "assetId": row.id,
                    "fileName": str(row.metadata_json.get("fileName") or row.id),
                    "sha256": row.sha256,
                    "sizeBytes": row.size_bytes,
                    "contentType": row.content_type,
                    "downloadPath": f"/companion/v2/media/{row.id}",
                }
                for row in (by_id[asset_id] for asset_id in asset_ids)
            ],
        }

    async def download_media(
        self, current: MobileBindingRow, asset_id: str
    ) -> tuple[bytes, str, str]:
        if self.object_store is None:
            raise ValidationError("media object store is not configured")
        async with self.database.unit_of_work() as session:
            row = await session.get(MediaAssetRow, asset_id)
        if row is None or row.tenant_id != current.tenant_id:
            raise NotFoundError("media asset was not found in tenant")
        stored = await self.object_store.get(row.object_key)
        if stored is None:
            raise NotFoundError("media object was not found")
        digest = hashlib.sha256(stored.content).hexdigest()
        if len(stored.content) != row.size_bytes or digest != row.sha256:
            raise ValidationError("media object checksum does not match asset record")
        return stored.content, stored.content_type or row.content_type, digest

    async def list_active_recipes(self, current: MobileBindingRow) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            rows = list(
                await session.scalars(
                    select(RecipeDeploymentRow).where(
                        RecipeDeploymentRow.tenant_id == current.tenant_id,
                        RecipeDeploymentRow.device_id == current.device_id,
                        RecipeDeploymentRow.status == "PUBLISHED",
                    )
                )
            )
            packages = {}
            if rows:
                versions = list(
                    await session.scalars(
                        select(AutomationVersionRow).where(
                            AutomationVersionRow.tenant_id == current.tenant_id,
                            AutomationVersionRow.id.in_({row.version_id for row in rows}),
                        )
                    )
                )
                packages = {item.id: item for item in versions}
        items = []
        for row in rows:
            package = packages.get(row.version_id)
            if package is None:
                continue
            items.append(
                {
                    "versionId": package.id,
                    "sha256": package.artifact_sha256,
                    "commandType": row.command_type,
                    "downloadPath": f"/companion/v2/recipes/{package.id}",
                    "engineMinVersion": package.manifest.get("manifest", {}).get("minEngineVersion", 1),
                    "previousVersionId": row.previous_version_id,
                }
            )
        return {"protocolVersion": "cloudctl.recipe/v1", "items": items}

    async def download_recipe(
        self, current: MobileBindingRow, version_id: str
    ) -> tuple[bytes, str]:
        async with self.database.unit_of_work() as session:
            deployment = await session.scalar(
                select(RecipeDeploymentRow).where(
                    RecipeDeploymentRow.tenant_id == current.tenant_id,
                    RecipeDeploymentRow.device_id == current.device_id,
                    RecipeDeploymentRow.version_id == version_id,
                    RecipeDeploymentRow.status == "PUBLISHED",
                )
            )
            if deployment is None:
                pinned = await session.scalar(
                    select(MobileTaskRow.id).where(
                        MobileTaskRow.tenant_id == current.tenant_id,
                        MobileTaskRow.device_id == current.device_id,
                        MobileTaskRow.recipe_pin["versionId"].as_string() == version_id,
                        MobileTaskRow.status.not_in(
                            ("SUCCEEDED", "FAILED", "CANCELLED", "CANCELED", "EXPIRED")
                        ),
                        MobileTaskRow.business_state.not_in(
                            ("SUCCEEDED", "FAILED", "CANCELLED", "CANCELED", "EXPIRED")
                        ),
                    )
                )
                if pinned is None:
                    raise NotFoundError("recipe package was not found for this device")
            package = await session.scalar(
                select(AutomationVersionRow).where(
                    AutomationVersionRow.tenant_id == current.tenant_id,
                    AutomationVersionRow.id == version_id,
                )
            )
            if package is None or package.manifest.get("kind") != "LocalRecipePackage":
                raise NotFoundError("recipe package was not found for this device")
            payload = json.dumps(
                package.manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
            return payload, package.artifact_sha256

    @staticmethod
    async def _published_recipe_ref(
        session: Any, tenant_id: str, device_id: str, command_type: str | None
    ) -> dict[str, Any] | None:
        if not command_type:
            return None
        deployment = await session.scalar(
            select(RecipeDeploymentRow).where(
                RecipeDeploymentRow.tenant_id == tenant_id,
                RecipeDeploymentRow.device_id == device_id,
                RecipeDeploymentRow.command_type == command_type,
                RecipeDeploymentRow.status == "PUBLISHED",
            )
        )
        if deployment is None:
            return None
        package = await session.scalar(
            select(AutomationVersionRow).where(
                AutomationVersionRow.tenant_id == tenant_id,
                AutomationVersionRow.id == deployment.version_id,
            )
        )
        if package is None:
            return None
        engine = package.manifest.get("manifest", {}).get("minEngineVersion", 1)
        return {
            "versionId": package.id,
            "sha256": package.artifact_sha256,
            "engineMinVersion": engine,
        }

    async def create_direct_device(
        self,
        actor: Actor,
        logical_name: str,
        android_version: str | None,
        companion_version: str | None,
        labels: list[str],
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        now = _now()
        row = DeviceRow(
            id=str(uuid.uuid4()),
            tenant_id=str(actor.tenant_id),
            edge_id=None,
            logical_name=logical_name,
            android_version=android_version,
            lamda_version=None,
            target_app_versions={},
            capabilities={"mobileDirect": True, "companionVersion": companion_version},
            labels=labels,
            state="REGISTERED",
            maintenance=False,
            last_seen_at=None,
            version=0,
            fencing_counter=0,
            created_at=now,
        )
        try:
            async with self.database.unit_of_work() as session:
                session.add(row)
        except IntegrityError as exc:
            raise ConflictError("mobile direct device logical name already exists") from exc
        return {
            "id": row.id,
            "tenantId": row.tenant_id,
            "edgeId": None,
            "logicalName": row.logical_name,
            "androidVersion": row.android_version,
            "capabilities": row.capabilities,
            "labels": row.labels,
            "state": row.state,
            "createdAt": row.created_at,
        }

    async def create_enrollment(
        self, actor: Actor, device_id: str, ttl_seconds: int
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        code = "-".join((secrets.token_hex(3), secrets.token_hex(3))).upper()
        now = _now()
        async with self.database.unit_of_work() as session:
            device = await session.get(DeviceRow, device_id)
            if device is None or device.tenant_id != str(actor.tenant_id):
                raise NotFoundError("device was not found")
            row = MobileEnrollmentRow(
                id=str(uuid.uuid4()),
                tenant_id=str(actor.tenant_id),
                device_id=device_id,
                code_digest=_digest("enrollment", code),
                expires_at=now + timedelta(seconds=ttl_seconds),
                consumed_at=None,
                created_by=str(actor.user_id),
                created_at=now,
            )
            session.add(row)
        return {
            "enrollmentId": row.id,
            "deviceId": device_id,
            "code": code,
            "expiresAt": row.expires_at,
        }

    async def enroll(
        self, code: str, app_instance_id: str, companion_version: str
    ) -> dict[str, Any]:
        now = _now()
        token = secrets.token_urlsafe(48)
        async with self.database.unit_of_work() as session:
            row = await session.scalar(
                select(MobileEnrollmentRow)
                .where(
                    MobileEnrollmentRow.code_digest == _digest("enrollment", code.strip().upper())
                )
                .with_for_update()
            )
            if row is None or row.consumed_at is not None or _aware(row.expires_at) <= now:
                raise AuthenticationError("enrollment code is invalid, consumed, or expired")
            row.consumed_at = now
            existing = await session.scalar(
                select(MobileBindingRow)
                .where(
                    MobileBindingRow.device_id == row.device_id,
                    MobileBindingRow.app_instance_id == app_instance_id,
                )
                .with_for_update()
            )
            if existing is None:
                others = list(
                    (
                        await session.execute(
                            select(MobileBindingRow)
                            .where(
                                MobileBindingRow.device_id == row.device_id,
                                MobileBindingRow.revoked_at.is_(None),
                            )
                            .with_for_update()
                        )
                    ).scalars()
                )
                for other in others:
                    other.revoked_at = now
                binding = MobileBindingRow(
                    id=str(uuid.uuid4()),
                    tenant_id=row.tenant_id,
                    device_id=row.device_id,
                    token_digest=_digest("binding", token),
                    app_instance_id=app_instance_id,
                    companion_version=companion_version,
                    last_seen_at=now,
                    revoked_at=None,
                    created_at=now,
                )
                session.add(binding)
            else:
                siblings = list(
                    (
                        await session.execute(
                            select(MobileBindingRow)
                            .where(
                                MobileBindingRow.device_id == row.device_id,
                                MobileBindingRow.id != existing.id,
                                MobileBindingRow.revoked_at.is_(None),
                            )
                            .with_for_update()
                        )
                    ).scalars()
                )
                for sibling in siblings:
                    sibling.revoked_at = now
                existing.token_digest = _digest("binding", token)
                existing.companion_version = companion_version
                existing.last_seen_at = now
                existing.revoked_at = None
                binding = existing
            device = await session.get(DeviceRow, row.device_id, with_for_update=True)
            if device is not None:
                device.last_seen_at = now
                device.control_epoch = int(getattr(device, "control_epoch", 0) or 0) + 1
                device.active_binding_id = binding.id
                device.fencing_counter = int(device.fencing_counter or 0) + 1
        return {
            "bindingToken": token,
            "bindingId": binding.id,
            "deviceId": binding.device_id,
            "controlEpoch": getattr(device, "control_epoch", 1) if device is not None else 1,
        }

    async def authenticate(self, token: str) -> MobileBindingRow:
        if not 32 <= len(token) <= 512:
            raise AuthenticationError("invalid Companion bearer token")
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await session.scalar(
                select(MobileBindingRow).where(
                    MobileBindingRow.token_digest == _digest("binding", token),
                    MobileBindingRow.revoked_at.is_(None),
                )
            )
            if row is None:
                raise AuthenticationError("invalid or revoked Companion bearer token")
            row.last_seen_at = now
            device = await session.get(DeviceRow, row.device_id)
            if device is not None:
                device.last_seen_at = now
            return row

    async def account_status(self, binding: MobileBindingRow) -> list[dict[str, Any]]:
        """Return non-secret authorization state for accounts bound to this device."""
        async with self.database.unit_of_work() as session:
            accounts = list(
                (
                    await session.execute(
                        select(PlatformAccountRow)
                        .where(
                            PlatformAccountRow.tenant_id == binding.tenant_id,
                            PlatformAccountRow.id.in_(
                                select(AccountDeviceBindingRow.account_id).where(
                                    AccountDeviceBindingRow.tenant_id == binding.tenant_id,
                                    AccountDeviceBindingRow.device_id == binding.device_id,
                                    AccountDeviceBindingRow.status == "BOUND",
                                )
                            ),
                        )
                        .order_by(PlatformAccountRow.id)
                    )
                ).scalars()
            )
            bindings = list(
                (
                    await session.execute(
                        select(AccountDeviceBindingRow).where(
                            AccountDeviceBindingRow.tenant_id == binding.tenant_id,
                            AccountDeviceBindingRow.device_id == binding.device_id,
                            AccountDeviceBindingRow.status == "BOUND",
                        )
                    )
                ).scalars()
            )
        bound_ids = {row.account_id for row in bindings}
        now = _now()
        return [
            {
                "accountId": row.id,
                "platform": row.platform,
                "displayLabel": row.display_label,
                "status": row.status,
                "authorized": row.status == "AUTHORIZED"
                and (row.expires_at is None or _aware(row.expires_at) > now),
                "expiresAt": row.expires_at,
                "lastCheckedAt": row.last_checked_at,
                "boundToDevice": row.id in bound_ids,
                "bindingVersion": next(
                    (item.binding_version for item in bindings if item.account_id == row.id),
                    None,
                ),
            }
            for row in accounts
        ]

    async def device_heartbeat(
        self, binding: MobileBindingRow, body: MobileDeviceHeartbeat
    ) -> dict[str, Any]:
        now = _now()
        async with self.database.unit_of_work() as session:
            stored = await session.get(MobileBindingRow, binding.id, with_for_update=True)
            if stored is None or stored.revoked_at is not None:
                raise AuthenticationError("invalid or revoked Companion bearer token")
            stored.last_seen_at = now
            stored.companion_version = body.companion_version
            device = await session.get(DeviceRow, stored.device_id, with_for_update=True)
            if device is None or device.tenant_id != stored.tenant_id:
                raise NotFoundError("device was not found")
            device.last_seen_at = now
            if body.android_version:
                device.android_version = body.android_version
            capabilities = dict(device.capabilities or {})
            capabilities["mobileDirect"] = True
            capabilities["companionVersion"] = body.companion_version
            capabilities["accessibilityEnabled"] = body.accessibility_enabled
            capabilities["runnerState"] = body.runner_state
            capabilities["capabilitiesVersion"] = int(capabilities.get("capabilitiesVersion") or 0) + 1
            if body.battery_optimization_ignored is not None:
                capabilities["batteryOptimizationIgnored"] = body.battery_optimization_ignored
            if body.health is not None:
                health = body.health.model_dump(mode="json", by_alias=True)
                network = health.get("network")
                if network not in {None, "WIFI", "CELLULAR", "UNKNOWN"}:
                    health["network"] = "UNKNOWN"
                capabilities["health"] = health
                if health.get("sdkInt") is not None:
                    capabilities["sdkInt"] = health["sdkInt"]
                if health.get("model"):
                    capabilities["model"] = health["model"]
                if health.get("manufacturer"):
                    capabilities["manufacturer"] = health["manufacturer"]
                if health.get("mediaProjection"):
                    capabilities["mediaProjection"] = health["mediaProjection"]
            device.capabilities = capabilities
            preview = await session.get(DevicePreviewRow, stored.device_id)
            resume = await session.scalar(
                select(MobileTaskRow)
                .where(
                    MobileTaskRow.tenant_id == stored.tenant_id,
                    MobileTaskRow.device_id == stored.device_id,
                    MobileTaskRow.business_state == "RESUME_CHECK",
                )
                .order_by(MobileTaskRow.created_at.desc())
            )
            payload: dict[str, Any] = {
                "ok": True,
                "deviceId": device.id,
                "receivedAt": now,
                "onlineUntil": now + timedelta(seconds=90),
                "preview": self._companion_preview_grant(preview, now),
            }
            if resume is not None:
                payload["resume"] = {
                    "taskId": resume.id,
                    "leaseId": resume.lease_id,
                    "controlEpoch": ((resume.steps or [{}])[0] or {}).get("controlEpoch"),
                    "resumeCount": resume.resume_count,
                    "pageVerified": True,
                    "reason": resume.stall_reason,
                    "controlMode": resume.control_mode or "AUTO",
                    "businessState": resume.business_state,
                }
            return payload

    async def create_task(
        self, actor: Actor, key: str, body: MobileTaskCreate
    ) -> tuple[dict[str, Any], bool]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        return await self._insert_task(
            tenant_id=str(actor.tenant_id),
            requested_by=str(actor.user_id),
            key=key,
            body=body,
        )

    async def enqueue_bound_text_publish(
        self,
        binding: MobileBindingRow,
        *,
        description: str,
        price: str,
        media_asset_ids: list[str] | None = None,
        delivery_id: str | None = None,
        auto_publish: bool = True,
        key: str,
    ) -> tuple[dict[str, Any], bool]:
        body = MobileTaskCreate.model_validate(
            build_text_publish_task(
                binding.device_id,
                description=description,
                price=price,
                media_asset_ids=media_asset_ids,
                delivery_id=delivery_id,
                auto_publish=auto_publish,
            )
        )
        return await self._insert_task(
            tenant_id=binding.tenant_id,
            requested_by=binding.device_id,
            key=key,
            body=body,
        )

    async def _insert_task(
        self,
        *,
        tenant_id: str,
        requested_by: str,
        key: str,
        body: MobileTaskCreate,
    ) -> tuple[dict[str, Any], bool]:
        if body.target_package not in ALLOWED_PACKAGES:
            raise ValidationError("targetPackage must be an allowlisted application")
        if not key or len(key) > 128:
            raise ValidationError("Idempotency-Key is required and must be at most 128 characters")
        document = body.model_dump(mode="json", by_alias=True, exclude_none=True)
        # Xianyu maintenance steps (ui.tapLayout/ui.assertBadge) are accepted only
        # when they match exactly one frozen maintenance command shape.
        from .mobile_actions import uses_maintenance_step_actions, validate_maintenance_steps

        maintenance_command = None
        if uses_maintenance_step_actions(document["steps"]):
            maintenance_command = validate_maintenance_steps(
                body.target_package, document["steps"]
            )
        digest = hashlib.sha256(_canonical(document).encode()).hexdigest()
        now = _now()
        try:
            async with self.database.unit_of_work() as session:
                existing = await session.scalar(
                    select(MobileTaskRow).where(
                        MobileTaskRow.tenant_id == tenant_id,
                        MobileTaskRow.idempotency_key == key,
                    )
                )
                if existing is not None:
                    if existing.request_sha256 != digest:
                        raise ConflictError(
                            "Idempotency-Key was reused with different task content"
                        )
                    return self._task_view(existing), False
                device = await session.get(DeviceRow, body.device_id, with_for_update=True)
                if device is None or device.tenant_id != tenant_id:
                    raise NotFoundError("device was not found")
                frozen_account_id = body.account_id
                frozen_binding_version = None
                if frozen_account_id:
                    account_binding = await session.scalar(
                        select(AccountDeviceBindingRow)
                        .where(
                            AccountDeviceBindingRow.tenant_id == tenant_id,
                            AccountDeviceBindingRow.account_id == frozen_account_id,
                            AccountDeviceBindingRow.device_id == body.device_id,
                            AccountDeviceBindingRow.status == "BOUND",
                        )
                        .with_for_update()
                    )
                    if account_binding is None:
                        raise ConflictError("account is not bound to the selected device")
                    if (
                        body.expected_binding_version is not None
                        and body.expected_binding_version != account_binding.binding_version
                    ):
                        raise ConflictError("binding version does not match expectedBindingVersion")
                    frozen_binding_version = account_binding.binding_version
                media_delivery = body.media_delivery
                if media_delivery is not None:
                    media_rows = list(
                        (
                            await session.execute(
                                select(MediaAssetRow).where(
                                    MediaAssetRow.tenant_id == tenant_id,
                                    MediaAssetRow.id.in_(media_delivery.asset_ids),
                                )
                            )
                        ).scalars()
                    )
                    if len(media_rows) != len(media_delivery.asset_ids):
                        raise NotFoundError("one or more media assets were not found in tenant")
                row = MobileTaskRow(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    device_id=body.device_id,
                    idempotency_key=key,
                    request_sha256=digest,
                    requested_by=requested_by,
                    target_package=body.target_package,
                    account_id=frozen_account_id,
                    binding_version=frozen_binding_version,
                    device_id_at_execution=None,
                    command_type=maintenance_command,
                    command_payload={},
                    business_state="QUEUED",
                    control_mode="AUTO",
                    batch_id=None,
                    scheduled_for=None,
                    stall_reason=None,
                    attempt_id=str(uuid.uuid4()),
                    resume_count=0,
                    pause_ack_at=None,
                    reconciliation={},
                    steps=[
                        {
                            "totalTimeoutMs": body.total_timeout_ms,
                            "mediaDelivery": document.get("mediaDelivery"),
                        },
                        *document["steps"],
                    ],
                    status="QUEUED",
                    lease_id=None,
                    lease_expires_at=None,
                    attempt=0,
                    last_sequence=0,
                    current_step=None,
                    result={},
                    error_code=None,
                    detail=None,
                    started_at=None,
                    completed_at=None,
                    created_at=now,
                )
                session.add(row)
            return self._task_view(row), True
        except IntegrityError as exc:
            raise ConflictError("task idempotency conflict") from exc

    async def list_tasks(self, actor: Actor) -> list[dict[str, Any]]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        async with self.database.unit_of_work() as session:
            rows = (
                await session.scalars(
                    select(MobileTaskRow)
                    .where(MobileTaskRow.tenant_id == str(actor.tenant_id))
                    .order_by(MobileTaskRow.created_at.desc())
                    .limit(200)
                )
            ).all()
            return [self._task_view(row) for row in rows]

    async def get_task(self, actor: Actor, task_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("mobile task was not found")
            events = (
                await session.scalars(
                    select(MobileTaskEventRow)
                    .where(MobileTaskEventRow.task_id == task_id)
                    .order_by(MobileTaskEventRow.sequence)
                )
            ).all()
            view = self._task_view(row)
            view["events"] = [self._event_view(event) for event in events]
            return view

    async def claim(self, binding: MobileBindingRow, lease_seconds: int) -> dict[str, Any] | None:
        now = _now()
        async with self.database.unit_of_work() as session:
            device = await session.get(DeviceRow, binding.device_id, with_for_update=True)
            if device is None or device.tenant_id != binding.tenant_id:
                raise NotFoundError("device was not found")
            if device.maintenance:
                raise ConflictError("device is in maintenance and cannot claim tasks")
            live_service = getattr(self, "live_service", None)
            if live_service is not None and live_service.has_remote(binding.device_id):
                raise ConflictError("DEVICE_REMOTE")
            if device.active_binding_id and device.active_binding_id != binding.id:
                raise AuthenticationError("companion instance is no longer the active binding")
            blocking = await session.scalar(
                select(MobileTaskRow)
                .where(
                    MobileTaskRow.tenant_id == binding.tenant_id,
                    MobileTaskRow.device_id == binding.device_id,
                    MobileTaskRow.business_state.in_(
                        {
                            "PAUSE_REQUESTED",
                            "PAUSED_WAITING_USER",
                            "RESUME_CHECK",
                            "CANCEL_REQUESTED",
                            "WAITING_MATERIALS",
                            "RECONCILING",
                        }
                    ),
                )
                .order_by(MobileTaskRow.created_at)
            )
            if blocking is not None:
                return None
            existing_lease = await session.get(DeviceLeaseRow, binding.device_id, with_for_update=True)
            if (
                existing_lease is not None
                and existing_lease.canceled_at is None
                and _aware(existing_lease.expires_at) > now
                and existing_lease.owner_type == "REMOTE"
            ):
                raise ConflictError("device write lease is held by remote control")
            active = await session.scalar(
                select(MobileTaskRow)
                .where(
                    MobileTaskRow.tenant_id == binding.tenant_id,
                    MobileTaskRow.device_id == binding.device_id,
                    MobileTaskRow.status.in_(ACTIVE_STATES),
                )
                .order_by(MobileTaskRow.created_at)
                .with_for_update()
            )
            if (
                active is not None
                and active.lease_expires_at is not None
                and _aware(active.lease_expires_at) > now
            ):
                return None
            if active is not None:
                active.status = "QUEUED"
                active.lease_id = None
                active.lease_expires_at = None
            queued = list(
                await session.scalars(
                    select(MobileTaskRow)
                    .where(
                        MobileTaskRow.tenant_id == binding.tenant_id,
                        MobileTaskRow.device_id == binding.device_id,
                        MobileTaskRow.status == "QUEUED",
                    )
                    .order_by(MobileTaskRow.created_at)
                    .with_for_update()
                )
            )
            row = None
            for candidate in queued:
                mismatch = await self._account_binding_mismatch(session, candidate)
                if mismatch:
                    candidate.status = "FAILED"
                    candidate.business_state = "FAILED"
                    candidate.error_code = "ACCOUNT_CHANGED"
                    candidate.detail = mismatch
                    candidate.completed_at = now
                    candidate.lease_id = None
                    candidate.lease_expires_at = None
                    from .im_service import settle_reply_delivery

                    await settle_reply_delivery(session, candidate.id, "FAILED")
                    continue
                row = candidate
                break
            if row is None:
                return None
            if row.command_type and row.attempt > 0 and row.recipe_pin is None:
                raise ConflictError(
                    "legacy task has no persisted recipe pin; reconcile before continuing"
                )
            row.status = "CLAIMED"
            row.business_state = "PREFLIGHT"
            row.lease_id = str(uuid.uuid4())
            row.lease_expires_at = now + timedelta(seconds=lease_seconds)
            row.attempt += 1
            row.started_at = now
            row.device_id_at_execution = binding.device_id
            device.fencing_counter += 1
            if existing_lease is not None:
                await session.delete(existing_lease)
                await session.flush()
            session.add(
                DeviceLeaseRow(
                    device_id=device.id,
                    tenant_id=binding.tenant_id,
                    lease_id=row.lease_id,
                    owner_workflow_id=f"auto/{row.id}",
                    fencing_token=device.fencing_counter,
                    expires_at=row.lease_expires_at,
                    canceled_at=None,
                    owner_type="AUTO",
                    created_at=now,
                )
            )
            if row.steps:
                metadata = dict(row.steps[0])
                metadata["controlEpoch"] = device.fencing_counter
                row.steps = [metadata, *row.steps[1:]]
            if row.recipe_pin is None and row.command_type:
                from .builtin_recipes import builtin_recipe_ref

                from .mobile_actions import MAINTENANCE_COMMAND_TYPES

                if row.command_type in MAINTENANCE_COMMAND_TYPES:
                    # Maintenance steps are gated by the controlled action ledger,
                    # not by a recipe pin; claim must not resolve a builtin recipe.
                    row.recipe_pin = None
                else:
                    published = await self._published_recipe_ref(
                        session, binding.tenant_id, binding.device_id, row.command_type
                    )
                    row.recipe_pin = published or builtin_recipe_ref(row.command_type)
                session.add(
                    AuditEventRow(
                        id=str(uuid.uuid4()),
                        tenant_id=binding.tenant_id,
                        actor_id=binding.id,
                        actor_type="companion",
                        action="recipe.task.pinned",
                        resource_type="mobile_task",
                        resource_id=row.id,
                        request_id=row.id,
                        device_id=binding.device_id,
                        result="SUCCEEDED",
                        metadata_json={"deviceId": binding.device_id, "recipe": row.recipe_pin},
                        occurred_at=now,
                    )
                )
            return self._task_view(row, companion_claim=True)

    async def heartbeat(
        self,
        binding: MobileBindingRow,
        task_id: str,
        lease_id: str,
        current_step: int | None,
        lease_seconds: int,
    ) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            stored = await session.get(MobileTaskRow, task_id, with_for_update=True)
            self._validate_owned_task(stored, binding)
            assert stored is not None
            self._validate_active_lease(stored, lease_id)
            stored.status = "RUNNING"
            if stored.business_state == "RESUME_CHECK":
                stored.business_state = "RUNNING"
            elif stored.business_state not in {
                "PAUSE_REQUESTED",
                "CANCEL_REQUESTED",
                "PAUSED_WAITING_USER",
                "RECONCILING",
            }:
                stored.business_state = "RUNNING"
            stored.current_step = current_step
            stored.lease_expires_at = _now() + timedelta(seconds=lease_seconds)
            lease = await session.get(DeviceLeaseRow, binding.device_id, with_for_update=True)
            if lease is not None and lease.lease_id == stored.lease_id:
                lease.expires_at = stored.lease_expires_at
            return self._task_view(stored)

    async def event(
        self,
        binding: MobileBindingRow,
        task_id: str,
        lease_id: str,
        sequence: int,
        event_type: str,
        step_index: int | None,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        now = _now()
        async with self.database.unit_of_work() as session:
            task = await session.get(MobileTaskRow, task_id, with_for_update=True)
            self._validate_owned_task(task, binding)
            assert task is not None
            self._validate_active_lease(task, lease_id)
            if sequence <= task.last_sequence:
                existing = await session.scalar(
                    select(MobileTaskEventRow).where(
                        MobileTaskEventRow.task_id == task_id,
                        MobileTaskEventRow.sequence == sequence,
                    )
                )
                if (
                    existing is None
                    or existing.event_type != event_type
                    or existing.step_index != step_index
                    or existing.payload != payload
                ):
                    raise ConflictError("event sequence was replayed with different content")
                return self._event_view(existing), False
            if sequence != task.last_sequence + 1:
                raise ConflictError("mobile task event sequence has a gap")
            # Replays above remain idempotent even if reconciliation started later.
            if task.business_state == "RECONCILING" and event_type in {
                "PAUSE_REQUESTED", "PAUSED_WAITING_USER", "RESUME_CHECK"
            }:
                raise ConflictError("uncertain result must be reconciled before changing task state")
            if event_type == "PAUSE_REQUESTED":
                task.business_state = "PAUSE_REQUESTED"
            elif event_type == "PAUSED_WAITING_USER":
                if (task.command_payload or {}).get("commitIntent"):
                    task.business_state = "RECONCILING"
                    task.stall_reason = task.stall_reason or "commit intent already written"
                else:
                    task.business_state = "PAUSED_WAITING_USER"
                task.control_mode = "REMOTE"
                task.pause_ack_at = now
            elif event_type == "RESUME_CHECK":
                task.business_state = "RESUME_CHECK"
            elif event_type == "RECONCILING":
                task.business_state = "RECONCILING"
            event = MobileTaskEventRow(
                id=str(uuid.uuid4()),
                tenant_id=task.tenant_id,
                task_id=task_id,
                sequence=sequence,
                event_type=event_type,
                step_index=step_index,
                step_id=str(payload.get("stepId")) if isinstance(payload.get("stepId"), str) else None,
                attempt_id=task.attempt_id,
                payload=payload,
                occurred_at=now,
                received_at=now,
            )
            session.add(event)
            task.last_sequence = sequence
            task.current_step = step_index
            return self._event_view(event), True

    async def finish(
        self,
        binding: MobileBindingRow,
        task_id: str,
        lease_id: str,
        *,
        status: str,
        result: dict[str, Any],
        error_code: str | None = None,
        detail: str | None = None,
    ) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            self._validate_owned_task(row, binding)
            assert row is not None
            if row.business_state == "RECONCILING":
                raise ConflictError("uncertain result must be resolved by explicit reconciliation")
            if row.status in {"SUCCEEDED", "FAILED"}:
                if (
                    row.status == status
                    and row.result == result
                    and row.error_code == error_code
                    and row.detail == detail
                ):
                    return self._task_view(row)
                raise ConflictError("mobile task already has a different terminal result")
            self._validate_active_lease(row, lease_id)
            expected_type = None
            if row.command_type:
                from .mobile_schemas import RESULT_TYPES

                expected_type = RESULT_TYPES.get(row.command_type)
            incoming_type = result.get("resultType") if isinstance(result, dict) else None
            if expected_type and incoming_type and incoming_type != expected_type:
                raise ValidationError("resultType does not match commandType")
            if incoming_type and expected_type is None and row.command_type:
                raise ValidationError("resultType is not defined for this command")
            row.status, row.result, row.error_code, row.detail = status, result, error_code, detail
            row.business_state = RUNNER_TO_BUSINESS.get(status, status)
            row.completed_at, row.lease_expires_at = _now(), None
            # Reply OUT messages follow the task terminal state (idempotent).
            from .im_service import settle_reply_delivery

            await settle_reply_delivery(session, row.id, row.business_state)
            lease = await session.get(DeviceLeaseRow, binding.device_id, with_for_update=True)
            if lease is not None and lease.lease_id == row.lease_id:
                lease.canceled_at = row.completed_at
            return self._task_view(row)

    async def start_preview(
        self,
        actor: Actor,
        device_id: str,
        *,
        ttl_seconds: int,
        capture_interval_ms: int,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        now = _now()
        async with self.database.unit_of_work() as session:
            device = await session.get(DeviceRow, device_id, with_for_update=True)
            if device is None or device.tenant_id != str(actor.tenant_id):
                raise NotFoundError("device was not found")
            row = await session.get(DevicePreviewRow, device_id, with_for_update=True)
            if row is None:
                row = DevicePreviewRow(
                    device_id=device_id,
                    tenant_id=device.tenant_id,
                    capture_interval_ms=capture_interval_ms,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            row.session_id = str(uuid.uuid4())
            row.session_expires_at = now + timedelta(seconds=ttl_seconds)
            row.requested_by = str(actor.user_id)
            row.capture_interval_ms = capture_interval_ms
            row.updated_at = now
            return self._preview_view(row, now)

    async def stop_preview(self, actor: Actor, device_id: str, session_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_MAINTAIN)
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await self._owned_preview(session, actor, device_id)
            if row.session_id != session_id:
                raise ConflictError("preview session does not match")
            row.session_expires_at = now
            row.updated_at = now
            return self._preview_view(row, now)

    async def preview_status(self, actor: Actor, device_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_READ)
        now = _now()
        async with self.database.unit_of_work() as session:
            device = await session.get(DeviceRow, device_id)
            if device is None or device.tenant_id != str(actor.tenant_id):
                raise NotFoundError("device was not found")
            row = await session.get(DevicePreviewRow, device_id)
            if row is None:
                return {
                    "deviceId": device_id,
                    "sessionId": None,
                    "active": False,
                    "expiresAt": None,
                    "captureIntervalMs": PREVIEW_CAPTURE_INTERVAL_MS,
                    "waitingForFrame": False,
                    "capturedAt": None,
                    "sha256": None,
                    "width": None,
                    "height": None,
                    "contentType": None,
                    "hasFrame": False,
                }
            return self._preview_view(row, now)

    async def preview_frame(self, actor: Actor, device_id: str) -> tuple[bytes, str, str] | None:
        require_permissions(actor.roles, Permission.DEVICE_READ)
        async with self.database.unit_of_work() as session:
            row = await self._owned_preview(session, actor, device_id)
            if not row.image_bytes or not row.content_type or not row.sha256:
                return None
            return row.image_bytes, row.content_type, row.sha256

    async def upload_preview(
        self, binding: MobileBindingRow, body: DevicePreviewUpload
    ) -> dict[str, Any]:
        image = self._decode_preview_jpeg(body)
        now = _now()
        async with self.database.unit_of_work() as session:
            stored = await session.get(MobileBindingRow, binding.id, with_for_update=True)
            if stored is None or stored.revoked_at is not None:
                raise AuthenticationError("invalid or revoked Companion bearer token")
            row = await session.get(DevicePreviewRow, stored.device_id, with_for_update=True)
            if row is None or row.session_id != body.session_id:
                raise ConflictError("preview session is not active")
            if row.session_expires_at is None or _aware(row.session_expires_at) <= now:
                raise ConflictError("preview session has expired")
            row.frame_session_id = body.session_id
            row.content_type = body.content_type
            row.sha256 = body.sha256
            row.width = body.width
            row.height = body.height
            row.image_bytes = image
            row.captured_at = now
            row.updated_at = now
            return self._preview_view(row, now)

    async def unbind(self, binding: MobileBindingRow) -> None:
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileBindingRow, binding.id, with_for_update=True)
            if row is None or row.revoked_at is not None:
                raise AuthenticationError("binding is already revoked")
            row.revoked_at = now
            device = await session.get(DeviceRow, row.device_id, with_for_update=True)
            if device is not None:
                device.last_seen_at = None

    @staticmethod
    async def _owned_preview(session: Any, actor: Actor, device_id: str) -> DevicePreviewRow:
        device = await session.get(DeviceRow, device_id)
        if device is None or device.tenant_id != str(actor.tenant_id):
            raise NotFoundError("device was not found")
        row = await session.get(DevicePreviewRow, device_id)
        if row is None:
            raise NotFoundError("preview session was not found")
        return row

    @classmethod
    def _preview_view(cls, row: DevicePreviewRow, now: datetime) -> dict[str, Any]:
        active = bool(
            row.session_id
            and row.session_expires_at is not None
            and _aware(row.session_expires_at) > now
        )
        has_frame = bool(row.image_bytes and row.sha256)
        return {
            "deviceId": row.device_id,
            "sessionId": row.session_id if active else None,
            "active": active,
            "expiresAt": row.session_expires_at if active else None,
            "captureIntervalMs": row.capture_interval_ms,
            "waitingForFrame": active and (not has_frame or row.frame_session_id != row.session_id),
            "capturedAt": row.captured_at,
            "sha256": row.sha256 if has_frame else None,
            "width": row.width if has_frame else None,
            "height": row.height if has_frame else None,
            "contentType": row.content_type if has_frame else None,
            "hasFrame": has_frame,
        }

    @staticmethod
    def _companion_preview_grant(
        row: DevicePreviewRow | None, now: datetime
    ) -> dict[str, Any] | None:
        if (
            row is None
            or not row.session_id
            or row.session_expires_at is None
            or _aware(row.session_expires_at) <= now
        ):
            return None
        return {
            "sessionId": row.session_id,
            "expiresAt": row.session_expires_at,
            "captureIntervalMs": row.capture_interval_ms,
        }

    @staticmethod
    def _decode_preview_jpeg(body: DevicePreviewUpload) -> bytes:
        try:
            image = base64.b64decode(body.image_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValidationError("preview image is not valid base64") from exc
        if len(image) > PREVIEW_MAX_BYTES:
            raise ValidationError("preview image exceeds size limit")
        if not image.startswith(PREVIEW_JPEG_MAGIC):
            raise ValidationError("preview image must be JPEG")
        digest = hashlib.sha256(image).hexdigest()
        if digest != body.sha256:
            raise ValidationError("preview image checksum does not match")
        return image

    @staticmethod
    async def _account_binding_mismatch(
        session: Any, task: MobileTaskRow
    ) -> str | None:
        if not task.account_id:
            return None
        live = await session.scalar(
            select(AccountDeviceBindingRow).where(
                AccountDeviceBindingRow.tenant_id == task.tenant_id,
                AccountDeviceBindingRow.account_id == task.account_id,
                AccountDeviceBindingRow.device_id == task.device_id,
                AccountDeviceBindingRow.status == "BOUND",
            )
        )
        if live is None:
            return "account is no longer bound to this device"
        if task.binding_version is not None and live.binding_version != task.binding_version:
            return "account binding version changed"
        return None

    @staticmethod
    def _validate_owned_task(row: MobileTaskRow | None, binding: MobileBindingRow) -> None:
        if row is None or row.tenant_id != binding.tenant_id or row.device_id != binding.device_id:
            raise NotFoundError("mobile task was not found")

    @staticmethod
    def _validate_active_lease(row: MobileTaskRow, lease_id: str) -> None:
        if row.business_state in TERMINAL_BUSINESS_STATES:
            raise ConflictError("terminal mobile task cannot accept runner updates")
        if row.status not in ACTIVE_STATES or row.lease_id != lease_id:
            raise ConflictError("mobile task lease does not match")
        if row.lease_expires_at is None or _aware(row.lease_expires_at) <= _now():
            raise ConflictError("mobile task lease has expired")

    @staticmethod
    def _task_view(
        row: MobileTaskRow,
        *,
        companion_claim: bool = False,
    ) -> dict[str, Any]:
        from .command_v1 import PROTOCOL_VERSION, command_v1_from_task

        metadata, *steps = row.steps
        total_timeout_ms = int(metadata.get("totalTimeoutMs", 0))
        issued_at = row.started_at or row.created_at
        view: dict[str, Any] = {
            "protocolVersion": "cloudctl.mobile/v1",
            "id": row.id,
            "taskId": row.id,
            "deviceId": row.device_id,
            "accountId": row.account_id,
            "bindingVersion": row.binding_version,
            "deviceIdAtExecution": row.device_id_at_execution,
            "targetPackage": row.target_package,
            "commandType": row.command_type,
            "issuedAt": issued_at,
            "expiresAt": _aware(issued_at) + timedelta(milliseconds=total_timeout_ms),
            "maxRunSeconds": (total_timeout_ms + 999) // 1000,
            "totalTimeoutMs": total_timeout_ms,
            "mediaDelivery": metadata.get("mediaDelivery"),
            "steps": steps,
            "status": row.status,
            "leaseId": row.lease_id,
            "leaseExpiresAt": row.lease_expires_at,
            "controlEpoch": metadata.get("controlEpoch"),
            "attempt": row.attempt,
            "lastSequence": row.last_sequence,
            "currentStep": row.current_step,
            "businessState": row.business_state,
            "controlMode": row.control_mode or "AUTO",
            "stallReason": row.stall_reason,
            "result": row.result,
            "errorCode": row.error_code,
            "detail": row.detail,
            "createdAt": row.created_at,
            "startedAt": row.started_at,
            "completedAt": _aware(row.completed_at) if row.completed_at is not None else None,
        }
        control_epoch = metadata.get("controlEpoch")
        if (
            row.command_type
            and row.account_id
            and row.binding_version
            and row.attempt_id
            and row.lease_expires_at is not None
            and isinstance(control_epoch, int)
            and control_epoch >= 1
        ):
            try:
                command = command_v1_from_task(
                    task_id=row.id,
                    attempt_id=row.attempt_id,
                    command_type=row.command_type,
                    device_id=row.device_id,
                    account_id=row.account_id,
                    binding_version=row.binding_version,
                    target_package=row.target_package,
                    command_payload=row.command_payload,
                    control_epoch=control_epoch,
                    lease_expires_at=_aware(row.lease_expires_at),
                    media_delivery_id=(row.command_payload or {}).get("mediaDeliveryId"),
                    published_recipe=row.recipe_pin,
                )
            except ValueError:
                command = None
            if command is not None:
                view["command"] = command
                view["attemptId"] = row.attempt_id
                if companion_claim:
                    view["protocolVersion"] = PROTOCOL_VERSION
                    if not command.get("legacyStepsEnabled"):
                        view.pop("steps", None)
        return view

    @staticmethod
    def _event_view(row: MobileTaskEventRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "taskId": row.task_id,
            "sequence": row.sequence,
            "eventType": row.event_type,
            "stepIndex": row.step_index,
            "stepId": row.step_id,
            "attemptId": row.attempt_id,
            "payload": row.payload,
            "occurredAt": row.occurred_at,
            "receivedAt": row.received_at,
        }
