package com.company.cloudctl.companion.ime

import com.company.cloudctl.companion.automation.ExecutorFailure
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * B14 semantic gate: a chat proof is bound to one task, one peer and a
 * monotonic TTL. Page text never enters the slot. A consumed or expired
 * proof cannot authorize a second send.
 */
class ChatSendProofBindingTest {
    private fun proof(
        taskId: String? = "task-1",
        peerName: String? = "lucas",
        expiresAtElapsedMs: Long? = 31_000L,
        expected: String = "你好，在的",
        field: String = "com.taobao.idlefish|1|6|-1|",
        generation: Long = 4L,
    ) = InputProof(
        target = "com.taobao.idlefish",
        field = field,
        generation = generation,
        expected = expected,
        snapshot = EditorSnapshot(generation, field, expected, 0, 0, false, true, 0, false, selectionKnown = false),
        targetPackage = "com.taobao.idlefish",
        locatorRef = ChatSendProof.CHAT_INPUT,
        nodeKey = "7|10,20,30,40|android.widget.EditText|com.taobao.idlefish:id/input",
        selectionKnown = false,
        taskId = taskId,
        peerName = peerName,
        expiresAtElapsedMs = expiresAtElapsedMs,
    )

    @Test fun holdRequiresTaskPeerAndMonotonicTtl() {
        val slot = ChatSendProof()
        val missing = assertFailsWith<ExecutorFailure> { slot.hold(proof(taskId = null)) }
        assertEquals("INPUT_REJECTED", missing.code)
        val noPeer = assertFailsWith<ExecutorFailure> { slot.hold(proof(peerName = " ")) }
        assertEquals("INPUT_REJECTED", noPeer.code)
        val noTtl = assertFailsWith<ExecutorFailure> { slot.hold(proof(expiresAtElapsedMs = null)) }
        assertEquals("INPUT_REJECTED", noTtl.code)
        assertNull(slot.peek())
    }

    @Test fun descriptionLocatorCannotAuthorizeASend() {
        val slot = ChatSendProof()
        val error = assertFailsWith<ExecutorFailure> {
            slot.hold(proof().copy(locatorRef = "xianyu_description"))
        }
        assertEquals("INPUT_REJECTED", error.code)
        assertNull(slot.peek())
    }

    @Test fun ttlIsMonotonicAndAConsumedProofCannotBeReused() {
        val slot = ChatSendProof()
        val held = proof(expiresAtElapsedMs = 5_000L)
        slot.hold(held)
        assertTrue(slot.live(held, nowElapsedMs = 5_000L))
        assertFalse(slot.live(held, nowElapsedMs = 5_001L))
        // A clock that moved backwards is not a longer life.
        assertFalse(slot.live(held, nowElapsedMs = -1L))
        assertEquals(held, slot.consume())
        assertNull(slot.peek())
        assertNull(slot.consume())
        assertFalse(slot.live(held, nowElapsedMs = 1L))
    }

    @Test fun clearDropsTheProofSoAFailedTaskCannotSendLater() {
        val slot = ChatSendProof()
        slot.hold(proof())
        slot.clear()
        assertNull(slot.peek())
    }
}
