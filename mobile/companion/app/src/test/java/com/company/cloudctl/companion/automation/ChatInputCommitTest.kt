package com.company.cloudctl.companion.automation

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse

class ChatInputCommitTest {
    private class Fake : ChatInputCommit.Port {
        var selected = true
        var focus = true
        var activation = true
        var token: Long? = 1
        var acknowledged = true
        var actual: String? = "reply"
        var activations = 0
        var writes = 0
        var pauses = 0
        val events = mutableListOf<String>()
        var onPause: () -> Unit = {}
        var onWrite: () -> Unit = {}
        override fun imeSelected() = selected
        override suspend fun activate(): Boolean { activations++; return activation }
        override fun focused() = focus
        override fun session() = token
        override fun replace(session: Long, value: String): Boolean {
            assertEquals(token, session)
            assertEquals("reply", value)
            writes++
            onWrite()
            return acknowledged
        }
        override fun readText(session: Long) = actual
        override fun event(code: String) { events += code }
        override suspend fun pause() { pauses++; onPause() }
    }

    private suspend fun rejected(fake: Fake, code: String = "INPUT_REJECTED") {
        assertEquals(code, assertFailsWith<ExecutorFailure> { ChatInputCommit(fake).execute("reply") }.code)
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
        assertEquals("CHAT_IME_VERIFIED", fake.events.last())
    }

    @Test fun waitsForConnectionInsteadOfFixedKeyboardDelay() = runBlocking {
        val fake = Fake().apply { token = null; onPause = { if (pauses == 5) token = 7 } }
        ChatInputCommit(fake).execute("reply")
        assertEquals(5, fake.pauses)
        assertEquals(1, fake.writes)
    }

    @Test fun absentConnectionNeverWrites() = runBlocking {
        val fake = Fake().apply { token = null }
        rejected(fake)
        assertEquals(20, fake.pauses)
        assertEquals(0, fake.writes)
    }

    @Test fun missingComposerFocusNeverWrites() = runBlocking {
        val fake = Fake().apply { focus = false }
        rejected(fake)
        assertEquals(0, fake.writes)
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
        assertEquals(20, fake.pauses)
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

    @Test fun switchedSessionCannotConfirmOldCommit() = runBlocking {
        val fake = Fake().apply { onWrite = { token = 2 } }
        rejected(fake)
        assertEquals(1, fake.writes)
    }

    @Test fun lostFocusCannotConfirmCommit() = runBlocking {
        rejected(Fake().apply { onWrite = { focus = false } })
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
}
