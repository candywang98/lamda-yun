package com.company.cloudctl.companion.im

import java.time.Instant
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ImCanonicalTextTest {
    private val emoji = "\uD83D\uDE00" // U+1F600, one code point, two UTF-16 units

    @Test
    fun hashesMatchSharedBackendFixtures() {
        val fixture = javaClass.classLoader!!.getResourceAsStream("fixtures/im-m3-canonical.json")!!
            .bufferedReader().use { JSONObject(it.readText()) }
        val cases = fixture.getJSONArray("cases")
        for (index in 0 until cases.length()) {
            val sample = cases.getJSONObject(index)
            val raw = sample.getString("character").repeat(sample.getInt("repeat")) + sample.getString("suffix")
            val event = ImEvent(fixture.getString("platform"), fixture.getString("peerKey"), raw,
                Instant.ofEpochSecond(fixture.getLong("epochSecond")))
            val expected = sample.getString("sha256")
            assertEquals(expected, event.dedupeKey(fixture.getString("deviceId")), sample.getString("name"))
            assertEquals(expected, event.copy(text = ImCanonicalText.canonical(raw)).dedupeKey(fixture.getString("deviceId")))
        }
    }

    @Test
    fun shortTextIsUnchangedAndIdempotent() {
        assertEquals("在吗", ImCanonicalText.canonical("在吗"))
        val once = ImCanonicalText.canonical("  hello  ")
        assertEquals(once, ImCanonicalText.canonical(once))
    }

    @Test
    fun exactly2000CodePointsStayUnprefixed() {
        val body = "a".repeat(2000)
        assertEquals(body, ImCanonicalText.canonical(body))
        assertEquals(2000, ImCanonicalText.codePointCount(body))
    }

    @Test
    fun codePoint2001GainsOneTruncatedPrefix() {
        val raw = "b".repeat(2001)
        val canonical = ImCanonicalText.canonical(raw)
        assertEquals("TRUNCATED " + "b".repeat(2000), canonical)
        assertEquals(canonical, ImCanonicalText.canonical(canonical))
        assertFalse(canonical.startsWith("TRUNCATED TRUNCATED "))
    }

    @Test
    fun over4000KeepsFirst4000ThenCanonicalizes() {
        val raw = "c".repeat(4500)
        val canonical = ImCanonicalText.canonical(raw)
        assertEquals("TRUNCATED " + "c".repeat(2000), canonical)
        assertEquals(canonical, ImCanonicalText.canonical(canonical))
    }

    @Test
    fun supplementaryCharacterCountsAsOneAndIsNotSplit() {
        val head = "d".repeat(1999)
        val raw = head + emoji + "z"
        assertEquals(2001, ImCanonicalText.codePointCount(raw))
        val canonical = ImCanonicalText.canonical(raw)
        assertTrue(canonical.endsWith(emoji))
        assertFalse(canonical.contains("\uD83D") && !canonical.contains(emoji))
        assertEquals("TRUNCATED $head$emoji", canonical)
        assertEquals(canonical, ImCanonicalText.canonical(canonical))
    }

    @Test
    fun transportCutDoesNotSplitASupplementaryCharacter() {
        val head = "e".repeat(3999)
        val raw = head + emoji + "tail"
        val cut = ImCanonicalText.takeCodePoints(raw, ImCanonicalText.TRANSPORT_LIMIT)
        assertEquals(head + emoji, cut)
        assertEquals(4000, ImCanonicalText.codePointCount(cut))
        // 4000 code points end on the emoji. The 2000-point canonical cut is
        // before it, so the stored body does not contain a split surrogate.
        val canonical = ImCanonicalText.canonical(raw)
        assertEquals("TRUNCATED " + "e".repeat(2000), canonical)
        assertFalse(canonical.contains(emoji))
        assertEquals(canonical, ImCanonicalText.canonical(canonical))
    }

    @Test
    fun enqueueDedupeAndPayloadShareOneCanonicalValue() {
        val raw = "f".repeat(2001)
        val event = ImEvent("xianyu", "买家", raw, Instant.ofEpochSecond(1_800_000_000))
        val key = event.dedupeKey("device-a")
        val again = event.copy(text = ImCanonicalText.canonical(raw)).dedupeKey("device-a")
        assertEquals(key, again)
        assertEquals(
            "device-a|xianyu|买家|1800000000|${ImCanonicalText.canonical(raw)}",
            ImDedupe.raw("device-a", event),
        )
    }
}
