package com.company.cloudctl.companion.ime

import com.company.cloudctl.companion.automation.ExecutorFailure
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * B14 API 30–32 send re-check, extracted from the service so it can run without
 * a device. The temporary rebind may observe a new editor generation, but the
 * public EditorInfo fingerprint must be the same and the full text must be
 * stable twice inside that generation. The original IME is restored afterwards.
 * The block never commits.
 */
class Api30SendProofReadbackTest {
    private class FakeSwitcher : ImeSwitcher {
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

    private class ReadModel(
        var fingerprint: String = "com.taobao.idlefish|1|6|-1|",
        var generation: Long = 9L,
        var text: String = "你好，在的",
        var commits: Int = 0,
    ) {
        fun sample(): Pair<Long, String>? {
            if (fingerprint != PINNED) return null
            if (text != EXPECTED) return null
            return generation to text
        }
    }

    private fun proof(generation: Long = 4L) = InputProof(
        target = "com.taobao.idlefish",
        field = PINNED,
        generation = generation,
        expected = EXPECTED,
        snapshot = EditorSnapshot(generation, PINNED, EXPECTED, 0, 0, false, true, 0, false, selectionKnown = false),
        targetPackage = "com.taobao.idlefish",
        locatorRef = "xianyu_chat_input",
        nodeKey = "7|0,0,10,10|android.widget.EditText|",
        selectionKnown = false,
        taskId = "task-1",
        peerName = "lucas",
        expiresAtElapsedMs = 30_000L,
    )

    @Test fun newGenerationWithTheSameFingerprintAndTwoStableReadsPassesAndRestores() = runBlocking {
        val switcher = FakeSwitcher()
        val model = ReadModel(generation = 9L)
        val ok = TemporaryImeSwitch(switcher, pause = {}).around {
            val first = model.sample() ?: return@around false
            val second = model.sample() ?: return@around false
            first == second && model.commits == 0
        }
        assertTrue(ok)
        assertEquals(listOf(switcher.cloud.first(), "com.sogou/.SogouIME"), switcher.switches)
        assertEquals("com.sogou/.SogouIME", switcher.current)
        assertEquals(0, model.commits)
        // The proof's original generation is not required to survive the rebind.
        assertTrue(proof().generation != model.generation)
    }

    @Test fun aDifferentFingerprintRefusesAndStillRestores() = runBlocking {
        val switcher = FakeSwitcher()
        val model = ReadModel(fingerprint = "com.taobao.idlefish|1|6|99|other")
        val ok = TemporaryImeSwitch(switcher, pause = {}).around {
            model.sample() != null
        }
        assertFalse(ok)
        assertEquals("com.sogou/.SogouIME", switcher.current)
    }

    @Test fun unstableTextBetweenTheTwoReadsRefuses() = runBlocking {
        val switcher = FakeSwitcher()
        val model = ReadModel()
        var reads = 0
        val ok = TemporaryImeSwitch(switcher, pause = {}).around {
            val first = model.sample()
            reads++
            model.text = "用户改了"
            val second = model.sample()
            first != null && first == second
        }
        assertFalse(ok)
        assertEquals(1, reads)
        assertEquals("com.sogou/.SogouIME", switcher.current)
    }

    @Test fun aGenerationChangeBetweenTheTwoReadsIsNotYetStable() = runBlocking {
        val model = ReadModel(generation = 9L)
        val first = model.sample()
        model.generation = 10L
        val second = model.sample()
        assertTrue(first != null && second != null)
        assertFalse(first == second)
    }

    @Test fun userPickingAThirdImeDuringTheReadIsKept() {
        val switcher = FakeSwitcher()
        val error = assertFailsWith<ExecutorFailure> {
            runBlocking {
                TemporaryImeSwitch(switcher, pause = {}).around {
                    switcher.current = "com.iflytek/.Ifly"
                    true
                }
            }
        }
        assertEquals("USER_INTERFERENCE", error.code)
        assertEquals("com.iflytek/.Ifly", switcher.current)
    }

    private companion object {
        const val PINNED = "com.taobao.idlefish|1|6|-1|"
        const val EXPECTED = "你好，在的"
    }
}
