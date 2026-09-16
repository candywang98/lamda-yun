package com.company.cloudctl.companion.observation

import org.json.JSONObject

/**
 * ui-observation/v1@20260916.1 §6 — frozen polling budget.
 *
 * Consecutive [noProgressLimit] frames with the same business digest (same
 * sessionEpoch) exit NO_PROGRESS with zero side effects; budget exhaustion
 * fail-closes with LOCATOR_TIMEOUT. No dangerous strategy is auto-tried.
 * [minIntervalMs] is a live-pacing parameter and is intentionally unused by
 * the offline replayer (frames arrive as fast as they are fed).
 */
data class PollingBudget(
    val maxAttempts: Int,
    val minIntervalMs: Long,
    val noProgressLimit: Int,
) {
    init {
        require(maxAttempts > 0 && noProgressLimit > 0 && minIntervalMs >= 0)
    }

    companion object {
        fun fromJson(json: JSONObject): PollingBudget = PollingBudget(
            maxAttempts = json.getInt("maxAttempts"),
            minIntervalMs = json.getLong("minIntervalMs"),
            noProgressLimit = json.getInt("noProgressLimit"),
        )
    }
}

/** §6 terminal outcomes of a monitored poll loop. */
enum class PollTerminal { CONTINUE, NO_PROGRESS, LOCATOR_TIMEOUT }

/**
 * §6 no-progress monitor — banner-displacement aware.
 *
 * Progress is judged on the BUSINESS-node subset digest (banner/keyboard
 * layers excluded, uniform displacement normalized away), never on the whole
 * tree digest: a banner appearing shifts every bound and changes treeDigest
 * without being progress (frozen counter-example fixture). Frames from a
 * different sessionEpoch are never compared (counter resets). The monitor
 * performs zero side effects by construction; [sideEffectsPerformed] exists
 * so callers/tests can assert that invariant against their own plumbing.
 */
class NoProgressMonitor(private val budget: PollingBudget) {
    var attempts: Int = 0
        private set
    var sideEffectsPerformed: Int = 0
        private set

    private var consecutiveNoProgress = 0
    private var lastBusinessDigest: String? = null
    private var lastSessionEpoch: Long? = null

    /**
     * Caller declares that a side effect has happened somewhere in the loop.
     * After the first side effect the monitor refuses further observations:
     * no-progress exit is a ZERO-side-effect exit and must be decided before
     * anything irreversible runs (§5/§6).
     */
    fun markSideEffect() {
        sideEffectsPerformed += 1
    }

    /** Feed one observed frame; returns the terminal judgement for the loop. */
    fun observe(businessDigest: String, sessionEpoch: Long): PollTerminal {
        check(sideEffectsPerformed == 0) { "no-progress monitor must run before any side effect" }
        attempts += 1
        if (attempts > budget.maxAttempts) return PollTerminal.LOCATOR_TIMEOUT
        val previousDigest = lastBusinessDigest
        val previousEpoch = lastSessionEpoch
        lastBusinessDigest = businessDigest
        lastSessionEpoch = sessionEpoch
        // §2/§6: cross-epoch frames are incomparable — reset instead of counting.
        if (previousDigest == null || previousEpoch != sessionEpoch) {
            consecutiveNoProgress = 1
        } else if (businessDigest == previousDigest) {
            consecutiveNoProgress += 1
        } else {
            consecutiveNoProgress = 1
        }
        return if (consecutiveNoProgress >= budget.noProgressLimit) {
            PollTerminal.NO_PROGRESS
        } else {
            PollTerminal.CONTINUE
        }
    }
}

/**
 * B12 replay engine — fixture in, deterministic outcome out.
 *
 * Both replay shapes are pure functions of the fixture text (no clock, no
 * randomness, no device), which is what "same fixture, same result" pins:
 * replaying a fixture twice yields equal outcomes (data classes). The
 * engine NEVER trusts a pinned digest as an input: digests are recomputed
 * and compared, so a tampered fixture fails loudly instead of replaying.
 */
object ObservationReplayer {
    const val CONTRACT_ID = "ui-observation/v1@20260916.1"

    /** Result of replaying a locate fixture (samename / wrapper cases). */
    data class LocateOutcome(
        val caseName: String,
        val observation: Observation,
        val query: TextQuery,
        val recomputedTreeDigest: String,
        val pinnedDigestMatches: Boolean,
        val resolution: Resolution,
        /** Raw candidates before the anti-misselect precheck (trap evidence). */
        val rawCandidateIndices: List<Int>,
    )

