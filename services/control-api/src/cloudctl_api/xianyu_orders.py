"""Xianyu order collection orchestration (order-sync/20260915.1, slice2 §1/§2).

One controlled steps task per run: navigate to the sold/bought order list,
read the visible rows with ui.readOrders, screenshot evidence, closing
run.log. screens=1 keeps the validated v1 shape (exactly one read); screens
2..3 use the v2 multi-screen shape where each extra screen is one ui.swipeUp
on the list container followed by one ui.readOrders. The task is read-only
(no ledger-gated click); the frozen step shape itself is the gate. Run
grouping follows the maintenance batch pattern: MobileTaskRow.batch_id =
uuid5 run id, orchestration metadata lives in the steps[0] header under
"orderCollection" and never carries an "action" key, so the Companion step
hash identity is unaffected. Screen ordinals never enter the hashed step
bodies: readOrders/swipeUp carry exactly the slice1 parameter set, the
ordinal appears only in per-screen stepIds (uniqueness is mandatory) and in
runtime LOG events (ORDERS_READ_N).
"""

from __future__ import annotations

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
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .db import Database, DeviceRow, MobileTaskEventRow, MobileTaskRow
from .mobile_actions import (
    ORDERS_LOG_CODE,
    ORDERS_MAX_SCREENS,
    ORDERS_READ_LOCATOR,
    validate_orders_steps,
)
from .mobile_schemas import MobileTaskCreate
from .mobile_service import RUNNER_TO_BUSINESS, XIANYU_PACKAGE, MobileTaskService
from .xianyu_maintenance import (
    LOG_TIMEOUT_MS,
    NAV_TAP_TIMEOUT_MS,
    SCREENSHOT_TIMEOUT_MS,
    TOTAL_TIMEOUT_MARGIN_MS,
)

READ_ORDERS_TIMEOUT_MS = 20_000
SWIPE_ORDERS_TIMEOUT_MS = 8_000
# Per-screen read LOG events (ORDERS_READ_1..N) aggregated into the run view.
ORDERS_READ_LOG_PREFIX = "ORDERS_READ_"
TERMINAL_BUSINESS = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"})
# Deterministic v5 namespace so a replayed run key resolves to the same run id.
ORDERS_RUN_ID_NAMESPACE = uuid.UUID("5d3a1c7f-9e42-5b18-a6d4-83f0c2e5b914")


def _tap(step_id: str, locator_ref: str) -> dict[str, Any]:
    return {
        "stepId": step_id,
        "action": "ui.tap",
        "locatorRef": locator_ref,
        "timeoutMs": NAV_TAP_TIMEOUT_MS,
    }


def _screenshot(label: str) -> dict[str, Any]:
    return {
        "stepId": f"capture-{label}",
        "action": "ui.screenshot",
        "label": label,
        "timeoutMs": SCREENSHOT_TIMEOUT_MS,
    }


def _log(message_code: str) -> dict[str, Any]:
    return {
        "stepId": "mark-done",
        "action": "run.log",
        "level": "INFO",
        "messageCode": message_code,
        "timeoutMs": LOG_TIMEOUT_MS,
    }


def _read_orders(step_id: str, direction: str, max_rows: int) -> dict[str, Any]:
    return {
        "stepId": step_id,
        "action": "ui.readOrders",
        "locatorRef": ORDERS_READ_LOCATOR,
        "direction": direction,
        "maxRows": max_rows,
        "timeoutMs": READ_ORDERS_TIMEOUT_MS,
    }


def _swipe_up(step_id: str) -> dict[str, Any]:
    return {
        "stepId": step_id,
        "action": "ui.swipeUp",
        "locatorRef": ORDERS_READ_LOCATOR,
        "timeoutMs": SWIPE_ORDERS_TIMEOUT_MS,
    }


def build_collect_orders_steps(direction: str, max_rows: int) -> list[dict[str, Any]]:
    """Frozen shape xianyu.collect_orders.steps.v1 (contract §5, fixed order)."""

    entry = "xianyu_order_list_sold" if direction == "SOLD" else "xianyu_order_list_bought"
    return [
        _tap("open-profile", "xianyu_profile_tab"),
        _tap("open-order-list", entry),
        _read_orders("read-orders", direction, max_rows),
        _screenshot("xianyu_collect_orders"),
        _log(ORDERS_LOG_CODE),
    ]


