package com.company.cloudctl.companion.ime

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * B14 acceptance: after a connection rebuild the OLD InputConnection generation is
 * rejected; input may only continue on a freshly captured generation.
 */
class ImeSessionGateTest {
    @Test
    fun capturedGenerationIsRejectedAfterEditorRestart() {
        val gate = ImeSessionGate()
        val first = gate.onEditorStarted()
        assertTrue(gate.admits(first))
        val second = gate.onEditorStarted()
        // The old connection is stale: refuse it, admit only the re-captured one.
        assertFalse(gate.admits(first))
        assertTrue(gate.admits(second))
        assertTrue(first < second)
    }

    @Test
    fun finishedSessionAdmitsNothing() {
        val gate = ImeSessionGate()
        val session = gate.onEditorStarted()
        gate.onEditorFinished()
        assertFalse(gate.admits(session))
        assertNull(gate.currentSession())
    }

    @Test
    fun liveSessionTracksTheLatestGenerationOnly() {
        val gate = ImeSessionGate()
        val first = gate.onEditorStarted()
        val second = gate.onEditorStarted()
        assertEquals(second, gate.currentSession())
        assertFalse(gate.admits(first))
    }
}
