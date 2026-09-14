package com.company.cloudctl.companion.automation

import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * Gate routing for the xianyu maintenance steps (contract
 * xianyu-maintenance-anchors-20260915): the destructive confirm strikes
 * (下架/删除 second strike) stop the executor and run only through the
 * controlled ledger — one authorization, one dispatchGesture coordinate tap,
 * badge verification — while the light-risk 一键擦亮 stays outside the ledger
 * but is screenshotted before and after. Fail-safe paths (foreign screen
 * geometry, missing gate, missing badge baseline) must reject before any
 * gesture.
 */
class XianyuMaintenanceGateRoutingTest {
    private val fixedNow = Instant.parse("2026-09-15T08:00:00Z")

    /** Records ledger confirmations; models the real gate's single tap. */
    private class RecordingGate(
        val ui: FakeUi,
        var baseline: Int? = 1,
        var tapPoint: Pair<Int, Int>? = null,
        var badgeAfter: Pair<String, String>? = null,
    ) : DestructiveClickGate {
        val confirms = mutableListOf<AutomationStep.TapLayout>()

        override suspend fun confirmOnce(task: AutomationTask, step: AutomationStep.TapLayout): Int? {
            confirms += step
            val point = tapPoint ?: return null
            ui.ensureReady(task.targetPackage)
            ui.tapScreenAt(task.targetPackage, point.first, point.second)
            badgeAfter?.let { (ref, description) -> ui.nodes[ref] = ui.node(description) }
            return baseline
        }
    }

    @Test
    fun delistConfirmRunsOnceThroughTheLedgerAndVerifiesTheOnsaleBadge() = runBlocking {
        val ui = FakeUi().apply {
            nodes["xianyu_pub_tab_onsale"] = node(description = "3\n在卖")
        }
        val gate = RecordingGate(ui, baseline = 3, tapPoint = 755 to 1305,
            badgeAfter = "xianyu_pub_tab_onsale" to "2\n在卖")
        val journal = mutableListOf<String>()

        executor(ui, gate).execute(
            task(
                AutomationStep.TapLayout(
                    "confirm-delist", 1_000,
                    XianyuMaintenanceLayout.Tab.ONSALE,
                    XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELIST,
                    0, null,
                ),
                AutomationStep.AssertBadge("verify-onsale", 1_000, "xianyu_pub_tab_onsale", -1, null),
            ),
        ) { step, state -> journal += "${step.stepId}:$state" }

        // Exactly one ledger confirmation and exactly one coordinate tap, ever.
        assertEquals(listOf("confirm-delist"), gate.confirms.map { it.stepId })
        assertEquals(listOf(755 to 1305), ui.coordinateTaps)
        // The gated path never screenshots through the plain executor flow;
        // the ledger owns its own before/after evidence.
        assertTrue(ui.screenshotLabels.isEmpty())
        // 下架成功 ⇒ 在卖 N-1（3 → 2）由 assertBadge 核验通过。
        assertEquals(
            listOf("confirm-delist:STARTED", "confirm-delist:SUCCEEDED", "verify-onsale:STARTED", "verify-onsale:SUCCEEDED"),
            journal,
        )
        assertTrue(ui.logs.contains(LogLevel.INFO to "LAYOUT_GUARD_PASSED"))
    }

    @Test
    fun deleteConfirmRunsOnceThroughTheLedgerAndVerifiesTheDelistedBadge() = runBlocking {
        val ui = FakeUi().apply {
            nodes["xianyu_pub_tab_delisted"] = node(description = "1\n已下架")
        }
        val gate = RecordingGate(ui, baseline = 1, tapPoint = 745 to 1305,
            badgeAfter = "xianyu_pub_tab_delisted" to "0\n已下架")

        executor(ui, gate).execute(
            task(
                AutomationStep.TapLayout(
                    "confirm-delete", 1_000,
                    XianyuMaintenanceLayout.Tab.DELISTED,
                    XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELETE,
                    0, null,
                ),
                AutomationStep.AssertBadge("verify-delisted", 1_000, "xianyu_pub_tab_delisted", -1, null),
            ),
        ) { _, _ -> }

        assertEquals(listOf("confirm-delete"), gate.confirms.map { it.stepId })
        // GATED 击点绝不双击：受控账本内单次 dispatchGesture。
        assertEquals(1, ui.coordinateTaps.size)
        assertEquals(745 to 1305, ui.coordinateTaps.single())
    }

