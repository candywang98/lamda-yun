package com.company.cloudctl.companion.observation

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * Observation parsing fail-closes on anything the frozen contract does not
 * define, and the §1 same-source discipline is pinned: digest equality is
 * only meaningful within one source, and nothing in this package may merge
 * sources or fabricate cross-source evidence.
 */
class ObservationJsonTest {

    private fun goldenObservationJson(): JSONObject = JSONObject(
        FixturePaths.classpathUiReplay("contracts/k11-positive-observation.json"),
    ).getJSONObject("observation")

    @Test
    fun goldenObservationParsesWithAllFrozenFields() {
        val observation = Observation.fromJson(goldenObservationJson())
        assertEquals(ObservationSource.A11Y_TREE, observation.source)
        assertEquals("com.taobao.idlefish", observation.packageName)
        assertEquals("7.10.20", observation.appVersion)
        assertEquals(123, observation.windowId)
        assertEquals(Insets(0, 132, 0, 96), observation.insets)
        assertEquals(0, observation.rotation)
        assertEquals(5L, observation.sessionEpoch)
        assertEquals(2, observation.nodes.size)
        assertTrue(observation.digestIsSelfConsistent)
    }

    @Test
    fun missingSourceLabelIsRejected() {
        val json = goldenObservationJson().apply { remove("source") }
        val error = assertFailsWith<IllegalArgumentException> { Observation.fromJson(json) }
        assertTrue("source" in error.message.orEmpty())
    }

    @Test
    fun unknownSourceLabelIsRejectedWithTheFrozenSet() {
        val json = goldenObservationJson().put("source", "wired_magic")
        val error = assertFailsWith<IllegalArgumentException> { Observation.fromJson(json) }
        assertTrue("a11y_tree" in error.message.orEmpty())
        assertTrue("screenshot" in error.message.orEmpty())
    }

    @Test
    fun nodeMissingAnIdentityFieldIsRejected() {
        val json = goldenObservationJson()
        json.getJSONArray("nodes").getJSONObject(0).remove("bounds")
        val error = assertFailsWith<IllegalArgumentException> { Observation.fromJson(json) }
        assertTrue("bounds" in error.message.orEmpty())
    }

    @Test
    fun nonBooleanClickableIsRejected() {
        val json = goldenObservationJson()
        json.getJSONArray("nodes").getJSONObject(0).put("clickable", "true")
        val error = assertFailsWith<IllegalArgumentException> { Observation.fromJson(json) }
        assertTrue("clickable" in error.message.orEmpty())
    }

    @Test
    fun malformedBoundsAreRejected() {
        val error = assertFailsWith<IllegalArgumentException> {
            Bounds.parse("0,0,1080")
        }
        assertTrue("left,top,right,bottom" in error.message.orEmpty())
        assertFailsWith<IllegalArgumentException> { Bounds.parse("a,b,c,d") }
    }

    @Test
    fun digestEqualityAloneNeverProvesCrossSourceEquivalence() {
        // §1: identical nodes captured under two different sources produce the
        // same canonical digest — and that is NOT an equivalence proof across
        // sources. This package therefore never emits it as one: the locator's
        // IdentityProof lists only its own source until real second-source
        // evidence exists (§4), and no API merges sources into one fixture.
        val a11y = Observation.fromJson(goldenObservationJson())
        val dump = JSONObject(goldenObservationJson().toString()).put("source", "uiautomator_dump")
        val uiautomator = Observation.fromJson(dump)
        assertEquals(a11y.recomputedTreeDigest, uiautomator.recomputedTreeDigest)
        assertTrue(a11y.source != uiautomator.source)
        val proof = (TreeTextLocator.resolve(a11y, TextQuery(LocatorKind.TEXT, "取消")) as Resolution.Resolved)
            .identityProof
        assertEquals(listOf(ObservationSource.A11Y_TREE), proof.crossCheckedAgainst)
    }

    @Test
    fun blankPlatformItemIdIsRefused() {
        val error = assertFailsWith<IllegalArgumentException> {
            IdentityProof(
                locatorKind = LocatorKind.PLATFORM_ITEM_ID,
                source = ObservationSource.A11Y_TREE,
                nodeDigest = "d".repeat(64),
                crossCheckedAgainst = listOf(ObservationSource.A11Y_TREE),
                excluded = emptyList(),
                platformItemId = "  ",
            )
        }
        assertTrue("platformItemId" in error.message.orEmpty())
    }

    @Test
    fun textQueryRejectsEmptyTextAndForeignKinds() {
        assertFailsWith<IllegalArgumentException> { TextQuery(LocatorKind.TEXT, "") }
        assertFailsWith<IllegalArgumentException> {
            TextQuery(LocatorKind.RESOURCE_ID, "btn_cancel")
        }
    }

    @Test
    fun pollingBudgetRejectsNonPositiveLimits() {
        assertFailsWith<IllegalArgumentException> { PollingBudget(0, 500, 3) }
        assertFailsWith<IllegalArgumentException> { PollingBudget(20, 500, 0) }
        assertFailsWith<IllegalArgumentException> { PollingBudget(20, -1, 3) }
    }
}
