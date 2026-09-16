package com.company.cloudctl.companion.observation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * B12 cross-language golden test: the Kotlin [CanonicalTree] port must be
 * byte-for-byte identical with the frozen Python reference
 * (contracts/ui-observation/v1/tools/check_fixtures.py), pinned by the
 * digests frozen into k11-positive-observation.json (§2, §8).
 */
class CanonicalTreeGoldenTest {
    private val fixtureText =
        FixturePaths.classpathUiReplay("contracts/k11-positive-observation.json")

    /** The exact canonical text the Python checker produces for the golden fixture. */
    private val expectedCanonicalTree =
        "bounds=0,345,1080,764\n" +
            "class=android.widget.TextView\n" +
            "clickable=true\n" +
            "contentDesc=\n" +
            "resourceId=title\n" +
            "text=如果历史是一群喵4\n" +
            "bounds=120,1330,480,1400\n" +
            "class=android.widget.Button\n" +
            "clickable=true\n" +
            "contentDesc=\n" +
            "resourceId=btn_cancel\n" +
            "text=取消"

    @Test
    fun fieldOrderIsTheFrozenAlphabeticalOrder() {
        assertEquals(
            listOf("bounds", "class", "clickable", "contentDesc", "resourceId", "text"),
            CanonicalTree.NODE_FIELD_ORDER,
        )
    }

    @Test
    fun canonicalTreeMatchesPythonReferenceByteForByte() {
        val observation = Observation.fromJson(org.json.JSONObject(fixtureText).getJSONObject("observation"))
        assertEquals(expectedCanonicalTree, CanonicalTree.canonicalTree(observation.nodes))
    }

    @Test
    fun treeDigestMatchesContractPinnedValue() {
        val pos = org.json.JSONObject(fixtureText)
        val observation = Observation.fromJson(pos.getJSONObject("observation"))
        assertEquals(
            "bdd20465c6ea8cdb085a82f6d5b9b8060a8925bf414fa0dd7194c39b4071f84d",
            CanonicalTree.treeDigest(observation.nodes),
        )
        assertEquals(pos.getString("expectedTreeDigest"), observation.recomputedTreeDigest)
        assertTrue(observation.digestIsSelfConsistent)
    }

    @Test
    fun nodeDigestMatchesContractPinnedValue() {
        val pos = org.json.JSONObject(fixtureText)
        val proof = pos.getJSONObject("resolution").getJSONObject("identityProof")
        val observation = Observation.fromJson(pos.getJSONObject("observation"))
        val first = observation.nodes.sortedWith(compareBy({ it.depth }, { it.index })).first()
        assertEquals(
            "b23b04af5cda66a1916445ef3b262981775054cb7923cb34068671c1faca919c",
            CanonicalTree.nodeDigest(first),
        )
        assertEquals(proof.getString("nodeDigest"), CanonicalTree.nodeDigest(first))
    }

    @Test
    fun nodeOrderingIsStableRegardlessOfInputOrder() {
        val observation = Observation.fromJson(org.json.JSONObject(fixtureText).getJSONObject("observation"))
        val shuffled = observation.nodes.reversed()
        assertEquals(
            CanonicalTree.canonicalTree(observation.nodes),
            CanonicalTree.canonicalTree(shuffled),
        )
    }

    @Test
    fun digestIsLowercaseHexSha256() {
        assertEquals(64, CanonicalTree.digest("x").length)
        assertTrue(CanonicalTree.digest("x").all { it in "0123456789abcdef" })
    }
}
