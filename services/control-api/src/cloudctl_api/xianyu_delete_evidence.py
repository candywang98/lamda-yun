"""Xianyu delete evidence loop (X10, fleet-first-20260916.1).

P09 删除专项的后端半边：**删除批准清单的持久与查询** + **删除结果上报与
A13 受控台账对账**。语义与设备侧 ``features/xianyu/maintenance/delete``
（DeleteApprovalLedger / DeleteFailureTaxonomy / DeleteResultReadback）互为镜像：

- 批准逐目标含 账号(accountId) / 证据(identityEvidence, B13 级别) / 动作
  (delete-delisted，冻结) / 有效期(validFrom..validUntil)。
- **一次只发一次确认**：``POST /approvals/{id}:issue-confirm`` 把 APPROVED 推到
  CONSUMED 并记录唯一 taskId；第二次一律 409 CONFIRM_ALREADY_ISSUED——服务端
  destructiveGate 单发语义（p09-ledger/20260910.1「Never return AUTHORIZED for a
  retry」）的清单侧镜像。
- **保护期是明确拒绝**：同目标存在 CONSUMED 且未核销的批准时，新批准 409
  PROTECTION_PERIOD——没有队列、没有倒计时、不会自动重发（「未知任务不自动
  重新删除」）。解除唯一路径：操作员 ``:resolve``（须先完成 A13 台账核销）。
- **取消闭环**：``:abort`` 把未发放的批准记 ABORTED_BY_OPERATOR（到达确认框后
  选择取消、零副作用退出）。
- **结果上报对账 A13**：结果只接受已发放确认的任务；VERIFIED_DELETED 需要列表
  消失观察 + A13 行已上报（APPLIED/UNKNOWN）；操作员核销 (:resolve) 需要 A13 行
  ``platform_result_proven``（A13 纯函数只读复用），CONFIRMED_APPLIED 还要求
  行状态为 APPLIED。

误卡/同名/旧窗口/无目标 ID/证据不足的**触击前**裁决在设备侧编排器完成（B13
只读复用）；本模块的创建门只做证据充分性（platformItemId 或 复合≥2 属性）的
服务端兜底，不重复六序裁决。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from cloudctl_domain import Actor, ConflictError, NotFoundError, ValidationError
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .auth import current_actor
from .controlled_actions import platform_result_proven
from .db import Base, Database, DeviceRow, MobileActionCommitRow, TimestampMixin
from .mobile_service import _aware

# Frozen contract pins (cite, never restate): the delete confirm actionId comes
# from the frozen maintenance shapes (mobile_actions XIANYU_MAINTENANCE_V2_SHAPES
# xianyu.delete_delisted.steps.v2) and is deliberately NOT imported from the
# A13-frozen module to keep this slice's writes self-contained.
DELETE_ACTION_ID = "confirm-delete"
DELETE_ACTION = "delete-delisted"
# B13 MIN_COMPOSITE_ATTRIBUTES parity: title counts as one visible attribute and
# at least one further attribute (price / listing state) is required.
MIN_COMPOSITE_ATTRIBUTES = 2
TITLE_MAX = 64

APPROVAL_APPROVED = "APPROVED"
APPROVAL_CONSUMED = "CONSUMED"
APPROVAL_ABORTED = "ABORTED_BY_OPERATOR"
APPROVAL_RESOLVED = "RESOLVED"

VERDICT_VERIFIED_DELETED = "VERIFIED_DELETED"
VERDICT_PENDING_VERIFICATION = "PENDING_VERIFICATION"
VERDICT_STILL_PRESENT = "STILL_PRESENT"
VERDICT_INCONCLUSIVE = "INCONCLUSIVE"
VERDICTS = frozenset(
    {
        VERDICT_VERIFIED_DELETED,
        VERDICT_PENDING_VERIFICATION,
        VERDICT_STILL_PRESENT,
        VERDICT_INCONCLUSIVE,
    }
)


class DeleteProtectionPeriodError(ConflictError):
    """Explicit protection-period rejection: nothing is queued, nothing retries."""

    code = "PROTECTION_PERIOD"


class DeleteEvidenceValidationError(ValidationError):
    code = "DELETE_EVIDENCE_INVALID"


def _now() -> datetime:
    return datetime.now(UTC)


def target_identity_key(
    account_id: str,
    platform_item_id: str | None,
    title_contains: str | None,
    price: str | None,
    listing_state: str | None,
) -> str:
    """Canonical per-target key (mirror of the device-side DeleteTargetKey).

    platformItemId is the strong identity; without it the key is the account
    scope plus the composite visible attributes — a faceless target (no id, no
    title) is refused by the callers, never keyed here.
    """

    real_id = (platform_item_id or "").strip()
    if real_id:
        return f"id:{real_id}"
    # Byte-mirror of the device-side DeleteTargetKey.identityKey composite
    # form ("composite:account|title|price|listingState") so both ledgers key
    # the same target identically.
    return f"composite:{account_id}|{title_contains or ''}|{price or ''}|{listing_state or ''}"


class XianyuDeleteApprovalRow(Base, TimestampMixin):
    __tablename__ = "xianyu_delete_approval"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(36), nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_key: Mapped[str] = mapped_column(String(256), nullable=False)
    identity_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    issued_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (
        CheckConstraint(
            "state IN ('APPROVED','CONSUMED','ABORTED_BY_OPERATOR','RESOLVED')",
            name="ck_xianyu_delete_approval_state",
        ),
        CheckConstraint("valid_until > valid_from", name="ck_xianyu_delete_approval_window"),
        CheckConstraint("action = 'delete-delisted'", name="ck_xianyu_delete_approval_action"),
    )


class XianyuDeleteResultRow(Base, TimestampMixin):
    __tablename__ = "xianyu_delete_result"
    approval_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("xianyu_delete_approval.id"),
        primary_key=True,
    )
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action_key: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    readback: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('VERIFIED_DELETED','PENDING_VERIFICATION','STILL_PRESENT','INCONCLUSIVE')",
            name="ck_xianyu_delete_result_verdict",
        ),
    )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

TitleFragment = Annotated[str, StringConstraints(min_length=1, max_length=TITLE_MAX)]


class DeleteIdentityEvidencePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    platform_item_id: str | None = Field(default=None, alias="platformItemId")
    title_contains: TitleFragment | None = Field(default=None, alias="titleContains")
    price: str | None = None
    listing_state: str | None = Field(default=None, alias="listingState")

    def evidence_level(self) -> str:
        real_id = (self.platform_item_id or "").strip()
        if real_id:
            return "PLATFORM_ITEM_ID"
        title = (self.title_contains or "").strip()
        if not title:
            raise DeleteEvidenceValidationError(
                "identity evidence needs a platformItemId or a title fragment "
                "(a faceless target is never deletable)"
            )
        extra = [value for value in (self.price, self.listing_state) if value]
        if 1 + len(extra) < MIN_COMPOSITE_ATTRIBUTES:
            raise DeleteEvidenceValidationError(
                f"composite identity needs >= {MIN_COMPOSITE_ATTRIBUTES} visible "
                "attributes (title alone is not an identity)"
            )
        return "COMPOSITE_HUMAN_CONFIRMED"


class DeleteApprovalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    device_id: str = Field(alias="deviceId", min_length=1, max_length=36)
    account_id: str = Field(alias="accountId", min_length=1, max_length=64)
    identity_evidence: DeleteIdentityEvidencePayload = Field(alias="identityEvidence")
    valid_from: datetime | None = Field(default=None, alias="validFrom")
    valid_until: datetime = Field(alias="validUntil")


class DeleteIssueConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    task_id: str = Field(alias="taskId", min_length=1, max_length=36)


class DeleteAbortRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: str = Field(min_length=1, max_length=500)


class DeleteResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    decision: Literal["CONFIRMED_APPLIED", "CONFIRMED_NOT_SUBMITTED"]
    evidence: str = Field(min_length=1, max_length=500)


class DeleteResultReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    approval_id: str = Field(alias="approvalId", min_length=1, max_length=36)
    task_id: str = Field(alias="taskId", min_length=1, max_length=36)
    verdict: Literal[
        "VERIFIED_DELETED",
        "PENDING_VERIFICATION",
        "STILL_PRESENT",
        "INCONCLUSIVE",
    ]
    readback: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def approval_view(row: XianyuDeleteApprovalRow, *, protected: bool) -> dict[str, Any]:
    return {
        "approvalId": row.id,
        "tenantId": row.tenant_id,
        "deviceId": row.device_id,
        "accountId": row.account_id,
        "targetKey": row.target_key,
        "identityEvidence": row.identity_evidence,
        "action": row.action,
        "validFrom": _iso(row.valid_from),
        "validUntil": _iso(row.valid_until),
        "state": row.state,
        # Computed, never stored: protection is derived from an unresolved
        # CONSUMED approval — an explicit rejection cause, not a countdown.
        "protected": protected,
        "issuedTaskId": row.issued_task_id,
        "issuedAt": _iso(row.issued_at),
        "createdAt": _iso(row.created_at),
    }


def result_view(row: XianyuDeleteResultRow) -> dict[str, Any]:
    return {
        "approvalId": row.approval_id,
        "taskId": row.task_id,
        "actionKey": row.action_key,
        "verdict": row.verdict,
        "readback": row.readback,
        "resolved": row.resolved,
        "resolution": row.resolution,
        "createdAt": _iso(row.created_at),
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class XianyuDeleteEvidenceService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def _owned_approval(
        self, session: AsyncSession, tenant_id: str, approval_id: str, *, for_update: bool = True
    ) -> XianyuDeleteApprovalRow:
        statement = select(XianyuDeleteApprovalRow).where(
            XianyuDeleteApprovalRow.tenant_id == tenant_id,
            XianyuDeleteApprovalRow.id == approval_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = await session.scalar(statement)
        if row is None:
            raise NotFoundError("delete approval was not found")
        return row

    @staticmethod
    def _protected(approval: XianyuDeleteApprovalRow, result: XianyuDeleteResultRow | None) -> bool:
        # The target is protected exactly while a confirm was issued and the
        # outcome has not been resolved by the operator (UNKNOWN discipline).
        return approval.state == APPROVAL_CONSUMED and not (result is not None and result.resolved)

    async def create_approval(
        self, actor: Actor, payload: DeleteApprovalCreateRequest
    ) -> dict[str, Any]:
        tenant_id = str(actor.tenant_id)
        level = payload.identity_evidence.evidence_level()
        now = _now()
        valid_from = payload.valid_from or now
        if payload.valid_until <= valid_from:
            raise DeleteEvidenceValidationError("validUntil must be after validFrom")
        key = target_identity_key(
            payload.account_id,
            payload.identity_evidence.platform_item_id,
            payload.identity_evidence.title_contains,
            payload.identity_evidence.price,
            payload.identity_evidence.listing_state,
        )
        async with self.database.unit_of_work() as session:
            device = await session.get(DeviceRow, payload.device_id)
            if device is None or device.tenant_id != tenant_id:
                raise NotFoundError("device was not found for this tenant")
            # Protection check: an unresolved CONSUMED approval for the same
            # target is an explicit rejection — nothing is queued, nothing
            # retries automatically when it clears.
            conflict = await session.scalar(
                select(XianyuDeleteApprovalRow).where(
                    XianyuDeleteApprovalRow.tenant_id == tenant_id,
                    XianyuDeleteApprovalRow.target_key == key,
                    XianyuDeleteApprovalRow.state == APPROVAL_CONSUMED,
                )
            )
            if conflict is not None:
                unresolved = await session.get(XianyuDeleteResultRow, conflict.id)
                if unresolved is None or not unresolved.resolved:
                    raise DeleteProtectionPeriodError(
                        f"target {key} has an unresolved delete attempt "
                        f"(approval {conflict.id}, task {conflict.issued_task_id}); "
                        "explicit rejection — resolve the prior attempt first, "
                        "no retry is queued"
                    )
            row = XianyuDeleteApprovalRow(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                device_id=payload.device_id,
                account_id=payload.account_id,
                target_key=key,
                identity_evidence={
                    **payload.identity_evidence.model_dump(by_alias=True),
                    "evidenceLevel": level,
                },
                action=DELETE_ACTION,
                valid_from=valid_from,
                valid_until=payload.valid_until,
                state=APPROVAL_APPROVED,
                requested_by=str(actor.user_id),
                created_at=now,
            )
            session.add(row)
            await session.flush()
            return approval_view(row, protected=False)

    async def get_approval(self, actor: Actor, approval_id: str) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            row = await self._owned_approval(session, str(actor.tenant_id), approval_id)
            result = await session.get(XianyuDeleteResultRow, row.id)
            return approval_view(row, protected=self._protected(row, result))

    async def issue_confirm_once(
        self, actor: Actor, approval_id: str, payload: DeleteIssueConfirmRequest
    ) -> dict[str, Any]:
        """The single confirm issuance (destructiveGate single-grant mirror)."""

        async with self.database.unit_of_work() as session:
            row = await self._owned_approval(session, str(actor.tenant_id), approval_id)
            if row.state == APPROVAL_CONSUMED:
                raise ConflictError(
                    f"confirm already issued once for task {row.issued_task_id}; "
                    "a second strike is never granted"
                )
            if row.state != APPROVAL_APPROVED:
                raise ConflictError(f"approval is {row.state}; no confirm can be issued")
            now = _now()
            if now < _aware(row.valid_from) or now > _aware(row.valid_until):
                raise ConflictError(
                    "approval validity window does not cover now; request a fresh approval"
                )
            row.state = APPROVAL_CONSUMED
            row.issued_task_id = payload.task_id
            row.issued_at = now
            await session.flush()
            result = await session.get(XianyuDeleteResultRow, row.id)
            return approval_view(row, protected=self._protected(row, result))

    async def abort(
        self, actor: Actor, approval_id: str, payload: DeleteAbortRequest
    ) -> dict[str, Any]:
        """Cancel-loop closure: zero side effects, ABORTED_BY_OPERATOR."""

        async with self.database.unit_of_work() as session:
            row = await self._owned_approval(session, str(actor.tenant_id), approval_id)
            if row.state == APPROVAL_CONSUMED:
                raise ConflictError("a spent confirm must be reconciled, never retro-cancelled")
            if row.state != APPROVAL_APPROVED:
                raise ConflictError(f"approval is {row.state}; only APPROVED can be aborted")
            row.state = APPROVAL_ABORTED
            await session.flush()
            return approval_view(row, protected=False)

    async def report_result(
        self, actor: Actor, payload: DeleteResultReportRequest
    ) -> tuple[dict[str, Any], bool]:
        """Record the readback verdict, reconciled against the A13 ledger row.

        The A13 controlled-action ledger (mobile_action_commit, frozen) is the
        authority for whether a destructive strike happened:
        - the report's taskId must be the one the confirm was issued for;
        - the frozen confirm-delete action row must exist AND have a reported
          outcome (APPLIED/UNKNOWN) — an INTENT-only row means the strike was
          never reported, so no verdict may be recorded;
        - VERIFIED_DELETED additionally requires the readback to say the target
          vanished from the list (server-side fail-closed twin).
        """

        async with self.database.unit_of_work() as session:
            approval = await self._owned_approval(
                session, str(actor.tenant_id), payload.approval_id
            )
            if approval.state != APPROVAL_CONSUMED or approval.issued_task_id != payload.task_id:
                raise ConflictError(
                    "delete result requires the approval's single issued confirm "
                    f"for task {payload.task_id} (state={approval.state}, "
                    f"issuedTaskId={approval.issued_task_id})"
                )
            action_row = await session.scalar(
                select(MobileActionCommitRow).where(
                    MobileActionCommitRow.task_id == payload.task_id,
                    MobileActionCommitRow.action_id == DELETE_ACTION_ID,
                )
            )
            if action_row is None:
                raise ConflictError(
                    "no controlled-action ledger row for the frozen confirm-delete "
                    "action; a delete result cannot precede its strike authorization"
                )
            if action_row.status not in ("APPLIED", "UNKNOWN"):
                raise ConflictError(
                    "the confirm strike has no reported outcome yet "
                    f"(ledger status {action_row.status}); report the outcome "
                    "before the readback verdict"
                )
            if payload.verdict == VERDICT_VERIFIED_DELETED and not payload.readback.get(
                "targetGone", False
            ):
                raise ConflictError(
                    "VERIFIED_DELETED requires the authoritative list observation "
                    "(targetGone); success is never fabricated"
                )
            existing = await session.get(
                XianyuDeleteResultRow, payload.approval_id, with_for_update=True
            )
            if existing is not None:
                if existing.verdict == payload.verdict and (existing.readback or {}) == (
                    payload.readback or {}
                ):
                    return result_view(existing), False
                raise ConflictError("delete result replay differs")
            row = XianyuDeleteResultRow(
                approval_id=payload.approval_id,
                tenant_id=str(actor.tenant_id),
                task_id=payload.task_id,
                action_key=action_row.action_key,
                verdict=payload.verdict,
                readback=payload.readback,
                created_at=_now(),
            )
            session.add(row)
            await session.flush()
            return result_view(row), True

    async def resolve(
        self, actor: Actor, approval_id: str, payload: DeleteResolveRequest
    ) -> dict[str, Any]:
        """Operator resolution, gated on the A13 ledger's own closure proof.

        Reuses A13's pure ``platform_result_proven`` (read-only import): the
        controlled-action row must have been resolved through the existing
        platform-task reconcile flow before the approval can unlock. This is
        the delete-loop's reconciliation seam to the frozen ledger.
        """

        async with self.database.unit_of_work() as session:
            approval = await self._owned_approval(session, str(actor.tenant_id), approval_id)
            if approval.state != APPROVAL_CONSUMED or approval.issued_task_id is None:
                raise ConflictError(
                    f"approval is {approval.state}; only a CONSUMED approval can be resolved"
                )
            action_row = await session.scalar(
                select(MobileActionCommitRow).where(
                    MobileActionCommitRow.task_id == approval.issued_task_id,
                    MobileActionCommitRow.action_id == DELETE_ACTION_ID,
                )
            )
            if action_row is None or not platform_result_proven(action_row):
                raise ConflictError(
                    "the A13 controlled-action row is not resolved yet "
                    "(revision/status/resolvedAt/evidence incomplete); finish the "
                    "platform-task reconciliation first"
                )
            if payload.decision == "CONFIRMED_APPLIED" and action_row.status != "APPLIED":
                raise ConflictError(
                    "CONFIRMED_APPLIED requires the A13 ledger row to be terminal APPLIED"
                )
            if (
                payload.decision == "CONFIRMED_NOT_SUBMITTED"
                and action_row.status != "NOT_SUBMITTED"
            ):
                raise ConflictError(
                    "CONFIRMED_NOT_SUBMITTED requires the A13 ledger row to be "
                    "terminal NOT_SUBMITTED"
                )
            result = await session.get(XianyuDeleteResultRow, approval_id, with_for_update=True)
            if result is not None:
                result.resolved = True
                result.resolution = {
                    "decision": payload.decision,
                    "evidence": payload.evidence,
                    "resolvedBy": str(actor.user_id),
                    "resolvedAt": _now().isoformat(),
                }
            approval.state = APPROVAL_RESOLVED
            await session.flush()
            return approval_view(approval, protected=False)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/xianyu/delete", tags=["xianyu-delete-evidence"])


def service(request: Request) -> XianyuDeleteEvidenceService:
    return cast(XianyuDeleteEvidenceService, request.app.state.xianyu_delete_evidence_service)


Service = Annotated[XianyuDeleteEvidenceService, Depends(service)]
ActorDep = Annotated[Any, Depends(current_actor)]


@router.post("/approvals", status_code=201)
async def create_delete_approval(
    body: DeleteApprovalCreateRequest, actor: ActorDep, svc: Service
) -> dict[str, Any]:
    return await svc.create_approval(actor, body)


@router.get("/approvals/{approval_id}")
async def get_delete_approval(approval_id: str, actor: ActorDep, svc: Service) -> dict[str, Any]:
    return await svc.get_approval(actor, approval_id)


@router.post("/approvals/{approval_id}:issue-confirm")
async def issue_delete_confirm(
    approval_id: str, body: DeleteIssueConfirmRequest, actor: ActorDep, svc: Service
) -> dict[str, Any]:
    return await svc.issue_confirm_once(actor, approval_id, body)


@router.post("/approvals/{approval_id}:abort")
async def abort_delete_approval(
    approval_id: str, body: DeleteAbortRequest, actor: ActorDep, svc: Service
) -> dict[str, Any]:
    return await svc.abort(actor, approval_id, body)


@router.post("/approvals/{approval_id}:resolve")
async def resolve_delete_approval(
    approval_id: str, body: DeleteResolveRequest, actor: ActorDep, svc: Service
) -> dict[str, Any]:
    return await svc.resolve(actor, approval_id, body)


@router.post("/results", status_code=201)
async def report_delete_result(
    body: DeleteResultReportRequest,
    actor: ActorDep,
    svc: Service,
    response: Response,
) -> dict[str, Any]:
    result, created = await svc.report_result(actor, body)
    if not created:
        response.status_code = 200
    return result


@router.get("/results/{approval_id}")
async def get_delete_result(approval_id: str, actor: ActorDep, svc: Service) -> dict[str, Any]:
    async with svc.database.unit_of_work() as session:
        row = await session.get(XianyuDeleteResultRow, approval_id)
        if row is None or row.tenant_id != str(actor.tenant_id):
            raise NotFoundError("delete result was not found")
        return result_view(row)
