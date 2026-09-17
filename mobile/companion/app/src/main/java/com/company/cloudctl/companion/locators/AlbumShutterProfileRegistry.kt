package com.company.cloudctl.companion.locators

import com.company.cloudctl.companion.media.AlbumShutterPolicy
import com.company.cloudctl.companion.media.ShutterProbe
import java.util.concurrent.ConcurrentHashMap

/**
 * B15X (fleet-first-20260916.1) — in-memory registry of device-profile
 * knowledge about shutter (screenshot) exclusion, feeding the media package's
 * [AlbumShutterPolicy]. B15 semantics: [AlbumShutterPolicy.exclusionVerified]
 * is true ONLY for profiles whose album view was verified to hide screenshots;
 * every unknown or re-flashed profile fails closed (unverified), which makes
 * [com.company.cloudctl.companion.media.AlbumSelection] demand a fresh
 * [ShutterProbe] before planning. Verification never spreads across profiles.
 *
 * Pure state, no clock and no I/O: probe freshness is judged against a
 * caller-supplied nowMs (JVM-testable, same discipline as the B13 gate).
 */
class AlbumShutterProfileRegistry {

    private val policies = ConcurrentHashMap<String, AlbumShutterPolicy>()
    private val probes = ConcurrentHashMap<String, ShutterProbe>()

    /** Registers a policy verdict as-is (keyed by its own profileId). */
    fun register(policy: AlbumShutterPolicy) {
        policies[policy.profileId] = policy
    }

    /**
     * Intake of a device-side probe result: a FRESH probe flips
     * [AlbumShutterPolicy.exclusionVerified] to exactly
     * `!probe.screenshotsVisibleInAlbum`; a STALE or clock-skewed probe
     * (|nowMs - probedAtMs| > [maxProbeAgeMs]) is recorded but grants NO
     * verification — old evidence must not pass for fresh (fail-closed, same
     * shape as B15's own probe validation).
     *
     * @return the resulting policy (also registered under the probe's profile).
     */
    fun recordProbe(
        probe: ShutterProbe,
        nowMs: Long,
        maxProbeAgeMs: Long = DEFAULT_PROBE_MAX_AGE_MS,
    ): AlbumShutterPolicy {
        probes[probe.profileId] = probe
        val fresh = kotlin.math.abs(nowMs - probe.probedAtMs) <= maxProbeAgeMs
        val policy = AlbumShutterPolicy(
            profileId = probe.profileId,
            exclusionVerified = fresh && !probe.screenshotsVisibleInAlbum,
        )
        policies[probe.profileId] = policy
        return policy
    }

    /**
     * The policy for a profile: the registered verdict, or the fail-closed
     * unverified default for an unknown profile — an unknown device version
     * must re-probe, never inherit another profile's verification.
     */
    fun policyFor(profileId: String): AlbumShutterPolicy =
        policies[profileId] ?: AlbumShutterPolicy(profileId = profileId, exclusionVerified = false)

    /** Latest recorded probe for a profile, if any. */
    fun latestProbe(profileId: String): ShutterProbe? = probes[profileId]

    /** Profiles currently carrying a verified exclusion verdict. */
    fun verifiedProfileIds(): Set<String> =
        policies.filterValues { it.exclusionVerified }.keys.toSet()

    /** Test/maintenance helper: drops all state. */
    fun clear() {
        policies.clear()
        probes.clear()
    }

    companion object {
        /** Default probe validity window (24h); re-probe per app version anyway. */
        const val DEFAULT_PROBE_MAX_AGE_MS: Long = 24L * 60L * 60L * 1000L
    }
}
