package com.company.cloudctl.companion.features.xianyu.publish

import com.company.cloudctl.companion.features.xianyu.publish.PublishEvent.HumanConfirmed
import com.company.cloudctl.companion.features.xianyu.publish.PublishEvent.InputProof
import com.company.cloudctl.companion.features.xianyu.publish.PublishEvent.MediaCropReturned
import com.company.cloudctl.companion.features.xianyu.publish.PublishEvent.MenuSettled
import com.company.cloudctl.companion.features.xianyu.publish.PublishEvent.PublishSuccessObserved
import com.company.cloudctl.companion.features.xianyu.publish.PublishEvent.RequiredFieldSnapshot
import com.company.cloudctl.companion.features.xianyu.publish.PublishStepPrimitive.HumanCheckpoint
import com.company.cloudctl.companion.features.xianyu.publish.PublishStepPrimitive.ProveTextInput
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * P10 验收用例（Android 侧）——发布编排步骤原语：
 * 媒体裁剪返回续行、菜单 settle、输入证明、必填检查、WAITING_USER 检查点，
 * 以及完成边界在编排终态的收口（低完成度不记全自动）。
 */
class PublishOrchestratorTest {

    private fun feedFullAutoUntilSuccess(
        orchestrator: PublishOrchestrator,
        stagedImages: Int = 12,
        plannedImages: Int = 12,
        success: PublishSuccessObserved = PublishSuccessObserved(byHuman = false),
    ): PublishDecision {
        orchestrator.submit(MenuSettled(entryVisible = true))
        orchestrator.submit(
            MediaCropReturned(backToPublishPage = true, plannedImages = plannedImages, stagedImages = stagedImages),
        )
        orchestrator.submit(
            InputProof(textField = ProveTextInput.TextField.DESCRIPTION, readbackMatches = true, commitAuthorized = true),
        )
        orchestrator.submit(RequiredFieldSnapshot(priceFilled = true, stockFilled = true, deliveryFilled = true))
        orchestrator.submit(
            InputProof(textField = ProveTextInput.TextField.PRICE, readbackMatches = true, commitAuthorized = true),
        )
        return orchestrator.submit(success)
    }

    @Test
    fun fullAutoPlanSucceedsWithMachineEvidence() {
        val orchestrator = PublishOrchestrator(
            PublishOrchestrator.planFor(PublishCompletionBoundary.FULL_AUTO),
            PublishCompletionBoundary.FULL_AUTO,
        )
        val decision = feedFullAutoUntilSuccess(orchestrator)
        val succeeded = assertIs<PublishDecision.Succeeded>(decision)
        assertEquals(PublishCompletionBoundary.FULL_AUTO, succeeded.judgment.recorded)
        assertTrue(succeeded.judgment.successEligible)
        assertFalse(succeeded.judgment.downgraded)
    }

    @Test
    fun mediaCropReturnWithoutPageBlocksContinuation() {
        val orchestrator = PublishOrchestrator(
            PublishOrchestrator.planFor(PublishCompletionBoundary.FULL_AUTO),
            PublishCompletionBoundary.FULL_AUTO,
        )
        orchestrator.submit(MenuSettled(entryVisible = true))
        // 裁剪确认后页面没回到发布表单 → 续行失败，不许盲填。
        val decision = orchestrator.submit(
            MediaCropReturned(backToPublishPage = false, plannedImages = 12, stagedImages = 12),
        )
        assertEquals("CROP_RETURN_LOST_PAGE", assertIs<PublishDecision.Failed>(decision).code)
    }

    @Test
    fun menuNotSettledRefusesToAdvance() {
        val orchestrator = PublishOrchestrator(
            PublishOrchestrator.planFor(PublishCompletionBoundary.FULL_AUTO),
            PublishCompletionBoundary.FULL_AUTO,
        )
        val decision = orchestrator.submit(MenuSettled(entryVisible = false))
        assertEquals(
            "UNEXPECTED_EVENT:menu-settle",
            assertIs<PublishDecision.Failed>(decision).code,
        )
    }

