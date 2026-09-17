package com.company.cloudctl.companion.automation

import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * B13 / FLEET-20 — wait-step recovery by page summary: a stalled wait (for
 * example the recipe `wait-home` state) recovers through BOUNDED back /
 * dialog actions, re-sampling the page summary after every action, with an
 * explicit no-progress counter and termination conditions. No force-stop,
 * no forced relaunch, no unbounded back — budget exhaustion fails closed.
 */
class NavigationResetWaitRecoveryTest {

    /** Port fake: records every navigation primitive NavigationReset may call. */
    private class FakePort(
        var foreground: Boolean = true,
        val dialogQueue: MutableList<String> = mutableListOf(),
        var failCheckpointAfter: Int = Int.MAX_VALUE,
    ) : NavigationReset.Port {
        var backs = 0
        var relaunches = 0
        var checkpoints = 0
        val events = mutableListOf<String>()
        val settles = mutableListOf<Long>()

        override fun atRootPage() = false // wait recovery judges its own target page
        override fun isTargetForeground() = foreground
        override suspend fun dismissBlockedDialog(): String? =
            dialogQueue.removeFirstOrNull()
        override suspend fun goBack() {
            backs += 1
        }
        override suspend fun relaunch() {
            relaunches += 1
        }
        override suspend fun settle(ms: Long) {
            settles += ms
        }
        override fun checkpoint() {
            checkpoints += 1
            if (checkpoints > failCheckpointAfter) {
                throw ExecutorFailure("CANCELLED", "operator taking over")
            }
        }
        override fun event(code: String) {
            events += code
        }
    }

    /**
     * Stateful page summary: the digest is a pure function of the recovery
     * state (backs/dialogs so far), so double-sampling inside one loop turn
     * stays consistent, exactly like a settled live page.
     */
    private class FakeSummary(
        private val port: FakePort,
        var targetAfterBacks: Int? = null,
        private val digestOf: (backs: Int, dialogs: Int) -> String = { b, _ -> "page-$b" },
        var epochOf: () -> Long = { 5L },
    ) : NavigationReset.PageSummarySource {
        var dialogsDismissed = 0
        var samples = 0
        override fun sessionEpoch(): Long = epochOf()
        override fun pageDigest(): String {
            samples += 1
            return digestOf(port.backs, dialogsDismissed)
        }
        override fun isTargetPage(): Boolean = targetAfterBacks != null && port.backs >= targetAfterBacks!!
    }

    @Test
    fun stalledWaitRecoversWithBoundedBacksAndNoRelaunch() = runBlocking {
        val port = FakePort()
        val summary = FakeSummary(port, targetAfterBacks = 2)
        val result = NavigationReset(port).recoverStalledWait(summary)
        val recovered = result as NavigationReset.WaitRecovery.Recovered
        assertEquals(2, recovered.actions)
        assertEquals(2, port.backs)
        assertEquals(0, port.relaunches) // no force-stop path either: never called
        assertTrue(port.events.any { it.startsWith("NAV_WAIT_BACK") })
        assertTrue(port.events.contains("NAV_WAIT_RECOVERED actions=2"))
        assertTrue(recovered.trace.all { it.kind == NavigationReset.RecoveryStep.Kind.BACK })
    }

    @Test
    fun dialogsAreDismissedBeforeBacksWithPageResampling() = runBlocking {
        val port = FakePort().apply { dialogQueue += "rate_us" }
        // Digest reflects the live page: "dialog-up" while the allowlisted
        // dialog is showing, then the back-counted pages after it is gone.
        val summary = FakeSummary(port, targetAfterBacks = 1)
        val liveDigest = object : NavigationReset.PageSummarySource by summary {
            override fun pageDigest(): String =
                if (port.dialogQueue.isNotEmpty()) "dialog-up" else summary.pageDigest()
        }
        val result = NavigationReset(port).recoverStalledWait(liveDigest)
        val recovered = result as NavigationReset.WaitRecovery.Recovered
        assertEquals(2, recovered.actions) // 1 dialog + 1 back
        assertEquals(1, port.backs)
        assertTrue(port.events.any { it.startsWith("NAV_WAIT_DIALOG_DISMISSED label=rate_us") })
        assertEquals(
            listOf(NavigationReset.RecoveryStep.Kind.DIALOG_DISMISS, NavigationReset.RecoveryStep.Kind.BACK),
            recovered.trace.map { it.kind },
        )
    }

    @Test
    fun unchangedPageDigestTerminatesNoProgressFailClosed() = runBlocking {
        val port = FakePort()
        val summary = FakeSummary(port, targetAfterBacks = null, digestOf = { _, _ -> "frozen-page" })
        val result = NavigationReset(port).recoverStalledWait(summary)
        val failed = result as NavigationReset.WaitRecovery.Failed
        assertEquals("NAV_WAIT_NO_PROGRESS", failed.code)
        assertEquals(2, failed.actions) // noProgressLimit = 2 by default
        assertTrue("unchanged after 2 consecutive recovery actions" in failed.reason)
        assertTrue(failed.trace.all { it.digestAfter == "frozen-page" })
    }

