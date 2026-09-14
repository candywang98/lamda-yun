"""Xianyu maintenance actions (polish / delist / delete-delisted).

Extends the frozen publish steps contract with three maintenance command
shapes anchored on the device-verified 2026-09-15 evidence
(contracts/phase1/xianyu-maintenance-anchors-20260915.md):

- ``xianyu.polish.steps.v1``: light risk, no ledger gated click, screenshot
  evidence mandatory.
- ``xianyu.delist.steps.v1``: destructive, one ledger-gated
  ``tapLayout(confirm_delist)`` plus an onsale badge delta assertion.
- ``xianyu.delete_delisted.steps.v1``: destructive, one ledger-gated
  ``tapLayout(confirm_delete)`` plus a delisted badge delta assertion.

The batch entry point creates one controlled steps task per target; each
destructive task carries its own step identity hash, so every gated confirm
click is authorized independently by the P09 action ledger.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Literal

from cloudctl_domain import (
    Actor,
    ConflictError,
    NotFoundError,
    Permission,
    ValidationError,
    require_permissions,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from .db import Database, DeviceRow, MobileTaskRow
from .mobile_actions import validate_maintenance_steps
from .mobile_schemas import MAX_CARD_INDEX, MobileTaskCreate
from .mobile_service import RUNNER_TO_BUSINESS, XIANYU_PACKAGE, MobileTaskService

NAV_TAP_TIMEOUT_MS = 8_000
LAYOUT_TAP_TIMEOUT_MS = 10_000
BADGE_ASSERT_TIMEOUT_MS = 15_000
SCREENSHOT_TIMEOUT_MS = 10_000
LOG_TIMEOUT_MS = 1_000
TOTAL_TIMEOUT_MARGIN_MS = 8_000
MAX_RUN_TASKS = 50
TERMINAL_BUSINESS = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"})
# Deterministic v5 namespace so a replayed run key resolves to the same run id.
RUN_ID_NAMESPACE = uuid.UUID("8f1d0b6e-4c2a-5d97-b3f0-6a21c9d4e770")
ACTION_COMMANDS: dict[str, str] = {
    "polish": "xianyu.polish.steps.v1",
    "delist": "xianyu.delist.steps.v1",
    "delete": "xianyu.delete_delisted.steps.v1",
}


def _tap(step_id: str, locator_ref: str) -> dict[str, Any]:
    return {
        "stepId": step_id,
        "action": "ui.tap",
        "locatorRef": locator_ref,
        "timeoutMs": NAV_TAP_TIMEOUT_MS,
    }


def _tap_layout(step_id: str, layout_ref: str, card_index: int | None = None) -> dict[str, Any]:
    step: dict[str, Any] = {
        "stepId": step_id,
        "action": "ui.tapLayout",
        "layoutRef": layout_ref,
        "timeoutMs": LAYOUT_TAP_TIMEOUT_MS,
    }
    if card_index is not None:
        step["cardIndex"] = card_index
    return step


def _screenshot(label: str) -> dict[str, Any]:
    return {
        "stepId": f"capture-{label}",
        "action": "ui.screenshot",
        "label": label,
        "timeoutMs": SCREENSHOT_TIMEOUT_MS,
    }


def _assert_badge(tab: str) -> dict[str, Any]:
    return {
        "stepId": f"assert-badge-{tab}",
        "action": "ui.assertBadge",
        "tab": tab,
        "delta": -1,
        "timeoutMs": BADGE_ASSERT_TIMEOUT_MS,
    }


def _log(message_code: str) -> dict[str, Any]:
    return {
        "stepId": "mark-done",
        "action": "run.log",
        "level": "INFO",
        "messageCode": message_code,
        "timeoutMs": LOG_TIMEOUT_MS,
    }


def build_polish_steps() -> list[dict[str, Any]]:
    return [
        _tap("open-profile", "xianyu_profile_tab"),
        _tap("open-my-published", "xianyu_my_published"),
        _tap_layout("tap-polish-all", "polish_all"),
        _screenshot("xianyu_polish_all"),
        _log("XIANYU_POLISH_DONE"),
    ]


def build_delist_steps(card_index: int) -> list[dict[str, Any]]:
    return [
        _tap("open-profile", "xianyu_profile_tab"),
        _tap("open-my-published", "xianyu_my_published"),
        _tap_layout("open-card-menu", "more", card_index),
        _screenshot("xianyu_delist_menu"),
        _tap_layout("tap-delist-item", "delist_menu_item"),
        _screenshot("xianyu_delist_confirm"),
        _tap_layout("confirm-delist", "confirm_delist"),
        _assert_badge("onsale"),
        _screenshot("xianyu_delist_result"),
        _log("XIANYU_DELIST_DONE"),
    ]


def build_delete_delisted_steps(card_index: int) -> list[dict[str, Any]]:
    return [
        _tap("open-profile", "xianyu_profile_tab"),
        _tap("open-my-published", "xianyu_my_published"),
        _tap("open-delisted-tab", "xianyu_pub_tab_delisted"),
        _tap_layout("tap-delete-card", "delete_card", card_index),
        _screenshot("xianyu_delete_confirm"),
        _tap_layout("confirm-delete", "confirm_delete"),
        _assert_badge("delisted"),
        _screenshot("xianyu_delete_result"),
        _log("XIANYU_DELETE_DELISTED_DONE"),
    ]


def build_maintenance_steps(action: str, card_index: int | None) -> list[dict[str, Any]]:
    if action == "polish":
        return build_polish_steps()
    if action == "delist":
        return build_delist_steps(card_index or 0)
    if action == "delete":
        return build_delete_delisted_steps(card_index or 0)
    raise ValidationError(f"unknown maintenance action: {action}")


class MaintenanceTargets(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    all: bool = Field(default=False)
    card_indices: list[int] = Field(
        default_factory=list, alias="cardIndices", max_length=MAX_RUN_TASKS
    )
    card_limit: int | None = Field(
        default=None, alias="cardLimit", ge=1, le=MAX_RUN_TASKS
    )
    title_contains: str | None = Field(
        default=None, alias="titleContains", min_length=1, max_length=128
    )


class XianyuMaintenanceRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    device_id: str = Field(alias="deviceId", min_length=1, max_length=36)
    action: Literal["polish", "delist", "delete"]
    account_id: str | None = Field(default=None, alias="accountId", min_length=1, max_length=36)
    targets: MaintenanceTargets = Field(default_factory=MaintenanceTargets)

    @model_validator(mode="after")
    def validate_targets(self) -> XianyuMaintenanceRunRequest:
        targets = self.targets
        if targets.title_contains is not None:
            raise ValueError(
                "titleContains filtering is not implemented yet; enumerate cardIndices"
            )
        if any(not 0 <= index <= MAX_CARD_INDEX for index in targets.card_indices):
            raise ValueError(f"cardIndices must be within 0..{MAX_CARD_INDEX}")
        if self.action == "polish":
            if targets.all or targets.card_indices or targets.card_limit is not None:
                raise ValueError("polish is a single one-tap task and takes no targets")
            return self
        if targets.all and targets.card_indices:
            raise ValueError("choose either targets.all or targets.cardIndices, not both")
        if targets.all:
            if targets.card_limit is None:
                raise ValueError(
                    "targets.all requires cardLimit: the server cannot read the on-device "
                    "badge count, so the sweep must stay bounded"
                )
        elif targets.card_indices:
            if targets.card_limit is not None:
                raise ValueError("cardLimit only applies to targets.all")
        else:
            raise ValueError("delist/delete require targets: all or cardIndices")
        return self


class XianyuMaintenanceService:
    """Batch orchestration over the existing controlled steps task queue."""

    def __init__(self, database: Database, mobile: MobileTaskService) -> None:
        self.database = database
        self.mobile = mobile

    async def run(
        self, actor: Actor, key: str, body: XianyuMaintenanceRunRequest
    ) -> tuple[dict[str, Any], bool]:
        # Same write permission model as the operator IM reply endpoint.
        require_permissions(actor.roles, Permission.DEVICE_CONTROL)
        if not key or len(key) > 100:
            raise ValidationError("Idempotency-Key is required and must be at most 100 characters")
        tenant_id = str(actor.tenant_id)
        run_id = str(uuid.uuid5(RUN_ID_NAMESPACE, f"{tenant_id}:maintenance:{key}"))
        async with self.database.unit_of_work() as session:
            device = await session.get(DeviceRow, body.device_id)
            if device is None or device.tenant_id != tenant_id:
                raise NotFoundError("device was not found")
        run_suffix = hashlib.sha256(run_id.encode()).hexdigest()[:8]
        created_any = False
        tasks: list[dict[str, Any]] = []
        for sequence, target in enumerate(self._expand_targets(body), start=1):
            label, card_index = target
            steps = build_maintenance_steps(body.action, card_index)
            command = validate_maintenance_steps(XIANYU_PACKAGE, steps)
            task_key = f"maintenance-{body.action}-{body.device_id}-{label}-{sequence}-{run_suffix}"
            payload: dict[str, Any] = {
                "deviceId": body.device_id,
                "targetPackage": XIANYU_PACKAGE,
                "totalTimeoutMs": sum(int(step["timeoutMs"]) for step in steps)
                + TOTAL_TIMEOUT_MARGIN_MS,
                "steps": steps,
            }
            if body.account_id:
                payload["accountId"] = body.account_id
            view, created = await self.mobile._insert_task(
                tenant_id=tenant_id,
                requested_by=str(actor.user_id),
                key=task_key,
                body=MobileTaskCreate.model_validate(payload),
            )
            created_any = created_any or created
            if created:
                await self._stamp_run_fields(
                    task_id=str(view["taskId"]),
                    run_id=run_id,
                    action=body.action,
                    command_type=command,
                    card_index=card_index,
                    sequence=sequence,
                )
            tasks.append(
                {
                    "taskId": view["taskId"],
                    "idempotencyKey": task_key,
                    "action": body.action,
                    "commandType": command,
                    "cardIndex": card_index,
                    "sequence": sequence,
                    "state": view.get("businessState") or view.get("status"),
                    "createdAt": view.get("createdAt"),
                }
            )
        return (
            {
                "runId": run_id,
                "deviceId": body.device_id,
                "action": body.action,
                "commandType": ACTION_COMMANDS[body.action],
                "targetCount": len(tasks),
                "taskIds": [task["taskId"] for task in tasks],
                "tasks": tasks,
            },
            created_any,
        )

    async def get_run(self, actor: Actor, run_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_READ)
        if not run_id or len(run_id) > 36:
            raise NotFoundError("maintenance run was not found")
        async with self.database.unit_of_work() as session:
            rows = list(
                await session.scalars(
                    select(MobileTaskRow)
                    .where(
                        MobileTaskRow.tenant_id == str(actor.tenant_id),
                        MobileTaskRow.batch_id == run_id,
                    )
                    .order_by(MobileTaskRow.created_at, MobileTaskRow.id)
                )
            )
        if not rows:
            raise NotFoundError("maintenance run was not found")
        tasks = []
        summary: dict[str, int] = {}
        for row in rows:
            header = (row.steps or [{}])[0] or {}
            meta = header.get("maintenance") or {}
            state = row.business_state or RUNNER_TO_BUSINESS.get(row.status, row.status)
            summary[state] = summary.get(state, 0) + 1
            tasks.append(
                {
                    "taskId": row.id,
                    "idempotencyKey": row.idempotency_key,
                    "action": meta.get("action"),
                    "commandType": meta.get("commandType"),
                    "cardIndex": meta.get("cardIndex"),
                    "sequence": meta.get("sequence"),
                    "state": state,
                    "runnerStatus": row.status,
                    "errorCode": row.error_code,
                    "stallReason": row.stall_reason,
                    "createdAt": row.created_at,
                    "completedAt": row.completed_at,
                }
            )
        terminal = sum(count for state, count in summary.items() if state in TERMINAL_BUSINESS)
        first_meta = ((rows[0].steps or [{}])[0] or {}).get("maintenance") or {}
        return {
            "runId": run_id,
            "deviceId": rows[0].device_id,
            "action": first_meta.get("action"),
            "commandType": first_meta.get("commandType"),
            "taskCount": len(rows),
            "summary": summary,
            "allTerminal": terminal == len(rows),
            "tasks": tasks,
        }

    @staticmethod
    def _expand_targets(body: XianyuMaintenanceRunRequest) -> list[tuple[str, int | None]]:
        if body.action == "polish":
            return [("all", None)]
        if body.targets.all:
            return [(str(index), index) for index in range(body.targets.card_limit or 0)]
        return [(str(index), index) for index in sorted(set(body.targets.card_indices))]

    async def _stamp_run_fields(
        self,
        *,
        task_id: str,
        run_id: str,
        action: str,
        command_type: str,
        card_index: int | None,
        sequence: int,
    ) -> None:
        """Group the task under its run without touching the hashed steps body.

        The header entry carries no ``action`` key, so the Companion step hash
        (and therefore the ledger gated identity) is unaffected; this mirrors
        how claim/resume prepend controlEpoch metadata.
        """

        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None:
                raise NotFoundError("platform task was not found")
            if row.batch_id not in (None, run_id):
                raise ConflictError("task already belongs to another maintenance run")
            row.batch_id = run_id
            header = dict((row.steps or [{}])[0] or {})
            header["maintenance"] = {
                "runId": run_id,
                "action": action,
                "commandType": command_type,
                "cardIndex": card_index,
                "sequence": sequence,
            }
            row.steps = [header, *list(row.steps or [])[1:]]