    /** Result of replaying a poll fixture (banner-displacement case). */
    data class PollOutcome(
        val caseName: String,
        val terminal: PollTerminal,
        val attemptsUsed: Int,
        val frameTreeDigests: List<String>,
        val frameBusinessDigests: List<String>,
        val sideEffects: Int,
    )

    /** One observed frame of a poll replay. */
    data class ReplayFrame(
        val n: Int,
        val banner: String,
        val displacementY: Int,
        val excludedLayerResourceIds: Set<String>,
        val observation: Observation,
    )

    /**
     * Business-subset digest (§6): canonical digest over nodes minus the
     * excluded banner/keyboard layers, with the frame's uniform vertical
     * displacement normalized away. Two frames that differ only by banner
     * presence and the resulting shift produce the SAME business digest.
     */
    fun businessDigest(
        observation: Observation,
        excludedLayerResourceIds: Set<String>,
        displacementY: Int,
    ): String {
        val businessNodes = observation.nodes
            .filter { it.resourceId !in excludedLayerResourceIds }
            .map { node -> node.copy(bounds = node.bounds.translated(-displacementY)) }
        return CanonicalTree.treeDigest(businessNodes)
    }

    /** Replay a locate fixture (JSON text) to its resolution outcome. */
    fun replayLocate(fixtureText: String): LocateOutcome {
        val fixture = JSONObject(fixtureText)
        requireContract(fixture)
        val observation = Observation.fromJson(fixture.getJSONObject("observation"))
        val queryJson = fixture.getJSONObject("query")
        val query = TextQuery(
            locatorKind = LocatorKind.fromWire(queryJson.getString("locatorKind")),
            text = queryJson.getString("text"),
        )
        val raw = TreeTextLocator.rawMatches(observation, query)
        return LocateOutcome(
            caseName = fixture.getString("case"),
            observation = observation,
            query = query,
            recomputedTreeDigest = observation.recomputedTreeDigest,
            pinnedDigestMatches = observation.digestIsSelfConsistent,
            resolution = TreeTextLocator.resolve(observation, query),
            rawCandidateIndices = raw.map { it.index },
        )
    }

    /**
     * Replay a poll fixture: frames are fed in the fixture's declared order
     * (`feed`), e.g. `[1,2,2]` = banner appears on frame 2 and persists.
     * Terminal NO_PROGRESS / LOCATOR_TIMEOUT per §6, zero side effects.
     */
    fun replayPoll(fixtureText: String): PollOutcome {
        val fixture = JSONObject(fixtureText)
        requireContract(fixture)
        val expect = fixture.getJSONObject("expect")
        val budget = PollingBudget.fromJson(expect.getJSONObject("pollingBudget"))
        val frames = fixture.getJSONArray("frames").let { array ->
            List(array.length()) { i ->
                val frame = array.getJSONObject(i)
                ReplayFrame(
                    n = frame.getInt("n"),
                    banner = frame.getString("banner"),
                    displacementY = frame.getInt("displacementY"),
                    excludedLayerResourceIds = frame.optJSONArray("excludedLayerResourceIds")
                        ?.let { ids -> List(ids.length()) { ids.getString(it) } }?.toSet()
                        ?: emptySet(),
                    observation = Observation.fromJson(frame.getJSONObject("observation")),
                )
            }
        }
        val byNumber = frames.associateBy { it.n }
        val feed = expect.getJSONArray("feed").let { array -> List(array.length()) { array.getInt(it) } }
        val monitor = NoProgressMonitor(budget)
        val treeDigests = mutableListOf<String>()
        val businessDigests = mutableListOf<String>()
        var terminal = PollTerminal.CONTINUE
        for (number in feed) {
            val frame = requireNotNull(byNumber[number]) { "feed references unknown frame n=$number" }
            val business = businessDigest(frame.observation, frame.excludedLayerResourceIds, frame.displacementY)
            treeDigests += frame.observation.recomputedTreeDigest
            businessDigests += business
            terminal = monitor.observe(business, frame.observation.sessionEpoch)
            if (terminal != PollTerminal.CONTINUE) break
        }
        return PollOutcome(
            caseName = fixture.getString("case"),
            terminal = terminal,
            attemptsUsed = monitor.attempts,
            frameTreeDigests = treeDigests,
            frameBusinessDigests = businessDigests,
            sideEffects = monitor.sideEffectsPerformed,
        )
    }

    private fun requireContract(fixture: JSONObject) {
        val contract = fixture.getString("contract")
        require(contract == CONTRACT_ID) {
            "fixture contract '$contract' does not match replay engine '$CONTRACT_ID'"
        }
    }
}
