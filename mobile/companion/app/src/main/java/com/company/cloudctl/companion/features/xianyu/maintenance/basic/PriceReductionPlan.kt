package com.company.cloudctl.companion.features.xianyu.maintenance.basic

import com.company.cloudctl.companion.locators.ItemIdentityEvidence

/**
 * X11 — 降价计划（任务卡第 2 条铁律）。
 *
 * 三件套 = 动作按钮锚点（B13 locateActionButton 的同卡证明）+ 目标身份证明
 * （B13 ItemIdentityEvidence）+ 字段回读（降价后价格字段必须回读等于期望值）。
 *
 * 金额与百分比互斥：一个计划只能一种减法，amount 与 percent 同时给出 = 混合，
 * [validate] 直接拒绝（[PricePlanError.MIXED_AMOUNT_AND_PERCENT]）；两者都缺同样
 * 拒绝。回读不符 → [PriceReductionVerdict.ReadbackMismatch]，**不记成功**
 * （台账记 READBACK_HELD，验收用例 3）。
 */
sealed interface PriceReducer {
    /** 按金额直降（分）。 */
    data class ByAmountCents(val amountCents: Long) : PriceReducer

    /** 按百分比降（基点，10000bp = 100%）。 */
    data class ByPercentBasisPoints(val basisPoints: Int) : PriceReducer
}

/** 计划级校验错误（原因码独立，绝不归并成一个 INVALID_PLAN）。 */
enum class PricePlanError(val wire: String) {
    MIXED_AMOUNT_AND_PERCENT("MIXED_AMOUNT_AND_PERCENT"),
    NO_REDUCER_SPECIFIED("NO_REDUCER_SPECIFIED"),
    INVALID_AMOUNT("INVALID_AMOUNT"),
    PERCENT_OUT_OF_RANGE("PERCENT_OUT_OF_RANGE"),
    RESULT_PRICE_NOT_POSITIVE("RESULT_PRICE_NOT_POSITIVE"),
    INVALID_CURRENT_PRICE("INVALID_CURRENT_PRICE"),
}

/** 校验结果。 */
sealed interface PricePlanValidation {
    data class Valid(val plan: PriceReductionPlan) : PricePlanValidation
    data class Invalid(val error: PricePlanError, val reason: String) : PricePlanValidation
}

/**
 * 一个已冻结的降价计划：当前价 + 唯一一种减法。纯值对象，期望价由
 * [expectedNewPriceCents] 整数推导（不引入浮点）。
 */
class PriceReductionPlan private constructor(
    val currentPriceCents: Long,
    val reducer: PriceReducer,
) {
    /** 期望新价（分）：金额=直减；百分比=向下取整（价格字段只接受分精度）。 */
    val expectedNewPriceCents: Long
        get() = when (reducer) {
            is PriceReducer.ByAmountCents -> currentPriceCents - reducer.amountCents
            is PriceReducer.ByPercentBasisPoints ->
                currentPriceCents * (BASIS - reducer.basisPoints) / BASIS
        }

    /** 计划降幅（分）：预算守卫用（BUDGET_LIMIT_EXCEEDED 的加数）。 */
    val plannedDeltaCents: Long get() = currentPriceCents - expectedNewPriceCents

    companion object {
        const val BASIS = 10_000

        /**
         * 唯一构造口：互斥与取值守卫全部在此。
         * 混合（amount 与 percent 同时给出）即拒绝——一个计划只能一种。
         */
        fun validate(
            currentPriceCents: Long,
            amountCents: Long? = null,
            percentBasisPoints: Int? = null,
        ): PricePlanValidation {
            if (currentPriceCents <= 0) {
                return PricePlanValidation.Invalid(
                    PricePlanError.INVALID_CURRENT_PRICE,
                    "current price must be positive cents, got $currentPriceCents",
                )
            }
            if (amountCents != null && percentBasisPoints != null) {
                return PricePlanValidation.Invalid(
                    PricePlanError.MIXED_AMOUNT_AND_PERCENT,
                    "a price plan takes exactly ONE reducer: amountCents=$amountCents and " +
                        "percentBasisPoints=$percentBasisPoints were both given; mixing is rejected",
                )
            }
            val reducer = when {
                amountCents != null -> {
                    if (amountCents <= 0) {
                        return PricePlanValidation.Invalid(
                            PricePlanError.INVALID_AMOUNT,
                            "amountCents must be positive, got $amountCents",
                        )
                    }
                    if (amountCents >= currentPriceCents) {
                        return PricePlanValidation.Invalid(
                            PricePlanError.RESULT_PRICE_NOT_POSITIVE,
                            "reduction $amountCents would bring $currentPriceCents to <= 0",
                        )
                    }
                    PriceReducer.ByAmountCents(amountCents)
                }
                percentBasisPoints != null -> {
                    if (percentBasisPoints !in 1 until BASIS) {
                        return PricePlanValidation.Invalid(
                            PricePlanError.PERCENT_OUT_OF_RANGE,
                            "percentBasisPoints must be in 1..9999 (1bp..99.99%), got " +
                                "$percentBasisPoints",
                        )
                    }
                    PriceReducer.ByPercentBasisPoints(percentBasisPoints)
                }
                else -> return PricePlanValidation.Invalid(
                    PricePlanError.NO_REDUCER_SPECIFIED,
                    "a price plan needs exactly one reducer: amountCents or percentBasisPoints",
                )
            }
            val plan = PriceReductionPlan(currentPriceCents, reducer)
            if (plan.expectedNewPriceCents <= 0) {
                return PricePlanValidation.Invalid(
                    PricePlanError.RESULT_PRICE_NOT_POSITIVE,
                    "expected new price must stay positive, got ${plan.expectedNewPriceCents}",
                )
            }
            return PricePlanValidation.Valid(plan)
        }
    }
}

