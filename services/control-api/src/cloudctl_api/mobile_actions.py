"""P09 controlled action ledger. One legacy idlefish publish shape; no auto reconciliation."""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Annotated, Any, Literal

from cloudctl_automation_sdk.recipe import validate_recipe_package
from cloudctl_domain import ConflictError, NotFoundError, ValidationError
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


STEPS_SHAPES = {
    XIANYU_PACKAGE: {
        "command_type": "xianyu.publish_listing.steps.v1",
        "publish_button": "xianyu_publish_button",
        "postcondition": "xianyu_publish_success",
        "content_input": "xianyu_description",
    },
    "com.xingin.xhs": {
        "command_type": "xhs.publish_note.steps.v1",
        "publish_button": "xhs_publish_button",
        "postcondition": "xhs_publish_success",
        "content_input": "xhs_note_body",
    },
    "com.ss.android.ugc.aweme": {
        "command_type": "douyin.publish_note.steps.v1",
        "publish_button": "dy_publish_button",
        "postcondition": "dy_publish_success",
        "content_input": "dy_note_body",
    },
}


def _steps_action_row(
    command_type: str, action_id: str, task: MobileTaskRow, steps: list[dict[str, Any]]
) -> dict[str, Any]:
    digest = hashlib.sha256(canonical_steps(steps).encode()).hexdigest()
    key, parameters = action_identity(
        task.id,
        command_type,
        task.device_id,
        task.binding_version or 0,
        digest,
        digest,
        action_id,
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
        action_id=action_id,
        parameter_hash=parameters,
    )


def steps_action_identity(task: MobileTaskRow) -> dict[str, Any]:
    # The claim path prepends a dynamic header entry (controlEpoch/lease fields,
    # no "action" key) to the stored steps; identity covers the real steps only,
    # exactly matching what the Companion hashes from its claimed payload.
    steps = [step for step in (task.steps or []) if step.get("action")]
    shape = STEPS_SHAPES.get(task.target_package or "")
    if shape is not None and _publish_shape_matches(shape, steps):
        return _steps_action_row(shape["command_type"], STEPS_ACTION_ID, task, steps)
    for command_type, maintenance in XIANYU_MAINTENANCE_SHAPES.items():
        if maintenance["action_id"] is None:
            # Light-risk shapes (polish) have no ledger gated click by contract.
            continue
        if _maintenance_shape_error(maintenance, steps) is None:
            return _steps_action_row(command_type, maintenance["action_id"], task, steps)
    raise ConflictError("G3_NOT_ACCEPTED")


