package com.company.cloudctl.companion.ime

import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull

/**
 * The slot the accessibility service uses for lastInputProof.
 *
 * A new write clears the previous proof before the write runs. A throw, or a
 * null return, leaves the slot empty. The previous proof is not restored.
 */
class FieldProofSlotTest {
    @Test
    fun failureAfterAPreviousProofLeavesTheSlotEmpty() = runBlocking {
        val slot = FieldProofSlot<String>()
        assertEquals("first", slot.replace { "first" })
        assertEquals("first", slot.current())

        assertFailsWith<IllegalStateException> {
            slot.replace { throw IllegalStateException("INPUT_REJECTED") }
        }
        assertNull(slot.current())
    }

    @Test
    fun nullWriteDoesNotRestoreThePreviousProof() = runBlocking {
        val slot = FieldProofSlot<String>()
        slot.replace { "first" }
        assertNull(slot.replace { null })
        assertNull(slot.current())
    }

    @Test
    fun theSlotIsEmptyBeforeTheWriteReturns() = runBlocking {
        val slot = FieldProofSlot<String>()
        slot.replace { "first" }
        var seenDuringWrite: String? = "unset"
        slot.replace {
            seenDuringWrite = slot.current()
            "second"
        }
        assertNull(seenDuringWrite)
        assertEquals("second", slot.current())
    }
}
