"""F12 fleet schedule pure functions: occurrences, DST rules, missed-fire policy, fire identity.

Fleet-first-20260916.1 F12「立即/定时/周期调度与取消语义」。本模块只放纯函数：
时间格点、DST 折叠规则、补漏策略、fire identity。IO 一律在 service.py。

设计口径（与旧 task-schedule/v1 §5 的差异即 F12 的重设计）：

1. 触发格点是调度定义的纯函数。锚点 = 调度 created_at（持久化在
   TaskScheduleRow），格点只由 (created_at, timezone, rrule) 决定，与轮询
   时刻无关 —— 任何时刻查询同一周期得到同一 period_marker，这是
   「同周期 fire identity 稳定」的前提。旧实现的 next_occurrences 以
   轮询时刻的 hh:mm 为锚，不同分钟级轮询会产生不同格点，F12 废弃该口径。

2. DST 规则钉死（金样测试 tests/integration/test_fleet_schedule_delta.py）：
   - HOURLY：绝对时间步进（UTC + INTERVAL 小时）。夏令时回拨日同一本地
     小时出现两次（fold=0 / fold=1），是两个不同的 occurrence、两个不同
     marker；跳时日本地标签跳过缺失小时。
   - DAILY/WEEKLY：本地墙上时钟步进（固定本地 hh:mm）。春季跳时产生的不
     存在的本地时间向后顺延到下一个合法瞬间（PEP 495 gap 语义）；秋季
     重复小时取 fold=0（第一次出现），确定性且唯一。
   - period_marker = occurrence 的规范 UTC ISO-8601 串。

3. 补漏策略显式重设计（不照搬旧的 30 分钟 startDeadline 窗口）：
   「晚到」的判定边界是动态的下一个周期格点，而不是固定墙钟窗口。
   - 到期未 mint 的 occurrence 只有一个（当前周期内恢复）→ 照常 mint，
     不算 miss。
   - 积压 >= 2 个到期未 mint（跨过至少一个周期边界才可能发生）：
     * COALESCE_LATEST（默认；旧 miss_policy=QUEUE_ONE 的别名）：只 mint
       最新一个，更早的标记 SKIPPED（coalesced）——绝不补发风暴。
     * SKIP：整段积压全部 SKIPPED，等下一个新周期——错过即作废。
   - ONCE 只有一个格点，永远不构成积压，恢复后照常 mint（原 scheduledFor
     原样钉在任务上）；要「过期作废」语义就选 SKIP 且不晚于其周期末恢复
     之外的策略由操作者显式选择。
   SKIPPED / ERROR 的台账行是终态：重复 tick 不会把已决策的周期改判。

4. fire identity（A04/K03 兼容，公式与旧 schedules.py 完全一致）：
   key = sha256(f"{schedule_id}:{utc_time.isoformat()}:{device_id}")[:64]
   经 PlatformTaskService.create 的 Idempotency-Key 语义落库
   （201 首铸 / 200 幂等重放），台账行 Unique(schedule_id, scheduled_for,
   device_id) 兜底。Temporal Activity 重试只重发同键请求。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cloudctl_domain import ValidationError

RRULE_FIELD = {"rrule": "仅支持 FREQ=HOURLY/DAILY/WEEKLY + INTERVAL"}
SUPPORTED_FREQ = ("HOURLY", "DAILY", "WEEKLY")

MISS_POLICY_COALESCE_LATEST = "COALESCE_LATEST"
MISS_POLICY_SKIP = "SKIP"
MINT_POLICIES = frozenset({MISS_POLICY_COALESCE_LATEST, MISS_POLICY_SKIP})
# 旧 task-schedule/v1 §5 的 miss_policy 值 → F12 策略（QUEUE_ONE 与
# COALESCE_LATEST 同义：旧实现同样只 queue 最新一个周期）。
LEGACY_MISS_POLICY_ALIASES = {
    "QUEUE_ONE": MISS_POLICY_COALESCE_LATEST,
    MISS_POLICY_COALESCE_LATEST: MISS_POLICY_COALESCE_LATEST,
    "SKIP": MISS_POLICY_SKIP,
    MISS_POLICY_SKIP: MISS_POLICY_SKIP,
}

MAX_GRID_POINTS = 10_000


def resolve_miss_policy(value: str | None) -> str:
    """Map a persisted miss_policy to the closed F12 policy vocabulary."""
    canonical = LEGACY_MISS_POLICY_ALIASES.get((value or "").strip().upper())
    if canonical is None:
        raise ValidationError(
            "missPolicy must be COALESCE_LATEST (alias QUEUE_ONE) or SKIP",
            fields={"missPolicy": "must be COALESCE_LATEST or SKIP"},
        )
    return canonical


@dataclass(frozen=True)
class Occurrence:
    """One stable grid point of a schedule."""

    utc: datetime  # aware UTC instant; .isoformat() feeds the fire key
    local_label: str  # renormalized local wall-clock label (fold annotated)

    @property
    def marker(self) -> str:
        return period_marker(self.utc)


def period_marker(value: datetime) -> str:
    """Canonical period marker: the occurrence's UTC ISO-8601 instant."""
    return _aware(value).isoformat()


