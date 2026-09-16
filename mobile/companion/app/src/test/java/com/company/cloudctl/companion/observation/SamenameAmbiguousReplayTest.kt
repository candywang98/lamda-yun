package com.company.cloudctl.companion.observation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * K11 consumer obligation — the samename-ambiguous negative must be consumed
 * by B12: two same-title candidates resolve to Ambiguous, never an automatic
 * selection (first/center/largest are forbidden, §3). LOCATOR_AMBIGUOUS is
 * the terminal; the replay never picks a winner.
 */
class SamenameAmbiguousReplayTest {

    private fun outcome() = ObservationReplayer.replayLocate(
        FixturePaths.classpathUiReplay("replay/b12-samename-ambiguous.json"),
    )

    @Test
    fun twoSameTitleCardsResolveAmbiguous() {
        val ambiguous = outcome().resolution as Resolution.Ambiguous
        assertEquals(listOf(4, 9), ambiguous.candidates.map { it.index })
        // §3: Ambiguous is a normal result carrying the reason.
        assertTrue("multiple candidates" in ambiguous.reason)
        assertTrue("forbidden" in ambiguous.reason)
    }

    @Test
    fun noCandidateIsEverSelectedOrReordered() {
        val fixture = org.json.JSONObject(
            FixturePaths.classpathUiReplay("replay/b12-samename-ambiguous.json"),
        )
        val expect = fixture.getJSONObject("expect")
        assertEquals("Ambiguous", expect.getString("result"))
        val forbidden = expect.getJSONArray("forbidden")
            .let { array -> List(array.length()) { array.getString(it) } }
        assertEquals(listOf("select-first", "select-center", "select-largest", "auto-retry"), forbidden)
        // Candidates keep the tree's canonical order — no center/largest
        // sorting ever happened on the way out.
        val ambiguous = outcome().resolution as Resolution.Ambiguous
        assertEquals(
            ambiguous.candidates.sortedWith(compareBy({ it.depth }, { it.index })).map { it.index },
            ambiguous.candidates.map { it.index },
        )
        // And the raw pre-check set equals the surviving set: nothing was
        // dropped (neither card is a wrapper — bounds are disjoint).
        assertEquals(outcome().rawCandidateIndices, ambiguous.candidates.map { it.index })
    }

    @Test
    fun zeroCandidatesIsAlsoAmbiguousNeverInvented() {
        val fixture = org.json.JSONObject(
            FixturePaths.classpathUiReplay("replay/b12-samename-ambiguous.json"),
        )
        val observation = Observation.fromJson(
            fixture.getJSONObject("observation").put("nodes", org.json.JSONArray()),
        )
        val ambiguous = TreeTextLocator.resolve(observation, TextQuery(LocatorKind.TEXT, "不存在的商品")) as Resolution.Ambiguous
        assertTrue(ambiguous.candidates.isEmpty())
        assertTrue("zero candidates" in ambiguous.reason)
    }

    @Test
    fun ambiguousWithExactlyOneCandidateIsRejectedByContract() {
        // A resolution outcome carrying exactly one candidate while claiming
        // Ambiguous would be a contract violation (§3) — the model refuses it.
        val node = ObservedNode(
            depth = 0, index = 0, className = "android.widget.TextView", resourceId = "",
            text = "x", contentDesc = "", bounds = Bounds.parse("0,0,1,1"), clickable = false,
        )
        val error = kotlin.test.assertFailsWith<IllegalArgumentException> {
            Resolution.Ambiguous(candidates = listOf(node), reason = "must not exist")
        }
        assertTrue("contract violation" in error.message.orEmpty())
    }
}
