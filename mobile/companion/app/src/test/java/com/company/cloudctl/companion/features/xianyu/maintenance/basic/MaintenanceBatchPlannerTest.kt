package com.company.cloudctl.companion.features.xianyu.maintenance.basic

import com.company.cloudctl.companion.locators.ItemIdentityEvidence
import com.company.cloudctl.companion.features.xianyu.maintenance.basic.MaintenanceBasicFixtures as F
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue

/**
 * X11 批量编排：按身份逐件执行 + 四个独立停止条件 + 幂等再运行 + 身份闸门。
 */
class MaintenanceBatchPlannerTest {

    private val platformId = ItemIdentityEvidence.PlatformItemId(
        itemId = "7123456789",
        accountScope = F.ACCOUNT,
    )

    /** 造一套已登记台账+批准清单的运行现场。 */
    private fun rig(
        vararg targets: MaintenanceBatchTarget,
        limits: MaintenanceLimits = MaintenanceLimits(),
    ): Triple<MaintenanceTargetLedger, MaintenanceApprovalLedger, MaintenanceBatchPlan> {
        val targetLedger = MaintenanceTargetLedger()
        val approvals = F.ledger()
        targets.forEach { target ->
            targetLedger.enroll(target.targetId, target.key, target.action)
            approvals.register(F.approval(target.approvalId, target.key, action = target.action))
        }
        val plan = MaintenanceBatchPlan("run-x", targets.toList(), limits)
        return Triple(targetLedger, approvals, plan)
    }

    private fun startRun(
        rig: Triple<MaintenanceTargetLedger, MaintenanceApprovalLedger, MaintenanceBatchPlan>,
    ): Pair<MaintenanceBatchRun, List<PerTargetSubtask>> {
        val (ledger, approvals, plan) = rig
        val subtasks = assertIs<BatchExpansion.Subtasks>(MaintenanceBatchPlanner.expand(plan)).subtasks
        return MaintenanceBatchRun(
            runId = plan.runId,
            subtasks = subtasks,
            targetLedger = ledger,
            approvalLedger = approvals,
            limits = plan.limits,
        ) to subtasks
    }

    /** 驱动一个子任务走到终局（身份→单发→结果）。 */
    private fun driveTo(
        batchRun: MaintenanceBatchRun,
        subtaskId: String,
        outcome: MaintenanceOutcome,
    ) {
        batchRun.submitIdentity(subtaskId, platformId)
        batchRun.claimConfirmOnce(subtaskId)
        val recorded = batchRun.reportOutcome(subtaskId, outcome)
        assertIs<ReportDecision.Recorded>(recorded)
    }

    // ---- 验收 1：部分成功后再次运行 → 已完成动作不重复执行 ----

    @Test
    fun rerunAfterFullSuccessIssuesNothing() {
        val (targetLedger, approvals, plan) = rig(
            F.delistTarget("t-1", "二战史-01"),
            F.delistTarget("t-2", "二战史-02"),
        )
        val (first, _) = startRun(Triple(targetLedger, approvals, plan))

        val issue1 = assertIs<NextDecision.Issue>(first.nextDecision())
        driveTo(first, issue1.subtask.subtaskId, MaintenanceOutcome.Completed(MaintenanceActionResult.Delisted))
        val issue2 = assertIs<NextDecision.Issue>(first.nextDecision())
        driveTo(first, issue2.subtask.subtaskId, MaintenanceOutcome.Completed(MaintenanceActionResult.Delisted))
        assertIs<NextDecision.Finished>(first.nextDecision())

        // 再运行：新 run 对象、同一台账与批准清单——全部 COMPLETED，不发放任何新动作。
        val (second, _) = startRun(Triple(targetLedger, approvals, plan))
        assertIs<NextDecision.Finished>(second.nextDecision())
        assertEquals(2, targetLedger.all().count { it.state == MaintenanceTargetState.COMPLETED })
    }

