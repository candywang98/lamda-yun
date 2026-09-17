package com.company.cloudctl.companion.features.xianyu.maintenance.delete

/**
 * X10 (fleet-first-20260916.1) — P09 删除专项：失败分类学。
 *
 * 重放 P09 删除三次真实历史（artifacts/tasks/P09-unknown/xianyu-maintenance-20260915/
 * report.md，设备 OnePlus 9R b0644fb5）：
 *
 * 1. 任务 `4d226249`：intent 409（actionId 错位/未受理）→ 确认单击从未获得服务端
 *    授权、从未派发 → **未派发**（NOT_DISPATCHED / INTENT_REJECTED）。零副作用。
 * 2. 任务 `6d22dd62`：已下架首卡坐标漂移（横幅有无可移动 y 达 532px），布局守卫
 *    拦截 → 若照旧坐标点击将命中错误卡片，守卫失败安全 → **误卡类**（WRONG_TARGET /
 *    LAYOUT_DRIFT_BLOCKED）。零副作用（这是「误卡」作为失败类别的原型：定位/身份
 *    层失效，与是否真点错无关）。
 * 3. 任务 `37a665b0`：确认单击已派发且真实删除发生，但弹窗消失信号时序未捕获 →
 *    机器核验只能 UNKNOWN，操作员以 platformItemId 证据 CONFIRMED_APPLIED →
 *    **已派发结果未知**（DISPATCHED_UNKNOWN / DIALOG_DISMISSAL_UNCAPTURED）。
 *
 * 第四类 **保护期拒绝**（PROTECTION_PERIOD）是本专项新增：同目标存在未解除的
 * 上一次尝试（UNKNOWN 未核销）时，新的删除批准被明确拒绝——不是倒计时、不是排队
 * 重试，操作员先核销旧尝试才可能再批。
 *
 * 四类各有独立状态与处置，绝不归并为一个「点击失败」：分类字段（[failureClass]）
 * 决定台账状态（[ledgerState]）与处置（[disposition]），处置里没有任何一类是
 * 「自动重试」。
 */
enum class DeleteFailureClass(val wire: String) {
    /** 误卡：目标定位/身份层失效（同名歧义、旧窗口、无目标 ID、证据不足、坐标漂移）。 */
    WRONG_TARGET("WRONG_TARGET"),

    /** 未派发：破坏性确认单击从未发生（授权被拒、导航/菜单/确认框未验证、批准失效）。 */
    NOT_DISPATCHED("NOT_DISPATCHED"),

    /** 已派发结果未知：单击已发生但结果证据不权威（弹窗信号丢失、badge 不可读）。 */
    DISPATCHED_UNKNOWN("DISPATCHED_UNKNOWN"),

    /** 保护期拒绝：同目标有未解除的旧尝试，新批准被明确拒绝，不排队不倒计时。 */
    PROTECTION_PERIOD("PROTECTION_PERIOD"),
}

/** 分类给出的台账状态（独立于其他类，禁止共用一个「失败」状态）。 */
enum class DeleteFailureLedgerState(val wire: String) {
    /** 误卡类安全停：身份阻断，待操作员消歧，绝不重定位重试。 */
    BLOCKED_IDENTITY("BLOCKED_IDENTITY"),

    /** 未派发安全停：零副作用，如需再试必须走新批准（旧 actionKey 永不再执行）。 */
    NOT_DISPATCHED("NOT_DISPATCHED"),

    /** 已派发未知：保持 UNKNOWN（A13 相位不回退），等待操作员核销。 */
    UNKNOWN("UNKNOWN"),

    /** 保护期：明确拒绝态，无排队、无到期自动重发。 */
    PROTECTION_PERIOD("PROTECTION_PERIOD"),
}

/** 分类处置：每类一条，互不相同；没有任何一条是自动重试。 */
enum class DeleteFailureDisposition(val wire: String) {
    /** 误卡：不触击、不重定位；停机报原因码，操作员消歧（改标题片段/补 platformItemId）。 */
    STOP_NO_STRIKE_OPERATOR_DISAMBIGUATE("STOP_NO_STRIKE_OPERATOR_DISAMBIGUATE"),

    /** 未派发：安全退出（取消/BACK 零副作用），新尝试需重新授权，旧身份作废。 */
    SAFE_EXIT_NEW_AUTHORIZATION_REQUIRED("SAFE_EXIT_NEW_AUTHORIZATION_REQUIRED"),

    /** 已派发未知：绝不二次派发（destructiveGate 单发语义），回读置「待核对」。 */
    NEVER_RESTRIKE_PENDING_VERIFICATION("NEVER_RESTRIKE_PENDING_VERIFICATION"),

