package com.company.cloudctl.companion.observation

import org.json.JSONObject

/**
 * ui-observation/v1@20260916.1 §2 — frozen Observation structure.
 *
 * `treeDigest = sha256(canonical_tree(nodes))` ([CanonicalTree]); it is
 * carried by the snapshot but ALWAYS recomputed on replay — a pinned digest
 * is an assertion, never an input. `sessionEpoch` aligns with the
 * fleet-identity AuthorizationEnvelope: two frames across different epochs
 * must never be compared for "no progress" (compare sessionEpoch first, §6).
 * Rotation/inset changes within a session do not change node identity fields
 * but do change bounds (§6 banner counter-example).
 */
data class Observation(
    val source: ObservationSource,
    val packageName: String,
    val appVersion: String?,
    val windowId: Int,
    val display: Int,
    val insets: Insets,
    val rotation: Int,
    val capturedAt: String,
    val sessionEpoch: Long,
    val treeDigest: String,
    val nodes: List<ObservedNode>,
) {
    /**
     * Recomputed digest of this observation's node tree. Equal to
     * [treeDigest] for a self-consistent snapshot; comparing the two is the
     * fixture-integrity check used by replay (§2, §8).
     */
    val recomputedTreeDigest: String get() = CanonicalTree.treeDigest(nodes)

    /** True when the pinned [treeDigest] matches the recomputed digest. */
    val digestIsSelfConsistent: Boolean get() = treeDigest == recomputedTreeDigest

    fun toJson(): JSONObject = JSONObject()
        .put("source", source.wire)
        .put("package", packageName)
        .put("appVersion", appVersion ?: JSONObject.NULL)
        .put("windowId", windowId)
        .put("display", display)
        .put("insets", insets.toJson())
        .put("rotation", rotation)
        .put("capturedAt", capturedAt)
        .put("sessionEpoch", sessionEpoch)
        .put("treeDigest", treeDigest)
        .put("nodes", org.json.JSONArray().apply { nodes.forEach { put(it.toJson()) } })

    companion object {
        fun fromJson(json: JSONObject): Observation {
            for (key in listOf(
                "source", "package", "windowId", "display", "insets",
                "rotation", "capturedAt", "sessionEpoch", "nodes",
            )) {
                require(json.has(key)) { "observation missing required field '$key'" }
            }
            val nodes = json.getJSONArray("nodes").let { array ->
                List(array.length()) { ObservedNode.fromJson(array.getJSONObject(it)) }
            }
            return Observation(
                source = ObservationSource.fromWire(json.getString("source")),
                packageName = json.getString("package"),
                appVersion = if (json.isNull("appVersion")) null else json.optString("appVersion", null),
                windowId = json.getInt("windowId"),
                display = json.getInt("display"),
                insets = Insets.fromJson(json.getJSONObject("insets")),
                rotation = json.getInt("rotation"),
                capturedAt = json.getString("capturedAt"),
                sessionEpoch = json.getLong("sessionEpoch"),
                // A freshly captured snapshot may not carry its digest yet
                // (the frozen k11-positive fixture pins expectedTreeDigest at
                // the top level instead) — compute it, never guess it.
                treeDigest = if (json.has("treeDigest")) json.getString("treeDigest")
                else CanonicalTree.treeDigest(nodes),
                nodes = nodes,
            )
        }
    }
}
