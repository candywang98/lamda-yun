"""Application service for audited, short-lived debug-session capabilities."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from cloudctl_domain import (
    Actor,
    ConflictError,
    ForbiddenError,
    Permission,
    Role,
    ValidationError,
    require_permissions,
)

from .db import Database, DebugEvidenceRow, DebugSessionRow, DeviceLeaseRow
from .debug_repository import DebugRepository
from .debug_schemas import DebugEvidenceCreate, DebugHeartbeat, DebugSessionCreate
from .repository import ControlRepository
from .settings import Settings

ALLOWED_DEBUG_CAPABILITIES = frozenset(
    {
        "view.frame",
        "view.layout",
        "input.tap",
        "input.swipe",
        "input.text",
        "debug.steps",
        "debug.variables",
        "evidence.capture",
    }
)
TERMINAL_DEBUG_STATES = frozenset({"REVOKED", "EXPIRED"})
PROHIBITED_FRAGMENTS = frozenset(
    {
        "adb",
        "captcha",
        "command",
        "credential",
        "frida",
        "mitm",
        "password",
        "pem",
        "privatekey",
        "proxy",
        "script",
        "secret",
        "shell",
        "token",
    }
)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _digest(secret_value: str) -> str:
    return hashlib.sha256(secret_value.encode("utf-8")).hexdigest()


class DebugSessionService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    async def create(self, actor: Actor, body: DebugSessionCreate) -> dict[str, Any]:
        self._require_debug_actor(actor)
        capabilities = self._validated_capabilities(body.capabilities)
        self._validate_return_url(body.return_url)
        launch_code = secrets.token_urlsafe(32)
        async with self.database.unit_of_work() as session:
            control = ControlRepository(session, actor)
            device = await control.device(body.device_id, for_update=True)
            if not device.maintenance:
                raise ConflictError("device must be in maintenance before a debug session starts")
            now = _now()
            existing_lease = await control.lease_for_device(device.id)
            if (
                existing_lease is not None
                and existing_lease.canceled_at is None
                and _aware(existing_lease.expires_at) > now
            ):
                raise ConflictError("device already has an active runner lease")
            if existing_lease is not None:
                await session.delete(existing_lease)
                await session.flush()
            session_id = control.new_id()
            lease_id = control.new_id()
            device.fencing_counter += 1
            expires_at = now + timedelta(seconds=body.ttl_seconds)
            lease = DeviceLeaseRow(
                device_id=device.id,
                tenant_id=control.tenant_id,
                lease_id=lease_id,
                owner_workflow_id=f"debug-session/{session_id}",
                fencing_token=device.fencing_counter,
                expires_at=expires_at,
                canceled_at=None,
                created_at=now,
            )
            control.add(lease)
            row = DebugSessionRow(
                id=session_id,
                tenant_id=control.tenant_id,
                edge_id=device.edge_id,
                device_id=device.id,
                lease_id=lease.lease_id,
                fencing_token=lease.fencing_token,
                created_by=str(actor.user_id),
                purpose=body.purpose,
                capabilities=capabilities,
                status="PENDING_EXCHANGE",
                expires_at=expires_at,
                launch_code_hash=_digest(launch_code),
                launch_code_used_at=None,
                relay_token_hash=None,
                relay_token_expires_at=None,
                exchanged_at=None,
                last_heartbeat_at=None,
                stage=None,
                last_event=None,
                detail=None,
                return_url=body.return_url,
                revoked_at=None,
                revoked_by=None,
                revoke_reason=None,
                created_at=now,
            )
            control.add(row)
            control.audit(
                action="device.lease.acquired",
                resource_type="device_lease",
                resource_id=lease.lease_id,
                after={
                    "device_id": device.id,
                    "fencing_token": lease.fencing_token,
                    "expires_at": lease.expires_at,
                },
                workflow_id=lease.owner_workflow_id,
                device_id=device.id,
                edge_id=device.edge_id,
            )
            control.audit(
                action="debug.session.created",
                resource_type="debug_session",
                resource_id=row.id,
                after={
                    "device_id": row.device_id,
                    "edge_id": row.edge_id,
                    "lease_id": row.lease_id,
                    "fencing_token": row.fencing_token,
                    "capabilities": capabilities,
                    "expires_at": row.expires_at,
                },
                device_id=row.device_id,
                metadata={"purpose_sha256": _digest(body.purpose)},
            )
            control.emit(
                control.event(
                    "debug_session",
                    row.id,
                    "debug.session.created",
                    {
                        "sessionId": row.id,
                        "deviceId": row.device_id,
                        "edgeId": row.edge_id,
                        "leaseId": row.lease_id,
                        "fencingToken": row.fencing_token,
                        "capabilities": capabilities,
                        "expiresAt": row.expires_at.isoformat(),
                    },
                )
            )
            return {"session": self._view(row), "launchCode": launch_code}

    async def get(self, actor: Actor, session_id: str) -> dict[str, Any]:
        self._require_debug_actor(actor)
        async with self.database.unit_of_work() as session:
            repository = DebugRepository(session, actor)
            control = ControlRepository(session, actor)
            row = await repository.session(session_id, for_update=True)
            await self._expire_if_needed(row, control)
            await self._revoke_if_lease_lost(row, control)
            evidence = await repository.evidence(row.id)
            result = self._view(row)
            result["evidence"] = [self._evidence_view(item) for item in evidence]
            return result

    async def exchange(self, actor: Actor, launch_code: str) -> dict[str, Any]:
        self._require_debug_actor(actor)
        launch_hash = _digest(launch_code)
        relay_token = secrets.token_urlsafe(48)
        async with self.database.unit_of_work() as session:
            repository = DebugRepository(session, actor)
            control = ControlRepository(session, actor)
            row = await repository.session_by_launch_hash(launch_hash, for_update=True)
            await self._expire_if_needed(row, control)
            if row.status != "PENDING_EXCHANGE":
                raise ConflictError(f"debug session cannot be exchanged while {row.status}")
            if row.launch_code_used_at is not None:
                raise ConflictError("debug launch code was already consumed")
            if row.created_by != str(actor.user_id) and Role.SECURITY_ADMIN not in actor.roles:
                raise ForbiddenError(
                    "only the creator or SecurityAdmin may exchange this launch code"
                )
            await self._require_active_lease(row, control)
            now = _now()
            row.launch_code_used_at = now
            row.relay_token_hash = _digest(relay_token)
            row.relay_token_expires_at = row.expires_at
            row.exchanged_at = now
            row.status = "ACTIVE"
            control.audit(
                action="debug.session.exchanged",
                resource_type="debug_session",
                resource_id=row.id,
                after={"status": row.status, "expires_at": row.expires_at},
                device_id=row.device_id,
            )
            control.emit(
                control.event(
                    "debug_session",
                    row.id,
                    "debug.session.grant_requested",
                    {
                        "sessionId": row.id,
                        "deviceId": row.device_id,
                        "edgeId": row.edge_id,
                        "leaseId": row.lease_id,
                        "fencingToken": row.fencing_token,
                        "capabilities": row.capabilities,
                        "expiresAt": _aware(row.expires_at).isoformat(),
                        # This field is an internal mTLS-delivery secret. It is never written to
                        # audit metadata or application logs; the Edge Hub consumes it once.
                        "relayToken": relay_token,
                    },
                )
            )
            return {
                "session": self._view(row),
                "relayToken": relay_token,
                "relayUrl": self.settings.debug_relay_url,
            }

    async def heartbeat(
        self,
        actor: Actor,
        session_id: str,
        relay_token: str,
        body: DebugHeartbeat,
    ) -> dict[str, Any]:
        self._require_debug_actor(actor)
        async with self.database.unit_of_work() as session:
            repository = DebugRepository(session, actor)
            control = ControlRepository(session, actor)
            row = await repository.session(session_id, for_update=True)
            await self._authorize_relay(row, relay_token, control)
            now = _now()
            row.last_heartbeat_at = now
            row.stage = body.stage
            row.last_event = body.event
            row.detail = body.detail
            control.audit(
                action="debug.session.heartbeat",
                resource_type="debug_session",
                resource_id=row.id,
                after={"stage": body.stage, "event": body.event},
                device_id=row.device_id,
                metadata={"evidence_count": len(body.evidence_refs)},
            )
            control.emit(
                control.event(
                    "debug_session",
                    row.id,
                    "debug.session.heartbeat",
                    {
                        "sessionId": row.id,
                        "stage": body.stage,
                        "event": body.event,
                        "evidenceRefs": body.evidence_refs,
                    },
                )
            )
            return self._view(row)

    async def add_evidence(
        self,
        actor: Actor,
        session_id: str,
        relay_token: str,
        body: DebugEvidenceCreate,
    ) -> tuple[dict[str, Any], bool]:
        self._require_debug_actor(actor)
        self._validate_evidence(body)
        async with self.database.unit_of_work() as session:
            repository = DebugRepository(session, actor)
            control = ControlRepository(session, actor)
            row = await repository.session(session_id, for_update=True)
            await self._authorize_relay(row, relay_token, control)
            existing = await repository.evidence_by_hash(row.id, body.sha256)
            if existing is not None:
                if (
                    existing.kind != body.kind
                    or existing.object_ref != body.object_ref
                    or existing.metadata_json != body.metadata
                ):
                    raise ConflictError("evidence hash already exists with different metadata")
                return self._evidence_view(existing), False
            evidence = DebugEvidenceRow(
                id=control.new_id(),
                tenant_id=control.tenant_id,
                session_id=row.id,
                kind=body.kind,
                sha256=body.sha256,
                object_ref=body.object_ref,
                metadata_json=body.metadata,
                created_at=_now(),
            )
            repository.add(evidence)
            control.audit(
                action="debug.session.evidence_registered",
                resource_type="debug_session",
                resource_id=row.id,
                after={"evidence_id": evidence.id, "kind": evidence.kind, "sha256": body.sha256},
                device_id=row.device_id,
            )
            control.emit(
                control.event(
                    "debug_session",
                    row.id,
                    "debug.session.evidence_registered",
                    {"sessionId": row.id, "evidenceId": evidence.id, "kind": evidence.kind},
                )
            )
            return self._evidence_view(evidence), True

    async def revoke(self, actor: Actor, session_id: str, reason: str) -> dict[str, Any]:
        self._require_debug_actor(actor)
        async with self.database.unit_of_work() as session:
            repository = DebugRepository(session, actor)
            control = ControlRepository(session, actor)
            row = await repository.session(session_id, for_update=True)
            if row.created_by != str(actor.user_id) and Role.SECURITY_ADMIN not in actor.roles:
                raise ForbiddenError("only the creator or SecurityAdmin may revoke this session")
            if row.status in TERMINAL_DEBUG_STATES:
                if row.status == "REVOKED" and row.revoke_reason == reason:
                    return self._view(row)
                raise ConflictError(f"debug session is already {row.status}")
            now = _now()
            row.status = "REVOKED"
            row.revoked_at = now
            row.revoked_by = str(actor.user_id)
            row.revoke_reason = reason
            row.relay_token_hash = None
            row.relay_token_expires_at = None
            await self._release_device_lease(row, control)
            control.audit(
                action="debug.session.revoked",
                resource_type="debug_session",
                resource_id=row.id,
                after={"status": row.status},
                device_id=row.device_id,
                metadata={"reason": reason},
            )
            control.emit(
                control.event(
                    "debug_session",
                    row.id,
                    "debug.session.revoked",
                    {
                        "sessionId": row.id,
                        "deviceId": row.device_id,
                        "leaseId": row.lease_id,
                        "fencingToken": row.fencing_token,
                        "reason": reason,
                    },
                )
            )
            return self._view(row)

    @staticmethod
    def _require_debug_actor(actor: Actor) -> None:
        require_permissions(actor.roles, Permission.DEBUG_SESSION_MANAGE)
        if not actor.mfa:
            raise ForbiddenError("MFA is required for debug sessions")

    @staticmethod
    def _validated_capabilities(capabilities: list[str]) -> list[str]:
        requested = set(capabilities)
        prohibited = requested - ALLOWED_DEBUG_CAPABILITIES
        if prohibited:
            raise ForbiddenError(
                f"debug capabilities are not allowed: {', '.join(sorted(prohibited))}"
            )
        return sorted(requested)

    def _validate_return_url(self, return_url: str | None) -> None:
        if return_url is None:
            return
        parsed = urlsplit(return_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValidationError("returnUrl must be an absolute HTTP(S) URL")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.settings.cors_allowed_origins:
            raise ForbiddenError("returnUrl origin is not allowed")

    @staticmethod
    def _validate_evidence(body: DebugEvidenceCreate) -> None:
        parsed = urlsplit(body.object_ref)
        if parsed.scheme not in {"s3", "https"} or not parsed.netloc:
            raise ValidationError("evidence objectRef must use an absolute s3:// or https:// URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValidationError("evidence objectRef cannot contain URL credentials")
        encoded = json.dumps(body.metadata, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode()) > 8192:
            raise ValidationError("evidence metadata exceeds 8 KiB")
        DebugSessionService._inspect_safe_metadata(body.metadata)

    @staticmethod
    def _inspect_safe_metadata(value: Any, key: str = "") -> None:
        normalized = key.lower().replace("_", "").replace("-", "")
        if any(fragment in normalized for fragment in PROHIBITED_FRAGMENTS):
            raise ValidationError(f"unsafe evidence metadata field is prohibited: {key}")
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                DebugSessionService._inspect_safe_metadata(child_value, str(child_key))
        elif isinstance(value, list):
            for child_value in value:
                DebugSessionService._inspect_safe_metadata(child_value, key)

    async def _expire_if_needed(self, row: DebugSessionRow, control: ControlRepository) -> None:
        if row.status not in TERMINAL_DEBUG_STATES and _aware(row.expires_at) <= _now():
            row.status = "EXPIRED"
            row.relay_token_hash = None
            row.relay_token_expires_at = None
            await self._release_device_lease(row, control)
            control.audit(
                action="debug.session.expired",
                resource_type="debug_session",
                resource_id=row.id,
                after={"status": row.status},
                device_id=row.device_id,
            )
            control.emit(
                control.event(
                    "debug_session",
                    row.id,
                    "debug.session.expired",
                    {
                        "sessionId": row.id,
                        "deviceId": row.device_id,
                        "leaseId": row.lease_id,
                        "fencingToken": row.fencing_token,
                    },
                )
            )

    async def _authorize_relay(
        self, row: DebugSessionRow, relay_token: str, control: ControlRepository
    ) -> None:
        await self._expire_if_needed(row, control)
        if row.status != "ACTIVE" or row.relay_token_hash is None:
            raise ConflictError(f"debug relay is unavailable while session is {row.status}")
        if row.relay_token_expires_at is None or _aware(row.relay_token_expires_at) <= _now():
            raise ConflictError("debug relay token expired")
        if not hmac.compare_digest(row.relay_token_hash, _digest(relay_token)):
            raise ForbiddenError("invalid debug relay token")
        await self._require_active_lease(row, control)

    async def _revoke_if_lease_lost(self, row: DebugSessionRow, control: ControlRepository) -> bool:
        if row.status in TERMINAL_DEBUG_STATES:
            return False
        try:
            await self._require_active_lease(row, control)
        except ConflictError:
            now = _now()
            row.status = "REVOKED"
            row.revoked_at = now
            row.revoked_by = None
            row.revoke_reason = "device lease lost"
            row.relay_token_hash = None
            row.relay_token_expires_at = None
            control.audit(
                action="debug.session.lease_lost",
                resource_type="debug_session",
                resource_id=row.id,
                after={"status": row.status, "reason": row.revoke_reason},
                device_id=row.device_id,
                result="REVOKED",
            )
            control.emit(
                control.event(
                    "debug_session",
                    row.id,
                    "debug.session.revoked",
                    {
                        "sessionId": row.id,
                        "deviceId": row.device_id,
                        "leaseId": row.lease_id,
                        "fencingToken": row.fencing_token,
                        "reason": row.revoke_reason,
                    },
                )
            )
            return True
        return False

    @staticmethod
    async def _require_active_lease(
        row: DebugSessionRow, control: ControlRepository
    ) -> DeviceLeaseRow:
        if row.lease_id is None or row.fencing_token is None:
            raise ConflictError("debug session has no valid device lease")
        lease = await control.lease_for_device(row.device_id)
        if (
            lease is None
            or lease.lease_id != row.lease_id
            or lease.fencing_token != row.fencing_token
            or lease.owner_workflow_id != f"debug-session/{row.id}"
            or lease.canceled_at is not None
            or _aware(lease.expires_at) <= _now()
        ):
            raise ConflictError("debug session device lease is no longer active")
        return lease

    @staticmethod
    async def _release_device_lease(row: DebugSessionRow, control: ControlRepository) -> None:
        if row.lease_id is None:
            return
        lease = await control.lease_for_device(row.device_id)
        if lease is None or lease.lease_id != row.lease_id or lease.canceled_at is not None:
            return
        lease.canceled_at = _now()
        control.audit(
            action="device.lease.released",
            resource_type="device_lease",
            resource_id=lease.lease_id,
            device_id=row.device_id,
            edge_id=row.edge_id,
            workflow_id=lease.owner_workflow_id,
        )

    @staticmethod
    def _view(row: DebugSessionRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "tenantId": row.tenant_id,
            "edgeId": row.edge_id,
            "deviceId": row.device_id,
            "leaseId": row.lease_id,
            "fencingToken": row.fencing_token,
            "createdBy": row.created_by,
            "purpose": row.purpose,
            "capabilities": row.capabilities,
            "status": row.status,
            "expiresAt": _aware(row.expires_at),
            "exchangedAt": _aware(row.exchanged_at) if row.exchanged_at is not None else None,
            "lastHeartbeatAt": (
                _aware(row.last_heartbeat_at) if row.last_heartbeat_at is not None else None
            ),
            "stage": row.stage,
            "event": row.last_event,
            "detail": row.detail,
            "returnUrl": row.return_url,
            "revokedAt": _aware(row.revoked_at) if row.revoked_at is not None else None,
            "revokedBy": row.revoked_by,
            "revokeReason": row.revoke_reason,
            "createdAt": _aware(row.created_at),
        }

    @staticmethod
    def _evidence_view(row: DebugEvidenceRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "sessionId": row.session_id,
            "kind": row.kind,
            "sha256": row.sha256,
            "objectRef": row.object_ref,
            "metadata": row.metadata_json,
            "createdAt": _aware(row.created_at),
        }
