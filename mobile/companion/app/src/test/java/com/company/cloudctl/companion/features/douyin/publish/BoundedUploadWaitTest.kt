package com.company.cloudctl.companion.features.douyin.publish

import com.company.cloudctl.companion.features.douyin.publish.BoundedUploadWait.DouyinUploadStage
import com.company.cloudctl.companion.features.douyin.publish.BoundedUploadWait.UploadWaitDecision
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

class BoundedUploadWaitTest {
    private val stage = DouyinUploadStage.MEDIA_UPLOAD

    @Test
    fun monotonicProgressResetsConsecutiveStallBudget() {
        var wait = BoundedUploadWait()
        var pair = wait.onProgressAdvanced(stage, 10)
        wait = pair.first
        assertTrue(assertIs<UploadWaitDecision.Progressing>(pair.second).monotonic)

        repeat(3) {
            pair = wait.onProgressAdvanced(stage, 10)
            wait = pair.first
        }
        assertEquals(3, assertIs<UploadWaitDecision.Progressing>(pair.second).stallTicksLeft)

        pair = wait.onProgressAdvanced(stage, 25)
        wait = pair.first
        val progress = assertIs<UploadWaitDecision.Progressing>(pair.second)
        assertTrue(progress.monotonic)
        assertEquals(6, progress.stallTicksLeft)

        pair = wait.onProgressAdvanced(stage, 25)
        assertEquals(5, assertIs<UploadWaitDecision.Progressing>(pair.second).stallTicksLeft)
    }

    @Test
    fun exhaustedStallBudgetFailsBoundedWithStallCode() {
        var wait = BoundedUploadWait(stallBudgetPerStage = mapOf(stage to 1))
        wait = wait.onProgressAdvanced(stage, 50).first
        val stalled = assertIs<UploadWaitDecision.Stalled>(wait.onProgress(stage, 50))
        assertEquals(BoundedUploadWait.STALL_CODE, stalled.code)
        assertEquals(stage, stalled.stage)
        assertTrue(stalled.retryable)
        assertTrue(stalled.reason.contains("非单调"))
    }

    @Test
    fun stageTimeoutFailsBoundedAndRetryable() {
        val stalled = assertIs<UploadWaitDecision.Stalled>(
            BoundedUploadWait().onStageTimeout(DouyinUploadStage.PROCESSING),
        )
        assertEquals(BoundedUploadWait.STALL_CODE, stalled.code)
        assertTrue(stalled.retryable)
        assertTrue(stalled.reason.contains("超时"))
    }

    @Test
    fun perStageBudgetsAreIndependent() {
        var wait = BoundedUploadWait()
        repeat(3) { wait = wait.onProgressAdvanced(stage, 5).first }
        val progressing = assertIs<UploadWaitDecision.Progressing>(
            wait.onProgress(DouyinUploadStage.PROCESSING, 1),
        )
        assertTrue(progressing.monotonic)
        assertEquals(4, progressing.stallTicksLeft)
    }

    @Test
    fun commitIsReservedExactlyOnce() {
        var wait = BoundedUploadWait()
        val first = wait.requestCommitAdvanced()
        assertIs<UploadWaitDecision.CommitAuthorized>(first.second)
        assertTrue(first.first.commitAttemptReserved())

        wait = first.first
        val second = assertIs<UploadWaitDecision.WaitingUser>(wait.requestCommit())
        assertTrue(second.reason.contains("DOUYIN_COMMIT_ALREADY_RESERVED"))
    }

    @Test
    fun unknownOutcomeForcesWaitingUserAndNeverAutoResends() {
        var wait = BoundedUploadWait().markUnknownOutcome()
        val decision = assertIs<UploadWaitDecision.WaitingUser>(wait.requestCommit())
        assertTrue(decision.reason.contains("DOUYIN_UNKNOWN_KEEP_WAITING"))
        assertTrue(decision.reason.contains("禁止自动重发"))

        wait = wait.retryAfterStall()
        assertTrue(wait.unknownOutcome())
        assertIs<UploadWaitDecision.WaitingUser>(wait.requestCommit())
        assertIs<UploadWaitDecision.WaitingUser>(wait.onProgress(stage, 99))
        assertIs<UploadWaitDecision.WaitingUser>(wait.onStageTimeout(stage))
    }

    @Test
    fun retryAfterStallKeepsCommitDiscipline() {
        var wait = BoundedUploadWait(stallBudgetPerStage = mapOf(stage to 1))
        wait = wait.onProgressAdvanced(stage, 7).first
        assertIs<UploadWaitDecision.Stalled>(wait.onProgress(stage, 7))

        val retried = wait.retryAfterStall()
        assertIs<UploadWaitDecision.Progressing>(retried.onProgress(stage, 7))

        var committed = BoundedUploadWait().requestCommitAdvanced().first
        committed = committed.retryAfterStall()
        val refused = assertIs<UploadWaitDecision.WaitingUser>(committed.requestCommit())
        assertTrue(refused.reason.contains("DOUYIN_COMMIT_ALREADY_RESERVED"))
    }

    @Test
    fun invalidBudgetIsRejectedAtConstruction() {
        assertTrue(runCatching { BoundedUploadWait(stallBudgetPerStage = emptyMap()) }.isFailure)
        assertTrue(runCatching { BoundedUploadWait(stallBudgetPerStage = mapOf(stage to 0)) }.isFailure)
        assertFalse(runCatching { BoundedUploadWait(stallBudgetPerStage = mapOf(stage to 1)) }.isFailure)
    }
}
