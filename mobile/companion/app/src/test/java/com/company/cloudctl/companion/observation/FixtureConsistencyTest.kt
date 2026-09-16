package com.company.cloudctl.companion.observation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Same-source fixture consistency (§1) + B12 acceptance case 2 (explicit
 * missing-evidence list, no fabricated captured XML).
 *
 * Three copies of every fixture must stay byte-identical:
 *  1. the frozen contract original  contracts/ui-observation/v1/fixtures/
 *  2. the repo replay copy          tests/fixtures/ui-replay/contracts|replay/
 *  3. the unit-test classpath mirror src/test/resources/ui-replay/
 * Drift anywhere fails here, so nobody can edit one copy silently.
 */
class FixtureConsistencyTest {

    @Test
    fun contractFixtureCopiesAreByteIdenticalEverywhere() {
        for (name in FixturePaths.contractFixtureNames) {
            val original = FixturePaths.repoContractFixture(name).readBytes()
            val replayCopy = FixturePaths.repoUiReplay("contracts/$name").readBytes()
            val classpathCopy = FixturePaths::class.java.classLoader
                .getResourceAsStream("ui-replay/contracts/$name")!!.readBytes()
            assertTrue(original.contentEquals(replayCopy), "repo ui-replay copy drifted: $name")
            assertTrue(original.contentEquals(classpathCopy), "classpath mirror drifted: $name")
            val json = org.json.JSONObject(String(original))
            assertEquals(FixturePaths.CONTRACT_ID, json.getString("contract"), name)
        }
    }

    @Test
    fun replayFixturesAreByteIdenticalBetweenRepoRootAndClasspath() {
        for (name in FixturePaths.replayFixtureNames) {
            val repo = FixturePaths.repoUiReplay("replay/$name").readBytes()
            val classpath = FixturePaths::class.java.classLoader
                .getResourceAsStream("ui-replay/replay/$name")!!.readBytes()
            assertTrue(repo.contentEquals(classpath), "replay fixture mirror drifted: $name")
            assertEquals(FixturePaths.CONTRACT_ID, org.json.JSONObject(String(repo)).getString("contract"))
        }
    }

    @Test
    fun frozenContractOriginalsAreReachableOnTheTestClasspath() {
        // build.gradle.kts maps the repo contracts/ dir onto the unit-test
        // classpath; the frozen originals are therefore directly consumable
        // by tests without any copy — and must equal the repo files.
        for (name in FixturePaths.contractFixtureNames) {
            val onClasspath = FixturePaths.classpathText("ui-observation/v1/fixtures/$name")
            assertEquals(
                FixturePaths.repoContractFixture(name).readText(),
                onClasspath,
                "contracts srcDir classpath wiring broken for $name",
            )
        }
    }

    @Test
    fun everyDerivedFixtureDeclaresItsContractAncestor() {
        val ancestors = listOf(
            "b12-samename-ambiguous.json" to "k11-negative-samename-ambiguous.json",
            "b12-fullheight-wrapper.json" to "k11-negative-fullheight-wrapper.json",
            "b12-banner-displacement.json" to "k11-negative-banner-displacement.json",
        )
        for ((name, ancestor) in ancestors) {
            val fixture = org.json.JSONObject(FixturePaths.repoUiReplay("replay/$name").readText())
            assertEquals(ancestor, fixture.getString("derivedFrom"))
            assertTrue(FixturePaths.repoContractFixture(ancestor).isFile)
        }
    }

    @Test
    fun evidenceManifestListsMissingEvidenceAndFabricatesNothing() {
        val manifest = EvidenceManifest.fromJson(
            FixturePaths.classpathUiReplay("replay/evidence-manifest.json"),
        )
        assertEquals("B12", manifest.task)
        assertEquals(FixturePaths.CONTRACT_ID, manifest.contract)
        // Every fixture directory entry is covered — nothing hides from the list.
        val listed = manifest.fixtures.map { it.file }.toSet()
        assertEquals(
            (FixturePaths.contractFixtureNames.map { "contracts/$it" } +
                FixturePaths.replayFixtureNames.map { "replay/$it" }).toSet(),
            listed,
        )
        for (entry in manifest.fixtures) {
            assertEquals(null, entry.capturedXml, "${entry.file} must not claim a captured XML")
            assertTrue(entry.missingEvidence.isNotEmpty(), "${entry.file} must list missing evidence")
            assertTrue(FixturePaths.repoUiReplay(entry.file).isFile, "manifest references missing file ${entry.file}")
        }
    }
}
