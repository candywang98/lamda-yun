package com.company.cloudctl.companion.features.xianyu.maintenance.basic

import com.company.cloudctl.companion.locators.CompositeItemAttributes
import com.company.cloudctl.companion.locators.ItemIdentityEvidence
import com.company.cloudctl.companion.locators.ItemIdentityEvidencePolicy
import com.company.cloudctl.companion.features.xianyu.maintenance.basic.MaintenanceBasicFixtures as F
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * X11 任务卡第 2 条 + 验收用例 3：降价三件套与金额/百分比互斥。
 */
class PriceReductionPlanTest {

    // ---- 互斥：一个计划只能一种减法，混合即拒绝 ----

    @Test
    fun mixingAmountAndPercentIsRejected() {
        val invalid = PriceReductionPlan.validate(
            currentPriceCents = 1_000L,
            amountCents = 100L,
            percentBasisPoints = 1_000,
        )
        val rejection = assertIs<PricePlanValidation.Invalid>(invalid)
        assertEquals(PricePlanError.MIXED_AMOUNT_AND_PERCENT, rejection.error)
    }

    @Test
    fun missingBothReducersIsRejected() {
        val invalid = PriceReductionPlan.validate(currentPriceCents = 1_000L)
        val rejection = assertIs<PricePlanValidation.Invalid>(invalid)
        assertEquals(PricePlanError.NO_REDUCER_SPECIFIED, rejection.error)
    }

    @Test
    fun reducerBoundsAreEnforced() {
        assertEquals(
            PricePlanError.RESULT_PRICE_NOT_POSITIVE,
            assertIs<PricePlanValidation.Invalid>(
                PriceReductionPlan.validate(1_000L, amountCents = 1_000L),
            ).error,
        )
        assertEquals(
            PricePlanError.INVALID_AMOUNT,
            assertIs<PricePlanValidation.Invalid>(
                PriceReductionPlan.validate(1_000L, amountCents = 0L),
            ).error,
        )
        assertEquals(
            PricePlanError.PERCENT_OUT_OF_RANGE,
            assertIs<PricePlanValidation.Invalid>(
                PriceReductionPlan.validate(1_000L, percentBasisPoints = 10_000),
            ).error,
        )
        assertEquals(
            PricePlanError.PERCENT_OUT_OF_RANGE,
            assertIs<PricePlanValidation.Invalid>(
                PriceReductionPlan.validate(1_000L, percentBasisPoints = 0),
            ).error,
        )
    }

    @Test
    fun expectedPriceUsesIntegerMath() {
        val amount = assertIs<PricePlanValidation.Valid>(
            PriceReductionPlan.validate(1_990L, amountCents = 500L),
        ).plan
        assertEquals(1_490L, amount.expectedNewPriceCents)

        val percent = assertIs<PricePlanValidation.Valid>(
            PriceReductionPlan.validate(1_990L, percentBasisPoints = 2_500),
        ).plan
        // 1990 * 7500 / 10000 = 1492.5 → 向下取整 1492（分精度，不引入浮点）。
        assertEquals(1_492L, percent.expectedNewPriceCents)
        assertEquals(498L, percent.plannedDeltaCents)
    }

    // ---- 三件套判定：锚点 → 身份 → 回读 ----

    private val platformId = ItemIdentityEvidence.PlatformItemId(
        itemId = "7123456789",
        accountScope = F.ACCOUNT,
    )

    private fun plan() = assertIs<PricePlanValidation.Valid>(
        PriceReductionPlan.validate(1_000L, amountCents = 200L),
    ).plan

    private fun observation(
        anchor: PriceActionAnchor? = PriceActionAnchor(
            actionLabel = "降价",
            matchedTitleLine = "二战史-01 ¥10.00",
            sameCardProven = true,
            distinctMatchingCards = 1,
        ),
        identity: ItemIdentityEvidence? = platformId,
        humanConfirmedComposite: Boolean = false,
        observedNewPriceCents: Long? = 800L,
    ) = PriceReadbackObservation(
        anchor = anchor,
        identity = identity,
        humanConfirmedComposite = humanConfirmedComposite,
        observedNewPriceCents = observedNewPriceCents,
    )

