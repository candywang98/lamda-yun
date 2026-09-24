package com.company.cloudctl.companion.ime

import com.company.cloudctl.companion.automation.ChatInputCommit
import com.company.cloudctl.companion.automation.ChatInputReadback
import com.company.cloudctl.companion.automation.ExecutorFailure
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * The real API 30–32 chat commit path: [ChatInputCommit.execute] runs inside
 * [TemporaryImeSwitch.around], and the proof is the readback that execute already
 * finished — two stable full-text reads, the final generation, and the EditorInfo
 * fingerprint. A single [readText] after around restores the original keyboard is
 * not the proof and is not consulted.
 */
class Api30ChatInputCommitTest {
    private class Switcher : ImeSwitcher {
        var current: String? = "com.sogou/.SogouIME"
        val cloud = setOf("com.company.cloudctl.companion/.ime.CloudCtlInputMethod")
        val switches = mutableListOf<String>()
        override fun currentDefaultId(): String? = current
        override fun cloudCtlIds(): Set<String> = cloud
        override fun switchTo(id: String): Boolean {
            switches += id
            current = id
            return true
        }
        override fun observeSelectedId(): String? = current
    }

    /**
     * The chat port [ChatInputCommit] actually drives. Reads after the verified
     * return are counted so a post-restore read cannot hide inside the proof.
     */
    private class ChatPort(
        private val value: String,
        private val switcher: Switcher,
        private val cloudId: String,
    ) : ChatInputCommit.Port {
        var generation = 4L
        var fingerprint: String? = FINGERPRINT
        var text = ""
        var writes = 0
        var readsAfterVerified = 0
        private var verified = false
        override fun imeSelected(): Boolean = switcher.current == cloudId
        override suspend fun activate(): Boolean = true
        override fun focused(): Boolean = true
        override fun session(): Long = generation
        override fun replace(session: Long, value: String): Boolean {
            check(session == generation)
            writes += 1
            text = value
            // Flutter rebuilds the editor after the single write. The two stable
            // reads below are this new generation, not the one that was written.
            generation = 9L
            return true
        }
        override fun readText(session: Long): String? {
            if (verified) readsAfterVerified += 1
            return text.takeIf { session == generation }
        }
        override fun fieldClearFor(value: String): Boolean = text.isEmpty() || text == value
        override fun fieldIdentity(): String? = fingerprint
        override fun event(code: String) {
            if (code == "CHAT_IME_VERIFIED") verified = true
        }
        override suspend fun pause() = Unit
    }

    private fun commit(port: ChatPort, switcher: Switcher): Api30ChatInputCommit {
        val cloudId = switcher.cloud.first()
        return Api30ChatInputCommit(
            commit = { ChatInputCommit(port).execute(it) },
            switchToCloudCtl = { block -> TemporaryImeSwitch(switcher, pause = {}).around(block) },
            anchorOf = { ANCHOR },
            cloudCtlStillSelected = { switcher.current == cloudId },
            livePackage = { port.fingerprint?.substringBefore('|') },
        )
    }

    @Test fun proofIsTheReadbackCapturedWhileCloudCtlIsStillSelected() = runBlocking {
        val switcher = Switcher()
        val port = ChatPort(EXPECTED, switcher, switcher.cloud.first())
        val seenInside = mutableListOf<String?>()
        val cloudId = switcher.cloud.first()
        val proof = Api30ChatInputCommit(
            commit = { value ->
                val readback = ChatInputCommit(port).execute(value)
                seenInside += switcher.current
                readback
            },
            switchToCloudCtl = { block -> TemporaryImeSwitch(switcher, pause = {}).around(block) },
            anchorOf = { ANCHOR },
            cloudCtlStillSelected = { switcher.current == cloudId },
            livePackage = { port.fingerprint?.substringBefore('|') },
        ).execute("com.taobao.idlefish", "xianyu_chat_input", EXPECTED)

        assertEquals(listOf<String?>(cloudId), seenInside)
        assertEquals(EXPECTED, proof.expected)
        assertEquals(EXPECTED, proof.snapshot.text)
        // The final generation is the one the two stable reads agreed on (9),
        // not the generation that received the single write (4).
        assertEquals(9L, proof.generation)
        assertEquals(9L, proof.snapshot.generation)
        assertEquals(FINGERPRINT, proof.field)
        assertEquals(FINGERPRINT, proof.snapshot.field)
        assertEquals("xianyu_chat_input", proof.locatorRef)
        assertEquals(ANCHOR.nodeKey, proof.nodeKey)
        assertEquals(1, port.writes)
        // around restored the original keyboard, and nothing read the field after that.
        assertEquals("com.sogou/.SogouIME", switcher.current)
        assertEquals(listOf(cloudId, "com.sogou/.SogouIME"), switcher.switches)
        assertEquals(0, port.readsAfterVerified)
    }