    @Test
    fun inputProofFailureFailsClosed() {
        val orchestrator = PublishOrchestrator(
            PublishOrchestrator.planFor(PublishCompletionBoundary.FULL_AUTO),
            PublishCompletionBoundary.FULL_AUTO,
        )
        orchestrator.submit(MenuSettled(entryVisible = true))
        orchestrator.submit(MediaCropReturned(backToPublishPage = true))
        // B14：回读不一致 → 不许静默放行。
        val decision = orchestrator.submit(
            InputProof(textField = ProveTextInput.TextField.DESCRIPTION, readbackMatches = false, commitAuthorized = true),
        )
        assertEquals(
            "INPUT_PROOF_FAILED:description",
            assertIs<PublishDecision.Failed>(decision).code,
        )
    }

    @Test
    fun missingRequiredStockFailsBeforeCommit() {
        val orchestrator = PublishOrchestrator(
            PublishOrchestrator.planFor(PublishCompletionBoundary.FULL_AUTO),
            PublishCompletionBoundary.FULL_AUTO,
        )
        orchestrator.submit(MenuSettled(entryVisible = true))
        orchestrator.submit(MediaCropReturned(backToPublishPage = true))
        orchestrator.submit(
            InputProof(textField = ProveTextInput.TextField.DESCRIPTION, readbackMatches = true, commitAuthorized = true),
        )
        val decision = orchestrator.submit(
            RequiredFieldSnapshot(priceFilled = true, stockFilled = false, deliveryFilled = true),
        )
        assertEquals("REQUIRED_FIELD_MISSING", assertIs<PublishDecision.Failed>(decision).code)
    }

    @Test
    fun humanPriceCheckpointPausesAndConfirms() {
        val orchestrator = PublishOrchestrator(
            PublishOrchestrator.planFor(PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE),
            PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE,
        )
        orchestrator.submit(MenuSettled(entryVisible = true))
        orchestrator.submit(MediaCropReturned(backToPublishPage = true))
        orchestrator.submit(
            InputProof(textField = ProveTextInput.TextField.DESCRIPTION, readbackMatches = true, commitAuthorized = true),
        )
        // 必填检查通过的那一步立即转 WAITING_USER（价格检查点），不吞后续事件。
        val waiting = orchestrator.submit(
            RequiredFieldSnapshot(priceFilled = true, stockFilled = true, deliveryFilled = true),
        )
        assertEquals(HumanCheckpoint.CheckpointPoint.PRICE_ENTRY, assertIs<PublishDecision.WaitingUser>(waiting).point)
        // 人工在确认点填价并确认。
        val resumed = orchestrator.submit(HumanConfirmed(HumanCheckpoint.CheckpointPoint.PRICE_ENTRY))
        assertIs<PublishDecision.Advance>(resumed)
        val decision = orchestrator.submit(PublishSuccessObserved(byHuman = true))
        val succeeded = assertIs<PublishDecision.Succeeded>(decision)
        // 声称自动填写+人工价格，但成功页由人工确认（= 人工点击证据位）→ 记录双人工。
        assertEquals(PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT, succeeded.judgment.recorded)
        assertTrue(succeeded.judgment.downgraded)
    }