/** 三件套观察快照（接线层从真机采集后传入，判定器纯函数）。 */
data class PriceReadbackObservation(
    /** 动作按钮锚点证明（B13 locateActionButton.Button 的翻译）。 */
    val anchor: PriceActionAnchor?,
    /** B13 身份证据评估结果（null = 连评估都无法进行）。 */
    val identity: ItemIdentityEvidence?,
    /** 复合证据的人工确认回执（CompositeConfirmed 必须先过人工门）。 */
    val humanConfirmedComposite: Boolean = false,
    /** 回读到的降价后价格（分）；null = 字段不可读。 */
    val observedNewPriceCents: Long? = null,
)

/** 动作按钮锚点（同卡证明的字段化翻译）。 */
data class PriceActionAnchor(
    val actionLabel: String,
    val matchedTitleLine: String,
    /** 按钮矩形完整位于被标题钉住的那张卡内（B13 两面证明）。 */
    val sameCardProven: Boolean,
    /** 该标题命中的不同卡片数（必须 =1）。 */
    val distinctMatchingCards: Int,
)

/** 回读判定原因码。 */
object PriceReadbackReason {
    const val ANCHOR_NOT_PROVEN = "ANCHOR_NOT_PROVEN"
    const val IDENTITY_INSUFFICIENT = "IDENTITY_INSUFFICIENT"
    const val IDENTITY_NEEDS_HUMAN = "IDENTITY_NEEDS_HUMAN"
    const val PRICE_READBACK_MISMATCH = "PRICE_READBACK_MISMATCH"
    const val PRICE_READBACK_UNREADABLE = "PRICE_READBACK_UNREADABLE"
}

/** 降价回读判定：只有 VERIFIED 可记 PRICE_REDUCED，其余一律不记成功。 */
sealed interface PriceReductionVerdict {
    /** 三件套齐备且回读等于期望价：唯一可记成功的形态。 */
    data class VerifiedPriceReduced(
        val expectedNewPriceCents: Long,
        val observedNewPriceCents: Long,
    ) : PriceReductionVerdict

    /** 回读不等于期望价：不记成功（READBACK_HELD）。 */
    data class ReadbackMismatch(
        val expectedNewPriceCents: Long,
        val observedNewPriceCents: Long,
    ) : PriceReductionVerdict

    /** 价格字段不可读：不记成功，等操作员核销。 */
    data class ReadbackUnreadable(val reason: String) : PriceReductionVerdict

    /** 锚点未证明（无按钮/跨卡/同名多卡）：fail-closed，零副作用停。 */
    data class AnchorNotProven(val reason: String) : PriceReductionVerdict

    /** 身份证明不足 / 复合证据未过人工门：fail-closed。 */
    data class IdentityNotProven(val reason: String) : PriceReductionVerdict
}

/** 三件套判定器（纯函数；判定顺序：锚点 → 身份 → 回读值）。 */
object PriceReadbackJudge {

    fun judge(
        plan: PriceReductionPlan,
        observation: PriceReadbackObservation,
    ): PriceReductionVerdict {
        // 1) 动作按钮锚点：同卡证明 + 唯一命中。
        val anchor = observation.anchor
        if (anchor == null ||
            !anchor.sameCardProven ||
            anchor.distinctMatchingCards != 1 ||
            anchor.matchedTitleLine.isBlank()
        ) {
            return PriceReductionVerdict.AnchorNotProven(
                "action-button anchor not proven (sameCard=${anchor?.sameCardProven}, " +
                    "distinctCards=${anchor?.distinctMatchingCards}); refusing to strike",
            )
        }
        // 2) 目标身份证明（B13 级别）。
        when (val identity = observation.identity) {
            null -> return PriceReductionVerdict.IdentityNotProven(
                "identity evaluation could not even run (no target id, no account-scoped composite)",
            )
            is ItemIdentityEvidence.PlatformItemId -> Unit
            is ItemIdentityEvidence.CompositeConfirmed -> {
                if (!observation.humanConfirmedComposite) {
                    return PriceReductionVerdict.IdentityNotProven(
                        "composite identity matched one card but human confirmation is still " +
                            "pending; an irreversible price change waits for the B13 gate",
                    )
                }
            }
            is ItemIdentityEvidence.Insufficient -> return PriceReductionVerdict.IdentityNotProven(
                identity.reason,
            )
        }
        // 3) 字段回读：必须等于期望价。
        val expected = plan.expectedNewPriceCents
        val observed = observation.observedNewPriceCents
            ?: return PriceReductionVerdict.ReadbackUnreadable(
                "the reduced price field could not be read back; success is NOT recorded",
            )
        return if (observed == expected) {
            PriceReductionVerdict.VerifiedPriceReduced(
                expectedNewPriceCents = expected,
                observedNewPriceCents = observed,
            )
        } else {
            PriceReductionVerdict.ReadbackMismatch(
                expectedNewPriceCents = expected,
                observedNewPriceCents = observed,
            )
        }
    }
}
