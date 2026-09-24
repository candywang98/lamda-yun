package com.company.cloudctl.companion.ime

import com.company.cloudctl.companion.automation.ExecutorFailure
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class FieldInputTransactionTest {
    private class Harness(var channel: InputChannel) {
        var anchor = FieldAnchor("com.taobao.idlefish", "xianyu_description", "7:11")
        var anchorVisible = true
        var a11yBound = true
        val a11y = MemoryTransport()
        val ime = MemoryTransport()
        val transaction = FieldInputTransaction(
            route = { channel },
            accessibilityBound = { a11yBound },
            accessibilityTransport = { if (a11yBound) a11y else null },
            imeTransport = { ime },
            anchorOf = { pkg, ref ->
                anchor.takeIf { anchorVisible && it.targetPackage == pkg && it.locatorRef == ref }
            },
            pause = {},
        )
    }

    private class MemoryTransport : EditorTransport {
        var text = ""
        var commits = 0
        override fun commitCount(): Int = commits
        var generation = 3L
        override suspend fun snapshot(): EditorSnapshot = EditorSnapshot(
            generation, "field", text, text.length, text.length, false, true, 0, false,
        )
        override suspend fun commit(snapshot: EditorSnapshot, text: String): Boolean {
            commits++
            this.text = text
            return true
        }
    }

    @Test fun accessibilityChannelWritesWithoutSwitching() = runBlocking {
        val harness = Harness(InputChannel.ACCESSIBILITY)
        harness.transaction.replace("com.taobao.idlefish", "xianyu_description", "描述199")
        assertEquals(1, harness.a11y.commits)
        assertEquals(0, harness.ime.commits)
    }

    @Test fun numericDescriptionDoesNotGoToPrice() = runBlocking {
        val harness = Harness(InputChannel.ACCESSIBILITY)
        harness.transaction.replace("com.taobao.idlefish", "xianyu_description", "199")
        assertEquals(listOf("199"), listOf(harness.a11y.text))
    }

    @Test fun priceLocatorIsRejected() {
        val harness = Harness(InputChannel.ACCESSIBILITY)
        val error = assertFailsWith<ExecutorFailure> {
            runBlocking { harness.transaction.replace("com.taobao.idlefish", "xianyu_price", "199") }
        }
        assertEquals("INPUT_REJECTED", error.code)
        assertEquals(0, harness.a11y.commits)
    }

    @Test fun api30WritesTheImeWithoutSwitchingInsideTheTransaction() = runBlocking {
        val harness = Harness(InputChannel.TEMPORARY_IME)
        harness.anchor = harness.anchor.copy(locatorRef = "xianyu_chat_input")
        // The service wraps this one replace in the temporary switch. The
        // transaction itself must not switch a second time.
        harness.transaction.replace("com.taobao.idlefish", "xianyu_chat_input", "在的")
        assertEquals(1, harness.ime.commits)
        assertEquals(0, harness.a11y.commits)
    }

    @Test fun api33UnboundRefusesWithoutSwitchingTheKeyboard() {
        val harness = Harness(InputChannel.ACCESSIBILITY).apply { a11yBound = false }
        val error = assertFailsWith<ExecutorFailure> {
            runBlocking { harness.transaction.replace("com.taobao.idlefish", "xianyu_description", "只此一次") }
        }
        assertEquals("INPUT_READBACK_UNAVAILABLE", error.code)
        assertEquals(0, harness.a11y.commits)
        assertEquals(0, harness.ime.commits)
    }

    @Test fun nodeDisappearingAfterCommitFailsClosed() {
        val harness = Harness(InputChannel.ACCESSIBILITY)
        val transport = object : EditorTransport by harness.a11y {
            override fun commitCount(): Int = harness.a11y.commitCount()
            override suspend fun commit(snapshot: EditorSnapshot, text: String): Boolean {
                val wrote = harness.a11y.commit(snapshot, text)
                harness.anchorVisible = false
                return wrote
            }
        }
        val transaction = FieldInputTransaction(
            route = { InputChannel.ACCESSIBILITY },
            accessibilityBound = { true },
            accessibilityTransport = { transport },
            imeTransport = { harness.ime },
            anchorOf = { pkg, ref ->
                harness.anchor.takeIf { harness.anchorVisible && it.targetPackage == pkg && it.locatorRef == ref }
            },
            pause = {},
        )
        val error = assertFailsWith<ExecutorFailure> {
            runBlocking { transaction.replace("com.taobao.idlefish", "xianyu_description", "会消失") }
        }
        assertEquals("INPUT_TARGET_CHANGED", error.code)
        assertEquals(1, harness.a11y.commits)
    }

    @Test fun nodeIdentityChangeFailsClosed() {
        val harness = Harness(InputChannel.ACCESSIBILITY)
        var reads = 0
        val transport = object : EditorTransport {
            override fun commitCount(): Int = harness.a11y.commitCount()
            override suspend fun snapshot(): EditorSnapshot {
                reads++
                if (reads > 3) harness.anchor = harness.anchor.copy(nodeKey = "8:99")
                return harness.a11y.snapshot()
            }
            override suspend fun commit(snapshot: EditorSnapshot, text: String): Boolean {
                harness.a11y.commit(snapshot, text)
                harness.anchor = harness.anchor.copy(nodeKey = "8:99")
                return true
            }
        }
        val transaction = FieldInputTransaction(
            route = { InputChannel.ACCESSIBILITY },
            accessibilityBound = { true },
            accessibilityTransport = { transport },
            imeTransport = { harness.ime },
            anchorOf = { _, _ -> harness.anchor },
            pause = {},
        )
        val error = assertFailsWith<ExecutorFailure> {
            runBlocking { transaction.replace("com.taobao.idlefish", "xianyu_description", "新描述") }
        }
        assertEquals("INPUT_TARGET_CHANGED", error.code)
    }
}
