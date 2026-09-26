"""X10 — P09 delete evidence loop: approval ledger + A13 reconciliation.

Covers the backend half of the delete evidence loop (services/control-api
xianyu_delete_evidence.py) against the REAL frozen A13 controlled-action
ledger: every result report is reconciled with the mobile_action_commit row
of the frozen confirm-delete action, the single confirm issuance mirrors the
destructiveGate single grant, and protection period is an explicit rejection
(no queue, no countdown, no auto re-delete of unresolved tasks).

Device-side fail-closed classes (误卡/同名/旧窗口/无目标ID/证据不足 before any
strike) live in the Android orchestrator tests under
mobile/companion/app/src/test/java/com/company/cloudctl/companion/features/
xianyu/maintenance/delete/; this module keeps the server-side twins:
evidence sufficiency at approval creation and result/ledger consistency.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import MobileActionCommitRow
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import select
from test_platform_tasks import create_direct_device, identity
from test_xianyu_maintenance import _start_task, delete_v2_steps

XIANYU = "com.taobao.idlefish"

# ---------------------------------------------------------------------------
# Real-device acceptance runbook (software-only wave: this documents the
# executable script; the physical run needs the user-listed deletable items)
# ---------------------------------------------------------------------------
# Prerequisites (enforced, not assumed):
#   1. The operator lists the deletable test items explicitly (title +
#      platformItemId where readable). NOTHING outside that list is approved.
#   2. Each item gets one approval row: POST /api/v1/xianyu/delete/approvals
#      {deviceId, accountId, identityEvidence{platformItemId|title+price+
#      listingState}, validUntil}. Faceless targets are rejected (422).
# Step 1 (cancel loop first — prove safe arrival and retreat):
#   - run the companion CANCEL_LOOP plan on ONE listed item: title-locate ->
#     detail -> manage menu -> delete confirm dialog -> CANCEL -> zero side
#     effects; record :abort (ABORTED_BY_OPERATOR). Only after a clean cancel
#     loop may any delete be authorized.
# Step 2 (single authorized delete, one item at a time):
#   - :issue-confirm exactly once for the item's taskId (v2 delete task),
#     destructiveGate single strike, outcome reported (APPLIED|UNKNOWN).
# Step 3 (readback + report):
#   - list disappearance + delisted badge N-1 -> POST /results
#     VERIFIED_DELETED; badge gate missing -> PENDING_VERIFICATION (held for
#     the operator, never fabricated success).
# Step 4 (protection discipline):
#   - an UNKNOWN/unresolved attempt locks the target: new approvals 409
#     PROTECTION_PERIOD until the operator resolves (platform-task reconcile
#     first, then :resolve). UNKNOWN tasks are never auto re-deleted.
REAL_DEVICE_ACCEPTANCE_STEPS = (
    "user-listed deletable items only",
    "cancel loop first (zero side effects, ABORTED_BY_OPERATOR)",
    "one issue-confirm per approval",
    "readback VERIFIED_DELETED or PENDING_VERIFICATION (never fabricated)",
    "UNKNOWN locks the target until operator resolution (no auto re-delete)",
)


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


async def _create_approval(
    client: httpx.AsyncClient,
    device: str,
    *,
    platform_item_id: str | None = "7123456789",
    title: str | None = "用户列明可删测试品-01",
    price: str | None = "¥1.00",
    listing_state: str | None = "已下架",
    valid_until: datetime | None = None,
    account_id: str = "xianyu-seller-A",
) -> httpx.Response:
    return await client.post(
        "/api/v1/xianyu/delete/approvals",
        headers=identity(),
        json={
            "deviceId": device,
            "accountId": account_id,
            "identityEvidence": {
                "platformItemId": platform_item_id,
                "titleContains": title,
                "price": price,
                "listingState": listing_state,
            },
            "validUntil": (valid_until or datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        },
    )


async def _issue(client: httpx.AsyncClient, approval_id: str, task_id: str) -> httpx.Response:
    return await client.post(
        f"/api/v1/xianyu/delete/approvals/{approval_id}:issue-confirm",
        headers=identity(),
        json={"taskId": task_id},
    )


async def _report(
    client: httpx.AsyncClient, approval_id: str, task_id: str, verdict: str, **readback: Any
) -> httpx.Response:
    return await client.post(
        "/api/v1/xianyu/delete/results",
        headers=identity(),
        json={
            "approvalId": approval_id,
            "taskId": task_id,
            "verdict": verdict,
            "readback": {"targetGone": True, **readback},
        },
    )


async def _delete_v2_task_with_ledger(
    client: httpx.AsyncClient, app: FastAPI, device: str, title: str
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Create + claim + start a delete v2 task; return ids and intent body."""

    return await _start_task(
        client,
        app,
        device,
        delete_v2_steps(title),
        f"delete-evidence-{device[:12]}",
        instance=f"instance-{device[:8]}",
    )