    @Test
    fun rerunAfterUnknownHaltsAtProtectionAndSkipsCompleted() {
        val (targetLedger, approvals, plan) = rig(
            F.delistTarget("t-1", "二战史-01"),
            F.delistTarget("t-2", "二战史-02"),
            F.delistTarget("t-3", "二战史-03"),
        )
        val (first, _) = startRun(Triple(targetLedger, approvals, plan))

        // t-1 完成；t-2 派发后结果 UNKNOWN。
        val issue1 = assertIs<NextDecision.Issue>(first.nextDecision())
        driveTo(first, issue1.subtask.subtaskId, MaintenanceOutcome.Completed(MaintenanceActionResult.Delisted))
        val issue2 = assertIs<NextDecision.Issue>(first.nextDecision())
        driveTo(first, issue2.subtask.subtaskId, MaintenanceOutcome.Unknown("DIALOG_DISMISSAL_UNCAPTURED", "lost"))

        // UNKNOWN 之后：停机（保护期），t-3 不被自动续跑。
        val halted = assertIs<NextDecision.Halted>(first.nextDecision())
        val stop = assertIs<MaintenanceHalt.StopConditionHit>(halted.halt)
        assertEquals(MaintenanceStopCondition.PROTECTION_PERIOD_ACTIVE, stop.condition)

        // 部分成功后再次运行：跳过已完成的 t-1，仍在 t-2 保护期停住，t-3 原封不动。
        val (second, _) = startRun(Triple(targetLedger, approvals, plan))
        val haltedAgain = assertIs<NextDecision.Halted>(second.nextDecision())
        assertEquals(
            MaintenanceStopCondition.PROTECTION_PERIOD_ACTIVE,
            assertIs<MaintenanceHalt.StopConditionHit>(haltedAgain.halt).condition,
        )
        assertEquals(MaintenanceTargetState.COMPLETED, targetLedger.record("t-1")?.state)
        assertEquals(MaintenanceTargetState.UNKNOWN, targetLedger.record("t-2")?.state)
        assertEquals(MaintenanceTargetState.PENDING, targetLedger.record("t-3")?.state)
    }

    // ---- 验收 2：页面布局变化 → 身份证明失败即停，不把下一项当原对象 ----

    @Test
    fun identityProofFailureHaltsAndNeverTakesTheNextItem() {
        val (targetLedger, approvals, plan) = rig(
            F.delistTarget("t-1", "二战史-01"),
            F.delistTarget("t-2", "二战史-02"),
        )
        val (first, _) = startRun(Triple(targetLedger, approvals, plan))
        val issue = assertIs<NextDecision.Issue>(first.nextDecision())

        // 目标被顶走/插队：复合命中 2 张卡（或 0 张）——身份证明失败。
        val ambiguous = ItemIdentityEvidence.Insufficient(
            reason = "attribute ambiguity: composite (title='二战史-01') matches 2 distinct cards",
        )
        val halted = assertIs<IdentityDecision.Halted>(first.submitIdentity(issue.subtask.subtaskId, ambiguous))
        val identityHalt = assertIs<MaintenanceHalt.IdentityProofFailed>(halted.halt)
        assertEquals(MaintenanceHalt.IdentityProofFailed.IDENTITY_PROOF_FAILED, identityHalt.reasonCode)

        // 闩死：nextDecision 永远同一停机，t-2 不被当作替身继续执行。
        val same = assertIs<NextDecision.Halted>(first.nextDecision())
        assertSame(identityHalt, assertIs<MaintenanceHalt.IdentityProofFailed>(same.halt))
        assertEquals(MaintenanceTargetState.FAILED, targetLedger.record("t-1")?.state)
        assertEquals(MaintenanceTargetState.PENDING, targetLedger.record("t-2")?.state)

        // 零命中（目标被顶出屏幕）同样停机。
        val (ledger2, approvals2, plan2) = rig(
            F.delistTarget("t-1", "被顶走-01"),
            F.delistTarget("t-2", "二战史-02"),
        )
        val (second, _) = startRun(Triple(ledger2, approvals2, plan2))
        val issue2 = assertIs<NextDecision.Issue>(second.nextDecision())
        val zero = ItemIdentityEvidence.Insufficient(
            reason = "composite attributes match ZERO distinct cards (title='被顶走-01')",
        )
        assertIs<IdentityDecision.Halted>(second.submitIdentity(issue2.subtask.subtaskId, zero))
        assertIs<NextDecision.Halted>(second.nextDecision())
    }

    @Test
    fun compositeIdentityWaitsForHumanConfirmationBeforeProceeding() {
        val (targetLedger, approvals, plan) = rig(F.delistTarget("t-1", "二战史-01"))
        val (batchRun, _) = startRun(Triple(targetLedger, approvals, plan))
        val issue = assertIs<NextDecision.Issue>(batchRun.nextDecision())

        val composite = ItemIdentityEvidence.CompositeConfirmed(
            attributes = com.company.cloudctl.companion.locators.CompositeItemAttributes(
                accountScope = F.ACCOUNT,
                titleContains = "二战史-01",
                price = "¥10.00",
            ),
            confirmingLines = listOf("二战史-01", "¥10.00"),
            distinctMatchingCards = 1,
        )
        assertIs<IdentityDecision.NeedHumanConfirm>(batchRun.submitIdentity(issue.subtask.subtaskId, composite))
        assertIs<IdentityDecision.Admitted>(batchRun.confirmHumanIdentity(issue.subtask.subtaskId))
        assertIs<IdentityDecision.Admitted>(batchRun.submitIdentity(issue.subtask.subtaskId, composite))
    }