    @Test fun aReadbackTakenAfterRestoreIsNotUsed() = runBlocking {
        val switcher = Switcher()
        val port = ChatPort(EXPECTED, switcher, switcher.cloud.first())
        var readAfterRestore: String? = "should-not-be-consulted"
        val cloudId = switcher.cloud.first()
        Api30ChatInputCommit(
            commit = { ChatInputCommit(port).execute(it) },
            switchToCloudCtl = { block ->
                val proof: InputProof = TemporaryImeSwitch(switcher, pause = {}).around(block)
                // The original keyboard is back. A single read here used to be
                // the proof; it must not be.
                readAfterRestore = port.readText(port.generation)
                proof
            },
            anchorOf = { ANCHOR },
            cloudCtlStillSelected = { switcher.current == cloudId },
            livePackage = { "com.taobao.idlefish" },
        ).execute("com.taobao.idlefish", "xianyu_chat_input", EXPECTED)
        assertEquals(EXPECTED, readAfterRestore)
        // That post-restore read is exactly the one the old path performed.
        // The proof above was already returned from inside around, so this read
        // is counted and is not what authorized the proof.
        assertEquals(1, port.readsAfterVerified)
        assertTrue(switcher.current != cloudId)
    }

    @Test fun proofRefusesWhenCloudCtlIsNoLongerSelectedInsideTheBlock() = runBlocking {
        val switcher = Switcher()
        val port = ChatPort(EXPECTED, switcher, switcher.cloud.first())
        val failure = assertFailsWith<ExecutorFailure> {
            Api30ChatInputCommit(
                commit = { value ->
                    val readback = ChatInputCommit(port).execute(value)
                    switcher.current = "com.sogou/.SogouIME"
                    readback
                },
                switchToCloudCtl = { block -> TemporaryImeSwitch(switcher, pause = {}).around(block) },
                anchorOf = { ANCHOR },
                cloudCtlStillSelected = { switcher.current == switcher.cloud.first() },
                livePackage = { "com.taobao.idlefish" },
            ).execute("com.taobao.idlefish", "xianyu_chat_input", EXPECTED)
        }
        assertEquals("INPUT_IME_REQUIRED", failure.code)
        assertEquals("com.sogou/.SogouIME", switcher.current)
    }

    @Test fun readbackCarriesTheTwoStableReadsNotACopiedModel() = runBlocking {
        val direct = ChatPort(EXPECTED, Switcher().apply { current = cloudId() }, cloudId())
        val readback: ChatInputReadback = ChatInputCommit(direct).execute(EXPECTED)
        assertEquals(EXPECTED, readback.text)
        assertEquals(9L, readback.generation)
        assertEquals(FINGERPRINT, readback.fingerprint)
        // A second, fresh field. Reusing the port above would be a non-empty draft.
        val switcher = Switcher()
        val port = ChatPort(EXPECTED, switcher, switcher.cloud.first())
        val proof = commit(port, switcher).execute("com.taobao.idlefish", "xianyu_chat_input", EXPECTED)
        assertEquals(readback.text, proof.snapshot.text)
        assertEquals(readback.generation, proof.generation)
        assertEquals(readback.fingerprint, proof.field)
        assertEquals(0, direct.readsAfterVerified)
    }

    private fun cloudId() = "com.company.cloudctl.companion/.ime.CloudCtlInputMethod"

    private companion object {
        const val EXPECTED = "你好，在的"
        const val FINGERPRINT = "com.taobao.idlefish|1|6|-1|"
        val ANCHOR = FieldAnchor("com.taobao.idlefish", "xianyu_chat_input", "7|0,0,10,10|android.widget.EditText|")
    }
}