def fire_key(schedule_id: str, occurrence_utc: datetime, device_id: str) -> str:
    """A04/K03-compatible mint idempotency key.

    Byte-identical formula to the legacy manual fire path
    (cloudctl_api/schedules.py): sha256(schedule_id:utc_time:device_id)[:64]
    with utc_time.isoformat() of an aware-UTC datetime, so a Temporal retry
    or a replayed manual :fire resolves to the same MobileTask.
    """
    return hashlib.sha256(
        f"{schedule_id}:{_aware(occurrence_utc).isoformat()}:{device_id}".encode()
    ).hexdigest()[:64]


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError(
            "timezone is not a valid IANA name",
            fields={"timezone": "not a valid IANA name"},
        ) from exc


def local_label(utc: datetime, zone: ZoneInfo) -> str:
    """Renormalized local label; the repeated hour is annotated with #fold."""
    local = _aware(utc).astimezone(zone)
    label = local.isoformat()
    return f"{label}#fold" if local.fold == 1 else label


def _parse_rrule(rrule: str) -> tuple[str, int]:
    if not rrule.startswith("FREQ="):
        raise ValidationError("rrule must start with FREQ=", fields=RRULE_FIELD)
    parts = dict(item.split("=", 1) for item in rrule.split(";") if "=" in item)
    freq = parts.get("FREQ", "").upper()
    if freq not in SUPPORTED_FREQ:
        raise ValidationError(
            "only FREQ=HOURLY,DAILY,WEEKLY are supported", fields=RRULE_FIELD
        )
    try:
        interval = int(parts.get("INTERVAL", "1"))
    except ValueError as exc:
        raise ValidationError("rrule INTERVAL must be an integer", fields=RRULE_FIELD) from exc
    if interval < 1:
        raise ValidationError("rrule INTERVAL must be >= 1", fields=RRULE_FIELD)
    return freq, interval


def _occurrence(utc: datetime, zone: ZoneInfo) -> Occurrence:
    return Occurrence(utc=_aware(utc), local_label=local_label(utc, zone))


def _hourly_grid(
    anchor_utc: datetime, interval_hours: int, *, through: datetime, zone: ZoneInfo
) -> list[Occurrence]:
    # 绝对时间步进：跨 DST 偏移变化本地 hh:mm 会平移；回拨日同一本地小时
    # 出现两次（两个不同的 UTC instant / marker）。锚点的分秒取整到分，
    # 让 fire identity 不携带 created_at 的微秒噪声。
    step = timedelta(hours=interval_hours)
    first = anchor_utc.replace(second=0, microsecond=0) + step
    span = (through - first) / step
    count = min(max(0, int(span) + 1) + 1, MAX_GRID_POINTS)
    return [_occurrence(first + step * index, zone) for index in range(count)]


