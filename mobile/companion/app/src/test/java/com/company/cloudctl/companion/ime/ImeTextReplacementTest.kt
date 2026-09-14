package com.company.cloudctl.companion.ime

import android.view.inputmethod.ExtractedText
import android.view.inputmethod.InputConnection
import java.lang.reflect.Proxy
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ImeTextReplacementTest {
    private class Fake {
        val calls = mutableListOf<String>()
        var extracted: ExtractedText? = ExtractedText().apply {
            text = "old draft"
            startOffset = 0
            partialStartOffset = -1
            partialEndOffset = -1
        }
        var beforeCursor: String? = "old draft"
        var afterCursor: String? = ""
        var selectionAccepted = true
        var commitAccepted = true
        var composingAccepted = true
        var throwOnCommit = false
        var selection: List<Any?> = emptyList()
        val connection = Proxy.newProxyInstance(
            InputConnection::class.java.classLoader, arrayOf(InputConnection::class.java),
        ) { _, method, args ->
            calls += method.name
            when (method.name) {
                "getExtractedText" -> extracted
                "getTextBeforeCursor" -> beforeCursor
                "getTextAfterCursor" -> afterCursor
                "finishComposingText" -> composingAccepted
                "setSelection" -> { selection = args.toList(); selectionAccepted }
                "commitText" -> {
                    if (throwOnCommit) throw IllegalStateException("disconnected")
                    assertEquals("reply", args[0])
                    assertEquals(1, args[1])
                    commitAccepted
                }
                "beginBatchEdit", "endBatchEdit" -> true
                else -> error("Forbidden or unexpected connection call: ${method.name}")
            }
        } as InputConnection
    }

    @Test fun replacesWholeDraftWithoutPasteOrDeletion() {
        val fake = Fake()
        assertTrue(ImeTextReplacement.replace(fake.connection, "reply"))
        assertEquals(listOf(0, 9), fake.selection)
        assertEquals(
            listOf("finishComposingText", "getTextBeforeCursor", "getTextAfterCursor", "beginBatchEdit", "setSelection", "commitText", "endBatchEdit"),
            fake.calls,
        )
    }

    @Test fun emptyDraftUsesEmptySelection() {
        val fake = Fake().apply { extracted!!.text = ""; beforeCursor = ""; afterCursor = "" }
        assertTrue(ImeTextReplacement.replace(fake.connection, "reply"))
        assertEquals(listOf(0, 0), fake.selection)
    }

    @Test fun unavailableSnapshotNeverWrites() {
        val fake = Fake().apply { extracted = null; beforeCursor = null; afterCursor = null }
        assertFalse(ImeTextReplacement.replace(fake.connection, "reply"))
        assertFalse("commitText" in fake.calls)
    }

    @Test fun platformPartialDefaultsStillReadTheSnapshot() {
        // Real devices report partialStartOffset/partialEndOffset = 0 (the int default),
        // not the documented -1 sentinel; with startOffset 0 the text is still whole.
        val fake = Fake().apply { extracted!!.partialStartOffset = 0; extracted!!.partialEndOffset = 0 }
        assertEquals("old draft", ImeTextReplacement.read(fake.connection))
        assertTrue(ImeTextReplacement.replace(fake.connection, "reply"))
    }

    @Test fun offsetSnapshotFallsBackToCursorWindows() {
        val fake = Fake().apply {
            extracted!!.startOffset = 4
            beforeCursor = "old "
            afterCursor = "draft"
        }
        assertEquals("old draft", ImeTextReplacement.read(fake.connection))
        assertTrue(ImeTextReplacement.replace(fake.connection, "reply"))
        assertEquals(listOf(0, 9), fake.selection)
    }

    @Test fun missingExtractedTextFallsBackToCursorWindows() {
        val fake = Fake().apply { extracted = null }
        assertEquals("old draft", ImeTextReplacement.read(fake.connection))
        assertTrue(ImeTextReplacement.replace(fake.connection, "reply"))
    }

    @Test fun rejectedSelectionNeverCommitsAndEndsBatch() {
        val fake = Fake().apply { selectionAccepted = false }
        assertFalse(ImeTextReplacement.replace(fake.connection, "reply"))
        assertFalse("commitText" in fake.calls)
        assertEquals("endBatchEdit", fake.calls.last())
    }

    @Test fun composingFailureNeverWrites() {
        val fake = Fake().apply { composingAccepted = false }
        assertFalse(ImeTextReplacement.replace(fake.connection, "reply"))
        assertEquals(listOf("finishComposingText"), fake.calls)
    }

    @Test fun commitFailureHasNoRetryOrQueuedReplay() {
        val fake = Fake().apply { commitAccepted = false }
        assertFalse(ImeTextReplacement.replace(fake.connection, "reply"))
        ImeTextReplacement.read(fake.connection)
        assertEquals(1, fake.calls.count { it == "commitText" })
    }

    @Test fun cursorWindowFailureRefusesToWrite() {
        val fake = Fake().apply { extracted = null; beforeCursor = null }
        assertFalse(ImeTextReplacement.replace(fake.connection, "reply"))
        assertNull(ImeTextReplacement.read(fake.connection))
        assertFalse("commitText" in fake.calls)
    }

    @Test fun exceptionStillEndsBatch() {
        val fake = Fake().apply { throwOnCommit = true }
        assertFailsWith<IllegalStateException> { ImeTextReplacement.replace(fake.connection, "reply") }
        assertEquals("endBatchEdit", fake.calls.last())
    }
}
