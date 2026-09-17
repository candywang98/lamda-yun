package com.company.cloudctl.companion.features.xianyu.publish

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * P10 验收用例（Android 侧）——四种完成边界：
 * 声称全自动但出现任何人工位必须降级记录；媒体未齐全/价格未验证不能记成功；
 * 现生产（自动填描述 + 人工价格 + 人工点击）落在 HUMAN_PRICE_HUMAN_COMMIT。
 */
class PublishCompletionBoundaryTest {

    @Test
    fun fullAutoClaimWithAnyHumanBitDowngrades() {
        // 人工价格位 → 至少 AUTO_FILL_HUMAN_PRICE（若证据还带人工点击则更保守）。
        val humanPriceOnly = PublishBoundaryJudge.judge(
            PublishCompletionBoundary.FULL_AUTO,
            PublishRunEvidence(
                descriptionProof = true,
                priceEnteredByMachine = false,
                priceHumanConfirmed = true,
                commitClickedByMachine = true,
                successObserved = true,
                mediaComplete = true,
                requiredFieldsComplete = true,
            ),
        )
        assertEquals(PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE, humanPriceOnly.recorded)
        assertTrue(humanPriceOnly.downgraded)

        val humanCommitOnly = PublishBoundaryJudge.judge(
            PublishCompletionBoundary.FULL_AUTO,
            PublishRunEvidence(
                descriptionProof = true,
                priceEnteredByMachine = true,
                commitClickedByMachine = false,
                commitHumanConfirmed = true,
                successObserved = true,
                mediaComplete = true,
                requiredFieldsComplete = true,
            ),
        )
        assertEquals(PublishCompletionBoundary.AUTO_FILL_HUMAN_COMMIT, humanCommitOnly.recorded)
        assertTrue(humanCommitOnly.downgraded)
    }

    @Test
    fun envelopeNeverUpgradesTowardsAutomation() {
        // 降级格：人工位只增不减——声称已含人工位时，机器证据不能"洗白"回全自动。
        val claimedManual = PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT
        val machineEvidence = PublishBoundaryJudge.judge(
            claimedManual,
            PublishRunEvidence(
                descriptionProof = true,
                priceEnteredByMachine = true,
                commitClickedByMachine = true,
                successObserved = true,
                mediaComplete = true,
                requiredFieldsComplete = true,
            ),
        )
        assertEquals(claimedManual, machineEvidence.recorded)
        assertFalse(machineEvidence.downgraded)

        assertEquals(
            PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT,
            PublishCompletionBoundary.envelope(
                PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE,
                PublishCompletionBoundary.AUTO_FILL_HUMAN_COMMIT,
            ),
        )
    }

    @Test
    fun mediaIncompleteOrUnverifiedPriceCannotBeFullAutoSuccess() {
        // 媒体未齐全 → 缺证据，不允许记全自动成功（完成度降级要写明缺口）。
        val mediaIncomplete = PublishBoundaryJudge.judge(
            PublishCompletionBoundary.FULL_AUTO,
            PublishRunEvidence(
                descriptionProof = true,
                priceEnteredByMachine = true,
                commitClickedByMachine = true,
                successObserved = true,
                mediaComplete = false,
                requiredFieldsComplete = true,
            ),
        )
        assertFalse(mediaIncomplete.successEligible)
        assertTrue("mediaComplete" in mediaIncomplete.missingEvidence)

        // 价格未经机器验证（也没有人工确认）→ 缺价格证据。
        val priceUnverified = PublishBoundaryJudge.judge(
            PublishCompletionBoundary.FULL_AUTO,
            PublishRunEvidence(
                descriptionProof = true,
                priceEnteredByMachine = false,
                commitClickedByMachine = true,
                successObserved = true,
                mediaComplete = true,
                requiredFieldsComplete = true,
            ),
        )
        assertFalse(priceUnverified.successEligible)
        // 价格缺机器验证 → 事实边界降为人工价，记录边界不再允许是全自动，
        // 且按记录边界的判据缺口是「人工价格确认」。
        assertEquals(PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE, priceUnverified.recorded)
        assertTrue("priceHumanConfirmed" in priceUnverified.missingEvidence)
    }

    @Test
    fun currentProductionSemanticsLandOnHumanPriceHumanCommit() {
        // Q03 现生产：描述自动填 + 人工在确认点填价 + 人工点发布。
        val judgment = PublishBoundaryJudge.judge(
            PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE,
            PublishRunEvidence(
                descriptionProof = true,
                priceEnteredByMachine = false,
                priceHumanConfirmed = true,
                commitClickedByMachine = false,
                commitHumanConfirmed = true,
                successObserved = true,
                mediaComplete = true,
                requiredFieldsComplete = true,
            ),
        )
        // 声称 AUTO_FILL_HUMAN_PRICE，但证据带人工点击 → 保守包络后按双人工记录。
        assertEquals(PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT, judgment.recorded)
        assertTrue(judgment.downgraded)
        assertTrue(judgment.successEligible)
    }

    @Test
    fun wireNameParsingIsFailClosed() {
        assertEquals(
            PublishCompletionBoundary.AUTO_FILL_HUMAN_COMMIT,
            PublishCompletionBoundary.fromWireName("AUTO_FILL_HUMAN_COMMIT"),
        )
        assertNull(PublishCompletionBoundary.fromWireName("auto-fill-human-commit"))
        assertNull(PublishCompletionBoundary.fromWireName("FULLY_AUTOMATIC"))
    }

    @Test
    fun boundaryFlagsFullyCoverTheFourCombinations() {
        assertEquals(4, PublishCompletionBoundary.entries.size)
        for (humanPrice in listOf(true, false)) {
            for (humanCommit in listOf(true, false)) {
                val boundary = PublishCompletionBoundary.fromFlags(humanPrice, humanCommit)
                assertEquals(humanPrice, boundary.humanPrice)
                assertEquals(humanCommit, boundary.humanCommit)
            }
        }
    }
}