def _publish_shape_matches(shape: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    publish_taps = [
        step
        for step in steps
        if step.get("action") == "ui.tap" and step.get("locatorRef") == shape["publish_button"]
    ]
    has_postcondition = any(step.get("locatorRef") == shape["postcondition"] for step in steps)
    has_description = any(
        step.get("action") == "ui.input" and step.get("locatorRef") == shape["content_input"]
        for step in steps
    )
    return len(publish_taps) == 1 and has_postcondition and has_description


# Frozen xianyu maintenance shapes against the device-verified 20260915 anchors.
# "screenshot_rules" entries are ("between", layoutA, layoutB) evidence captured
# before the gated confirm, or ("after_layout", layout) / ("after_badge", None)
# post-effect evidence requirements.
XIANYU_MAINTENANCE_SHAPES: dict[str, dict[str, Any]] = {
    "xianyu.polish.steps.v1": {
        "package": XIANYU_PACKAGE,
        "action": "polish",
        "action_id": None,
        "navigation": ("xianyu_profile_tab", "xianyu_my_published"),
        "layout_taps": {"polish_all": {"count": 1, "tab": "onsale", "max_card": 0}},
        "gated_layout": None,
        "badge": None,
        "screenshot_rules": (("after_layout", "polish_all"),),
        "log_code": "XIANYU_POLISH_DONE",
    },
    "xianyu.delist.steps.v1": {
        "package": XIANYU_PACKAGE,
        "action": "delist",
        "action_id": "confirm-delist",
        "navigation": ("xianyu_profile_tab", "xianyu_my_published"),
        "layout_taps": {
            "more": {"count": 1, "tab": "onsale", "max_card": 0},
            "delist_menu_item": {"count": 1, "tab": "onsale", "max_card": 0},
            "confirm_delist": {"count": 1, "tab": "onsale", "max_card": 0},
        },
        "gated_layout": "confirm_delist",
        "badge": {"locator": "xianyu_pub_tab_onsale", "delta": -1},
        "screenshot_rules": (
            ("between", "more", "delist_menu_item"),
            ("between", "delist_menu_item", "confirm_delist"),
            ("after_badge", None),
        ),
        "log_code": "XIANYU_DELIST_DONE",
    },
    "xianyu.delete_delisted.steps.v1": {
        "package": XIANYU_PACKAGE,
        "action": "delete",
        "action_id": "confirm-delete",
        "navigation": (
            "xianyu_profile_tab",
            "xianyu_my_published",
            "xianyu_pub_tab_delisted",
        ),
        "layout_taps": {
            "delete_card": {"count": 1, "tab": "delisted", "max_card": 2},
            "confirm_delete": {"count": 1, "tab": "delisted", "max_card": 0},
        },
        "gated_layout": "confirm_delete",
        "badge": {"locator": "xianyu_pub_tab_delisted", "delta": -1},
        "screenshot_rules": (
            ("between", "delete_card", "confirm_delete"),
            ("after_badge", None),
        ),
        "log_code": "XIANYU_DELETE_DELISTED_DONE",
    },
}
MAINTENANCE_STEP_ACTIONS = frozenset({"ui.tapLayout", "ui.assertBadge"})


def uses_maintenance_step_actions(steps: list[dict[str, Any]]) -> bool:
    return any(step.get("action") in MAINTENANCE_STEP_ACTIONS for step in steps)


def _step_index(steps: list[dict[str, Any]], predicate: Any) -> int:
    return next(position for position, step in enumerate(steps) if predicate(step))


def _layout_index(steps: list[dict[str, Any]], layout: str) -> int:
    return _step_index(
        steps,
        lambda step: step.get("action") == "ui.tapLayout" and step.get("layoutAction") == layout,
    )


def _maintenance_shape_error(shape: dict[str, Any], steps: list[dict[str, Any]]) -> str | None:
    """Return the first shape violation, or None when the steps match exactly."""

    command = f"{shape['action']} ({shape['package']})"
    layout_steps = [step for step in steps if step.get("action") == "ui.tapLayout"]
    badge_steps = [step for step in steps if step.get("action") == "ui.assertBadge"]
    tap_steps = [step for step in steps if step.get("action") == "ui.tap"]
    for ref in shape["navigation"]:
        hits = [step for step in tap_steps if step.get("locatorRef") == ref]
        if len(hits) != 1:
            return f"{command}: navigation tap {ref} must appear exactly once"
    for step in tap_steps:
        if step.get("locatorRef") not in shape["navigation"]:
            return f"{command}: ui.tap to {step.get('locatorRef')} is not part of the shape"
    for layout, rule in shape["layout_taps"].items():
        hits = [step for step in layout_steps if step.get("layoutAction") == layout]
        if len(hits) != rule["count"]:
            return f"{command}: tapLayout({layout}) must appear exactly {rule['count']} time(s)"
        for hit in hits:
            # Companion contract: layoutAction + tab + cardIndex always present.
            if hit.get("tab") != rule["tab"]:
                return f"{command}: tapLayout({layout}) requires tab {rule['tab']}"
            card = hit.get("cardIndex")
            if not isinstance(card, int) or not 0 <= card <= rule["max_card"]:
                return (
                    f"{command}: tapLayout({layout}) cardIndex must be 0..{rule['max_card']}"
                )
    for step in layout_steps:
        if step.get("layoutAction") not in shape["layout_taps"]:
            return f"{command}: tapLayout({step.get('layoutAction')}) is not part of the shape"
    if shape["badge"] is None:
        if badge_steps:
            return f"{command}: badge assertions are not part of this shape"
    else:
        if len(badge_steps) != 1:
            return f"{command}: exactly one ui.assertBadge step is required"
        badge = badge_steps[0]
        expected = shape["badge"]
        if badge.get("locatorRef") != expected["locator"] or badge.get("expectedDelta") != expected["delta"]:
            return (
                f"{command}: badge assertion must verify {expected['locator']} delta "
                f"{expected['delta']}"
            )
    shots = [
        position for position, step in enumerate(steps) if step.get("action") == "ui.screenshot"
    ]
    if layout_steps:
        first_layout = min(steps.index(step) for step in layout_steps)
        nav_indexes = [
            _step_index(
                steps,
                lambda step, ref=ref: step.get("action") == "ui.tap"
                and step.get("locatorRef") == ref,
            )
            for ref in shape["navigation"]
        ]
        if max(nav_indexes) > first_layout:
            return f"{command}: navigation must complete before the first layout tap"
    if shape["gated_layout"] is not None:
        gated_index = _layout_index(steps, shape["gated_layout"])
        if shape["badge"] is not None:
            badge_index = _step_index(steps, lambda step: step.get("action") == "ui.assertBadge")
            if badge_index < gated_index:
                return f"{command}: badge assertion must follow the gated confirm tap"
    for rule in shape["screenshot_rules"]:
        if rule[0] == "between":
            low = _layout_index(steps, rule[1])
            high = _layout_index(steps, rule[2])
            if not any(low < shot < high for shot in shots):
                return f"{command}: a screenshot is required between {rule[1]} and {rule[2]}"
        elif rule[0] == "after_layout":
            low = _layout_index(steps, rule[1])
            if not any(shot > low for shot in shots):
                return f"{command}: a screenshot is required after {rule[1]}"
        else:  # after_badge
            badge_index = _step_index(steps, lambda step: step.get("action") == "ui.assertBadge")
            if not any(shot > badge_index for shot in shots):
                return f"{command}: a screenshot is required after the badge assertion"
    if not any(
        step.get("action") == "run.log" and step.get("messageCode") == shape["log_code"]
        for step in steps
    ):
        return f"{command}: closing run.log {shape['log_code']} is required"
    return None


def validate_maintenance_steps(package: str, steps: list[dict[str, Any]]) -> str:
    """Creation gate: steps using maintenance actions must match exactly one frozen shape."""

    if not uses_maintenance_step_actions(steps):
        raise ValidationError("maintenance step actions are required for this validation")
    matches = [
        command
        for command, shape in XIANYU_MAINTENANCE_SHAPES.items()
        if shape["package"] == package and _maintenance_shape_error(shape, steps) is None
    ]
    if len(matches) != 1:
        raise ValidationError(
            "xianyu maintenance steps must match exactly one frozen command shape "
            "(one gated confirm tap, post-badge assertion, required screenshots)"
        )
    return matches[0]

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
        if task.command_type is None and task.target_package in STEPS_SHAPES:
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
