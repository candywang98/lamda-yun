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
        var backs = 0
        var settles = 0

        override fun onMessageList(): Boolean = onList()
        override suspend fun tapMessagesTabAnchor(): Boolean {
            anchorTaps++
            order += "anchor"
            return anchorOutcome()
        }

        override fun goBack() {
            backs++
            order += "back"
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
        assertEquals(0, fake.backs)
        assertTrue(fake.coordinateTaps.isEmpty())
        assertTrue(fake.events.isEmpty())
        assertEquals(0, fake.settles)
    }

    @Test fun anchorDirectHitTapsAnchorWithoutBackOrCoordinateFallback() = runBlocking {
        val fake = Fake().apply { anchorOutcome = { true } }
        assertTrue(DutyMessageListNav(fake).execute())
        assertEquals(1, fake.anchorTaps)
        assertEquals(0, fake.backs)
        assertEquals(1, fake.settles)
        assertTrue(fake.coordinateTaps.isEmpty())
        assertTrue(DutyMessageListNav.COORD_FALLBACK_EVENT !in fake.events)
        assertTrue(DutyMessageListNav.BACK_EVENT !in fake.events)
    }

    @Test fun anchorMissBacksOnceThenAnchorHitsAndStops() = runBlocking {
        var anchorCalls = 0
        val fake = Fake().apply { anchorOutcome = { ++anchorCalls > 1 } }
        assertTrue(DutyMessageListNav(fake).execute())
        // Initial resolve + one retry after the first BACK.
        assertEquals(2, fake.anchorTaps)
        assertEquals(1, fake.backs)
        assertEquals(1, fake.settles)
        assertEquals(listOf(DutyMessageListNav.BACK_EVENT), fake.events)
        assertTrue(fake.coordinateTaps.isEmpty())
    }

    @Test fun landingOnListAfterOneBackStopsWithoutFurtherTaps() = runBlocking {
        val fake = Fake().apply {
            anchorOutcome = { false }
            onList = { backs > 0 }
        }
        assertTrue(DutyMessageListNav(fake).execute())
        assertEquals(1, fake.anchorTaps)
        assertEquals(1, fake.backs)
        assertTrue(fake.coordinateTaps.isEmpty())
        assertEquals(listOf(DutyMessageListNav.BACK_EVENT), fake.events)
    }

    @Test fun backAttemptsExhaustedFallsBackToVerifiedCoordinateOnceWithAuditEvent() = runBlocking {
        val fake = Fake().apply {
            anchorOutcome = { false }
            onList = { coordinateTaps.isNotEmpty() }
        }
        assertTrue(DutyMessageListNav(fake).execute())
        assertEquals(2, fake.backs)
        assertEquals(
            listOf(DutyMessageListNav.BACK_EVENT, DutyMessageListNav.BACK_EVENT, DutyMessageListNav.COORD_FALLBACK_EVENT),
            fake.events,
        )
        assertEquals(listOf(975.0 to 2331.0), fake.coordinateTaps)
        assertEquals(1, fake.settles)
        // The audit flag must precede the blind tap, not explain it afterwards.
        assertTrue(fake.order.indexOf("event:${DutyMessageListNav.COORD_FALLBACK_EVENT}") < fake.order.indexOf("coord:975.0,2331.0"))
    }

    @Test fun fallbackFiresExactlyOnceEvenWhenItDoesNotLand() = runBlocking {
        val fake = Fake().apply { anchorOutcome = { false } }
        assertFalse(DutyMessageListNav(fake).execute())
        assertEquals(2, fake.backs)
        assertEquals(listOf(975.0 to 2331.0), fake.coordinateTaps)
        assertTrue(fake.events.count { it == DutyMessageListNav.COORD_FALLBACK_EVENT } == 1)
    }
}
