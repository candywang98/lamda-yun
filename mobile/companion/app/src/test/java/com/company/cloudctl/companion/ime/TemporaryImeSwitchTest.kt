package com.company.cloudctl.companion.ime

import com.company.cloudctl.companion.automation.ExecutorFailure
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class TemporaryImeSwitchTest {
    private class Fake : ImeSwitcher {
        var current: String? = "com.sogou/.SogouIME"
        val cloud = setOf("com.company.cloudctl.companion/.ime.CloudCtlInputMethod")
        var switchResult = true
        var observeAfterSwitch: String? = null
        var staleSelectionReads = 0
        val switches = mutableListOf<String>()
        override fun currentDefaultId(): String? = current
        override fun cloudCtlIds(): Set<String> = cloud
        override fun switchTo(id: String): Boolean {
            switches += id
            if (!switchResult) return false
            current = observeAfterSwitch ?: id
            return true
        }
        override fun observeSelectedId(): String? =
            if (staleSelectionReads-- > 0) "com.sogou/.SogouIME" else current
    }

    @Test fun switchesForTheBlockAndRestoresTheOriginalId() = runBlocking {
        val fake = Fake()
        val seen = mutableListOf<String?>()
        val value: String = TemporaryImeSwitch(fake, pause = {}).around {
            seen.add(fake.current)
            "ok"
        }
        assertEquals("ok", value)
        assertEquals(listOf(fake.cloud.first(), "com.sogou/.SogouIME"), fake.switches)
        assertEquals("com.sogou/.SogouIME", fake.current)
        assertEquals(listOf<String?>(fake.cloud.first()), seen)
    }

    @Test fun alreadyOnCloudCtlRefusesInputUntilUserSelectsAKeyboard() = runBlocking {
        val fake = Fake().apply { current = cloud.first() }
        var committed = false
        var started = false
        val error = assertFailsWith<ExecutorFailure> {
            TemporaryImeSwitch(fake, pause = {}, onSwitchStarted = { started = true }).around {
                committed = true
                "typed"
            }
        }
        assertEquals("INPUT_IME_RECOVERY_REQUIRED", error.code)
        assertTrue(error.message.orEmpty().contains("system input settings"))
        assertTrue(!committed)
        assertTrue(!started)
        assertTrue(fake.switches.isEmpty())
        assertEquals(fake.cloud.first(), fake.current)
    }

    @Test fun temporarySelectionEndsAfterSuccessFailureAndCancellation() {
        fun transaction(fake: Fake, block: suspend () -> String): Pair<String?, List<Boolean>> {
            val states = mutableListOf<Boolean>()
            val result = runCatching {
                runBlocking {
                    TemporaryImeSwitch(
                        fake,
                        pause = {},
                        onSwitchStarted = { states += true },
                        onSwitchFinished = { states += false },
                    ).around(block)
                }
            }
            return (result.exceptionOrNull() as? ExecutorFailure)?.code to states
        }

        assertEquals(null to listOf(true, false), transaction(Fake()) { "ok" })
        assertEquals("INPUT_IME_REQUIRED" to listOf(true, false), transaction(Fake().apply { switchResult = false }) { "nope" })
        val restoreFailure = Fake()
        assertEquals("IME_RESTORE_FAILED" to listOf(true, false), transaction(restoreFailure) {
            restoreFailure.switchResult = false
            "typed"
        })
        assertEquals(restoreFailure.cloud.first(), restoreFailure.current)
        assertEquals(null to listOf(true, false), transaction(Fake()) {
            throw kotlinx.coroutines.CancellationException("stopped")
        })
    }

    @Test fun thirdPartyKeyboardIsNotTakenOver() {
        val fake = Fake().apply { current = "com.iflytek/.Ifly" ; switchResult = false }
        // switchResult false means we never claim the user's keyboard.
        val error = assertFailsWith<ExecutorFailure> {
            runBlocking { TemporaryImeSwitch(fake, pause = {}).around { "nope" } }
        }
        assertEquals("INPUT_IME_REQUIRED", error.code)
        assertEquals("com.iflytek/.Ifly", fake.current)
    }

    @Test fun userPicksAThirdImeAndThatChoiceIsKept() {
        val fake = Fake()
        val error = assertFailsWith<ExecutorFailure> {
            runBlocking {
                TemporaryImeSwitch(fake, pause = {}).around {
                    fake.current = "com.baidu/.BaiduIME"
                    "typed"
                }
            }
        }
        assertEquals("USER_INTERFERENCE", error.code)
        assertEquals("com.baidu/.BaiduIME", fake.current)
        assertTrue(fake.switches.none { it == "com.baidu/.BaiduIME" })
    }

    @Test fun restoreFailureIsNotSuccess() {
        val fake = Fake()
        val error = assertFailsWith<ExecutorFailure> {
            runBlocking {
                TemporaryImeSwitch(fake, pause = {}).around {
                    fake.switchResult = false
                    fake.current = fake.cloud.first()
                    "typed"
                }
            }
        }
        assertEquals("IME_RESTORE_FAILED", error.code)
    }

    @Test fun cancellationStillRestores() {
        val fake = Fake()
        assertFailsWith<kotlinx.coroutines.CancellationException> {
            runBlocking {
                TemporaryImeSwitch(fake, pause = {}).around<String> {
                    throw kotlinx.coroutines.CancellationException("stopped")
                }
            }
        }
        assertEquals("com.sogou/.SogouIME", fake.current)
    }

    @Test fun cancellationWhileSelectingStillRollsBackAndClearsTemporaryState() {
        val fake = Fake().apply { staleSelectionReads = 1 }
        val states = mutableListOf<Boolean>()
        assertFailsWith<kotlinx.coroutines.CancellationException> {
            runBlocking {
                TemporaryImeSwitch(
                    fake,
                    pause = { throw kotlinx.coroutines.CancellationException("selection interrupted") },
                    onSwitchStarted = { states += true },
                    onSwitchFinished = { states += false },
                ).around { "never typed" }
            }
        }
        assertEquals(listOf(true, false), states)
        assertEquals("com.sogou/.SogouIME", fake.current)
    }

    @Test fun switchThatDoesNotStickRefusesTheWrite() {
        val fake = Fake().apply { observeAfterSwitch = "com.sogou/.SogouIME" }
        val error = assertFailsWith<ExecutorFailure> {
            runBlocking { TemporaryImeSwitch(fake, pause = {}, observeAttempts = 1).around { "nope" } }
        }
        assertEquals("INPUT_IME_REQUIRED", error.code)
        assertTrue("com.sogou/.SogouIME" == fake.current)
    }

    @Test fun cancelledJobAwaitsRestorationWhileSelecting() =
        assertCancelledJobAwaitsRestoration(cancelWhileSelecting = true)

    @Test fun cancelledJobAwaitsRestorationWhileInputIsSuspended() =
        assertCancelledJobAwaitsRestoration(cancelWhileSelecting = false)

    private fun assertCancelledJobAwaitsRestoration(cancelWhileSelecting: Boolean) = runBlocking {
        withTimeout(10_000) {
            val original = "com.sogou/.SogouIME"
            val cloud = "com.company.cloudctl.companion/.ime.CloudCtlInputMethod"
            var selected = original
            var restoring = false
            var temporary = false
            var finished = false
            var blockEntered = false
            var blockContinued = false
            var returnedSuccess = false
            var cancellationObserved = false
            val cancelPoint = CompletableDeferred<Unit>()
            val holdInput = CompletableDeferred<Unit>()
            val restoreStarted = CompletableDeferred<Unit>()
            val releaseRestore = CompletableDeferred<Unit>()
            val switches = mutableListOf<String>()
            val switcher = object : ImeSwitcher {
                override fun currentDefaultId() = original
                override fun cloudCtlIds() = setOf(cloud)
                override fun switchTo(id: String): Boolean {
                    switches += id
                    if (id == original) {
                        // The restore request succeeds before its selection is observable.
                        restoring = true
                    } else {
                        selected = id
                    }
                    return true
                }
                override fun observeSelectedId() =
                    if (cancelWhileSelecting && !restoring) original else selected
            }
            val job = launch {
                try {
                    TemporaryImeSwitch(
                        switcher,
                        pause = {
                            if (restoring) {
                                restoreStarted.complete(Unit)
                                releaseRestore.await()
                                selected = original
                            } else {
                                cancelPoint.complete(Unit)
                                holdInput.await()
                            }
                        },
                        onSwitchStarted = { temporary = true },
                        onSwitchFinished = { temporary = false; finished = true },
                    ).around {
                        blockEntered = true
                        cancelPoint.complete(Unit)
                        holdInput.await()
                        blockContinued = true
                        "typed"
                    }
                    returnedSuccess = true
                } catch (error: CancellationException) {
                    cancellationObserved = true
                    throw error
                }
            }
            try {
                cancelPoint.await()
                assertTrue(temporary)
                assertEquals(!cancelWhileSelecting, blockEntered)
                job.cancel()
                restoreStarted.await()
                assertTrue(job.isCancelled)
                assertFalse(job.isCompleted)
                assertTrue(temporary)
                assertFalse(finished)
                assertEquals(cloud, selected)
                assertFalse(blockContinued)
                assertFalse(returnedSuccess)
                assertFalse(cancellationObserved)

                releaseRestore.complete(Unit)
                job.join()
                assertTrue(job.isCompleted)
                assertTrue(job.isCancelled)
                assertTrue(cancellationObserved)
                assertEquals(original, selected)
                assertEquals(listOf(cloud, original), switches)
                assertFalse(temporary)
                assertTrue(finished)
                assertEquals(!cancelWhileSelecting, blockEntered)
                assertFalse(blockContinued)
                assertFalse(returnedSuccess)
            } finally {
                job.cancel()
                holdInput.complete(Unit)
                releaseRestore.complete(Unit)
                cancelPoint.complete(Unit)
                restoreStarted.complete(Unit)
                withContext(NonCancellable) {
                    withTimeout(10_000) { job.cancelAndJoin() }
                }
            }
        }
    }
}
