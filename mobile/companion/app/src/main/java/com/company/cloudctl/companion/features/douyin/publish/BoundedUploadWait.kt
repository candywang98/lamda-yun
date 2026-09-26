package com.company.cloudctl.companion.features.douyin.publish

/**
 * Pure state machine for bounded upload/page waits.
 *
 * A monotonic event advances the observation and resets the consecutive stall
 * budget. Duplicate or regressed events consume that stage's budget. A commit
 * reservation and an unknown outcome are sticky across retries, so retrying a
 * wait can never authorize a second publish attempt.
 */
class BoundedUploadWait(
    private val stallBudgetPerStage: Map<DouyinUploadStage, Int> = DEFAULT_STALL_BUDGET_PER_STAGE,
    private val lastProgressPerStage: Map<DouyinUploadStage, Long> = emptyMap(),
    private val stallTicksPerStage: Map<DouyinUploadStage, Int> = emptyMap(),
    private val commitAttemptReserved: Boolean = false,
    private val unknownOutcome: Boolean = false,
) {
    init {
        require(stallBudgetPerStage.isNotEmpty()) { "stallBudgetPerStage must not be empty" }
        require(stallBudgetPerStage.values.all { it in 1..64 }) {
            "stall budget must be within 1..64 per stage"
        }
        require(
            stallTicksPerStage.all { (stage, ticks) ->
                val budget = stallBudgetPerStage[stage]
                budget != null && ticks in 0..budget
            },
        ) { "stallTicksPerStage out of budget" }
    }

    enum class DouyinUploadStage(val wireName: String) {
        MEDIA_UPLOAD("media_upload"),
        PROCESSING("processing"),
        PUBLISH_PAGE_LOAD("publish_page_load"),
    }

    sealed interface UploadWaitDecision {
        data class Progressing(
            val stage: DouyinUploadStage,
            val monotonic: Boolean,
            val stallTicksLeft: Int,
        ) : UploadWaitDecision

        data class Stalled(
            val code: String,
            val stage: DouyinUploadStage,
            val retryable: Boolean,
            val reason: String,
        ) : UploadWaitDecision

        /** Reserves one commit_once attempt; this pure class does not perform it. */
        data class CommitAuthorized(val reason: String) : UploadWaitDecision

        data class WaitingUser(val reason: String) : UploadWaitDecision
    }

    fun onProgress(stage: DouyinUploadStage, observed: Long): UploadWaitDecision {
        if (unknownOutcome) return keepWaiting()
        val budget = budgetOf(stage)
        val last = lastProgressPerStage[stage]
        return if (last == null || observed > last) {
            UploadWaitDecision.Progressing(stage, monotonic = true, stallTicksLeft = budget)
        } else {
            val ticks = (stallTicksPerStage[stage] ?: 0) + 1
            if (ticks >= budget) {
                stalled(
                    stage,
                    "阶段 ${stage.wireName} 进展非单调（$observed <= $last），停滞预算 $budget 已耗尽",
                )
            } else {
                UploadWaitDecision.Progressing(stage, monotonic = false, stallTicksLeft = budget - ticks)
            }
        }
    }

    fun onProgressAdvanced(
        stage: DouyinUploadStage,
        observed: Long,
    ): Pair<BoundedUploadWait, UploadWaitDecision> {
        val decision = onProgress(stage, observed)
        val next = when (decision) {
            is UploadWaitDecision.Progressing -> copy(
                lastProgressPerStage = lastProgressPerStage + (stage to observed),
                stallTicksPerStage = stallTicksPerStage + (
                    stage to if (decision.monotonic) 0 else (stallTicksPerStage[stage] ?: 0) + 1
                ),
            )
            else -> this
        }
        return next to decision
    }

    fun onStageTimeout(stage: DouyinUploadStage): UploadWaitDecision {
        if (unknownOutcome) return keepWaiting()
        return stalled(stage, "阶段 ${stage.wireName} 等待超时（预算内无单调进展）")
    }

    /** Sticky marker for a commit attempt whose result cannot be reconciled yet. */
    fun markUnknownOutcome(): BoundedUploadWait = copy(unknownOutcome = true)

    /** One commit_once reservation; callers must reconcile before any later action. */
    fun requestCommit(): UploadWaitDecision = when {
        unknownOutcome -> UploadWaitDecision.WaitingUser(
            "DOUYIN_UNKNOWN_KEEP_WAITING: 发布提交结果未知，禁止自动重发，转 WAITING_USER",
        )
        commitAttemptReserved -> UploadWaitDecision.WaitingUser(
            "DOUYIN_COMMIT_ALREADY_RESERVED: commit_once 已保留一次，重复事件不重复发布",
        )
        else -> UploadWaitDecision.CommitAuthorized("发布前置链路 14 步齐，唯一一次 commit_once 授权")
    }

    fun requestCommitAdvanced(): Pair<BoundedUploadWait, UploadWaitDecision> {
        val decision = requestCommit()
        val next = if (decision is UploadWaitDecision.CommitAuthorized) {
            copy(commitAttemptReserved = true)
        } else {
            this
        }
        return next to decision
    }

    /** Clear only the current wait observation; commit and unknown markers remain sticky. */
    fun retryAfterStall(): BoundedUploadWait = copy(
        lastProgressPerStage = emptyMap(),
        stallTicksPerStage = emptyMap(),
    )

    fun commitAttemptReserved(): Boolean = commitAttemptReserved

    fun unknownOutcome(): Boolean = unknownOutcome

    private fun keepWaiting() = UploadWaitDecision.WaitingUser(
        "DOUYIN_UNKNOWN_KEEP_WAITING: 提交结果未知，等待段不再做进展判定，转 WAITING_USER",
    )

    private fun stalled(stage: DouyinUploadStage, detail: String) = UploadWaitDecision.Stalled(
        code = STALL_CODE,
        stage = stage,
        retryable = true,
        reason = "$STALL_CODE: $detail",
    )

    private fun budgetOf(stage: DouyinUploadStage): Int =
        stallBudgetPerStage[stage] ?: error("no budget registered for stage ${stage.wireName}")

    private fun copy(
        lastProgressPerStage: Map<DouyinUploadStage, Long> = this.lastProgressPerStage,
        stallTicksPerStage: Map<DouyinUploadStage, Int> = this.stallTicksPerStage,
        commitAttemptReserved: Boolean = this.commitAttemptReserved,
        unknownOutcome: Boolean = this.unknownOutcome,
    ) = BoundedUploadWait(
        stallBudgetPerStage = stallBudgetPerStage,
        lastProgressPerStage = lastProgressPerStage,
        stallTicksPerStage = stallTicksPerStage,
        commitAttemptReserved = commitAttemptReserved,
        unknownOutcome = unknownOutcome,
    )

    companion object {
        const val STALL_CODE = "DOUYIN_UPLOAD_STALLED"

        val DEFAULT_STALL_BUDGET_PER_STAGE: Map<DouyinUploadStage, Int> = mapOf(
            DouyinUploadStage.MEDIA_UPLOAD to 6,
            DouyinUploadStage.PROCESSING to 4,
            DouyinUploadStage.PUBLISH_PAGE_LOAD to 3,
        )
    }
}