def build_collect_orders_steps_v2(
    direction: str, max_rows: int, screens: int
) -> list[dict[str, Any]]:
    """Frozen shape xianyu.collect_orders.steps.v2 (order-sync-slice2 §1).

    Same navigation and closing as v1; each extra screen is one ui.swipeUp on
    the list container followed by one ui.readOrders. max_rows stays the
    per-screen cap; no ``screen`` field is added to the hashed step bodies.
    """

    entry = "xianyu_order_list_sold" if direction == "SOLD" else "xianyu_order_list_bought"
    steps = [
        _tap("open-profile", "xianyu_profile_tab"),
        _tap("open-order-list", entry),
        _read_orders("read-orders", direction, max_rows),
    ]
    for screen in range(2, screens + 1):
        steps.append(_swipe_up(f"swipe-up-{screen}"))
        steps.append(_read_orders(f"read-orders-{screen}", direction, max_rows))
    steps.append(_screenshot("xianyu_collect_orders"))
    steps.append(_log(ORDERS_LOG_CODE))
    return steps


class XianyuOrdersCollectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    device_id: str = Field(alias="deviceId", min_length=1, max_length=36)
    direction: Literal["SOLD", "BOUGHT"]
    max_rows: int = Field(alias="maxRows", ge=1, le=10)
    screens: int = Field(default=1, ge=1, le=ORDERS_MAX_SCREENS)