    /** 保护期：拒绝入账，操作员先核销旧尝试；到期不会自动放行。 */
    EXPLICIT_REJECT_NO_QUEUE("EXPLICIT_REJECT_NO_QUEUE"),
}

/**
 * 一条删除失败分类记录：失败类 + 稳定原因码 + 可读原因 + 出处（taskId/尝试号）。
 *
 * 原因码与 B13 的拒绝码保持血缘（TapAdmissionGate 的 WINDOW_CHANGED/
 * SESSION_EPOCH_CHANGED、ItemIdentityEvidence 的歧义/不足原因），但由本层重新
 * 命名归档，绝不把六序裁决的码吞成一个「CLICK_FAILED」。
 */
data class DeleteFailureRecord(
    val failureClass: DeleteFailureClass,
    val reasonCode: String,
    val reason: String,
    val taskId: String? = null,
    val attempt: Int = 0,
) {
    val ledgerState: DeleteFailureLedgerState
        get() = when (failureClass) {
            DeleteFailureClass.WRONG_TARGET -> DeleteFailureLedgerState.BLOCKED_IDENTITY
            DeleteFailureClass.NOT_DISPATCHED -> DeleteFailureLedgerState.NOT_DISPATCHED
            DeleteFailureClass.DISPATCHED_UNKNOWN -> DeleteFailureLedgerState.UNKNOWN
            DeleteFailureClass.PROTECTION_PERIOD -> DeleteFailureLedgerState.PROTECTION_PERIOD
        }

    val disposition: DeleteFailureDisposition
        get() = when (failureClass) {
            DeleteFailureClass.WRONG_TARGET ->
                DeleteFailureDisposition.STOP_NO_STRIKE_OPERATOR_DISAMBIGUATE
            DeleteFailureClass.NOT_DISPATCHED ->
                DeleteFailureDisposition.SAFE_EXIT_NEW_AUTHORIZATION_REQUIRED
            DeleteFailureClass.DISPATCHED_UNKNOWN ->
                DeleteFailureDisposition.NEVER_RESTRIKE_PENDING_VERIFICATION
            DeleteFailureClass.PROTECTION_PERIOD ->
                DeleteFailureDisposition.EXPLICIT_REJECT_NO_QUEUE
        }

    init {
        require(reasonCode.isNotBlank()) { "reason code is required (never a bare CLICK_FAILED)" }
    }
}

/** 误卡类的原因码（定位/身份层，全部在触击前 fail-closed）。 */
object WrongTargetReason {
    /** 详情页标题与清单定位到的目标不一致（进错详情/卡片被换）。 */
    const val DETAIL_TITLE_MISMATCH = "DETAIL_TITLE_MISMATCH"

    /** 复合可见属性命中多张卡片（同名/同标题歧义），禁止自动挑一张。 */
    const val SAME_TITLE_AMBIGUITY = "SAME_TITLE_AMBIGUITY"

    /** 采获来自另一无障碍窗口/会话 epoch（旧窗口），坐标作废。 */
    const val STALE_WINDOW = "STALE_WINDOW"

    /** 目标既无 platformItemId 也无可读复合属性（无目标 ID）。 */
    const val NO_TARGET_ID = "NO_TARGET_ID"

    /** 证据级别不足（B13 INSUFFICIENT：账号域缺失/属性数 < 2/零命中）。 */
    const val INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

    /** 列表布局漂移被守卫拦截（P09 第二次失败的原型：误卡风险，安全停）。 */
    const val LAYOUT_DRIFT_BLOCKED = "LAYOUT_DRIFT_BLOCKED"
}

/** 未派发类的原因码（单击从未发生）。 */
object NotDispatchedReason {
    /** 服务端受控台账拒绝授权（G3_NOT_ACCEPTED / intent 409）。 */
    const val INTENT_REJECTED = "INTENT_REJECTED"

    /** 导航未到达「我发布的-已下架」列表。 */
    const val NAVIGATION_FAILED = "NAVIGATION_FAILED"

    /** 管理菜单锚点缺失/异常（按锚点契约必须取消/BACK 零副作用退出）。 */
    const val MENU_NOT_VERIFIED = "MENU_NOT_VERIFIED"

    /** 确认框不唯一或文本不符（「您确定要删除这个宝贝吗？」+确定/取消缺一不可）。 */
    const val CONFIRM_DIALOG_NOT_UNIQUE = "CONFIRM_DIALOG_NOT_UNIQUE"

    /** 批准不存在/已过期/已消费，单击未获本地放行。 */
    const val APPROVAL_NOT_VALID = "APPROVAL_NOT_VALID"

