package com.company.cloudctl.companion.observation

/**
 * ui-observation/v1@20260916.1 §3 — text-locator resolution over an
 * Observation node tree, with the P09-13 anti-misselect precheck.
 *
 * Offline/deterministic by construction: the same Observation + query always
 * yield the same [Resolution] (pinned by replay tests). The two negative
 * shapes frozen by the contract are both handled here:
 *
 * - same-name cards → multiple surviving candidates → [Resolution.Ambiguous]
 *   (auto-selecting first/center/largest is forbidden, §3);
 * - full-height list wrapper matching the text via aggregated
 *   contentDescription → excluded as wrapper, exclusion recorded in
 *   IdentityProof.excluded (§3, §4) — the offline reproduction of the
 *   P09 wrapper-misselection trap.
 */
object TreeTextLocator {
    /**
     * A node matches a text query when its `text` equals the query or its
     * `contentDesc` contains it — list wrappers aggregate child text into
     * contentDescription (see k11-negative-fullheight-wrapper fixture note).
     */
    fun matches(node: ObservedNode, query: TextQuery): Boolean =
        node.text == query.text || node.contentDesc.contains(query.text)

    /**
     * All nodes matching [query], in canonical (depth, index) order — the
     * raw candidate set BEFORE the anti-misselect precheck. Exposed so replay
     * tests can demonstrate the trap existed (e.g. wrapper + real card both
     * matched) instead of merely asserting the filtered outcome.
     */
    fun rawMatches(observation: Observation, query: TextQuery): List<ObservedNode> =
        observation.nodes
            .filter { matches(it, query) }
            .sortedWith(compareBy({ it.depth }, { it.index }))

    /**
     * Resolve [query] against [observation] (§3). Pure function; no I/O, no
     * clock, no first/center/largest tie-breaks.
     */
    fun resolve(observation: Observation, query: TextQuery): Resolution {
        val raw = rawMatches(observation, query)
        val excluded = mutableListOf<IdentityProof.ExcludedCandidate>()
        val survivors = mutableListOf<ObservedNode>()
        for (candidate in raw) {
            val isWrapper = raw.any { other ->
                candidate !== other && candidate.bounds.strictlyContains(other.bounds)
            }
            if (isWrapper) {
                // P09-13: the whole-list wrapper matches text but must never be
                // selected; the exclusion and its reason are part of the proof.
                excluded += IdentityProof.ExcludedCandidate(
                    why = IdentityProof.ExcludedCandidate.WHY_FULL_HEIGHT_WRAPPER,
                    nodeIndex = candidate.index,
                )
            } else {
                survivors += candidate
            }
        }
        return when {
            survivors.size == 1 -> Resolution.Resolved(
                node = survivors[0],
                identityProof = IdentityProof(
                    locatorKind = LocatorKind.TEXT,
                    source = observation.source,
                    nodeDigest = CanonicalTree.nodeDigest(survivors[0]),
                    // Replay is single-source: we never fabricate a second
                    // source here (§1). Cross-source checks are the caller's
                    // job once real second-source evidence exists.
                    crossCheckedAgainst = listOf(observation.source),
                    excluded = excluded,
                ),
            )
            survivors.isEmpty() -> Resolution.Ambiguous(
                candidates = emptyList(),
                reason = "zero candidates for text query '${query.text}'",
            )
            else -> Resolution.Ambiguous(
                candidates = survivors,
                reason = "multiple candidates for text query '${query.text}' " +
                    "(indices=${survivors.map { it.index }}); " +
                    "auto-select first/center/largest is forbidden (§3)",
            )
        }
    }
}