async def _intent(
    client: httpx.AsyncClient, task_id: str, auth: dict[str, str], body: dict[str, Any]
):
    return await client.post(
        f"/companion/v2/tasks/{task_id}/actions/intent", headers=auth, json=body
    )


async def _outcome(
    client: httpx.AsyncClient,
    task_id: str,
    auth: dict[str, str],
    body: dict[str, Any],
    status: str,
):
    return await client.post(
        f"/companion/v2/tasks/{task_id}/actions/{body['actionKey']}/outcome",
        headers=auth,
        json={
            "leaseId": body["leaseId"],
            "parameterHash": body["parameterHash"],
            "status": status,
            "evidence": "sha256:" + "d" * 64,
        },
    )


async def _ledger_row(app: FastAPI, task_id: str) -> MobileActionCommitRow | None:
    async with app.state.database.unit_of_work() as session:
        return await session.scalar(
            select(MobileActionCommitRow).where(MobileActionCommitRow.task_id == task_id)
        )


# ---------------------------------------------------------------------------
# Approval ledger: creation gate & persistence
# ---------------------------------------------------------------------------


async def test_approval_persists_account_evidence_action_and_validity(api):
    client, _ = api
    device = await create_direct_device(client, "x10-approval-fields")
    created = await _create_approval(client, device)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["accountId"] == "xianyu-seller-A"
    assert body["action"] == "delete-delisted"
    assert body["state"] == "APPROVED"
    assert body["identityEvidence"]["platformItemId"] == "7123456789"
    assert body["identityEvidence"]["evidenceLevel"] == "PLATFORM_ITEM_ID"
    assert body["targetKey"] == "id:7123456789"
    assert body["validUntil"] is not None
    fetched = await client.get(
        f"/api/v1/xianyu/delete/approvals/{body['approvalId']}", headers=identity()
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["targetKey"] == "id:7123456789"
    assert fetched.json()["protected"] is False


async def test_faceless_and_title_only_targets_are_rejected(api):
    client, _ = api
    device = await create_direct_device(client, "x10-faceless")
    faceless = await _create_approval(
        client, device, platform_item_id=None, title=None, price=None, listing_state=None
    )
    assert faceless.status_code == 422, faceless.text
    title_only = await _create_approval(
        client, device, platform_item_id=None, price=None, listing_state=None
    )
    assert title_only.status_code == 422, title_only.text
    assert "composite" in title_only.json()["detail"].lower()


async def test_composite_evidence_level_requires_two_attributes(api):
    client, _ = api
    device = await create_direct_device(client, "x10-composite")
    created = await _create_approval(client, device, platform_item_id=None)
    assert created.status_code == 201, created.text
    evidence = created.json()["identityEvidence"]
    assert evidence["evidenceLevel"] == "COMPOSITE_HUMAN_CONFIRMED"
    assert created.json()["targetKey"].startswith("composite:xianyu-seller-A|")


async def test_empty_validity_window_is_rejected(api):
    client, _ = api
    device = await create_direct_device(client, "x10-window")
    now = datetime.now(UTC)
    bad = await _create_approval(client, device, valid_until=now - timedelta(hours=2))
    assert bad.status_code == 422, bad.text


# ---------------------------------------------------------------------------
# Single issuance (destructiveGate mirror) & cancel loop
# ---------------------------------------------------------------------------


async def test_confirm_is_issued_exactly_once(api):
    client, _ = api
    device = await create_direct_device(client, "x10-single-issue")
    approval = (await _create_approval(client, device)).json()["approvalId"]
    first = await _issue(client, approval, task_id="task-once")
    assert first.status_code == 200, first.text
    assert first.json()["state"] == "CONSUMED"
    assert first.json()["issuedTaskId"] == "task-once"
    assert first.json()["protected"] is True
    second = await _issue(client, approval, task_id="task-once-retry")
    assert second.status_code == 409, second.text
    assert "never granted" in second.json()["detail"]


async def test_cancel_loop_records_aborted_by_operator(api):
    client, _ = api
    device = await create_direct_device(client, "x10-abort")
    approval = (await _create_approval(client, device)).json()["approvalId"]
    aborted = await client.post(
        f"/api/v1/xianyu/delete/approvals/{approval}:abort",
        headers=identity(),
        json={"evidence": "cancel loop closed at the confirm dialog; zero side effects"},
    )
    assert aborted.status_code == 200, aborted.text
    assert aborted.json()["state"] == "ABORTED_BY_OPERATOR"
    # 撤出之后不再发放确认；再删除需要新批准。
    issue = await _issue(client, approval, task_id="task-after-abort")
    assert issue.status_code == 409, issue.text


async def test_abort_after_issuance_is_refused(api):
    client, _ = api
    device = await create_direct_device(client, "x10-abort-spent")
    approval = (await _create_approval(client, device)).json()["approvalId"]
    await _issue(client, approval, task_id="task-1")
    late = await client.post(
        f"/api/v1/xianyu/delete/approvals/{approval}:abort",
        headers=identity(),
        json={"evidence": "late abort"},
    )
    assert late.status_code == 409, late.text


async def test_expired_window_cannot_issue(api):
    client, _ = api
    device = await create_direct_device(client, "x10-expired")
    now = datetime.now(UTC)
    # 显式过去的窗口：创建合法（validUntil > validFrom），发放时已过期。
    created = await client.post(
        "/api/v1/xianyu/delete/approvals",
        headers=identity(),
        json={
            "deviceId": device,
            "accountId": "xianyu-seller-A",
            "identityEvidence": {"platformItemId": "7123456700"},
            "validFrom": (now - timedelta(hours=2)).isoformat(),
            "validUntil": (now - timedelta(hours=1)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    approval = created.json()["approvalId"]
    issue = await _issue(client, approval, task_id="task-late")
    assert issue.status_code == 409, issue.text
    assert "validity" in issue.json()["detail"]


# ---------------------------------------------------------------------------
# Result reporting reconciled against the REAL A13 ledger
# ---------------------------------------------------------------------------


async def test_result_lifecycle_against_a13_ledger(api):
    client, app = api
    device = await create_direct_device(client, "x10-lifecycle")
    title = "用户列明可删测试品-02"
    task_id, auth, body = await _delete_v2_task_with_ledger(client, app, device, title)

    approval = (
        await _create_approval(
            client, device, platform_item_id=None, title=title, account_id="xianyu-seller-A"
        )
    ).json()["approvalId"]

    # 未发放确认就上报 → 拒绝（结果不能先于单击授权）。
    premature = await _report(client, approval, task_id, "PENDING_VERIFICATION")
    assert premature.status_code == 409, premature.text

    assert (await _issue(client, approval, task_id)).status_code == 200

    # A13 台账只有 INTENT（单击已授权未上报结果）→ 任何判定都拒绝。
    granted = await _intent(client, task_id, auth, body)
    assert granted.status_code == 201, granted.text
    row = await _ledger_row(app, task_id)
    assert row is not None and row.status == "INTENT"
    no_outcome = await _report(client, approval, task_id, "VERIFIED_DELETED")
    assert no_outcome.status_code == 409, no_outcome.text
    assert "no reported outcome" in no_outcome.json()["detail"]

    # 单击上报 UNKNOWN（弹窗信号未捕获的 P09 原型）→ 回读「待核对」被接受。
    unknown = await _outcome(client, task_id, auth, body, status="UNKNOWN")
    assert unknown.status_code == 200, unknown.text
    pending = await _report(client, approval, task_id, "PENDING_VERIFICATION")
    assert pending.status_code == 201, pending.text
    assert pending.json()["verdict"] == "PENDING_VERIFICATION"
    assert pending.json()["actionKey"] == body["actionKey"]

    # 重放：一致 → 200 幂等；不一致 → 409。
    replay = await _report(client, approval, task_id, "PENDING_VERIFICATION")
    assert replay.status_code == 200, replay.text
    conflict = await _report(client, approval, task_id, "STILL_PRESENT", targetGone=False)
    assert conflict.status_code == 409, conflict.text

    fetched = await client.get(f"/api/v1/xianyu/delete/results/{approval}", headers=identity())
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["resolved"] is False


async def test_unknown_target_locks_protection_until_operator_resolution(api):
    client, app = api
    device = await create_direct_device(client, "x10-protection")
    title = "用户列明可删测试品-03"
    task_id, auth, body = await _delete_v2_task_with_ledger(client, app, device, title)
    created = await _create_approval(
        client, device, platform_item_id=None, title=title, account_id="xianyu-seller-A"
    )
    assert created.status_code == 201, created.text
    approval = created.json()["approvalId"]

    assert (await _issue(client, approval, task_id)).status_code == 200
    assert (await _intent(client, task_id, auth, body)).status_code == 201
    assert (await _outcome(client, task_id, auth, body, status="UNKNOWN")).status_code == 200
    assert (await _report(client, approval, task_id, "PENDING_VERIFICATION")).status_code == 201

    # 同目标新批准：保护期明确拒绝（不排队、不倒计时）。
    rejected = await _create_approval(
        client, device, platform_item_id=None, title=title, account_id="xianyu-seller-A"
    )
    assert rejected.status_code == 409, rejected.text
    problem = rejected.json()
    assert problem["code"] == "PROTECTION_PERIOD"
    assert problem["retryable"] is False
    assert "resolve" in problem["detail"]

    # :resolve 需要先走既有 platform-task reconcile（A13 闭环证明）。
    early = await client.post(
        f"/api/v1/xianyu/delete/approvals/{approval}:resolve",
        headers=identity(),
        json={"decision": "CONFIRMED_APPLIED", "evidence": "operator: platformItemId + 截图"},
    )
    assert early.status_code == 409, early.text

    reconciled = await client.post(
        f"/api/v1/platform-tasks/{task_id}:reconcile",
        headers=identity(),
        json={
            "decision": "CONFIRMED_APPLIED",
            "evidence": "operator verified the card vanished",
            "platformItemId": "xianyu-delete-evidence-03",
        },
    )
    assert reconciled.status_code == 200, reconciled.text

    resolved = await client.post(
        f"/api/v1/xianyu/delete/approvals/{approval}:resolve",
        headers=identity(),
        json={"decision": "CONFIRMED_APPLIED", "evidence": "operator: platformItemId + 截图"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "RESOLVED"
    assert resolved.json()["protected"] is False

    # 核销后同目标才可能再批（新批准、新单击，不复用旧 actionKey）。
    again = await _create_approval(
        client, device, platform_item_id=None, title=title, account_id="xianyu-seller-A"
    )
    assert again.status_code == 201, again.text


async def test_verified_deleted_requires_target_gone_and_reported_strike(api):
    client, app = api
    device = await create_direct_device(client, "x10-verified")
    title = "用户列明可删测试品-04"
    task_id, auth, body = await _delete_v2_task_with_ledger(client, app, device, title)
    approval = (
        await _create_approval(
            client, device, platform_item_id=None, title=title, account_id="xianyu-seller-A"
        )
    ).json()["approvalId"]
    await _issue(client, approval, task_id)
    await _intent(client, task_id, auth, body)
    # 台账 INTENT：成功判定直接拒绝。
    early = await _report(client, approval, task_id, "VERIFIED_DELETED")
    assert early.status_code == 409, early.text

    assert (await _outcome(client, task_id, auth, body, status="APPLIED")).status_code == 200
    # targetGone=False：机器成功绝不伪造。
    fabricated = await _report(client, approval, task_id, "VERIFIED_DELETED", targetGone=False)
    assert fabricated.status_code == 409, fabricated.text
    assert "never fabricated" in fabricated.json()["detail"]

    honest = await _report(
        client,
        approval,
        task_id,
        "VERIFIED_DELETED",
        delistedBadgeBaseline=2,
        delistedBadgeCount=1,
    )
    assert honest.status_code == 201, honest.text
    assert honest.json()["verdict"] == "VERIFIED_DELETED"


async def test_result_for_another_task_is_rejected(api):
    client, app = api
    device = await create_direct_device(client, "x10-wrong-task")
    task_id, auth, body = await _delete_v2_task_with_ledger(client, app, device, "标题-05")
    approval = (await _create_approval(client, device, platform_item_id="999000111")).json()[
        "approvalId"
    ]
    await _issue(client, approval, task_id)
    await _intent(client, task_id, auth, body)
    await _outcome(client, task_id, auth, body, status="UNKNOWN")
    stranger = await _report(
        client, approval, "00000000-0000-0000-0000-000000000000", "STILL_PRESENT"
    )
    assert stranger.status_code == 409, stranger.text


async def test_not_submitted_resolution_uses_a13_terminal_status(api):
    client, app = api
    device = await create_direct_device(client, "x10-not-submitted")
    title = "用户列明可删测试品-06"
    task_id, auth, body = await _delete_v2_task_with_ledger(client, app, device, title)
    approval = (
        await _create_approval(
            client, device, platform_item_id=None, title=title, account_id="xianyu-seller-A"
        )
    ).json()["approvalId"]
    await _issue(client, approval, task_id)
    await _intent(client, task_id, auth, body)
    await _outcome(client, task_id, auth, body, status="UNKNOWN")
    await _report(client, approval, task_id, "PENDING_VERIFICATION")

    reconciled = await client.post(
        f"/api/v1/platform-tasks/{task_id}:reconcile",
        headers=identity(),
        json={
            "decision": "CONFIRMED_NOT_SUBMITTED",
            "evidence": "operator confirmed the strike never landed",
        },
    )
    assert reconciled.status_code == 200, reconciled.text
    resolved = await client.post(
        f"/api/v1/xianyu/delete/approvals/{approval}:resolve",
        headers=identity(),
        json={"decision": "CONFIRMED_NOT_SUBMITTED", "evidence": "operator evidence"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "RESOLVED"


# ---------------------------------------------------------------------------
# Runbook (real-device acceptance, software-only wave)
# ---------------------------------------------------------------------------


def test_real_device_acceptance_runbook_is_pinned():
    """The executable acceptance script description stays pinned: user-listed
    deletable test items only, cancel loop first, single authorization,
    honest readback, and no re-delete of unresolved (UNKNOWN) tasks."""

    joined = "\n".join(REAL_DEVICE_ACCEPTANCE_STEPS)
    assert "user-listed deletable items only" in joined
    assert "cancel loop first" in joined
    assert "one issue-confirm per approval" in joined
    assert "never fabricated" in joined
    assert "no auto re-delete" in joined