    /** 取消闭环退出不干净（有副作用/未回到安全页）。 */
    const val CANCEL_LOOP_NOT_CLEAN = "CANCEL_LOOP_NOT_CLEAN"

    /** 事件与当前原语不匹配（接线错序，一律安全停）。 */
    const val UNEXPECTED_EVENT = "UNEXPECTED_EVENT"
}

/** 已派发结果未知类的原因码。 */
object DispatchedUnknownReason {
    /** 确认弹窗消失信号时序未捕获（P09 第三次失败/终版验收的机器核验形态）。 */
    const val DIALOG_DISMISSAL_UNCAPTURED = "DIALOG_DISMISSAL_UNCAPTURED"

    /** badge 门禁不可读（v2 详情路径 tabs 不在树内；B/W 既有 BADGE_UNREADABLE 血缘）。 */
    const val BADGE_UNREADABLE = "BADGE_UNREADABLE"

    /** 回读不结论（列表状态与 badge 证据互相矛盾）。 */
    const val READBACK_INCONCLUSIVE = "READBACK_INCONCLUSIVE"
}

/** 保护期拒绝类的原因码。 */
object ProtectionPeriodReason {
    /** 同目标上一次尝试仍 UNKNOWN 未核销。 */
    const val UNRESOLVED_PRIOR_ATTEMPT = "UNRESOLVED_PRIOR_ATTEMPT"

    /** 批准自带保护窗口（操作员显式设定，窗口内明确拒绝）。 */
    const val APPROVAL_PROTECTION_WINDOW = "APPROVAL_PROTECTION_WINDOW"
}

/**
 * P09 三次历史失败的分类重放（冻结证据 → 分类学的对照表）。
 *
 * 三次尝试各归一类，验证「不归并」纪律：没有任何两次尝试共享同一个
 * (failureClass, ledgerState, disposition) 组合——归并即是回归。
 */
object P09DeleteHistoryReplay {
    data class HistoricalAttempt(
        val taskId: String,
        val outcomeOnDevice: String,
        val record: DeleteFailureRecord,
    )

    val attempts: List<HistoricalAttempt> = listOf(
        HistoricalAttempt(
            taskId = "4d226249",
            outcomeOnDevice = "intent 409 → 未受理，本地 NOT_SUBMITTED 收尾",
            record = DeleteFailureRecord(
                failureClass = DeleteFailureClass.NOT_DISPATCHED,
                reasonCode = NotDispatchedReason.INTENT_REJECTED,
                reason = "受控台账拒绝授权（actionId 错位期），确认单击从未派发；" +
                    "404/409 一律本地 NOT_SUBMITTED，不重试",
                taskId = "4d226249",
                attempt = 1,
            ),
        ),
        HistoricalAttempt(
            taskId = "6d22dd62",
            outcomeOnDevice = "坐标漂移 → 布局守卫安全停，CONFIRMED_NOT_SUBMITTED",
            record = DeleteFailureRecord(
                failureClass = DeleteFailureClass.WRONG_TARGET,
                reasonCode = WrongTargetReason.LAYOUT_DRIFT_BLOCKED,
                reason = "已下架首卡 y 随横幅漂移（实测可达 532px），旧坐标指向错误卡片；" +
                    "守卫拦截，误卡类安全停",
                taskId = "6d22dd62",
                attempt = 2,
            ),
        ),
        HistoricalAttempt(
            taskId = "37a665b0",
            outcomeOnDevice = "确认单击已派发、真实删除发生；弹窗消失信号未捕获 → 机器 UNKNOWN，" +
                "操作员 CONFIRMED_APPLIED",
            record = DeleteFailureRecord(
                failureClass = DeleteFailureClass.DISPATCHED_UNKNOWN,
                reasonCode = DispatchedUnknownReason.DIALOG_DISMISSAL_UNCAPTURED,
                reason = "单击已发生但结果证据不权威；UNKNOWN 不重试，操作员以 " +
                    "platformItemId + 卡片消失证据核销",
                taskId = "37a665b0",
                attempt = 3,
            ),
        ),
    )

    /** 四类在三次历史 + 保护期场景中各出现且仅出现于自己的形态（分类不塌缩）。 */
    fun classesStayDistinct(): Boolean {
        val states = attempts.map { it.record.ledgerState }.toSet()
        val dispositions = attempts.map { it.record.disposition }.toSet()
        // 三次历史覆盖三类、三种状态、三种处置；保护期是第四类，与三者均不同。
        return states.size == attempts.size && dispositions.size == attempts.size
    }
}
