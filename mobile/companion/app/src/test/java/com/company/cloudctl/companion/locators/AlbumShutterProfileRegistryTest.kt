package com.company.cloudctl.companion.locators

import com.company.cloudctl.companion.media.AlbumSelection
import com.company.cloudctl.companion.media.AlbumSelectionFailure
import com.company.cloudctl.companion.media.AlbumSelectionResult
import com.company.cloudctl.companion.media.AlbumShutterPolicy
import com.company.cloudctl.companion.media.SelectionBudget
import com.company.cloudctl.companion.media.ShutterProbe
import com.company.cloudctl.companion.media.StagedMediaAsset
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * B15X — profile knowledge about shutter (screenshot) exclusion: probes grant
 * verification per profile only while fresh; unknown profiles and stale probes
 * fail closed, which the B15 planner enforces as RequiresShutterProbe.
 */
class AlbumShutterProfileRegistryTest {

    private val registry = AlbumShutterProfileRegistry()
    private val nowMs = 1_724_000_000_000L
    private val budget = SelectionBudget(maxPages = 5, maxScrolls = 5, deadlineMs = 100_000L)

    @AfterTest
    fun tearDown() {
        registry.clear()
    }

    @Test
    fun unknownProfileFailsClosedAsUnverified() {
        val policy = registry.policyFor("build-never-probed")
        assertEquals("build-never-probed", policy.profileId)
        assertFalse(policy.exclusionVerified)
        assertNull(registry.latestProbe("build-never-probed"))
    }

    @Test
    fun freshProbeWithScreenshotsHiddenVerifiesTheProfile() {
        val policy = registry.recordProbe(
            ShutterProbe(
                profileId = "oneplus-9r/12.1",
                screenshotsVisibleInAlbum = false,
                probedAtMs = nowMs - 1_000L,
            ),
            nowMs = nowMs,
        )
        assertTrue(policy.exclusionVerified)
        assertTrue("oneplus-9r/12.1" in registry.verifiedProfileIds())
        assertEquals(policy, registry.policyFor("oneplus-9r/12.1"))
    }

    @Test
    fun freshProbeWithScreenshotsVisibleRecordsButDoesNotVerify() {
        // Screenshots visible: nothing to exclude — the profile stays
        // unverified so B15 keeps demanding a live probe alongside the plan.
        val policy = registry.recordProbe(
            ShutterProbe("build-x", screenshotsVisibleInAlbum = true, probedAtMs = nowMs),
            nowMs = nowMs,
        )
        assertFalse(policy.exclusionVerified)
        assertTrue(registry.latestProbe("build-x")!!.screenshotsVisibleInAlbum)
        assertFalse("build-x" in registry.verifiedProfileIds())
    }

    @Test
    fun staleProbeGrantsNoVerification() {
        val olderThanADay = nowMs - AlbumShutterProfileRegistry.DEFAULT_PROBE_MAX_AGE_MS - 1
        val policy = registry.recordProbe(
            ShutterProbe("build-old", screenshotsVisibleInAlbum = false, probedAtMs = olderThanADay),
            nowMs = nowMs,
        )
        assertFalse(policy.exclusionVerified, "old evidence must not pass for fresh")
        // A far-future probe (clock skew) is equally refused.
        val skewed = registry.recordProbe(
            ShutterProbe(
                "build-skew",
                screenshotsVisibleInAlbum = false,
                probedAtMs = nowMs + 10 * AlbumShutterProfileRegistry.DEFAULT_PROBE_MAX_AGE_MS,
            ),
            nowMs = nowMs,
        )
        assertFalse(skewed.exclusionVerified)
    }

    @Test
    fun registeredVerdictsDoNotSpreadAcrossProfiles() {
        registry.register(AlbumShutterPolicy("verified-a", exclusionVerified = true))
        assertTrue("verified-a" in registry.verifiedProfileIds())
        // A different profile on the same device inherits nothing.
        assertFalse(registry.policyFor("verified-b").exclusionVerified)
    }

    @Test
    fun unverifiedRegistryPolicyMakesThePlannerDemandAProbe() {
        // B15 linkage: the fail-closed default flows straight into plan().
        registry.register(AlbumShutterPolicy("oneplus-9r/13.0", exclusionVerified = false))
        val staged = listOf(StagedMediaAsset("asset-0", 0, "asset-0.jpg", "sha-0", 100L, "image/jpeg"))

        val failed = assertIs<AlbumSelectionResult.Failed>(
            AlbumSelection.plan(staged, emptyList(), registry.policyFor("oneplus-9r/13.0"), budget),
        )
        assertIs<AlbumSelectionFailure.RequiresShutterProbe>(failed.failure)
    }
}
