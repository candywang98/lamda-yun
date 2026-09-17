package com.company.cloudctl.companion.features.xianyu.publish

/**
 * P10 任务卡 §3：发布目标单独持久（与任务身份分离）+ 单件串行推进。
 *
 * - 发布目标（publish target）是「要发布的一件商品」的稳定身份；MobileTask 是一次
 *   执行尝试。同一目标重试会铸造新 taskId（taskIds 是列表），目标身份不变——所以
 *   「手机侧目标」与「Web/服务端记录」才能对同一目标对账同一结果。
 * - 队列推进规则（单件串行）：任一目标处于 [PublishTargetState.IN_FLIGHT] 时，
 *   [PublishTargetLedger.nextTarget] 不发放任何新目标；只有当前目标的结果被确认
 *   （成功/失败确认、取消）或进入未确认失败（可重发）后，队列才前进。
 * - 已确认成功的目标绝不重做；已确认失败的目标不再自动重发；可重发的只有
 *   未开始（PENDING）与未确认失败（FAILED_UNCONFIRMED）。
 * - 外部身份（platformItemId）在结果确认时写回目标，与任务身份分离。
 */
enum class PublishTargetState {
    /** 未开始。 */
    PENDING,

    /** 已发放（已铸造任务），结果未回。 */
    IN_FLIGHT,

    /** 任务报失败但结果未确认（可重发位）。 */
    FAILED_UNCONFIRMED,

    /** 人工/证据确认成功——终态，绝不重做。 */
    SUCCEEDED_CONFIRMED,

    /** 确认失败——终态，不再自动重发。 */
    FAILED_CONFIRMED,

    /** 取消——终态。 */
    CANCELLED,
}

/** 单个发布目标的设备侧账本行（持久化由接线层落库，本类型只定语义）。 */
data class PublishTargetRecord(
    val targetId: String,
    val queueId: String,
    val position: Int,
    val claimedBoundary: PublishCompletionBoundary,
    val state: PublishTargetState = PublishTargetState.PENDING,
    /** 该目标铸造过的全部任务（重试会追加；任务身份 ≠ 目标身份）。 */
    val taskIds: List<String> = emptyList(),
    /** 闲鱼商品外部身份，结果确认时写回。 */
    val externalItemId: String? = null,
    /** 记录的完成边界 + 降级痕迹（确认时由判定器给出）。 */
    val recordedBoundary: PublishCompletionBoundary? = null,
    val boundaryDowngraded: Boolean = false,
) {
    val terminal: Boolean
        get() = state in TERMINAL_STATES

    companion object {
        val TERMINAL_STATES = setOf(
            PublishTargetState.SUCCEEDED_CONFIRMED,
            PublishTargetState.FAILED_CONFIRMED,
            PublishTargetState.CANCELLED,
        )
    }
}

/**
 * 设备侧发布目标账本：单件串行推进的规则本体（纯内存实现，可单测；
 * 落库/与服务端对账由接线层负责——接缝留给主会话）。
 */
class PublishTargetLedger {

    private val targets = linkedMapOf<String, PublishTargetRecord>()
    private val queueOrder = mutableListOf<String>()

    fun enqueue(
        targetId: String,
        queueId: String,
        claimedBoundary: PublishCompletionBoundary,
    ): PublishTargetRecord {
        require(targetId.isNotEmpty()) { "targetId is required" }
        require(!targets.containsKey(targetId)) { "target already enrolled: $targetId" }
        val position = targets.values.count { it.queueId == queueId }
        val record = PublishTargetRecord(
            targetId = targetId,
            queueId = queueId,
            position = position,
            claimedBoundary = claimedBoundary,
        )
        targets[targetId] = record
        queueOrder.add(targetId)
        return record
    }

    fun record(targetId: String): PublishTargetRecord? = targets[targetId]

    fun queue(queueId: String): List<PublishTargetRecord> =
        targets.values.filter { it.queueId == queueId }.sortedBy { it.position }

    private fun update(targetId: String, transform: (PublishTargetRecord) -> PublishTargetRecord): PublishTargetRecord {
        val current = targets[targetId] ?: error("unknown publish target: $targetId")
        val next = transform(current)
        targets[targetId] = next
        return next
    }

    /** 发放：目标进入 IN_FLIGHT 并登记本次铸造的 taskId。 */
    fun markInFlight(targetId: String, taskId: String): PublishTargetRecord =
        update(targetId) { record ->
            when (record.state) {
                PublishTargetState.PENDING, PublishTargetState.FAILED_UNCONFIRMED -> record.copy(
                    state = PublishTargetState.IN_FLIGHT,
                    taskIds = record.taskIds + taskId,
                )
                else -> error("target $targetId is ${record.state}; only PENDING/FAILED_UNCONFIRMED can be issued")
            }
        }

    /** 执行器报失败（未确认）。 */
    fun markFailedUnconfirmed(targetId: String): PublishTargetRecord =
        update(targetId) { record ->
            check(record.state == PublishTargetState.IN_FLIGHT) { "target $targetId is not IN_FLIGHT" }
            record.copy(state = PublishTargetState.FAILED_UNCONFIRMED)
        }

    /** 确认成功：写回外部身份 + 记录边界（含降级痕迹）。终态，绝不重做。 */
    fun confirmSuccess(
        targetId: String,
        externalItemId: String,
        recordedBoundary: PublishCompletionBoundary,
        boundaryDowngraded: Boolean,
    ): PublishTargetRecord =
        update(targetId) { record ->
            check(record.state == PublishTargetState.IN_FLIGHT || record.state == PublishTargetState.FAILED_UNCONFIRMED) {
                "target $targetId cannot be confirmed from ${record.state}"
            }
            record.copy(
                state = PublishTargetState.SUCCEEDED_CONFIRMED,
                externalItemId = externalItemId,
                recordedBoundary = recordedBoundary,
                boundaryDowngraded = boundaryDowngraded,
            )
        }

    /** 确认失败：终态，不再自动重发。 */
    fun confirmFailure(targetId: String): PublishTargetRecord =
        update(targetId) { record ->
            check(record.state == PublishTargetState.IN_FLIGHT || record.state == PublishTargetState.FAILED_UNCONFIRMED) {
                "target $targetId cannot be confirmed from ${record.state}"
            }
            record.copy(state = PublishTargetState.FAILED_CONFIRMED)
        }

    /** 取消：只有未确认终态的目标可取消。 */
    fun cancel(targetId: String): PublishTargetRecord =
        update(targetId) { record ->
            check(!record.terminal) { "terminal target $targetId cannot be cancelled" }
            record.copy(state = PublishTargetState.CANCELLED)
        }

    /**
     * 单件串行推进：队列里存在 IN_FLIGHT 目标时返回 null（结果确认后才决定下一目标）；
     * 否则按 position 取第一个 未开始/未确认失败 的目标。已确认成功/确认失败/取消
     * 的目标永不返回（已成功项不重做）。
     */
    fun nextTarget(queueId: String): PublishTargetRecord? {
        val queue = queue(queueId)
        if (queue.any { it.state == PublishTargetState.IN_FLIGHT }) return null
        return queue.firstOrNull {
            it.state == PublishTargetState.PENDING || it.state == PublishTargetState.FAILED_UNCONFIRMED
        }
    }
}