    @Test
    fun humanPriceHumanCommitPlanWalksBothCheckpoints() {
        val orchestrator = PublishOrchestrator(
            PublishOrchestrator.planFor(PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT),
            PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT,
        )
        orchestrator.submit(MenuSettled(entryVisible = true))
        orchestrator.submit(MediaCropReturned(backToPublishPage = true))
        orchestrator.submit(
            InputProof(textField = ProveTextInput.TextField.DESCRIPTION, readbackMatches = true, commitAuthorized = true),
        )
        assertEquals(
            HumanCheckpoint.CheckpointPoint.PRICE_ENTRY,
            assertIs<PublishDecision.WaitingUser>(
                orchestrator.submit(
                    RequiredFieldSnapshot(priceFilled = true, stockFilled = true, deliveryFilled = true),
                ),
            ).point,
        )
        // 价格检查点完成后立即停在最终点击检查点（连续检查点也不吞事件）。
        assertEquals(
            HumanCheckpoint.CheckpointPoint.FINAL_COMMIT,
            assertIs<PublishDecision.WaitingUser>(
                orchestrator.submit(HumanConfirmed(HumanCheckpoint.CheckpointPoint.PRICE_ENTRY)),
            ).point,
        )
        assertIs<PublishDecision.Advance>(
            orchestrator.submit(HumanConfirmed(HumanCheckpoint.CheckpointPoint.FINAL_COMMIT)),
        )
        val decision = orchestrator.submit(PublishSuccessObserved(byHuman = true))
        val succeeded = assertIs<PublishDecision.Succeeded>(decision)
        assertEquals(PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT, succeeded.judgment.recorded)
        assertFalse(succeeded.judgment.downgraded)
    }

    @Test
    fun fullAutoClaimWithHumanSuccessObservationDowngrades() {
        val orchestrator = PublishOrchestrator(
            PublishOrchestrator.planFor(PublishCompletionBoundary.FULL_AUTO),
            PublishCompletionBoundary.FULL_AUTO,
        )
        // 成功页是人工确认的（机器没定位到）→ 人工点击证据位 → 禁止记全自动。
        val decision = feedFullAutoUntilSuccess(orchestrator, success = PublishSuccessObserved(byHuman = true))
        val succeeded = assertIs<PublishDecision.Succeeded>(decision)
        assertEquals(PublishCompletionBoundary.AUTO_FILL_HUMAN_COMMIT, succeeded.judgment.recorded)
        assertTrue(succeeded.judgment.downgraded)
    }

    @Test
    fun incompleteMediaStagingBlocksSuccess() {
        // 新旧草稿混合/媒体未齐全：规划 12 张只回传 10 张 → 媒体证据缺，不许记成功。
        val orchestrator = PublishOrchestrator(
            PublishOrchestrator.planFor(PublishCompletionBoundary.FULL_AUTO),
            PublishCompletionBoundary.FULL_AUTO,
        )
        val decision = feedFullAutoUntilSuccess(orchestrator, stagedImages = 10, plannedImages = 12)
        val failed = assertIs<PublishDecision.Failed>(decision)
        assertTrue(failed.code.startsWith("EVIDENCE_INCOMPLETE:"))
        assertTrue("mediaComplete" in failed.code)
    }

    @Test
    fun outOfOrderSuccessIsRefused() {
        val orchestrator = PublishOrchestrator(
            PublishOrchestrator.planFor(PublishCompletionBoundary.FULL_AUTO),
            PublishCompletionBoundary.FULL_AUTO,
        )
        orchestrator.submit(MenuSettled(entryVisible = true))
        val decision = orchestrator.submit(PublishSuccessObserved(byHuman = false))
        assertEquals("SUCCESS_OUT_OF_ORDER", assertIs<PublishDecision.Failed>(decision).code)
    }

    @Test
    fun checkpointMismatchIsRefused() {
        val orchestrator = PublishOrchestrator(
            PublishOrchestrator.planFor(PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT),
            PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT,
        )
        orchestrator.submit(MenuSettled(entryVisible = true))
        orchestrator.submit(MediaCropReturned(backToPublishPage = true))
        orchestrator.submit(
            InputProof(textField = ProveTextInput.TextField.DESCRIPTION, readbackMatches = true, commitAuthorized = true),
        )
        assertIs<PublishDecision.WaitingUser>(
            orchestrator.submit(
                RequiredFieldSnapshot(priceFilled = true, stockFilled = true, deliveryFilled = true),
            ),
        )
        // 停在价格检查点上却确认最终点击 → 检查点不匹配，拒绝。
        val decision = orchestrator.submit(HumanConfirmed(HumanCheckpoint.CheckpointPoint.FINAL_COMMIT))
        assertEquals(
            "CHECKPOINT_MISMATCH:final_commit",
            assertIs<PublishDecision.Failed>(decision).code,
        )
    }
}