    @Test
    fun fullTrioPassesAndOnlyExactReadbackRecordsSuccess() {
        val verdict = PriceReadbackJudge.judge(plan(), observation(observedNewPriceCents = 800L))
        val verified = assertIs<PriceReductionVerdict.VerifiedPriceReduced>(verdict)
        assertEquals(800L, verified.observedNewPriceCents)
    }

    @Test
    fun readbackMismatchNeverRecordsSuccess() {
        val verdict = PriceReadbackJudge.judge(plan(), observation(observedNewPriceCents = 700L))
        val mismatch = assertIs<PriceReductionVerdict.ReadbackMismatch>(verdict)
        assertEquals(800L, mismatch.expectedNewPriceCents)
        assertEquals(700L, mismatch.observedNewPriceCents)
    }

    @Test
    fun unreadablePriceFieldIsHeldNotFailed() {
        val verdict = PriceReadbackJudge.judge(plan(), observation(observedNewPriceCents = null))
        assertIs<PriceReductionVerdict.ReadbackUnreadable>(verdict)
    }

    @Test
    fun anchorNotProvenFailsClosedBeforeIdentityAndReadback() {
        val noAnchor = PriceReadbackJudge.judge(
            plan(),
            observation(anchor = null, observedNewPriceCents = 800L),
        )
        assertIs<PriceReductionVerdict.AnchorNotProven>(noAnchor)

        val crossCard = PriceReadbackJudge.judge(
            plan(),
            observation(
                anchor = PriceActionAnchor(
                    actionLabel = "降价",
                    matchedTitleLine = "二战史-01",
                    sameCardProven = false, // 跨卡/全列表包装节点：绝不是tap目标
                    distinctMatchingCards = 1,
                ),
                observedNewPriceCents = 800L,
            ),
        )
        assertIs<PriceReductionVerdict.AnchorNotProven>(crossCard)

        val ambiguous = PriceReadbackJudge.judge(
            plan(),
            observation(
                anchor = PriceActionAnchor(
                    actionLabel = "降价",
                    matchedTitleLine = "二战史-01",
                    sameCardProven = true,
                    distinctMatchingCards = 2, // 同名两张卡：禁止自动挑一张
                ),
                observedNewPriceCents = 800L,
            ),
        )
        assertIs<PriceReductionVerdict.AnchorNotProven>(ambiguous)
    }

    @Test
    fun identityGateNeedsHumanConfirmForCompositeEvidence() {
        val composite = ItemIdentityEvidencePolicy.evaluate(
            CompositeItemAttributes(
                accountScope = F.ACCOUNT,
                titleContains = "二战史-01",
                price = "¥10.00",
                actionLabel = "降价",
            ),
            cardLines = listOf("二战史-01", "¥10.00", "降价"),
            distinctMatchingCards = 1,
        )
        assertIs<ItemIdentityEvidence.CompositeConfirmed>(composite)

        val pending = PriceReadbackJudge.judge(
            plan(),
            observation(identity = composite, humanConfirmedComposite = false),
        )
        assertIs<PriceReductionVerdict.IdentityNotProven>(pending)

        val confirmed = PriceReadbackJudge.judge(
            plan(),
            observation(identity = composite, humanConfirmedComposite = true),
        )
        assertIs<PriceReductionVerdict.VerifiedPriceReduced>(confirmed)
    }

    @Test
    fun insufficientIdentityFailsClosedEvenWithPerfectReadback() {
        val insufficient = ItemIdentityEvidence.Insufficient(
            reason = "attribute ambiguity: composite (title='二战史-01') matches 2 distinct cards",
        )
        val verdict = PriceReadbackJudge.judge(
            plan(),
            observation(identity = insufficient, observedNewPriceCents = 800L),
        )
        val blocked = assertIs<PriceReductionVerdict.IdentityNotProven>(verdict)
        assertEquals(insufficient.reason, blocked.reason)
    }
}
