package com.company.cloudctl.companion.ime

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * onUnbind and onDestroy both call [ChatInputLifecycle.clear], which is what
 * [com.company.cloudctl.companion.automation.CloudCtlAccessibilityService.clearChatSendProof]
 * delegates to. A service that is rebound must not still hold the previous
 * task's proof, its pending bind, or a field string remembered for a later poll.
 */
class ChatInputLifecycleTest {
    private fun proof() = InputProof(
        target = "com.taobao.idlefish",
        field = "com.taobao.idlefish|1|6|-1|",
        generation = 9L,
        expected = "你好，在的",
        snapshot = EditorSnapshot(9L, "com.taobao.idlefish|1|6|-1|", "你好，在的", 0, 0, false, true, 0, false, selectionKnown = false),
        targetPackage = "com.taobao.idlefish",
        locatorRef = "xianyu_chat_input",
        nodeKey = "7|0,0,10,10|android.widget.EditText|",
        selectionKnown = false,
        taskId = "task-1",
        peerName = "lucas",
        expiresAtElapsedMs = 31_000L,
    )

    private fun filled(): ChatInputLifecycle = ChatInputLifecycle().apply {
        begin("task-1", "lucas", 30_000L, 1_000L)
        remember("xianyu_description", "自用闲置，支持当面交易")
        val pending = takeBind()
        hold(proof().copy(taskId = pending!!.taskId, peerName = pending.peerName, expiresAtElapsedMs = pending.expiresAtElapsedMs))
        begin("task-2", "另一个买家", 30_000L, 2_000L)
    }

    @Test fun clearDropsTheHeldProofThePendingBindAndRememberedFields() {
        val life = filled()
        assertEquals("task-1", life.peek()?.taskId)
        assertEquals("task-2", life.pendingTaskId())
        assertEquals("自用闲置，支持当面交易", life.committed("xianyu_description"))

        // The same call onUnbind and onDestroy make.
        life.clear()

        assertNull(life.peek())
        assertNull(life.pendingBind)
        assertNull(life.pendingTaskId())
        assertNull(life.committed("xianyu_description"))
        assertTrue(life.rememberedLocators().isEmpty())
    }

    @Test fun aClearedLifecycleCannotAuthorizeTheNextTask() {
        val life = filled()
        life.clear()
        assertNull(life.takeBind())
        assertNull(life.consume())
        assertNull(life.committed("xianyu_chat_input"))
    }
}
