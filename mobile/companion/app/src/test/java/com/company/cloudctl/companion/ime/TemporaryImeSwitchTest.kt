package com.company.cloudctl.companion.ime

import com.company.cloudctl.companion.automation.ExecutorFailure
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class TemporaryImeSwitchTest {
    private class Fake : ImeSwitcher {
        var current: String? = "com.sogou/.SogouIME"
        val cloud = setOf("com.company.cloudctl.companion/.ime.CloudCtlInputMethod")
        var switchResult = true
        var observeAfterSwitch: String? = null
        val switches = mutableListOf<String>()
        override fun currentDefaultId(): String? = current
        override fun cloudCtlIds(): Set<String> = cloud
        override fun switchTo(id: String): Boolean {
            switches += id
            if (!switchResult) return false
            current = observeAfterSwitch ?: id
            return true
        }
        override fun observeSelectedId(): String? = current
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

    @Test fun alreadyOnCloudCtlDoesNotSwitchAway() = runBlocking {
        val fake = Fake().apply { current = cloud.first() }
        val value = TemporaryImeSwitch(fake, pause = {}).around<String> { "ok" }
        assertEquals("ok", value)
        assertTrue(fake.switches.isEmpty())
        assertEquals(fake.cloud.first(), fake.current)
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

    @Test fun switchThatDoesNotStickRefusesTheWrite() {
        val fake = Fake().apply { observeAfterSwitch = "com.sogou/.SogouIME" }
        val error = assertFailsWith<ExecutorFailure> {
            runBlocking { TemporaryImeSwitch(fake, pause = {}, observeAttempts = 1).around { "nope" } }
        }
        assertEquals("INPUT_IME_REQUIRED", error.code)
        assertTrue("com.sogou/.SogouIME" == fake.current)
    }
}
