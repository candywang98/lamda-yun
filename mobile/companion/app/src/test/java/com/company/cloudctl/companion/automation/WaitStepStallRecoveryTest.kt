package com.company.cloudctl.companion.automation

import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * FLEET-20 wiring (B13): a stalled page-arrival wait step gets bounded
 * recovery through NavigationReset.recoverStalledWait instead of passively
 * burning the whole step budget. Recovery failure fails the step closed;
 * success is only accepted when the wait's own condition re-matches.
 */
class WaitStepStallRecoveryTest {

    private val fixedNow = Instant.parse("2026-09-17T09:00:00Z")

    private open class StallFakeUi(
        /** Home anchor becomes visible after this many BACK presses. */
        val homeAfterBacks: Int,
    ) : LocalAutomationUi {
        val nodes = mutableMapOf<String, LocalNodeState>()
        val logs = mutableListOf<Pair<LogLevel, String>>()
        var backs = 0
        var restarts = 0

        override fun ensureReady(targetPackage: String) = Unit

        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? {
            if (locatorRef == "xianyu_home_sell" && backs >= homeAfterBacks) {
                return LocalNodeState(
                    enabled = true, visible = true, clickable = true, editable = false, text = "卖闲置",
                )
            }
            return nodes[locatorRef]
        }

        /** Digest feed; distinct until navigation changes something real. */
        override fun pageSummary(targetPackage: String): String = "page-$backs"

        override suspend fun goBack() {
            backs += 1
        }

        override suspend fun tap(targetPackage: String, locatorRef: String) = Unit

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit

        override suspend fun restartTargetApp(targetPackage: String) {
            restarts += 1
        }

        override suspend fun screenshot(taskId: String, label: String) =
            ScreenshotEvidence("/private/proof.png", 32, "a".repeat(64))

        override fun log(level: LogLevel, messageCode: String) {
            logs += level to messageCode
        }
    }

    private fun executor(ui: StallFakeUi) = LocalAutomationExecutor(
        ui,
        now = { fixedNow },
        elapsedMs = { elapsed += 100L; elapsed },
        sleep = { _ -> },
    )

    private var elapsed = 0L

    private fun task(vararg steps: AutomationStep) = AutomationTask(
        taskId = "stall-1",
        deviceId = "device-1",
        targetPackage = "com.taobao.fleamarket",
        issuedAt = fixedNow.minusSeconds(60),
        expiresAt = fixedNow.plusSeconds(600),
        maxRunSeconds = 60,
        steps = steps.toList(),
    )

    @Test
    fun stalledWaitHomeRecoversByBoundedBackAndContinues() = runBlocking {
        val ui = StallFakeUi(homeAfterBacks = 1)
        val journal = mutableListOf<String>()

        executor(ui).execute(task(
            AutomationStep.Wait("1", 60_000, "xianyu_home_sell", NodeCondition.EXISTS, 200),
            AutomationStep.Log("2", 1_000, LogLevel.INFO, "AFTER_HOME"),
        )) { step, state -> journal += "${step.stepId}:$state" }

        // One BACK was enough: recovery re-sampled, the home anchor matched,
        // execution continued into the next step.
        assertEquals(1, ui.backs)
        assertEquals(0, ui.restarts)
        assertTrue(ui.logs.any { it.second.startsWith("NAV_WAIT_STALLED") })
        assertTrue(ui.logs.any { it.second.startsWith("NAV_WAIT_RECOVERED") })
        assertEquals(listOf("1:STARTED", "1:SUCCEEDED", "2:STARTED", "2:SUCCEEDED"), journal)
    }

    @Test
    fun unreadablePageFailsClosedInsteadOfBurningTheBudget() = runBlocking {
        // Page never arrives and the digest never changes: recovery must
        // terminate on its no-progress budget and fail the step closed —
        // no forced relaunch, no unbounded back.
        val ui = object : StallFakeUi(homeAfterBacks = Int.MAX_VALUE) {
            override fun pageSummary(targetPackage: String): String = "frozen"
        }

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(task(
                AutomationStep.Wait("1", 60_000, "xianyu_home_sell", NodeCondition.EXISTS, 200),
            )) { _, _ -> }
        }

        assertEquals("NAV_WAIT_NO_PROGRESS", failure.code)
        assertTrue(ui.backs in 1..NavigationReset.WAIT_RECOVERY_MAX_ACTIONS)
        assertEquals(0, ui.restarts)
        assertTrue(ui.logs.none { it.second.startsWith("NAV_RESET_RELAUNCH") })
    }

    @Test
    fun nonPageWaitsNeverTriggerBackRecovery() = runBlocking {
        // A price-field EXISTS wait is NOT a page-arrival anchor: stalling must
        // keep plain polling (old behavior), never press BACK.
        val ui = StallFakeUi(homeAfterBacks = 0)

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(task(
                AutomationStep.Wait("1", 60_000, "xianyu_price", NodeCondition.EXISTS, 200),
            )) { _, _ -> }
        }

        assertEquals("TASK_TIMEOUT", failure.code)
        assertEquals(0, ui.backs)
    }
}
