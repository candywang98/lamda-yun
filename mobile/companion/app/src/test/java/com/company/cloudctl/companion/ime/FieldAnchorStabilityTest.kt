package com.company.cloudctl.companion.ime

import com.company.cloudctl.companion.automation.ExecutorFailure
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotEquals

/**
 * B14 field anchor: the key is a stable public signature. A fresh wrapper of
 * the same field (same window, bounds, class, view id) must pass. A different
 * window, position or field must fail closed. Object identity is not the key.
 */
class FieldAnchorStabilityTest {
    private class Harness {
        var anchor = FieldAnchor(
            "com.taobao.idlefish",
            "xianyu_chat_input",
            "7|10,800,1000,900|android.widget.EditText|com.taobao.idlefish:id/input",
        )
        val transport = MemoryTransport()
        fun transaction() = FieldInputTransaction(
            route = { InputChannel.ACCESSIBILITY },
            accessibilityBound = { true },
            accessibilityTransport = { transport },
            imeTransport = { null },
            anchorOf = { pkg, ref ->
                anchor.takeIf { it.targetPackage == pkg && it.locatorRef == ref }
            },
            pause = {},
        )
    }

    private class MemoryTransport : EditorTransport {
        var text = ""
        var commits = 0
        override fun commitCount(): Int = commits
        override suspend fun snapshot(): EditorSnapshot = EditorSnapshot(
            3, "field", text, text.length, text.length, false, true, 0, false,
        )
        override suspend fun commit(snapshot: EditorSnapshot, text: String): Boolean {
            commits++
            this.text = text
            return true
        }
    }

    @Test fun aFreshWrapperWithTheSamePublicSignaturePasses() = runBlocking {
        val harness = Harness()
        var resolutions = 0
        val transaction = FieldInputTransaction(
            route = { InputChannel.ACCESSIBILITY },
            accessibilityBound = { true },
            accessibilityTransport = { harness.transport },
            imeTransport = { null },
            anchorOf = { pkg, ref ->
                resolutions++
                // Each resolution is a new object, the way AccessibilityNodeInfo
                // returns a fresh wrapper. The public signature stays put.
                FieldAnchor(pkg, ref, harness.anchor.nodeKey)
            },
            pause = {},
        )
        val proof = transaction.replace("com.taobao.idlefish", "xianyu_chat_input", "在的")
        assertEquals(harness.anchor.nodeKey, proof.nodeKey)
        assertEquals(1, harness.transport.commits)
        assertNotEquals(0, resolutions)
    }

    @Test fun aDifferentWindowPositionOrFieldRefuses() {
        val harness = Harness()
        val moved = listOf(
            harness.anchor.nodeKey!!.replace("7|", "8|"),
            harness.anchor.nodeKey!!.replace("10,800", "10,900"),
            harness.anchor.nodeKey!!.replace("input", "other"),
        )
        moved.forEach { changed ->
            val transport = object : EditorTransport by harness.transport {
                override fun commitCount(): Int = harness.transport.commitCount()
                override suspend fun commit(snapshot: EditorSnapshot, text: String): Boolean {
                    harness.transport.commit(snapshot, text)
                    harness.anchor = harness.anchor.copy(nodeKey = changed)
                    return true
                }
            }
            val transaction = FieldInputTransaction(
                route = { InputChannel.ACCESSIBILITY },
                accessibilityBound = { true },
                accessibilityTransport = { transport },
                imeTransport = { null },
                anchorOf = { _, _ -> harness.anchor },
                pause = {},
            )
            val error = assertFailsWith<ExecutorFailure> {
                runBlocking { transaction.replace("com.taobao.idlefish", "xianyu_chat_input", "在的") }
            }
            assertEquals("INPUT_TARGET_CHANGED", error.code)
            harness.anchor = harness.anchor.copy(
                nodeKey = "7|10,800,1000,900|android.widget.EditText|com.taobao.idlefish:id/input",
            )
            harness.transport.text = ""
        }
    }

    @Test fun stableKeyDoesNotUseWrapperIdentity() {
        val first = FieldAnchor("com.taobao.idlefish", "xianyu_chat_input", "7|1,2,3,4|android.widget.EditText|id")
        val second = FieldAnchor("com.taobao.idlefish", "xianyu_chat_input", "7|1,2,3,4|android.widget.EditText|id")
        assertEquals(first.nodeKey, second.nodeKey)
        // Two distinct objects. A key built from identityHashCode would differ.
        assertNotEquals(System.identityHashCode(first), System.identityHashCode(second))
    }
}