class XianyuOrdersService:
    """Collect-run orchestration over the existing controlled steps task queue."""

    def __init__(self, database: Database, mobile: MobileTaskService) -> None:
        self.database = database
        self.mobile = mobile

    async def run(
        self, actor: Actor, key: str, body: XianyuOrdersCollectRequest
    ) -> tuple[dict[str, Any], bool]:
        # Same write permission model as the operator maintenance run endpoint.
        require_permissions(actor.roles, Permission.DEVICE_CONTROL)
        if not key or len(key) > 100:
            raise ValidationError("Idempotency-Key is required and must be at most 100 characters")
        tenant_id = str(actor.tenant_id)
        # screens joins the uuid5 material only for the v2 (multi-screen) form:
        # the default screens=1 path keeps the exact v1 derivation so already
        # accepted runs replay to the same run id after this deploy.
        run_material = f"{tenant_id}:xianyu-orders-collect:{key}"
        if body.screens != 1:
            run_material = f"{run_material}:{body.screens}"
        run_id = str(uuid.uuid5(ORDERS_RUN_ID_NAMESPACE, run_material))
        async with self.database.unit_of_work() as session:
            device = await session.get(DeviceRow, body.device_id)
            if device is None or device.tenant_id != tenant_id:
                raise NotFoundError("device was not found")
        steps = (
            build_collect_orders_steps(body.direction, body.max_rows)
            if body.screens == 1
            else build_collect_orders_steps_v2(body.direction, body.max_rows, body.screens)
        )
        command = validate_orders_steps(XIANYU_PACKAGE, steps)
        run_suffix = run_id.replace("-", "")[:8]
        task_key = f"xianyu-collect-orders-{body.device_id}-{body.direction}-{run_suffix}"
        payload: dict[str, Any] = {
            "deviceId": body.device_id,
            "targetPackage": XIANYU_PACKAGE,
            "totalTimeoutMs": sum(int(step["timeoutMs"]) for step in steps)
            + TOTAL_TIMEOUT_MARGIN_MS,
            "steps": steps,
        }
        view, created = await self.mobile._insert_task(
            tenant_id=tenant_id,
            requested_by=str(actor.user_id),
            key=task_key,
            body=MobileTaskCreate.model_validate(payload),
        )
        if created:
            await self._stamp_run_fields(
                task_id=str(view["taskId"]),
                run_id=run_id,
                direction=body.direction,
                max_rows=body.max_rows,
                command_type=command,
                screens=body.screens,
            )
        task = {
            "taskId": view["taskId"],
            "idempotencyKey": task_key,
            "commandType": command,
            "direction": body.direction,
            "maxRows": body.max_rows,
            "state": view.get("businessState") or view.get("status"),
            "createdAt": view.get("createdAt"),
        }
        run_view = {
            "runId": run_id,
            "deviceId": body.device_id,
            "direction": body.direction,
            "maxRows": body.max_rows,
            "commandType": command,
            "targetCount": 1,
            "taskIds": [task["taskId"]],
            "tasks": [task],
        }
        if body.screens != 1:
            task["screens"] = body.screens
            run_view["screens"] = body.screens
        return (run_view, created)

    async def get_run(self, actor: Actor, run_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_READ)
        if not run_id or len(run_id) > 36:
            raise NotFoundError("order collection run was not found")
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
            log_events = (
                list(
                    await session.scalars(
                        select(MobileTaskEventRow)
                        .where(
                            MobileTaskEventRow.tenant_id == str(actor.tenant_id),
                            MobileTaskEventRow.task_id.in_([row.id for row in rows]),
                            MobileTaskEventRow.event_type == "LOG",
                        )
                        .order_by(MobileTaskEventRow.task_id, MobileTaskEventRow.sequence)
                    )
                )
                if rows
                else []
            )
        if not rows:
            raise NotFoundError("order collection run was not found")
        # Minimal slice2 aggregation: per-screen ORDERS_READ_N LOG events from
        # any task in the run are visible in one place. Other LOG events are
        # ignored here (the per-task event feed stays the detailed view).
        orders_read_logs = [
            {
                "taskId": event.task_id,
                "sequence": event.sequence,
                "stepId": event.step_id,
                "messageCode": code,
                "occurredAt": event.occurred_at,
            }
            for event in log_events
            if isinstance(code := event.payload.get("messageCode"), str)
            and code.startswith(ORDERS_READ_LOG_PREFIX)
        ]
        tasks = []
        summary: dict[str, int] = {}
        for row in rows:
            header = (row.steps or [{}])[0] or {}
            meta = header.get("orderCollection") or {}
            state = row.business_state or RUNNER_TO_BUSINESS.get(row.status, row.status)
            summary[state] = summary.get(state, 0) + 1
            task = {
                "taskId": row.id,
                "idempotencyKey": row.idempotency_key,
                "commandType": meta.get("commandType"),
                "direction": meta.get("direction"),
                "maxRows": meta.get("maxRows"),
                "state": state,
                "runnerStatus": row.status,
                "errorCode": row.error_code,
                "stallReason": row.stall_reason,
                "createdAt": row.created_at,
                "completedAt": row.completed_at,
            }
            if meta.get("screens") is not None:
                task["screens"] = meta["screens"]
            tasks.append(task)
        terminal = sum(count for state, count in summary.items() if state in TERMINAL_BUSINESS)
        first_meta = ((rows[0].steps or [{}])[0] or {}).get("orderCollection") or {}
        run = {
            "runId": run_id,
            "deviceId": rows[0].device_id,
            "direction": first_meta.get("direction"),
            "maxRows": first_meta.get("maxRows"),
            "commandType": first_meta.get("commandType"),
            "taskCount": len(rows),
            "summary": summary,
            "allTerminal": terminal == len(rows),
            "tasks": tasks,
        }
        if first_meta.get("screens") is not None:
            run["screens"] = first_meta["screens"]
        if orders_read_logs:
            run["ordersReadLogs"] = orders_read_logs
        return run

    async def _stamp_run_fields(
        self,
        *,
        task_id: str,
        run_id: str,
        direction: str,
        max_rows: int,
        command_type: str,
        screens: int = 1,
    ) -> None:
        """Group the task under its run without touching the hashed steps body.

        The header entry carries no ``action`` key (the metadata block is
        nested under "orderCollection"), so the Companion step hash and the
        P09 identity invariants are unaffected; this mirrors the maintenance
        run stamping. ``screens`` is stored only for multi-screen (v2) runs so
        the accepted v1 header stays byte-identical.
        """

        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None:
                raise NotFoundError("platform task was not found")
            if row.batch_id not in (None, run_id):
                raise ConflictError("task already belongs to another collection run")
            row.batch_id = run_id
            header = dict((row.steps or [{}])[0] or {})
            meta = {
                "runId": run_id,
                "direction": direction,
                "maxRows": max_rows,
                "commandType": command_type,
            }
            if screens != 1:
                meta["screens"] = screens
            header["orderCollection"] = meta
            row.steps = [header, *list(row.steps or [])[1:]]