    // ---- 验收 4：四种停止条件各一测，原因码独立 ----

    @Test
    fun targetCountOverLimitHaltsTheWholePlanBeforeAnyDispatch() {
        val targets = (1..51).map { F.delistTarget("t-$it", "二战史-$it") }
        val plan = MaintenanceBatchPlan(
            runId = "run-big",
            targets = targets,
            limits = MaintenanceLimits(maxTargetsPerRun = 50),
        )
        val halted = assertIs<BatchExpansion.Halted>(MaintenanceBatchPlanner.expand(plan))
        assertEquals(
            MaintenanceStopCondition.TARGET_COUNT_LIMIT_EXCEEDED,
            assertIs<MaintenanceHalt.StopConditionHit>(halted.halt).condition,
        )
    }

    @Test
    fun budgetOverLimitHaltsTheWholePlanBeforeAnyDispatch() {
        val priceA = MaintenanceBatchTarget(
            targetId = "t-1",
            key = F.key("降价品-01"),
            action = MaintenanceActionKind.PRICE_REDUCE,
            approvalId = "apr-t-1",
            pricePlan = assertIs<PricePlanValidation.Valid>(
                PriceReductionPlan.validate(1_000L, amountCents = 800L),
            ).plan,
        )
        val priceB = priceA.copy(targetId = "t-2", key = F.key("降价品-02"), approvalId = "apr-t-2")
        val plan = MaintenanceBatchPlan(
            runId = "run-budget",
            targets = listOf(priceA, priceB),
            limits = MaintenanceLimits(budgetCents = 1_000L), // 计划总降幅 1600 > 1000
        )
        val halted = assertIs<BatchExpansion.Halted>(MaintenanceBatchPlanner.expand(plan))
        assertEquals(
            MaintenanceStopCondition.BUDGET_LIMIT_EXCEEDED,
            assertIs<MaintenanceHalt.StopConditionHit>(halted.halt).condition,
        )
    }

    @Test
    fun paginationOverrunLatchesAndNeverAutoResumes() {
        val (targetLedger, approvals, plan) = rig(
            F.delistTarget("t-1", "二战史-01"),
            F.delistTarget("t-2", "二战史-02"),
            limits = MaintenanceLimits(maxPaginationDepth = 20),
        )
        val (batchRun, _) = startRun(Triple(targetLedger, approvals, plan))
        val issue = assertIs<NextDecision.Issue>(batchRun.nextDecision())

        // 扫页找目标：第 21 页超限 → 立即闩停。
        assertTrue(batchRun.reportPageDepth(21))
        val halted = assertIs<NextDecision.Halted>(batchRun.nextDecision())
        val stop = assertIs<MaintenanceHalt.StopConditionHit>(halted.halt)
        assertEquals(MaintenanceStopCondition.PAGINATION_LIMIT_EXCEEDED, stop.condition)

        // 停就是停：回退页深上报也不能复活，nextDecision 永远同一停机。
        assertTrue(batchRun.reportPageDepth(1))
        val again = assertIs<NextDecision.Halted>(batchRun.nextDecision())
        assertSame(stop, assertIs<MaintenanceHalt.StopConditionHit>(again.halt))
        assertEquals(MaintenanceTargetState.PENDING, targetLedger.record("t-2")?.state)
    }

    @Test
    fun protectionPeriodHaltsThroughApprovalAdmission() {
        // 保护期第二种形态：操作员设定的保护窗口未过（admit 拒绝→停机）。
        val targetLedger = MaintenanceTargetLedger()
        val approvals = F.ledger()
        val key = F.key("保护品-01")
        targetLedger.enroll("t-1", key, MaintenanceActionKind.DELIST)
        approvals.register(F.approval("apr-t-1", key, protectionUntilMs = F.NOW + 60_000))
        val plan = MaintenanceBatchPlan(
            "run-prot",
            listOf(F.delistTarget("t-1", "保护品-01")),
            MaintenanceLimits(),
        )
        val (batchRun, _) = startRun(Triple(targetLedger, approvals, plan))
        val halted = assertIs<NextDecision.Halted>(batchRun.nextDecision())
        assertEquals(
            MaintenanceStopCondition.PROTECTION_PERIOD_ACTIVE,
            assertIs<MaintenanceHalt.StopConditionHit>(halted.halt).condition,
        )
    }

