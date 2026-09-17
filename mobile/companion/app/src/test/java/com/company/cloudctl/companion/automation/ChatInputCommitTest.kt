package com.company.cloudctl.companion.automation

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ChatInputCommitTest {
    private class Fake(
        var value: String = "reply",
    ) : ChatInputCommit.Port {
        var selected = true
        var focus = true
        var activation = true
        var token: Long? = 1
        var identity: String? = "chat-field-1"
        var clipboard: String? = null
        var acknowledged = true
        var actual: String? = value
        var activations = 0
        var writes = 0
        val writtenSessions = mutableListOf<Long>()
        var pauses = 0
        val events = mutableListOf<String>()
        var onPause: () -> Unit = {}
        var onWrite: () -> Unit = {}
        override fun imeSelected() = selected
        override suspend fun activate(): Boolean { activations++; return activation }
        override fun focused() = focus
        override fun session() = token
        override fun fieldIdentity() = identity
        override fun clipboardContents() = clipboard
        override fun replace(session: Long, value: String): Boolean {
            assertEquals(token, session)
            assertEquals(this.value, value)
            writes++
            writtenSessions += session
            onWrite()
            return acknowledged
        }
        override fun readText(session: Long) = actual?.takeIf { session == token }
        override fun event(code: String) { events += code }
        override suspend fun pause() { pauses++; onPause() }
    }

    private suspend fun rejected(fake: Fake, code: String = "INPUT_REJECTED") {
        assertEquals(code, assertFailsWith<ExecutorFailure> { ChatInputCommit(fake).execute(fake.value) }.code)
        assertFalse("CHAT_IME_VERIFIED" in fake.events)
    }

    @Test fun thirdPartyImeFailsBeforeActivation() = runBlocking {
        val fake = Fake().apply { selected = false }
        rejected(fake, "INPUT_IME_REQUIRED")
        assertEquals(0, fake.activations)
        assertEquals(0, fake.writes)
    }

    @Test fun readySessionWritesExactlyOnce() = runBlocking {
        val fake = Fake()
        ChatInputCommit(fake).execute("reply")
        assertEquals(1, fake.writes)
        assertEquals(listOf(1L), fake.writtenSessions)
        assertEquals("CHAT_IME_VERIFIED", fake.events.last())
    }

    @Test fun waitsForConnectionInsteadOfFixedKeyboardDelay() = runBlocking {
        val fake = Fake().apply { token = null; onPause = { if (pauses == 5) token = 7 } }
        ChatInputCommit(fake).execute("reply")
        // 5 pauses bind the session; one more confirms stability before the write.
        assertEquals(6, fake.pauses)
        assertEquals(1, fake.writes)
    }

    @Test fun absentConnectionNeverWrites() = runBlocking {
        val fake = Fake().apply { token = null }
        rejected(fake)
        assertEquals(20, fake.pauses)
        assertEquals(0, fake.writes)
    }

    @Test fun subtreeFocusInImeWindowStillBindsSession() = runBlocking {
        // The focused accessibility node lives in the IME window on device; the
        // package-scoped session is the bind guarantee, not subtree focus.
        val fake = Fake().apply { focus = false }
        ChatInputCommit(fake).execute("reply")
        assertEquals(1, fake.writes)
    }

    @Test fun cancelledGestureNeverWrites() = runBlocking {
        val fake = Fake().apply { activation = false }
        rejected(fake)
        assertEquals(0, fake.writes)
    }

    @Test fun rejectedCommitIsNotRetriedEvenWithMatchingReadback() = runBlocking {
        val fake = Fake().apply { acknowledged = false }
        rejected(fake)
        assertEquals(1, fake.writes)
    }

    @Test fun transportSuccessWithEmptyReadbackFails() = runBlocking {
        val fake = Fake().apply { actual = "" }
        rejected(fake)
        assertEquals(1, fake.writes)
        assertEquals(21, fake.pauses)
    }

    @Test fun extraGarbageAndWhitespaceAreNotAccepted() = runBlocking {
        for (text in listOf("reply garbage", "garbage reply", " reply", "rep ly", "rep", null)) {
            val fake = Fake().apply { actual = text }
            rejected(fake)
            assertEquals(1, fake.writes)
        }
    }

    @Test fun delayedReadbackDoesNotRepeatCommit() = runBlocking {
        val fake = Fake().apply { actual = ""; onPause = { actual = "reply" } }
        ChatInputCommit(fake).execute("reply")
        assertEquals(1, fake.writes)
    }

    @Test fun churnedSessionWithoutReadableTextCannotConfirm() = runBlocking {
        val fake = Fake().apply { onWrite = { token = 2; actual = null } }
        rejected(fake)
        assertEquals(1, fake.writes)
    }


    @Test fun endedSessionCannotConfirmCommit() = runBlocking {
        // Leaving the editor kills the session: no live connection, no confirmation.
        rejected(Fake().apply { onWrite = { token = null } })
    }

    @Test fun imeSwitchWhileWaitingFailsBeforeWrite() = runBlocking {
        val fake = Fake().apply { token = null; onPause = { selected = false } }
        rejected(fake, "INPUT_IME_REQUIRED")
        assertEquals(0, fake.writes)
    }

    @Test fun cancellationStopsWaitingWithoutWrites() = runBlocking {
        val fake = Fake().apply { token = null; onPause = { throw CancellationException() } }
        assertFailsWith<CancellationException> { ChatInputCommit(fake).execute("reply") }
        assertEquals(0, fake.writes)
    }

    @Test fun blankReplyNeverActivatesOrWrites() = runBlocking {
        val fake = Fake()
        assertFailsWith<ExecutorFailure> { ChatInputCommit(fake).execute(" ") }
        assertEquals(0, fake.activations)
        assertEquals(0, fake.writes)
    }

    // ---- B14: generation-pinned commit, field-identity re-verification, readback proof ----

    @Test fun editorRestartOnSameFieldRebindsAndWritesOnlyOnNewGeneration() = runBlocking {
        // Connection rebuilt mid-stabilization: the stale generation is rejected,
        // the new one is re-captured (same field identity) and carries the write.
        val fake = Fake().apply { onPause = { if (pauses == 1) token = 2 } }
        ChatInputCommit(fake).execute("reply")
        assertEquals(1, fake.writes)
        assertEquals(listOf(2L), fake.writtenSessions)
        assertTrue("CHAT_IME_VERIFIED" in fake.events)
    }

    @Test fun userSwitchedToAnotherFieldRefusesToWriteFailClosed() = runBlocking {
        // New generation AND a different field: refuse to continue typing there.
        val fake = Fake().apply { onPause = { if (pauses == 1) { token = 2; identity = "search-box" } } }
        rejected(fake, "INPUT_TARGET_CHANGED")
        assertEquals(0, fake.writes)
    }

    @Test fun fieldSwitchDuringReadbackFailsClosedWithoutSuccess() = runBlocking {
        val fake = Fake().apply { onWrite = { identity = "other-field" } }
        rejected(fake, "INPUT_TARGET_CHANGED")
        assertEquals(1, fake.writes)
    }

    @Test fun unknownIdentityDegradesToSessionOnlyPinning() = runBlocking {
        // Port cannot name the field: session pinning alone still runs; a mismatch
        // (both known, different) is the only thing that hard-fails.
        val fake = Fake().apply { identity = null }
        ChatInputCommit(fake).execute("reply")
        assertEquals(1, fake.writes)
    }

    @Test fun emojiReadbackMustRoundTripExactly() = runBlocking {
        val emojiValue = "好的，稍等🙂马上改价"
        ChatInputCommit(Fake(emojiValue).apply { actual = emojiValue }).execute(emojiValue)
        // Emoji replaced by tofu or dropped: not the text we typed.
        rejected(Fake(emojiValue).apply { actual = emojiValue.replace("🙂", "?") })
        rejected(Fake(emojiValue).apply { actual = emojiValue.replace("🙂", "") })
    }

    @Test fun newlineReadbackMustRoundTripExactly() = runBlocking {
        val multiline = "第一行：改价说明\n第二行：发货说明"
        ChatInputCommit(Fake(multiline).apply { actual = multiline }).execute(multiline)
        // A whole line missing is content loss, not a formatting difference.
        rejected(Fake(multiline).apply { actual = multiline.substringBefore('\n') })
    }

    @Test fun longTextTruncatedToPrefixIsNotSuccess() = runBlocking {
        val long = "虚拟商品交付说明。".repeat(40) // 400 chars
        ChatInputCommit(Fake(long).apply { actual = long }).execute(long)
        // Only the first 16 characters agree: must not be reported as success.
        rejected(Fake(long).apply { actual = long.take(16) })
    }

    @Test fun oldDraftSharingThePrefixIsNotSuccess() = runBlocking {
        val value = "改价完成，请查收新价格，谢谢支持"
        val oldDraftSamePrefix = value.take(16) + "旧草稿残留在输入框里的后半段完全不同的内容"
        rejected(Fake(value).apply { actual = oldDraftSamePrefix })
    }

    @Test fun clipboardHoldingTheExactTextCannotAuthorizeSend() = runBlocking {
        // Polluted clipboard with the expected text, field disagrees: no success,
        // so no send-class action can be driven from the clipboard.
        val fake = Fake().apply { clipboard = "reply"; actual = "garbage" }
        rejected(fake)
        assertEquals(1, fake.writes)
    }

    @Test fun clipboardGarbageDoesNotVetoAVerifiedReadback() = runBlocking {
        val fake = Fake().apply { clipboard = "立即购买 BUY NOW" }
        ChatInputCommit(fake).execute("reply")
        assertEquals(1, fake.writes)
        assertTrue("CHAT_IME_VERIFIED" in fake.events)
    }
}
