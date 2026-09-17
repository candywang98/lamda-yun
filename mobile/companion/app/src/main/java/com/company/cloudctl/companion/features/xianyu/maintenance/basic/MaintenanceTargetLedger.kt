package com.company.cloudctl.companion.features.xianyu.maintenance.basic

/**
 * X11 — 逐目标执行台账（验收用例 1：逐目标台账幂等）。
 *
 * 目标身份（[MaintenanceTargetKey]）+ 动作（[MaintenanceActionKind]）构成
 * 「要对哪一件做什么」的稳定身份；subtask/taskId 只是一次执行尝试。
 * 部分成功后再次运行：COMPLETED 目标**永不重新发放**（[nextActionable] 跳过），
 * READBACK_HELD / FAILED 同为终态（重试需操作员重新批准，绝不自动重发）；
 * UNKNOWN 目标阻塞本运行（批量运行到达它时闩 PROTECTION_PERIOD_ACTIVE，
 * 与 X10「未知任务不自动重新删除」同血统）。
 *
 * 纯内存规则本体（与 X10 publish 的 PublishTargetLedger 同构的单件串行纪律）；
 * 落库/对账接线留给主会话。
 */
enum class MaintenanceTargetState(val wire: String) {
    /** 未开始。 */
    PENDING("PENDING"),

    /** 已发放（在飞），结果未回。 */
    IN_FLIGHT("IN_FLIGHT"),

    /** 机器可记成功（回读通过，结果类型已对齐动作）。终态，绝不重做。 */
    COMPLETED("COMPLETED"),

    /** 回读不符/不可读：不记成功，等操作员核销。终态（本运行内）。 */
    READBACK_HELD("READBACK_HELD"),

    /** 已派发结果未知：锁保护期，操作员核销前不可再动。 */
    UNKNOWN("UNKNOWN"),

    /** 零副作用失败（授权被拒/导航未达/锚点未验证）。终态，重试需新批准。 */
    FAILED("FAILED"),
}

/** 单目标台账行。 */
data class MaintenanceTargetRecord(
    val targetId: String,
    val key: MaintenanceTargetKey,
    val action: MaintenanceActionKind,
    val state: MaintenanceTargetState = MaintenanceTargetState.PENDING,
    /** 机器可记成功时的动作结果（类型对齐门由 [complete] 强制）。 */
    val result: MaintenanceActionResult? = null,
    /** 尝试过的 subtask（重发会追加；subtask ≠ 目标身份）。 */
    val subtaskIds: List<String> = emptyList(),
    /** 非成功终局的原因码（READBACK_HELD/UNKNOWN/FAILED）。 */
    val reasonCode: String? = null,
) {
    val terminal: Boolean
        get() = state in TERMINAL_STATES

    companion object {
        val TERMINAL_STATES = setOf(
            MaintenanceTargetState.COMPLETED,
            MaintenanceTargetState.READBACK_HELD,
            MaintenanceTargetState.FAILED,
        )
    }
}

/** 逐目标台账：登记、单件发放、终局记录、幂等再运行。 */
class MaintenanceTargetLedger {

    private val targets = linkedMapOf<String, MaintenanceTargetRecord>()

    fun enroll(
        targetId: String,
        key: MaintenanceTargetKey,
        action: MaintenanceActionKind,
    ): MaintenanceTargetRecord {
        require(targetId.isNotBlank()) { "targetId is required" }
        require(!targets.containsKey(targetId)) { "target already enrolled: $targetId" }
        val record = MaintenanceTargetRecord(targetId = targetId, key = key, action = action)
        targets[targetId] = record
        return record
    }

    fun record(targetId: String): MaintenanceTargetRecord? = targets[targetId]

    fun all(): List<MaintenanceTargetRecord> = targets.values.toList()

    private fun update(
        targetId: String,
        transform: (MaintenanceTargetRecord) -> MaintenanceTargetRecord,
    ): MaintenanceTargetRecord {
        val current = targets[targetId] ?: error("unknown maintenance target: $targetId")
        val next = transform(current)
        targets[targetId] = next
        return next
    }

