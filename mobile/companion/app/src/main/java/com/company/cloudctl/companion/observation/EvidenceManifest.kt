package com.company.cloudctl.companion.observation

import org.json.JSONArray
import org.json.JSONObject

/**
 * B12 evidence manifest — the explicit "missing evidence" list required by
 * the task card: every replay/contract fixture declares where it came from
 * and what real-device evidence is still missing. `capturedXml` MUST be null
 * in every entry: nothing here is a real captured XML dump, and nothing may
 * pretend to be one. Parsing a manifest that claims a capture fails closed.
 */
data class EvidenceManifest(
    val manifest: String,
    val contract: String,
    val task: String,
    val note: String,
    val fixtures: List<Entry>,
) {
    init {
        require(manifest == MANIFEST_ID) { "unknown manifest id: $manifest (expected $MANIFEST_ID)" }
        require(contract == CONTRACT_ID) { "manifest contract mismatch: $contract" }
        require(fixtures.isNotEmpty()) { "evidence manifest must list at least one fixture" }
        for (entry in fixtures) {
            require(entry.capturedXml == null) {
                "fixture ${entry.file} claims capturedXml='${entry.capturedXml}' — " +
                    "B12 has no real captured XML; fabricating capture evidence is forbidden"
            }
            require(entry.missingEvidence.isNotEmpty()) {
                "fixture ${entry.file} must list its missing evidence explicitly"
            }
        }
    }

    data class Entry(
        val file: String,
        val origin: String,
        val capturedXml: String?,
        val missingEvidence: List<String>,
    )

    companion object {
        const val MANIFEST_ID = "ui-replay-evidence/v1"
        const val CONTRACT_ID = "ui-observation/v1@20260916.1"

        fun fromJson(text: String): EvidenceManifest {
            val json = JSONObject(text)
            val fixtures = json.getJSONArray("fixtures").let { array ->
                List(array.length()) { i ->
                    val entry = array.getJSONObject(i)
                    Entry(
                        file = entry.getString("file"),
                        origin = entry.getString("origin"),
                        capturedXml = if (entry.isNull("capturedXml")) null else entry.getString("capturedXml"),
                        missingEvidence = entry.optJSONArray("missingEvidence")?.let(::strings) ?: emptyList(),
                    )
                }
            }
            return EvidenceManifest(
                manifest = json.getString("manifest"),
                contract = json.getString("contract"),
                task = json.getString("task"),
                note = json.getString("note"),
                fixtures = fixtures,
            )
        }

        private fun strings(array: JSONArray): List<String> =
            List(array.length()) { array.getString(it) }
    }
}
