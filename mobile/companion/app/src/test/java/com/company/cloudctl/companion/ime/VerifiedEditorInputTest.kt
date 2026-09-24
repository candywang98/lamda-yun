package com.company.cloudctl.companion.ime

import com.company.cloudctl.companion.automation.ExecutorFailure
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class VerifiedEditorInputTest {
    private class Fake(
        var text: String = "",
        var generation: Long = 1,
        var field: String = "pkg|1|0|7|desc",
        var composing: Boolean = false,
        var offset: Int = 0,
        var offsetKnown: Boolean = true,
        var truncated: Boolean = false,
        var selectionStart: Int = 0,
        var selectionEnd: Int = 0,
        var selectionKnown: Boolean = true,
    ) : EditorTransport {
        var commits = 0
        override fun commitCount(): Int = commits
        var target: String? = "com.taobao.idlefish"
        var commitAccepted = true
        val committed = mutableListOf<String>()
        private var reads = 0
        var onRead: () -> Unit = {}

        override suspend fun snapshot(): EditorSnapshot? {
            reads++
            onRead()
            if (target == null) return null
            return EditorSnapshot(
                generation, field, text, selectionStart, selectionEnd, composing,
                offsetKnown, offset, truncated, selectionKnown,
            )
        }

        override suspend fun commit(snapshot: EditorSnapshot, text: String): Boolean {
            commits++
            committed += text
            if (!commitAccepted) return false
            this.text = text
            selectionStart = text.length
            selectionEnd = text.length
            return true
        }
    }

    private fun input(fake: Fake) = VerifiedEditorInput(fake, target = { fake.target }, pause = {})

    private fun code(fake: Fake, value: String = "描述199"): String = runBlocking {
        assertFailsWith<ExecutorFailure> { input(fake).write(value) }.code
    }

    @Test fun emptyFieldCommitsOnceAndNeedsTwoStableReads() = runBlocking {
        val fake = Fake()
        val proof = input(fake).write("你好🙂\n第二行")
        assertEquals(1, fake.commits)
        assertEquals("你好🙂\n第二行", proof.expected)
        assertEquals(proof.snapshot.text, proof.expected)
    }

    @Test fun aSecondCommitIsNotASuccessfulProof() {
        val fake = Fake()
        val original = fake.onRead
        fake.onRead = original
        val doubleCommit = object : EditorTransport by fake {
            override fun commitCount(): Int = if (fake.commits == 0) 0 else 2
            override suspend fun commit(snapshot: EditorSnapshot, text: String): Boolean {
                val accepted = fake.commit(snapshot, text)
                return accepted
            }
        }
        val writer = VerifiedEditorInput(doubleCommit, target = { fake.target }, pause = {})
        val code = runBlocking { assertFailsWith<ExecutorFailure> { writer.write("描述199") }.code }
        assertEquals("INPUT_REJECTED", code)
        assertEquals(1, fake.commits)
    }

    @Test fun fieldAlreadyEqualDoesNotCommit() = runBlocking {
        val value = "已经是这段"
        val fake = Fake(text = value, selectionStart = value.length, selectionEnd = value.length)
        input(fake).write(value)
        assertEquals(0, fake.commits)
    }

    @Test fun dirtyDraftIsNotCleared() {
        val fake = Fake(text = "用户草稿")
        assertEquals("FIELD_DIRTY_BY_USER", code(fake))
        assertEquals(0, fake.commits)
        assertEquals("用户草稿", fake.text)
    }

    @Test fun passwordStyleTruncationAndUnknownOffsetFailBeforeCommit() {
        assertEquals("INPUT_READBACK_UNAVAILABLE", code(Fake(offsetKnown = false)))
        assertEquals("INPUT_READBACK_UNAVAILABLE", code(Fake(offset = 3)))
        assertEquals("INPUT_READBACK_UNAVAILABLE", code(Fake(truncated = true, text = "a".repeat(20))))
        assertEquals(0, Fake(offset = 3).commits)
    }

    @Test fun selectionOutsideTextIsNotAFullRead() {
        assertEquals("INPUT_READBACK_UNAVAILABLE", code(Fake(text = "ab", selectionStart = 0, selectionEnd = 9)))
    }

    @Test fun composingRefusesTheWrite() {
        val fake = Fake(composing = true)
        assertEquals("USER_INTERFERENCE", code(fake))
        assertEquals(0, fake.commits)
    }

    @Test fun commitHappensOnceEvenWhenReadbackIsLate() = runBlocking {
        val fake = Fake()
        var delivered = false
        fake.onRead = {
            if (fake.commits == 1 && !delivered) {
                fake.text = ""
                delivered = true
            }
        }
        // The commit itself fills the field; the hook above only blanks the first
        // post-commit observation. The next reads must match without a second commit.
        val original = fake.onRead
        fake.onRead = {
            original()
            if (fake.commits == 1 && fake.text.isEmpty() && delivered) {
                fake.onRead = {}
                fake.text = "描述199"
                fake.selectionStart = fake.text.length
                fake.selectionEnd = fake.text.length
            }
        }
        input(fake).write("描述199")
        assertEquals(1, fake.commits)
    }

    @Test fun generationChangeAfterCommitIsRereadNotRewritten() = runBlocking {
        val fake = Fake()
        fake.onRead = {
            if (fake.commits == 1 && fake.generation == 1L && fake.text == "描述199") fake.generation = 2
        }
        val proof = input(fake).write("描述199")
        assertEquals(1, fake.commits)
        assertEquals(2L, proof.generation)
    }

    @Test fun generationChangeWithoutCommitIsUserInterference() {
        val value = "描述199"
        val fake = Fake(text = value, selectionStart = value.length, selectionEnd = value.length)
        var reads = 0
        fake.onRead = {
            reads++
            if (reads == 2) fake.generation = 2
        }
        assertEquals("USER_INTERFERENCE", code(fake, value))
        assertEquals(0, fake.commits)
    }

    @Test fun fieldChangeFailsClosed() {
        val fake = Fake()
        var reads = 0
        fake.onRead = {
            reads++
            if (reads == 2) fake.field = "other"
        }
        assertEquals("INPUT_TARGET_CHANGED", code(fake))
        assertEquals(0, fake.commits)
    }

    @Test fun userTextAfterCommitIsNotOverwritten() {
        val fake = Fake()
        fake.onRead = {
            if (fake.commits == 1) {
                fake.text = "用户又打了一字"
                fake.selectionStart = fake.text.length
                fake.selectionEnd = fake.text.length
            }
        }
        assertEquals("USER_INTERFERENCE", code(fake))
        assertEquals(1, fake.commits)
    }

    @Test fun oneMatchingReadIsNotProof() {
        val fake = Fake()
        var matched = false
        fake.onRead = {
            if (fake.commits == 1 && fake.text == "描述199" && !matched) {
                matched = true
            } else if (matched) {
                fake.text = ""
                fake.selectionStart = 0
                fake.selectionEnd = 0
            }
        }
        assertEquals("INPUT_REJECTED", code(fake))
        assertEquals(1, fake.commits)
    }

    @Test fun disappearedTargetFails() {
        val fake = Fake().apply { target = null }
        assertEquals("INPUT_TARGET_CHANGED", code(fake))
    }

    @Test fun unknownSelectionProvesOnFullTextWithoutPretendingCaretAtEnd() = runBlocking {
        val fake = Fake(selectionKnown = false, selectionStart = 0, selectionEnd = 0)
        val proof = input(fake).write("你好🙂")
        assertEquals(false, proof.selectionKnown)
        assertEquals(1, fake.commits)
        input(fake).verify(proof)
    }

    @Test fun longEmojiTextRoundTripsAndAShortReadDoesNot() = runBlocking {
        val value = "兑换🙂".repeat(80)
        val fake = Fake()
        input(fake).write(value)
        assertEquals(value, fake.text)
        assertTrue(value.length > 16)
        val short = Fake(text = value.take(16), selectionStart = 16, selectionEnd = 16)
        assertEquals("FIELD_DIRTY_BY_USER", code(short, value))
    }
}