def _wall_clock_grid(
    anchor_utc: datetime,
    step_days: int,
    *,
    through: datetime,
    zone: ZoneInfo,
) -> list[Occurrence]:
    # 本地墙上时钟步进：固定本地 hh:mm。gap（春季跳时缺失的本地时间）按
    # PEP 495 语义向后顺延到下一个合法瞬间；ambiguous（秋季重复小时）取
    # fold=0 第一次出现 —— 两者都在 renormalize 时收敛到唯一 UTC instant。
    anchor_local = anchor_utc.astimezone(zone).replace(second=0, microsecond=0)
    through_local = through.astimezone(zone)
    days = (through_local.date() - anchor_local.date()).days
    count = max(0, days // step_days + 2)
    values: list[Occurrence] = []
    for index in range(1, min(count + 1, MAX_GRID_POINTS)):
        naive = anchor_local + timedelta(days=step_days * index)
        utc = naive.replace(tzinfo=zone).astimezone(UTC)
        values.append(_occurrence(utc, zone))
    return values


def occurrence_grid(
    timezone_name: str,
    rrule: str,
    *,
    anchor: datetime,
    through: datetime,
) -> list[Occurrence]:
    """Enumerate the schedule's grid points in (anchor, through].

    The grid is a pure function of the persisted definition: occurrences are
    strictly after ``anchor`` (the schedule's created_at) up to and including
    ``through``. Callers asking at different wall-clock times see identical
    markers for identical periods.
    """
    zone = _zone(timezone_name)
    freq, interval = _parse_rrule(rrule)
    anchor_utc = _aware(anchor)
    through_utc = _aware(through)
    if freq == "HOURLY":
        return _hourly_grid(anchor_utc, interval, through=through_utc, zone=zone)
    step_days = 7 * interval if freq == "WEEKLY" else interval
    return _wall_clock_grid(anchor_utc, step_days, through=through_utc, zone=zone)


# ---------------------------------------------------------------------------
# Missed-fire policy (explicit, window-free)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DueDecision:
    action: str  # MINT | SKIP
    occurrence: Occurrence
    detail: str | None = None


@dataclass(frozen=True)
class MissPolicyDecision:
    mint: Occurrence | None
    skipped: tuple[DueDecision, ...]

    @property
    def decisions(self) -> tuple[DueDecision, ...]:
        items: list[DueDecision] = list(self.skipped)
        if self.mint is not None:
            items.append(DueDecision(action="MINT", occurrence=self.mint))
        return tuple(sorted(items, key=lambda item: item.occurrence.utc))


def classify_due_occurrences(
    unminted_due: list[Occurrence], policy: str
) -> MissPolicyDecision:
    """Apply the explicit missed-fire policy to the due-but-unminted backlog.

    Boundary is the schedule's own next period, never a fixed wall-clock window:

    * 0 due → nothing to do.
    * 1 due → still the current period (recovered in-time): mint under both
      policies. Lateness is invisible without a backlog and must not be
      guessed from a timer.
    * >= 2 due → at least one full period was crossed while unminted:
      - COALESCE_LATEST: mint only the newest, older ones SKIPPED (coalesced).
      - SKIP: the whole backlog is stale; all SKIPPED, resume next period.
    """
    canonical = resolve_miss_policy(policy)
    ordered = sorted(unminted_due, key=lambda item: item.utc)
    if not ordered:
        return MissPolicyDecision(mint=None, skipped=())
    if len(ordered) == 1:
        return MissPolicyDecision(mint=ordered[0], skipped=())
    newest = ordered[-1]
    older = ordered[:-1]
    if canonical == MISS_POLICY_SKIP:
        return MissPolicyDecision(
            mint=None,
            skipped=tuple(
                DueDecision(
                    action="SKIP",
                    occurrence=item,
                    detail="stale backlog skipped; schedule resumes at the next fresh period",
                )
                for item in ordered
            ),
        )
    return MissPolicyDecision(
        mint=newest,
        skipped=tuple(
            DueDecision(
                action="SKIP",
                occurrence=item,
                detail="coalesced into newer period; older missed fires are never backfilled",
            )
            for item in older
        ),
    )


def schedule_snapshot(row: Any) -> dict[str, Any]:
    """Pin the schedule definition at mint time (fleet-first F12 §2).

    The expansion result (device list), timezone, templateRevision, command and
    parameters are read from the persisted row exactly once per mint; later
    template edits cannot drift an already-minted task because the snapshot
    lives on in the MobileTask command payload + snapshotSha256 (A04).
    """
    return {
        "id": row.id,
        "kind": row.kind,
        "timezone": row.timezone,
        "rrule": row.rrule,
        "once_at": _aware(row.once_at) if row.once_at else None,
        "miss_policy": resolve_miss_policy(row.miss_policy),
        "account_id": row.account_id,
        "binding_version": row.binding_version,
        "device_ids": list(row.device_ids or []),
        "command_type": row.command_type,
        "parameters": dict(row.parameters or {}),
        "template_revision": row.template_revision,
        "tenant_id": row.tenant_id,
        "created_at": _aware(row.created_at),
    }


__all__ = [
    "DueDecision",
    "LEGACY_MISS_POLICY_ALIASES",
    "MAX_GRID_POINTS",
    "MINT_POLICIES",
    "MISS_POLICY_COALESCE_LATEST",
    "MISS_POLICY_SKIP",
    "MissPolicyDecision",
    "Occurrence",
    "classify_due_occurrences",
    "fire_key",
    "local_label",
    "occurrence_grid",
    "period_marker",
    "resolve_miss_policy",
    "schedule_snapshot",
]