    @Test
    fun progressingButNeverArrivingFailsClosedAtTheBudget() = runBlocking {
        val port = FakePort()
        val summary = FakeSummary(port, targetAfterBacks = null, digestOf = { b, _ -> "page-$b" })
        val result = NavigationReset(port).recoverStalledWait(
            summary,
            NavigationReset.WaitRecoveryBudget(maxRecoveryActions = 4),
        )
        val failed = result as NavigationReset.WaitRecovery.Failed
        assertEquals("NAV_WAIT_RECOVERY_BUDGET_EXHAUSTED", failed.code)
        assertEquals(4, failed.actions)
        assertEquals(4, port.backs)
        assertEquals(0, port.relaunches) // FLEET-20: no forced relaunch / am force-stop
        assertTrue("no force-stop" in failed.reason)
    }

    @Test
    fun crossEpochSamplesResetTheNoProgressCounter() = runBlocking {
        // Same digest every sample, but the epoch moves each time: §2/§6 —
        // cross-epoch frames are incomparable, so this must run to budget
        // exhaustion, not die as no-progress.
        val port = FakePort()
        var epoch = 5L
        val summary = FakeSummary(
            port,
            targetAfterBacks = null,
            digestOf = { _, _ -> "frozen-page" },
            epochOf = { epoch.also { epoch += 1 } },
        )
        val result = NavigationReset(port).recoverStalledWait(
            summary,
            NavigationReset.WaitRecoveryBudget(maxRecoveryActions = 3, noProgressLimit = 2),
        )
        val failed = result as NavigationReset.WaitRecovery.Failed
        assertEquals("NAV_WAIT_RECOVERY_BUDGET_EXHAUSTED", failed.code)
        assertEquals(3, failed.actions)
    }

    @Test
    fun targetAlreadyShowingRecoversWithZeroActions() = runBlocking {
        val port = FakePort()
        val summary = FakeSummary(port, targetAfterBacks = 0)
        val result = NavigationReset(port).recoverStalledWait(summary)
        val recovered = result as NavigationReset.WaitRecovery.Recovered
        assertEquals(0, recovered.actions)
        assertEquals(0, port.backs)
        assertTrue(recovered.trace.isEmpty())
        assertTrue(port.events.none { it.startsWith("NAV_WAIT_BACK") })
    }

    @Test
    fun targetLostFromForegroundFailsClosedWithoutPressingBack() = runBlocking {
        val port = FakePort(foreground = false)
        val summary = FakeSummary(port, targetAfterBacks = null)
        val result = NavigationReset(port).recoverStalledWait(summary)
        val failed = result as NavigationReset.WaitRecovery.Failed
        assertEquals("NAV_WAIT_TARGET_LOST", failed.code)
        assertEquals(0, failed.actions)
        assertEquals(0, port.backs)
    }

    @Test
    fun cancellationPropagatesThroughTheCheckpoint() = runBlocking {
        val port = FakePort(failCheckpointAfter = 1)
        val summary = FakeSummary(port, targetAfterBacks = null)
        val failure = assertFailsWith<ExecutorFailure> {
            NavigationReset(port).recoverStalledWait(summary)
        }
        assertEquals("CANCELLED", failure.code)
        assertEquals(0, port.backs)
    }

    @Test
    fun orThrowConvertsAFailedRecoveryIntoExecutorFailure() = runBlocking {
        val port = FakePort()
        val summary = FakeSummary(port, targetAfterBacks = null, digestOf = { _, _ -> "frozen-page" })
        val failure = assertFailsWith<ExecutorFailure> {
            NavigationReset(port).recoverStalledWait(summary).let { result ->
                when (result) {
                    is NavigationReset.WaitRecovery.Recovered -> error("unexpected recovery")
                    is NavigationReset.WaitRecovery.Failed -> result.orThrow()
                }
            }
        }
        assertEquals("NAV_WAIT_NO_PROGRESS", failure.code)
        assertTrue(failure.message.orEmpty().contains("unchanged"))
    }

    @Test
    fun budgetRejectsNonPositiveLimits() {
        assertFailsWith<IllegalArgumentException> {
            NavigationReset.WaitRecoveryBudget(maxRecoveryActions = 0)
        }
        assertFailsWith<IllegalArgumentException> {
            NavigationReset.WaitRecoveryBudget(noProgressLimit = 0)
        }
        assertFailsWith<IllegalArgumentException> {
            NavigationReset.WaitRecoveryBudget(settleMs = -1)
        }
    }

    @Test
    fun recoverySettlesBetweenActionsWithTheBudgetInterval() = runBlocking {
        val port = FakePort()
        val summary = FakeSummary(port, targetAfterBacks = 1)
        NavigationReset(port).recoverStalledWait(
            summary,
            NavigationReset.WaitRecoveryBudget(settleMs = 250L),
        )
        assertTrue(port.settles.isNotEmpty() && port.settles.all { it == 250L })
    }
}
