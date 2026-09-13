package com.company.cloudctl.companion.live

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class LiveCoreTest {
    @Test
    fun seqGuardRejectsStaleAndReplayed() {
        val guard = InputSeqGuard()
        assertTrue(guard.accept(1))
        assertFalse(guard.accept(1))
        assertFalse(guard.accept(0))
        assertTrue(guard.accept(5))
        guard.reset()
        assertTrue(guard.accept(1))
    }

    @Test
    fun frameParamsScaleAndThrottle() {
        val params = FrameParams.DEFAULT
        assertEquals(720 to 1600, params.scale(1080, 2400))
        assertEquals(720 to 540, params.scale(800, 600))
        assertEquals(0 to 0, params.scale(0, 0))
        assertEquals(200, params.intervalMs(remote = true))
        assertEquals(1000, params.intervalMs(remote = false))
        assertFailsWith<IllegalArgumentException> { FrameParams(maxWidth = 100) }
        assertFailsWith<IllegalArgumentException> { FrameParams(remoteFps = 0) }
    }

    @Test
    fun clientStateMachineFollowsServerTransitions() {
        val machine = LiveClientStateMachine()
        machine.onOpened()
        assertEquals(LiveClientState.VIEWING, machine.state)
        machine.onTakeControl()
        assertEquals(LiveClientState.REMOTE, machine.state)
        assertTrue(machine.guard.accept(1))
        machine.onRelease()
        assertEquals(LiveClientState.VIEWING, machine.state)
        machine.onClosed()
        assertEquals(LiveClientState.CLOSED, machine.state)
        assertFailsWith<IllegalStateException> { machine.onOpened() }
    }
}
