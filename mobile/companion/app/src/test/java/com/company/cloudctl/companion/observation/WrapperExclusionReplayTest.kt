package com.company.cloudctl.companion.observation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * B12 acceptance case 1 — offline reproduction of the P09 wrapper
 * MISSELECTION trap, replayed from the fixture derived from
 * k11-negative-fullheight-wrapper.json (§3 anti-misselect precheck, §4
 * IdentityProof.excluded). No device is involved: the same fixture always
 * reproduces the same trap and the same exclusion.
 */
class WrapperExclusionReplayTest {

    private fun outcome() = ObservationReplayer.replayLocate(
        FixturePaths.classpathUiReplay("replay/b12-fullheight-wrapper.json"),
    )

    @Test
    fun wrapperTrapExistsBeforeThePrecheck() {
        // The raw candidate set contains BOTH the whole-list wrapper (index 1,
        // matched via aggregated contentDescription) and the real card title
        // (index 4) — i.e. without the P09-13 precheck an implementation that
        // picks the first candidate WOULD tap the wrapper. The trap is real
        // and replayable offline.
        assertEquals(listOf(1, 4), outcome().rawCandidateIndices)
    }

    @Test
    fun wrapperIsExcludedAndRealCardResolved() {
        val resolved = outcome().resolution as Resolution.Resolved
        assertEquals(4, resolved.node.index)
        assertEquals("item_title", resolved.node.resourceId)
        assertEquals("如果历史是一群喵4", resolved.node.text)
    }

    @Test
    fun exclusionReasonIsRecordedInTheIdentityProof() {
        val resolved = outcome().resolution as Resolution.Resolved
        assertEquals(
            listOf(IdentityProof.ExcludedCandidate(why = "full-height wrapper", nodeIndex = 1)),
            resolved.identityProof.excluded,
        )
    }

    @Test
    fun identityProofCarriesNodeDigestAndSingleHonestSource() {
        val resolved = outcome().resolution as Resolution.Resolved
        assertEquals(LocatorKind.TEXT, resolved.identityProof.locatorKind)
        assertEquals(ObservationSource.A11Y_TREE, resolved.identityProof.source)
        assertEquals(CanonicalTree.nodeDigest(resolved.node), resolved.identityProof.nodeDigest)
        // §1/§4: replay is single-source — no fabricated second source in
        // crossCheckedAgainst; real cross-source checks wait for real evidence.
        assertEquals(listOf(ObservationSource.A11Y_TREE), resolved.identityProof.crossCheckedAgainst)
        assertEquals(null, resolved.identityProof.platformItemId)
    }

    @Test
    fun expectationsFromTheDerivedFixtureHold() {
        val fixture = org.json.JSONObject(
            FixturePaths.classpathUiReplay("replay/b12-fullheight-wrapper.json"),
        )
        val expect = fixture.getJSONObject("expect")
        assertEquals("Resolved", expect.getString("result"))
        val resolved = outcome().resolution as Resolution.Resolved
        assertEquals(expect.getInt("selectedIndex"), resolved.node.index)
        assertEquals(
            expect.getJSONArray("excluded").getJSONObject(0).getInt("nodeIndex"),
            resolved.identityProof.excluded.single().nodeIndex,
        )
        // The contract fixture's chosen-card bounds survive derivation.
        val contractWrapper = org.json.JSONObject(
            FixturePaths.repoContractFixture("k11-negative-fullheight-wrapper.json").readText(),
        )
        val contractBounds = contractWrapper.getJSONArray("candidates")
            .let { candidates -> (0 until candidates.length()).map { candidates.getJSONObject(it) } }
            .first { it.getInt("index") == contractWrapper.getJSONObject("expect").getInt("selectedIndex") }
            .getString("bounds")
        assertEquals(contractBounds, resolved.node.bounds.wire)
        // ...and the wrapper is strictly taller than the chosen card (the Python
        // checker asserts the same geometric relation on the contract fixture).
        val wrapperBounds = Bounds.parse("0,345,1080,2337")
        assertTrue(wrapperBounds.height > resolved.node.bounds.height)
        assertTrue(wrapperBounds.strictlyContains(resolved.node.bounds))
    }
}
