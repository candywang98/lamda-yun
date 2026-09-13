"""P09 controlled action ledger. One legacy idlefish publish shape; no auto reconciliation."""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Annotated, Any, Literal

from cloudctl_automation_sdk.recipe import validate_recipe_package
from cloudctl_domain import ConflictError, NotFoundError
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select

from .db import (
    AccountDeviceBindingRow,
    AuditEventRow,
    AutomationVersionRow,
    DeviceLeaseRow,
    DeviceRow,
    MobileActionCommitRow,
    MobileBindingRow,
    MobileTaskRow,
)
from .mobile_service import COMPANION_PACKAGE, MobileTaskService, _aware, _now

Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Evidence = Annotated[str, StringConstraints(min_length=1, max_length=500, pattern=r"\S")]
Lease = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[^\r\n]+$")]


class IntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    lease_id: Lease = Field(alias="leaseId")
    action_id: str = Field(alias="actionId", pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    action_key: Digest = Field(alias="actionKey")
    parameter_hash: Digest = Field(alias="parameterHash")
    before_evidence: Evidence = Field(alias="beforeEvidence")


class OutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    lease_id: Lease = Field(alias="leaseId")
    parameter_hash: Digest = Field(alias="parameterHash")
    status: Literal["APPLIED", "UNKNOWN"]
    evidence: Evidence


def action_identity(
    task_id: str,
    command_type: str,
    account_id: str,
    binding_version: int,
    snapshot_sha256: str,
    recipe_sha256: str,
    action_id: str,
) -> tuple[str, str]:
    fields = (task_id, command_type, account_id, snapshot_sha256, recipe_sha256, action_id)
    if any(not v or "\n" in v or "\r" in v for v in fields):
        raise ConflictError("invalid action identity")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", action_id):
        raise ConflictError("invalid action ID")
    if any(not re.fullmatch(r"[a-f0-9]{64}", v) for v in (snapshot_sha256, recipe_sha256)):
        raise ConflictError("invalid frozen hash")
    key = f"cloudctl.action/v1\n{task_id}\n{recipe_sha256}\n{action_id}"
    parameters = (
        f"cloudctl.action-parameters/v1\n{task_id}\n{command_type}\n{account_id}\n"
        f"{binding_version}\n{snapshot_sha256}\n{recipe_sha256}"
    )
    return hashlib.sha256(key.encode()).hexdigest(), hashlib.sha256(parameters.encode()).hexdigest()


STEPS_COMMAND_TYPE = "xianyu.publish_listing.steps.v1"
STEPS_ACTION_ID = "click-publish"
XIANYU_PACKAGE = "com.taobao.idlefish"


def canonical_steps(steps: list[dict[str, Any]]) -> str:
    """Frozen steps text shared with the Companion (contract p09-steps-commit/20260913.1)."""

    def scalar(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    return "\n".join(
        "\n".join(f"{key}={scalar(step[key])}" for key in sorted(step)) for step in steps
    )


def steps_action_identity(task: MobileTaskRow) -> dict[str, Any]:
    steps = task.steps or []
    publish_taps = [
        step
        for step in steps
        if step.get("action") == "ui.tap" and step.get("locatorRef") == "xianyu_publish_button"
    ]
    has_postcondition = any(step.get("locatorRef") == "xianyu_publish_success" for step in steps)
    has_description = any(
        step.get("action") == "ui.input" and step.get("locatorRef") == "xianyu_description"
        for step in steps
    )
    if len(publish_taps) != 1 or not has_postcondition or not has_description:
        raise ConflictError("G3_NOT_ACCEPTED")
    digest = hashlib.sha256(canonical_steps(steps).encode()).hexdigest()
    key, parameters = action_identity(
        task.id,
        STEPS_COMMAND_TYPE,
        task.device_id,
        task.binding_version or 0,
        digest,
        digest,
        STEPS_ACTION_ID,
    )
    return dict(
        action_key=key,
        tenant_id=task.tenant_id,
        task_id=task.id,
        device_id=task.device_id,
        account_id=task.device_id,
        binding_version=task.binding_version or 0,
        recipe_version_id="steps",
        recipe_sha256=digest,
        snapshot_sha256=digest,
        action_id=STEPS_ACTION_ID,
        parameter_hash=parameters,
    )


def action_view(row: MobileActionCommitRow) -> dict[str, Any]:
    names = (
        "action_key",
        "task_id",
        "device_id",
        "account_id",
        "binding_version",
        "recipe_version_id",
        "recipe_sha256",
        "snapshot_sha256",
        "action_id",
        "parameter_hash",
        "status",
        "before_evidence",
        "reported_evidence",
        "resolution_revision",
        "resolution_evidence",
        "resolved_at",
        "created_at",
        "updated_at",
    )
    result = {}
    for name in names:
        first, *rest = name.split("_")
        value = getattr(row, name)
        if name.endswith("_at") and value is not None:
            value = _aware(value)
        result[first + "".join(part.title() for part in rest)] = value
    return result


def audit_action(session: Any, row: MobileActionCommitRow, actor_id: str, kind: str) -> None:
    session.add(
        AuditEventRow(
            id=str(uuid.uuid4()),
            tenant_id=row.tenant_id,
            actor_id=actor_id,
            actor_type="operator" if kind == "resolved" else "companion",
            resource_type="mobile_action_commit",
            resource_id=row.action_key,
            request_id=str(uuid.uuid4()),
            device_id=row.device_id,
            action=f"mobile.action.{kind}",
            metadata_json={
                "taskId": row.task_id,
                "actionKey": row.action_key,
                "status": row.status,
                "resolutionRevision": row.resolution_revision,
                "resolutionEvidence": row.resolution_evidence,
            },
            occurred_at=_now(),
            result="SUCCESS",
        )
    )


class MobileActionService:
    def __init__(self, mobile: MobileTaskService, public_keys: dict[str, str]) -> None:
        self.mobile = mobile
        self.public_keys = public_keys

    async def _owned(self, session: Any, binding: MobileBindingRow, task_id: str) -> MobileTaskRow:
        # Serialize with claim/enrollment before locking the task.
        device = await session.get(DeviceRow, binding.device_id, with_for_update=True)
        if device is None or device.active_binding_id != binding.id:
            raise ConflictError("Companion binding is no longer active")
        # Authentication touches binding then device. Do not invert that lock order;
        # the device lock already serializes active-binding replacement/enrollment.
        current = await session.get(MobileBindingRow, binding.id)
        if current is None or current.revoked_at is not None:
            raise ConflictError("Companion binding is no longer active")
        task = await session.get(MobileTaskRow, task_id, with_for_update=True)
        self.mobile._validate_owned_task(task, current)
        return task

    async def _lease(self, session: Any, task: MobileTaskRow, lease_id: str) -> None:
        self.mobile._validate_active_lease(task, lease_id)
        lease = await session.get(DeviceLeaseRow, task.device_id, with_for_update=True)
        if (
            lease is None
            or lease.lease_id != lease_id
            or lease.tenant_id != task.tenant_id
            or lease.canceled_at is not None
            or _aware(lease.expires_at) <= _now()
            or lease.owner_type != "AUTO"
            or lease.owner_workflow_id != f"auto/{task.id}"
        ):
            raise ConflictError("current device lease does not authorize this action")

    async def _identity(self, session: Any, task: MobileTaskRow, action_id: str) -> dict[str, Any]:
        if task.command_type is None and task.target_package == XIANYU_PACKAGE:
            frozen = steps_action_identity(task)
            if action_id != frozen["action_id"]:
                raise ConflictError("G3_NOT_ACCEPTED")
            return frozen
        if task.command_type != "device.probe_capabilities.v1":
            raise ConflictError("G3_NOT_ACCEPTED")
        pin = task.recipe_pin or {}
        package = await session.get(AutomationVersionRow, pin.get("versionId", ""))
        if package is None or package.tenant_id != task.tenant_id:
            raise ConflictError("signed pinned recipe required")
        value = package.manifest
        key = self.public_keys.get(value.get("signature", {}).get("keyId"))
        if not key:
            raise ConflictError("signed pinned recipe required")
        try:
            parsed = validate_recipe_package(value, public_key_base64=key)
        except ValueError as exc:
            raise ConflictError("signed pinned recipe invalid") from exc
        if parsed.manifest.app != COMPANION_PACKAGE or task.target_package != COMPANION_PACKAGE:
            raise ConflictError("G3_NOT_ACCEPTED")
        if (
            parsed.manifest.hash != pin.get("sha256")
            or package.artifact_sha256 != parsed.manifest.hash
            or parsed.manifest.signing_key_id != parsed.signature.key_id
            or task.command_type not in parsed.manifest.command_types
            or action_id not in {state.state_id for state in parsed.graph.states}
            or (parsed.graph.commit_action_id is not None and parsed.graph.commit_action_id != action_id)
        ):
            raise ConflictError("action does not match signed claim pin")
        live = await session.scalar(
            select(AccountDeviceBindingRow)
            .where(
                AccountDeviceBindingRow.tenant_id == task.tenant_id,
                AccountDeviceBindingRow.account_id == task.account_id,
                AccountDeviceBindingRow.device_id == task.device_id,
                AccountDeviceBindingRow.status == "BOUND",
            )
            .with_for_update()
        )
        if live is None or live.binding_version != task.binding_version:
            raise ConflictError("account binding changed")
        snapshot = (task.command_payload or {}).get("snapshotSha256", "")
        key, parameters = action_identity(
            task.id,
            task.command_type,
            task.account_id or "",
            task.binding_version or 0,
            snapshot,
            parsed.manifest.hash,
            action_id,
        )
        return dict(
            action_key=key,
            tenant_id=task.tenant_id,
            task_id=task.id,
            device_id=task.device_id,
            account_id=task.account_id,
            binding_version=task.binding_version,
            recipe_version_id=package.id,
            recipe_sha256=parsed.manifest.hash,
            snapshot_sha256=snapshot,
            action_id=action_id,
            parameter_hash=parameters,
        )

    @staticmethod
    def _matches(row: MobileActionCommitRow, frozen: dict[str, Any]) -> None:
        if any(getattr(row, name) != value for name, value in frozen.items()):
            raise ConflictError("immutable action identity changed")

    async def intent(self, binding: MobileBindingRow, task_id: str, body: IntentRequest):
        async with self.mobile.database.unit_of_work() as session:
            task = await self._owned(session, binding, task_id)
            frozen = await self._identity(session, task, body.action_id)
            await self._lease(session, task, body.lease_id)
            if (
                body.action_key != frozen["action_key"]
                or body.parameter_hash != frozen["parameter_hash"]
            ):
                raise ConflictError("action identity mismatch")
            row = await session.scalar(
                select(MobileActionCommitRow)
                .where(
                    MobileActionCommitRow.task_id == task.id,
                    MobileActionCommitRow.action_id == body.action_id,
                )
                .with_for_update()
            )
            if row is not None:
                self._matches(row, frozen)
                if row.before_evidence != body.before_evidence or row.lease_id != body.lease_id:
                    raise ConflictError("intent replay differs")
                return {"decision": "RECONCILE_REQUIRED", "action": action_view(row)}, False
            if task.status != "RUNNING" or task.business_state != "RUNNING":
                raise ConflictError("new intent requires RUNNING task")
            now = _now()
            row = MobileActionCommitRow(
                **frozen,
                lease_id=body.lease_id,
                status="INTENT",
                before_evidence=body.before_evidence,
                resolution_revision=0,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            task.business_state = "RECONCILING"
            audit_action(session, row, binding.id, "intent")
            await session.flush()
            return {"decision": "AUTHORIZED", "action": action_view(row)}, True

    async def outcome(
        self, binding: MobileBindingRow, task_id: str, key: str, body: OutcomeRequest
    ):
        async with self.mobile.database.unit_of_work() as session:
            task = await self._owned(session, binding, task_id)
            # Scope is enforced by _identity below for both probe and steps-publish shapes.
            row = await session.get(MobileActionCommitRow, key, with_for_update=True)
            if row is None or row.task_id != task.id or row.tenant_id != task.tenant_id:
                raise NotFoundError("action was not found")
            frozen = await self._identity(session, task, row.action_id)
            await self._lease(session, task, body.lease_id)
            self._matches(row, frozen)
            if body.parameter_hash != row.parameter_hash or body.lease_id != row.lease_id:
                raise ConflictError("outcome identity mismatch")
            if row.resolution_revision or task.business_state != "RECONCILING":
                raise ConflictError("action already resolved or task not reconciling")
            if row.status != "INTENT":
                if row.status != body.status or row.reported_evidence != body.evidence:
                    raise ConflictError("outcome replay differs")
                return action_view(row)
            if body.status == "APPLIED" and body.evidence == row.before_evidence:
                raise ConflictError("independent postcondition evidence required")
            row.status = body.status
            row.reported_evidence = body.evidence
            row.updated_at = _now()
            audit_action(session, row, binding.id, "outcome")
            return action_view(row)

    async def get(self, binding: MobileBindingRow, task_id: str, key: str):
        async with self.mobile.database.unit_of_work() as session:
            task = await self._owned(session, binding, task_id)
            row = await session.get(MobileActionCommitRow, key)
            if row is None or row.task_id != task.id or row.tenant_id != task.tenant_id:
                raise NotFoundError("action was not found")
            return action_view(row)