    @Test
    fun fourStopConditionsCarryFourDistinctReasonCodes() {
        // 汇总四种停机的原因码：互不相同（任务卡第 4 条独立性）。
        val codes = mutableSetOf<String>()

        // 1) 翻页超限
        run {
            val rigPair = rig(
                F.delistTarget("t-1", "二战史-01"),
                limits = MaintenanceLimits(maxPaginationDepth = 5),
            )
            val (batchRun, _) = startRun(rigPair)
            assertIs<NextDecision.Issue>(batchRun.nextDecision())
            batchRun.reportPageDepth(6)
            val halt = assertIs<NextDecision.Halted>(batchRun.nextDecision()).halt
            codes += assertIs<MaintenanceHalt.StopConditionHit>(halt).condition.wire
        }
        // 2) 保护期（UNKNOWN 目标）
        run {
            val (ledger, approvals, plan) = rig(
                F.delistTarget("t-1", "二战史-01"),
                F.delistTarget("t-2", "二战史-02"),
            )
            val (batchRun, _) = startRun(Triple(ledger, approvals, plan))
            val issue = assertIs<NextDecision.Issue>(batchRun.nextDecision())
            driveTo(batchRun, issue.subtask.subtaskId, MaintenanceOutcome.Unknown("BADGE_UNREADABLE", "x"))
            val halt = assertIs<NextDecision.Halted>(batchRun.nextDecision()).halt
            codes += assertIs<MaintenanceHalt.StopConditionHit>(halt).condition.wire
        }
        // 3) 目标数超限
        run {
            val plan = MaintenanceBatchPlan(
                "run-big",
                (1..3).map { F.delistTarget("t-$it", "二战史-$it") },
                MaintenanceLimits(maxTargetsPerRun = 2),
            )
            val halt = assertIs<BatchExpansion.Halted>(MaintenanceBatchPlanner.expand(plan)).halt
            codes += assertIs<MaintenanceHalt.StopConditionHit>(halt).condition.wire
        }
        // 4) 预算超限
        run {
            val price = MaintenanceBatchTarget(
                targetId = "t-1",
                key = F.key("降价品-01"),
                action = MaintenanceActionKind.PRICE_REDUCE,
                approvalId = "apr-t-1",
                pricePlan = assertIs<PricePlanValidation.Valid>(
                    PriceReductionPlan.validate(10_000L, amountCents = 9_000L),
                ).plan,
            )
            val plan = MaintenanceBatchPlan(
                "run-budget",
                listOf(price),
                MaintenanceLimits(budgetCents = 100L),
            )
            val halt = assertIs<BatchExpansion.Halted>(MaintenanceBatchPlanner.expand(plan)).halt
            codes += assertIs<MaintenanceHalt.StopConditionHit>(halt).condition.wire
        }
        assertEquals(
            setOf(
                "PAGINATION_LIMIT_EXCEEDED",
                "PROTECTION_PERIOD_ACTIVE",
                "TARGET_COUNT_LIMIT_EXCEEDED",
                "BUDGET_LIMIT_EXCEEDED",
            ),
            codes,
        )
    }

    // ---- 逐件独立性与单发纪律 ----

    @Test
    fun registrationRejectionFailsOnlyThatTargetAndMovesOn() {
        // 每目标独立批准：t-1 的批准过期（注册类拒绝）只废 t-1，t-2 照常发放。
        val targetLedger = MaintenanceTargetLedger()
        val approvals = F.ledger()
        val key1 = F.key("过期品-01")
        val key2 = F.key("二战史-02")
        targetLedger.enroll("t-1", key1, MaintenanceActionKind.DELIST)
        targetLedger.enroll("t-2", key2, MaintenanceActionKind.DELIST)
        approvals.register(
            F.approval("apr-t-1", key1, validFromMs = 0, validUntilMs = 500), // NOW=1000 已过窗
        )
        approvals.register(F.approval("apr-t-2", key2))
        val plan = MaintenanceBatchPlan(
            "run-mixed",
            listOf(
                F.delistTarget("t-1", "过期品-01"),
                F.delistTarget("t-2", "二战史-02"),
            ),
        )
        val (batchRun, _) = startRun(Triple(targetLedger, approvals, plan))

        val issue = assertIs<NextDecision.Issue>(batchRun.nextDecision())
        assertEquals("t-2", issue.subtask.targetId) // t-1 被跳过，直接发放 t-2
        assertEquals(MaintenanceTargetState.FAILED, targetLedger.record("t-1")?.state)
        assertEquals(BasicApprovalReason.APPROVAL_NOT_VALID, targetLedger.record("t-1")?.reasonCode)
    }

