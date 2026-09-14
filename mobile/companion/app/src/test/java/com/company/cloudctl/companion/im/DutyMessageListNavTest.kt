package com.company.cloudctl.companion.im

import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class DutyMessageListNavTest {
    private class Fake : DutyMessageListNav.Port {
        var onList: () -> Boolean = { false }
        var anchorOutcome: () -> Boolean = { true }
        val events = mutableListOf<String>()
        val coordinateTaps = mutableListOf<Pair<Double, Double>>()
        val order = mutableListOf<String>()
        var anchorTaps = 0
        var settles = 0

        override fun onMessageList(): Boolean = onList()
        override suspend fun tapMessagesTabAnchor(): Boolean {
            anchorTaps++
            order += "anchor"
            return anchorOutcome()
        }

        override suspend fun tapCoordinate(x: Double, y: Double) {
            coordinateTaps += x to y
            order += "coord:$x,$y"
        }

        override fun event(code: String) {
            events += code
            order += "event:$code"
        }

        override suspend fun settle() { settles++ }
    }

    @Test fun alreadyOnListNeverTapsAnything() = runBlocking {
        val fake = Fake().apply { onList = { true } }
        assertTrue(DutyMessageListNav(fake).execute())
        assertEquals(0, fake.anchorTaps)
        assertTrue(fake.coordinateTaps.isEmpty())
        assertTrue(fake.events.isEmpty())
        assertEquals(0, fake.settles)
    }

    @Test fun anchorHitTapsAnchorWithoutCoordinateFallback() = runBlocking {
        val fake = Fake().apply { anchorOutcome = { true } }
        assertTrue(DutyMessageListNav(fake).execute())
        assertEquals(1, fake.anchorTaps)
        assertEquals(1, fake.settles)
        assertTrue(fake.coordinateTaps.isEmpty())
        assertTrue(DutyMessageListNav.COORD_FALLBACK_EVENT !in fake.events)
    }

    @Test fun anchorMissOffListFallsBackToVerifiedCoordinateOnceWithAuditEvent() = runBlocking {
        val answers = ArrayDeque(listOf(false, false, true))
        val fake = Fake().apply {
            anchorOutcome = { false }
            onList = { answers.removeFirst() }
        }
        assertTrue(DutyMessageListNav(fake).execute())
        assertEquals(listOf("DUTY_NAV_COORD_FALLBACK"), fake.events)
        assertEquals(listOf(975.0 to 2331.0), fake.coordinateTaps)
        assertEquals(1, fake.settles)
        // The audit flag must precede the blind tap, not explain it afterwards.
        assertTrue(fake.order.indexOf("event:DUTY_NAV_COORD_FALLBACK") < fake.order.indexOf("coord:975.0,2331.0"))
    }

    @Test fun anchorMissWhileAlreadyOnMessageListNeverClicks() = runBlocking {
        val answers = ArrayDeque(listOf(false, true))
        val fake = Fake().apply {
            anchorOutcome = { false }
            onList = { answers.removeFirst() }
        }
        assertTrue(DutyMessageListNav(fake).execute())
        assertEquals(1, fake.anchorTaps)
        assertTrue(fake.coordinateTaps.isEmpty())
        assertTrue(fake.events.isEmpty())
        assertEquals(0, fake.settles)
    }

    @Test fun fallbackFiresExactlyOnceEvenWhenItDoesNotLand() = runBlocking {
        val fake = Fake().apply { anchorOutcome = { false } }
        assertFalse(DutyMessageListNav(fake).execute())
        assertEquals(listOf(975.0 to 2331.0), fake.coordinateTaps)
        assertEquals(listOf("DUTY_NAV_COORD_FALLBACK"), fake.events)
    }
}
