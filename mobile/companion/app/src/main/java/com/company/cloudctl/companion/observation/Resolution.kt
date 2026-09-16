package com.company.cloudctl.companion.observation

import org.json.JSONArray
import org.json.JSONObject

/**
 * ui-observation/v1@20260916.1 §3 — frozen candidate resolution results.
 * Exactly two outcomes exist; `Ambiguous` is a NORMAL result, not an error:
 * the task then fail-closes with zero side effects (`LOCATOR_AMBIGUOUS`) or
 * takes a declared fallback (§5). Picking first/center/largest is FORBIDDEN.
 */
sealed interface Resolution {
    data class Resolved(
        val node: ObservedNode,
        val identityProof: IdentityProof,
    ) : Resolution

    data class Ambiguous(
        val candidates: List<ObservedNode>,
        val reason: String,
    ) : Resolution {
        init {
            // §3: Ambiguous means multiple OR zero candidates.
            require(candidates.size != 1) {
                "Ambiguous with exactly one candidate is a contract violation (should be Resolved)"
            }
        }
    }
}

/** §4 IdentityProof — how a Resolved node was proven to be the right one. */
data class IdentityProof(
    val locatorKind: LocatorKind,
    val source: ObservationSource,
    val nodeDigest: String,
    val crossCheckedAgainst: List<ObservationSource>,
    /** Why each anti-misselect-excluded candidate was dropped (P09-13). */
    val excluded: List<ExcludedCandidate>,
    val platformItemId: String? = null,
) {
    init {
        // §4: platformItemId exists ONLY when really readable or operator-entered.
        require(platformItemId?.isNotBlank() ?: true) {
            "platformItemId must be a real id or null — never blank/fabricated"
        }
    }

    fun toJson(): JSONObject = JSONObject()
        .put("locatorKind", locatorKind.wire)
        .put("source", source.wire)
        .put("nodeDigest", nodeDigest)
        .put("crossCheckedAgainst", JSONArray().apply { crossCheckedAgainst.forEach { put(it.wire) } })
        .put("excluded", JSONArray().apply { excluded.forEach { put(it.toJson()) } })
        .apply { platformItemId?.let { put("platformItemId", it) } }

    /** One anti-misselect exclusion with its recorded justification (§3). */
    data class ExcludedCandidate(val why: String, val nodeIndex: Int) {
        fun toJson(): JSONObject = JSONObject().put("why", why).put("nodeIndex", nodeIndex)

        companion object {
            const val WHY_FULL_HEIGHT_WRAPPER = "full-height wrapper"
        }
    }
}

/** §4 locatorKind values. */
enum class LocatorKind(val wire: String) {
    TEXT("text"),
    RESOURCE_ID("resource-id"),
    ANCHOR_POSITION("anchor+position"),
    PLATFORM_ITEM_ID("platform-item-id");

    companion object {
        fun fromWire(value: String): LocatorKind =
            entries.firstOrNull { it.wire == value }
                ?: throw IllegalArgumentException("unknown locatorKind: $value")
    }
}

/** A text-locator query (the only kind B12 replay resolves). */
data class TextQuery(val locatorKind: LocatorKind, val text: String) {
    init {
        require(locatorKind == LocatorKind.TEXT) { "TextQuery requires locatorKind=text" }
        require(text.isNotEmpty()) { "text query must not be empty" }
    }

    fun toJson(): JSONObject = JSONObject().put("locatorKind", locatorKind.wire).put("text", text)
}