    @Test
    fun claimConfirmOnceThroughTheRunIsSingleShot() {
        val (targetLedger, approvals, plan) = rig(F.delistTarget("t-1", "二战史-01"))
        val (batchRun, _) = startRun(Triple(targetLedger, approvals, plan))
        val issue = assertIs<NextDecision.Issue>(batchRun.nextDecision())
        batchRun.submitIdentity(issue.subtask.subtaskId, platformId)

        assertIs<BasicApprovalDecision.Issued>(batchRun.claimConfirmOnce(issue.subtask.subtaskId))
        val second = assertIs<BasicApprovalDecision.Rejected>(
            batchRun.claimConfirmOnce(issue.subtask.subtaskId),
        )
        assertEquals(BasicApprovalReason.ALREADY_ISSUED, second.reasonCode)
    }

    @Test
    fun inFlightSubtaskMustReportBeforeTheNextIssue() {
        val (targetLedger, approvals, plan) = rig(
            F.delistTarget("t-1", "二战史-01"),
            F.delistTarget("t-2", "二战史-02"),
        )
        val (batchRun, _) = startRun(Triple(targetLedger, approvals, plan))
        val issue = assertIs<NextDecision.Issue>(batchRun.nextDecision())
        // 未报结果前：AwaitingResult（单件串行），不发放 t-2。
        assertIs<NextDecision.AwaitingResult>(batchRun.nextDecision())
        assertEquals("t-1", issue.subtask.targetId)
        driveTo(batchRun, issue.subtask.subtaskId, MaintenanceOutcome.Completed(MaintenanceActionResult.Delisted))
        val next = assertIs<NextDecision.Issue>(batchRun.nextDecision())
        assertEquals("t-2", next.subtask.targetId)
    }

    // ---- 验收 3 收口：回读不符走批量通道也不记成功 ----

    @Test
    fun readbackMismatchRecordsReadbackHeldNotSuccess() {
        val key = F.key("降价品-01")
        val pricePlan = assertIs<PricePlanValidation.Valid>(
            PriceReductionPlan.validate(1_000L, amountCents = 200L),
        ).plan
        val (targetLedger, approvals, plan) = rig(
            MaintenanceBatchTarget(
                targetId = "t-1",
                key = key,
                action = MaintenanceActionKind.PRICE_REDUCE,
                approvalId = "apr-t-1",
                pricePlan = pricePlan,
            ),
        )
        val (batchRun, _) = startRun(Triple(targetLedger, approvals, plan))
        val issue = assertIs<NextDecision.Issue>(batchRun.nextDecision())
        batchRun.submitIdentity(issue.subtask.subtaskId, platformId)
        batchRun.claimConfirmOnce(issue.subtask.subtaskId)

        // 回读 700 ≠ 期望 800：不记成功，台账 READBACK_HELD。
        val recorded = assertIs<ReportDecision.Recorded>(
            batchRun.reportOutcome(
                issue.subtask.subtaskId,
                MaintenanceOutcome.ReadbackHeld(
                    PriceReadbackReason.PRICE_READBACK_MISMATCH,
                    "observed 700, expected 800",
                ),
            ),
        )
        assertEquals(MaintenanceTargetState.READBACK_HELD, recorded.record.state)
        assertNull(recorded.record.result)
        assertIs<NextDecision.Finished>(batchRun.nextDecision()) // 唯一目标已终局
    }

    @Test
    fun unenrolledTargetsAreRejectedAtRunConstruction() {
        val (targetLedger, approvals, plan) = rig(F.delistTarget("t-1", "二战史-01"))
        val subtasks = assertIs<BatchExpansion.Subtasks>(MaintenanceBatchPlanner.expand(plan)).subtasks
        val emptyLedger = MaintenanceTargetLedger() // 未登记：构造期拒绝，不静默跳过
        val error = kotlin.test.assertFailsWith<IllegalArgumentException> {
            MaintenanceBatchRun("run-x", subtasks, emptyLedger, approvals, MaintenanceLimits())
        }
        assertTrue("must be enrolled" in (error.message ?: ""))
    }
}
