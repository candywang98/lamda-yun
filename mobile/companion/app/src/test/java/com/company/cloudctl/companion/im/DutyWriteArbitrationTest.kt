package com.company.cloudctl.companion.im

import java.time.LocalTime
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * I10 arbitration tests: publishing (an automation task) and duty triggering at
 * the same time must resolve to exactly one UI writer. The decision order is
 * frozen: config gate -> live arbiter ownership -> FLEET-21 pending-row guard.
 */
class DutyWriteArbitrationTest {
    private val noon = LocalTime.of(12, 0)
    private val duty = ImMonitorConfig(mode = ImMonitorConfig.MODE_DUTY, dutyStart = "09:00", dutyEnd = "23:00")
    private val idle = DutyWriteArbitration.OwnershipSnapshot()

    @Test
    fun idleDeviceGrantsDutyTheWriteRight() {
        val decision = DutyWriteArbitration.decide(duty, idle, noon)
        assertTrue(decision.dutyMayWrite)
        assertEquals(DutyWriteArbitration.WriteHolder.DUTY, decision.holder)
        assertEquals("DUTY_WRITE_GRANTED", decision.code)
    }

    @Test
    fun configGateYieldsWithoutContestingATaskWriter() {
        val disabled = DutyWriteArbitration.decide(
            ImMonitorConfig(enabled = false, mode = ImMonitorConfig.MODE_DUTY),
            DutyWriteArbitration.OwnershipSnapshot(activeTaskSessionId = "task-1"),
            noon,
        )
        assertEquals(DutyWriteArbitration.WriteHolder.DUTY_CONFIG, disabled.holder)
        assertEquals("DUTY_DISABLED", disabled.code)

        val offWindow = DutyWriteArbitration.decide(
            duty, DutyWriteArbitration.OwnershipSnapshot(activeTaskSessionId = "task-1"),
            LocalTime.of(23, 30),
        )
        assertEquals("DUTY_OFF_WINDOW", offWindow.code)

        val noXianyu = DutyWriteArbitration.decide(
            ImMonitorConfig(mode = ImMonitorConfig.MODE_DUTY, platforms = setOf(ImMonitorConfig.PLATFORM_XHS)),
            idle, noon,
        )
        assertEquals("DUTY_PLATFORM_NOT_MONITORED", noXianyu.code)
    }

    @Test
    fun runningTaskSessionWinsOverDuty() {
        val decision = DutyWriteArbitration.decide(
            duty,
            DutyWriteArbitration.OwnershipSnapshot(
                activeTaskSessionId = "publish-42",
                unfinishedTaskRows = true,
            ),
            noon,
        )
        assertFalse(decision.dutyMayWrite)
        assertEquals(DutyWriteArbitration.WriteHolder.TASK_SESSION, decision.holder)
        assertEquals("DUTY_YIELD_TASK_SESSION", decision.code)
        assertTrue(decision.detail!!.contains("publish-42"))
    }

    @Test
    fun remoteAndEdgeGrantsPauseDuty() {
        assertEquals(
            DutyWriteArbitration.WriteHolder.REMOTE_SESSION,
            DutyWriteArbitration.decide(
                duty, DutyWriteArbitration.OwnershipSnapshot(activeRemoteSession = true), noon,
            ).holder,
        )
        assertEquals(
            DutyWriteArbitration.WriteHolder.EDGE_SESSION,
            DutyWriteArbitration.decide(
                duty, DutyWriteArbitration.OwnershipSnapshot(activeEdgeSession = true), noon,
            ).holder,
        )
    }

    @Test
    fun queuedOrBlockedTaskRowsYieldEvenWithNoMintedSession() {
        // FLEET-21: a QUEUED / START_BLOCKED / RELEASE_BLOCKED row owns nothing
        // in the arbiter yet, but may start acting at any moment — duty stays
        // out of the target app meanwhile.
        val decision = DutyWriteArbitration.decide(
            duty, DutyWriteArbitration.OwnershipSnapshot(unfinishedTaskRows = true), noon,
        )
        assertFalse(decision.dutyMayWrite)
        assertEquals(DutyWriteArbitration.WriteHolder.TASK_ROW, decision.holder)
        assertEquals("DUTY_YIELD_TASK_ROW", decision.code)
    }

    @Test
    fun taskSessionOutranksPendingRowForTheReportedHolder() {
        // Both signals present: the RUNNING session is the concrete holder.
        val decision = DutyWriteArbitration.decide(
            duty,
            DutyWriteArbitration.OwnershipSnapshot(
                activeTaskSessionId = "task-9", unfinishedTaskRows = true,
            ),
            noon,
        )
        assertEquals(DutyWriteArbitration.WriteHolder.TASK_SESSION, decision.holder)
    }

    @Test
    fun notificationModeNeverGrantsDutyWrites() {
        val decision = DutyWriteArbitration.decide(
            ImMonitorConfig(mode = ImMonitorConfig.MODE_NOTIFICATION), idle, noon,
        )
        assertEquals("DUTY_OFF_WINDOW", decision.code)
        assertFalse(decision.dutyMayWrite)
    }

    @Test
    fun grantDecisionCarriesNoDetailToLog() {
        assertNull(DutyWriteArbitration.decide(duty, idle, noon).detail)
    }
}