    /** 发放：PENDING → IN_FLIGHT 并登记 subtask（一个目标可因重试多次在飞记录）。 */
    fun markInFlight(targetId: String, subtaskId: String): MaintenanceTargetRecord =
        update(targetId) { record ->
            when (record.state) {
                MaintenanceTargetState.PENDING -> record.copy(
                    state = MaintenanceTargetState.IN_FLIGHT,
                    subtaskIds = record.subtaskIds + subtaskId,
                )
                else -> error("target $targetId is ${record.state}; only PENDING can be issued")
            }
        }

    /**
     * 机器可记成功：结果类型必须对齐动作（跨动作记账直接抛错）。
     * 终态 COMPLETED，绝不重做。
     */
    fun complete(
        targetId: String,
        result: MaintenanceActionResult,
    ): MaintenanceTargetRecord = update(targetId) { record ->
        check(record.state == MaintenanceTargetState.IN_FLIGHT) {
            "target $targetId is ${record.state}; only IN_FLIGHT can complete"
        }
        MaintenanceActionResult.requireMatches(record.action, result)
        record.copy(state = MaintenanceTargetState.COMPLETED, result = result)
    }

    /** 回读不符/不可读：不记成功。终态 READBACK_HELD（等操作员）。 */
    fun holdReadback(targetId: String, reasonCode: String): MaintenanceTargetRecord =
        update(targetId) { record ->
            check(record.state == MaintenanceTargetState.IN_FLIGHT) {
                "target $targetId is ${record.state}; only IN_FLIGHT can hold a readback"
            }
            record.copy(
                state = MaintenanceTargetState.READBACK_HELD,
                reasonCode = reasonCode,
            )
        }

    /** 已派发结果未知：UNKNOWN，操作员核销前本目标锁死。 */
    fun markUnknown(targetId: String, reasonCode: String): MaintenanceTargetRecord =
        update(targetId) { record ->
            check(record.state == MaintenanceTargetState.IN_FLIGHT) {
                "target $targetId is ${record.state}; only IN_FLIGHT can go UNKNOWN"
            }
            record.copy(state = MaintenanceTargetState.UNKNOWN, reasonCode = reasonCode)
        }

    /** 零副作用失败：终态 FAILED（重试需新批准，绝不自动重发）。 */
    fun markFailed(targetId: String, reasonCode: String): MaintenanceTargetRecord =
        update(targetId) { record ->
            check(record.state == MaintenanceTargetState.IN_FLIGHT) {
                "target $targetId is ${record.state}; only IN_FLIGHT can fail"
            }
            record.copy(state = MaintenanceTargetState.FAILED, reasonCode = reasonCode)
        }

    /** 操作员核销 UNKNOWN 目标：可重新批准（状态回 PENDING 由新批准/新运行决定）。 */
    fun resolveUnknown(targetId: String, evidence: String): MaintenanceTargetRecord =
        update(targetId) { record ->
            require(evidence.isNotBlank()) { "resolution evidence is required" }
            check(record.state == MaintenanceTargetState.UNKNOWN) {
                "target $targetId is ${record.state}; only UNKNOWN can be resolved"
            }
            record.copy(state = MaintenanceTargetState.PENDING, reasonCode = null)
        }

    /**
     * 幂等再运行的准入视图：按登记序返回下一个可动目标——
     * COMPLETED/READBACK_HELD/FAILED 跳过（已完成动作不重复执行）；
     * UNKNOWN 阻塞（返回 null，调用方闩 PROTECTION_PERIOD_ACTIVE）；
     * IN_FLIGHT 返回它（单件在飞，先报结果）。
     */
    fun nextActionable(): MaintenanceTargetRecord? {
        val unknown = targets.values.firstOrNull { it.state == MaintenanceTargetState.UNKNOWN }
        if (unknown != null) return null
        return targets.values.firstOrNull {
            it.state == MaintenanceTargetState.IN_FLIGHT ||
                it.state == MaintenanceTargetState.PENDING
        }
    }

    /** 目标（按身份键+动作）是否已记成功——重复计划展开时用于跳过。 */
    fun completedKeys(): Set<String> = targets.values
        .filter { it.state == MaintenanceTargetState.COMPLETED }
        .map { "${it.key.identityKey}|${it.action.wire}" }
        .toSet()
}