    @Test
    fun confirmWithoutTheControlledLedgerFailsClosedBeforeAnyGesture() = runBlocking {
        val ui = FakeUi()
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui, null).execute(
                task(
                    AutomationStep.TapLayout(
                        "confirm-delist", 1_000,
                        XianyuMaintenanceLayout.Tab.ONSALE,
                        XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELIST,
                        0, null,
                    ),
                ),
            ) { _, _ -> }
        }
        assertEquals("G3_NOT_ACCEPTED", failure.code)
        assertTrue(ui.coordinateTaps.isEmpty())
        assertTrue(ui.screenshotLabels.isEmpty())
    }

    @Test
    fun reconciledPriorIntentNeverStrikesAgainAndYieldsNoBadgeBaseline() = runBlocking {
        val ui = FakeUi().apply {
            nodes["xianyu_pub_tab_onsale"] = node(description = "2\n在卖")
        }
        // baseline=null models a prior recorded intent that only reconciles.
        val gate = RecordingGate(ui, baseline = null)
        val journal = mutableListOf<String>()

        executor(ui, gate).execute(
            task(
                AutomationStep.TapLayout(
                    "confirm-delist", 1_000,
                    XianyuMaintenanceLayout.Tab.ONSALE,
                    XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELIST,
                    0, null,
                ),
            ),
        ) { step, state -> journal += "${step.stepId}:$state" }

        assertEquals(listOf("confirm-delist:STARTED", "confirm-delist:SUCCEEDED"), journal)
        assertTrue(ui.coordinateTaps.isEmpty())
        // A reconciled intent exposes no valid delta baseline: the follow-up
        // delta assertion must fail closed instead of trusting the badge.
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui, gate).execute(
                task(AutomationStep.AssertBadge("verify-onsale", 1_000, "xianyu_pub_tab_onsale", -1, null)),
            ) { _, _ -> }
        }
        assertEquals("BADGE_BASELINE_MISSING", failure.code)
    }

    @Test
    fun polishTapSkipsTheLedgerButScreenshotsBothSides() = runBlocking {
        val ui = FakeUi().apply {
            nodes["xianyu_pub_tab_onsale"] = node(description = "3\n在卖")
        }
        val gate = RecordingGate(ui)
        val journal = mutableListOf<String>()

        executor(ui, gate).execute(
            task(
                AutomationStep.TapLayout(
                    "polish", 1_000,
                    XianyuMaintenanceLayout.Tab.ONSALE,
                    XianyuMaintenanceLayout.LayoutAction.POLISH_ALL,
                    0, null,
                ),
            ),
        ) { step, state -> journal += "${step.stepId}:$state" }

        // 擦亮不进账本，但单击必须截图取证。
        assertTrue(gate.confirms.isEmpty())
        assertEquals(listOf(210 to 620), ui.coordinateTaps)
        assertEquals(listOf("layout-polish-before", "layout-polish-after"), ui.screenshotLabels)
        assertEquals(listOf("polish:STARTED", "polish:SUCCEEDED"), journal)
        assertTrue(ui.logs.contains(LogLevel.INFO to "LAYOUT_GUARD_PASSED"))
        assertTrue(ui.logs.contains(LogLevel.INFO to "SCREENSHOT_CAPTURED"))
    }

    @Test
    fun foreignScreenGeometryRejectsTheCoordinatePathWithoutGestures() = runBlocking {
        val wrongSize = FakeUi().apply { screenWidth = 1080; screenHeight = 2340 }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(wrongSize, null).execute(
                task(
                    AutomationStep.TapLayout(
                        "polish", 1_000,
                        XianyuMaintenanceLayout.Tab.ONSALE,
                        XianyuMaintenanceLayout.LayoutAction.POLISH_ALL,
                        0, null,
                    ),
                ),
            ) { _, _ -> }
        }
        assertEquals("LAYOUT_ACTION_UNMAPPED", failure.code)
        assertTrue(wrongSize.coordinateTaps.isEmpty())

        val unknownSize = FakeUi().apply { sizeKnown = false }
        val rejection = assertFailsWith<ExecutorFailure> {
            executor(unknownSize, null).execute(
                task(
                    AutomationStep.TapLayout(
                        "polish", 1_000,
                        XianyuMaintenanceLayout.Tab.ONSALE,
                        XianyuMaintenanceLayout.LayoutAction.POLISH_ALL,
                        0, null,
                    ),
                ),
            ) { _, _ -> }
        }
        assertEquals("LAYOUT_GUARD_REJECTED", rejection.code)
        assertTrue(unknownSize.coordinateTaps.isEmpty())
    }

    @Test
    fun layoutActionsAreRejectedForNonXianyuTargets() = runBlocking {
        val ui = FakeUi().apply { allowedPackage = TargetLocatorRegistry.XHS_PACKAGE }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui, null).execute(
                task(
                    TargetLocatorRegistry.XHS_PACKAGE,
                    AutomationStep.TapLayout(
                        "polish", 1_000,
                        XianyuMaintenanceLayout.Tab.ONSALE,
                        XianyuMaintenanceLayout.LayoutAction.POLISH_ALL,
                        0, null,
                    ),
                ),
            ) { _, _ -> }
        }
        assertEquals("TARGET_PACKAGE_REJECTED", failure.code)
        assertTrue(ui.coordinateTaps.isEmpty())
    }

    @Test
    fun unmappedCardPairingRejectsInsteadOfGuessing() = runBlocking {
        val ui = FakeUi()
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui, null).execute(
                task(
                    AutomationStep.TapLayout(
                        "delist-card", 1_000,
                        XianyuMaintenanceLayout.Tab.ONSALE,
                        XianyuMaintenanceLayout.LayoutAction.DELETE_CARD,
                        0, null,
                    ),
                ),
            ) { _, _ -> }
        }
        assertEquals("LAYOUT_ACTION_UNMAPPED", failure.code)
        assertTrue(ui.coordinateTaps.isEmpty())
    }

    @Test
    fun assertBadgePollsUntilTheExpectedAbsoluteValue() = runBlocking {
        val ui = FakeUi().apply {
            nodes["xianyu_pub_tab_delisted"] = node(description = "1\n已下架")
            onSleep = {
                nodes["xianyu_pub_tab_delisted"] = node(description = "0\n已下架")
            }
        }
        val journal = mutableListOf<String>()
        executor(ui, null).execute(
            task(AutomationStep.AssertBadge("wait-delisted-empty", 2_000, "xianyu_pub_tab_delisted", null, 0)),
        ) { step, state -> journal += "${step.stepId}:$state" }
        assertEquals(listOf("wait-delisted-empty:STARTED", "wait-delisted-empty:SUCCEEDED"), journal)
        assertTrue(ui.sleeps.isNotEmpty())
    }

    @Test
    fun assertBadgeTimesOutWhenTheExpectedValueNeverHolds() = runBlocking {
        val ui = FakeUi().apply {
            nodes["xianyu_pub_tab_onsale"] = node(description = "1\n在卖")
        }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui, null).execute(
                task(AutomationStep.AssertBadge("wait-onsale-empty", 300, "xianyu_pub_tab_onsale", null, 0)),
            ) { _, _ -> }
        }
        assertEquals("ASSERTION_FAILED", failure.code)
    }

    @Test
    fun assertBadgeRequiresAnApprovedBadgeLocator() = runBlocking {
        val ui = FakeUi()
        // xhs_home_publish is approved for XHS only: the xianyu badge assertion
        // must reject the cross-target locator before touching the UI.
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui, null).execute(
                task(AutomationStep.AssertBadge("wait-foreign", 300, "xhs_home_publish", null, 1)),
            ) { _, _ -> }
        }
        assertEquals("LOCATOR_NOT_APPROVED", failure.code)
    }

    private fun executor(ui: FakeUi, gate: DestructiveClickGate?) = LocalAutomationExecutor(
        ui = ui,
        now = { fixedNow },
        elapsedMs = { ui.clock },
        sleep = { ms ->
            ui.sleeps += ms
            ui.clock += ms
            ui.onSleep()
        },
        destructiveGate = gate,
    )

    private fun task(vararg steps: AutomationStep) = task(TargetLocatorRegistry.XIANYU_PACKAGE, *steps)

    private fun task(targetPackage: String, vararg steps: AutomationStep) = AutomationTask(
        taskId = "task-maintenance-1",
        deviceId = "device-1",
        targetPackage = targetPackage,
        issuedAt = fixedNow.minusSeconds(60),
        expiresAt = fixedNow.plusSeconds(600),
        maxRunSeconds = 60,
        steps = steps.toList(),
    )

    private fun node(description: String? = null) = LocalNodeState(
        enabled = true, visible = true, clickable = false, editable = false, text = null, description = description,
    )

    private class FakeUi : LocalAutomationUi {
        val nodes = mutableMapOf<String, LocalNodeState>()
        val coordinateTaps = mutableListOf<Pair<Int, Int>>()
        val screenshotLabels = mutableListOf<String>()
        val logs = mutableListOf<Pair<LogLevel, String>>()
        val sleeps = mutableListOf<Long>()
        var clock = 0L
        var sizeKnown = true
        var screenWidth = XianyuMaintenanceLayout.GUARD_WIDTH
        var screenHeight = XianyuMaintenanceLayout.GUARD_HEIGHT
        var allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
        var onSleep: () -> Unit = {}

        fun node(description: String? = null) = LocalNodeState(
            enabled = true, visible = true, clickable = false, editable = false, text = null, description = description,
        )

        override fun atRootPage(targetPackage: String) = true
        override fun isTargetForeground(targetPackage: String) = true
        override suspend fun dismissBlockedDialog(targetPackage: String): String? = null
        override suspend fun goBack() = error("unexpected goBack")
        override suspend fun restartTargetApp(targetPackage: String) = error("unexpected relaunch")
        override fun ensureReady(targetPackage: String) { check(targetPackage == allowedPackage) }
        override fun inspect(targetPackage: String, locatorRef: String) = nodes[locatorRef]
        override fun screenSize(targetPackage: String): Pair<Int, Int>? =
            if (sizeKnown) screenWidth to screenHeight else null
        override suspend fun tapScreenAt(targetPackage: String, x: Int, y: Int) { coordinateTaps += x to y }
        override suspend fun tap(targetPackage: String, locatorRef: String) = error("unexpected locator tap")
        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) =
            error("unexpected input")
        override suspend fun screenshot(taskId: String, label: String): ScreenshotEvidence {
            screenshotLabels += label
            return ScreenshotEvidence("/private/$label.png", 32, "a".repeat(64))
        }
        override fun log(level: LogLevel, messageCode: String) { logs += level to messageCode }
    }
}
