package com.company.cloudctl.companion.automation.recipes

import com.company.cloudctl.companion.automation.CanonicalJson
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest

/**
 * B16 static recipe validation — the Kotlin mirror of
 * scripts/validate-recipe-contract.py. Pure, offline, fixture-free: it rejects
 * forbidden execution fields (eval/shell/js — signature is provenance, not a
 * sandbox), per-action parameter cap violations, non-terminating loops and
 * irreversible submit actions inside loop bodies BEFORE any bytes reach the
 * engine. Bounded cycles (finite repeat/retry with a reachable terminal) pass.
 */
object RecipeStaticValidator {

    data class Violation(val code: String, val detail: String) {
        override fun toString(): String = "$code: $detail"
    }

    private val TERMINALS = setOf("SUCCEEDED", "FAILED", "WAITING_USER")

    /** @return violations; empty means the package is statically acceptable. */
    fun validate(encoded: String, strictSignature: Boolean = true): List<Violation> {
        val violations = mutableListOf<Violation>()
        val root = try {
            JSONObject(encoded)
        } catch (error: Exception) {
            return listOf(Violation("RECIPE_MALFORMED", error.message ?: "not parseable JSON"))
        }
        if (root.optString("apiVersion") != RecipeContract.PROTOCOL) {
            violations += Violation("UNSUPPORTED_PROTOCOL", "apiVersion must be ${RecipeContract.PROTOCOL}")
        }
        if (root.optString("kind") != RecipeContract.KIND) {
            violations += Violation("UNSUPPORTED_RECIPE", "kind must be ${RecipeContract.KIND}")
        }
        violations += forbiddenFieldViolations(root)
        val manifest = root.optJSONObject("manifest")
        val graph = root.optJSONObject("graph")
        if (manifest == null || graph == null) {
            violations += Violation("RECIPE_MALFORMED", "manifest and graph objects are required")
            return violations
        }
        violations += manifestViolations(manifest, root, strictSignature)
        violations += graphViolations(graph)
        violations += loopPolicyViolations(graph)
        return violations
    }

    fun requireValid(encoded: String) {
        val violations = validate(encoded)
        require(violations.isEmpty()) { violations.joinToString("; ") }
    }

    // ---- forbidden fields: no eval / shell / js / arbitrary code, anywhere ----

    private fun forbiddenFieldViolations(root: JSONObject): List<Violation> {
        val violations = mutableListOf<Violation>()
        fun walk(value: Any?, path: String) {
            when (value) {
                is JSONObject -> value.keys().asSequence().forEach { key ->
                    val lowered = key.lowercase()
                    val hit = RecipeContract.FORBIDDEN_FIELD_FRAGMENTS.firstOrNull { it in lowered }
                    if (hit != null) violations += Violation("FORBIDDEN_FIELD", "'$key' at $path contains '$hit'")
                    walk(value.get(key), "$path.$key")
                }
                is JSONArray -> for (index in 0 until value.length()) walk(value.get(index), "$path[$index]")
                else -> Unit
            }
        }
        walk(root, "$")
        return violations
    }

    private fun manifestViolations(manifest: JSONObject, root: JSONObject, strictSignature: Boolean): List<Violation> {
        val violations = mutableListOf<Violation>()
        val declared = manifest.optString("hash")
        if (!Regex("^[a-f0-9]{64}$").matches(declared)) {
            violations += Violation("HASH_MALFORMED", "manifest.hash must be lowercase sha256 hex")
        } else {
            val payload = CanonicalJson.recipeHashPayload(root)
            val computed = sha256Hex(payload)
            if (declared != computed) {
                violations += Violation("HASH_MISMATCH", "manifest.hash $declared != canonical $computed")
            }
        }
        val minEngine = manifest.optInt("minEngineVersion", -1)
        if (minEngine < 1) violations += Violation("ENGINE_VERSION_INVALID", "minEngineVersion must be >= 1")
        val types = manifest.optJSONArray("commandTypes")
        if (types == null || types.length() == 0) {
            violations += Violation("COMMAND_TYPES_EMPTY", "commandTypes must be a non-empty array")
        }
        val id = manifest.optString("id")
        if (!RecipeContract.STATE_ID_PATTERN.matches(id)) {
            violations += Violation("RECIPE_ID_INVALID", "manifest.id '$id' violates the id charset/length")
        }
        val signature = root.optJSONObject("signature")
        if (strictSignature) {
            if (signature == null) {
                violations += Violation("SIGNATURE_MISSING", "recipe packages must carry a signature block (provenance)")
            } else if (signature.optString("algorithm") != "Ed25519") {
                violations += Violation("SIGNATURE_ALGORITHM", "signature.algorithm must be Ed25519")
            }
        }
        return violations
    }

    private fun graphViolations(graph: JSONObject): List<Violation> {
        val violations = mutableListOf<Violation>()
        val iterations = graph.optInt("maxIterations", -1)
        if (iterations !in RecipeContract.GRAPH_MAX_ITERATIONS_RANGE) {
            violations += Violation(
                "GRAPH_MAX_ITERATIONS_OUT_OF_RANGE",
                "maxIterations $iterations outside ${RecipeContract.GRAPH_MAX_ITERATIONS_RANGE}",
            )
        }
        val duration = graph.optLong("maxDurationMs", -1)
        if (duration !in RecipeContract.GRAPH_MAX_DURATION_MS_RANGE) {
            violations += Violation(
                "GRAPH_MAX_DURATION_OUT_OF_RANGE",
                "maxDurationMs $duration outside ${RecipeContract.GRAPH_MAX_DURATION_MS_RANGE}",
            )
        }
        val statesJson = graph.optJSONArray("states")
        if (statesJson == null || statesJson.length() == 0) {
            violations += Violation("STATES_EMPTY", "graph.states must be a non-empty array")
            return violations
        }
        if (statesJson.length() > RecipeContract.MAX_STATES) {
            violations += Violation("STATES_OVER_CAP", "state count ${statesJson.length()} > ${RecipeContract.MAX_STATES}")
        }
        val ids = mutableSetOf<String>()
        val states = mutableMapOf<String, JSONObject>()
        for (index in 0 until statesJson.length()) {
            val state = statesJson.getJSONObject(index)
            val stateId = state.optString("stateId")
            if (!RecipeContract.STATE_ID_PATTERN.matches(stateId)) {
                violations += Violation("STATE_ID_INVALID", "stateId '$stateId' violates charset/length")
            }
            if (!ids.add(stateId)) violations += Violation("STATE_ID_DUPLICATE", "stateId '$stateId' appears twice")
            states[stateId] = state
            violations += stateViolations(state, duration)
        }
        val start = graph.optString("startStateId")
        if (start !in states) violations += Violation("START_STATE_MISSING", "startStateId '$start' is not a state")
        // Edge targets must resolve to states or terminal outcomes.
        for ((stateId, state) in states) {
            for (edge in listOf("onSuccess", "onFailure")) {
                if (!state.has(edge) || state.isNull(edge)) continue
                val target = state.optString(edge)
                if (target.isBlank()) continue
                if (target !in states && target !in TERMINALS) {
                    violations += Violation("EDGE_TARGET_UNKNOWN", "$stateId.$edge -> '$target' resolves to nothing")
                }
            }
        }
        val commitId = graph.optString("commitActionId").takeIf { !graph.isNull("commitActionId") && it.isNotBlank() }
        if (commitId != null) {
            val commit = states[commitId]
            if (commit == null) {
                violations += Violation("COMMIT_STATE_MISSING", "commitActionId '$commitId' is not a state")
            } else {
                if (commit.optString("action") != "tap" || commit.optString("locatorRef").isBlank() ||
                    commit.optString("postcondition").isBlank() ||
                    commit.optString("onSuccess") != "SUCCEEDED" || !commit.isNull("onFailure")
                ) {
                    violations += Violation("COMMIT_SHAPE_INVALID", "commit state must be one tap with a distinct postcondition")
                }
                if (hasBoundedFields(commit)) {
                    violations += Violation("COMMIT_NOT_RETRYABLE", "the irreversible commit state must not carry retry budgets")
                }
            }
        }
        return violations
    }

    private fun hasBoundedFields(state: JSONObject): Boolean =
        (state.has("maxAttempts") && !state.isNull("maxAttempts")) ||
            (state.has("noProgressBudget") && !state.isNull("noProgressBudget")) ||
            (state.has("deadlineMs") && !state.isNull("deadlineMs")) ||
            (state.has("onExhausted") && !state.isNull("onExhausted"))

    private fun stateViolations(state: JSONObject, graphMaxDurationMs: Long): List<Violation> {
        val violations = mutableListOf<Violation>()
        val stateId = state.optString("stateId")
        val action = state.optString("action")
        if (action !in RecipeContract.ACTION_WHITELIST) {
            violations += Violation("ACTION_NOT_WHITELISTED", "state '$stateId' action '$action' is not on the whitelist")
        }
        val valueRef = state.optString("valueRef").takeIf { !state.isNull("valueRef") && it.isNotBlank() }
        if (valueRef != null && !RecipeContract.VALUE_REF_PATTERN.matches(valueRef)) {
            violations += Violation("VALUE_REF_INVALID", "state '$stateId' valueRef '$valueRef' violates the parameter-key shape")
        }
        if (hasBoundedFields(state)) {
            if (action !in setOf("wait", "tap", "media")) {
                violations += Violation("BOUNDS_ON_NON_RETRYABLE", "state '$stateId' carries retry budgets but action '$action' has no retry loop")
            }
            state.optInt("maxAttempts", -1).takeIf { it != -1 }?.let {
                if (it < 1 || it > RecipeContract.MAX_WAIT_ATTEMPTS) {
                    violations += Violation("MAX_ATTEMPTS_OUT_OF_RANGE", "state '$stateId' maxAttempts $it outside 1..${RecipeContract.MAX_WAIT_ATTEMPTS}")
                }
            }
            state.optInt("noProgressBudget", -1).takeIf { it != -1 }?.let {
                if (it < 1 || it > RecipeContract.MAX_NO_PROGRESS_POLLS) {
                    violations += Violation("NO_PROGRESS_OUT_OF_RANGE", "state '$stateId' noProgressBudget $it outside 1..${RecipeContract.MAX_NO_PROGRESS_POLLS}")
                }
            }
            state.optLong("deadlineMs", -1L).takeIf { it != -1L }?.let {
                if (it < RecipeContract.MIN_STATE_DEADLINE_MS || it > graphMaxDurationMs) {
                    violations += Violation("STATE_DEADLINE_OUT_OF_RANGE", "state '$stateId' deadlineMs $it outside the graph budget")
                }
            }
            state.optString("onExhausted").takeIf { it.isNotBlank() }?.let {
                if (it !in RecipeContract.ON_EXHAUSTED_VALUES) {
                    violations += Violation("ON_EXHAUSTED_INVALID", "state '$stateId' onExhausted '$it' must be FAIL or WAITING_USER")
                }
            }
        }
        return violations
    }

    // ---- loop policy: bounded cycles pass; dead cycles and irreversible-in-cycle do not ----

    private fun loopPolicyViolations(graph: JSONObject): List<Violation> {
        val violations = mutableListOf<Violation>()
        val statesJson = graph.optJSONArray("states") ?: return violations
        val states = mutableMapOf<String, JSONObject>()
        val edges = mutableMapOf<String, MutableSet<String>>()
        for (index in 0 until statesJson.length()) {
            val state = statesJson.getJSONObject(index)
            val id = state.optString("stateId")
            states[id] = state
            edges.getOrPut(id) { mutableSetOf() }
            for (edge in listOf("onSuccess", "onFailure")) {
                val target = state.optString(edge).takeIf { !state.isNull(edge) && it.isNotBlank() } ?: continue
                edges.getOrPut(id) { mutableSetOf() } += target
            }
        }
        // (a) every state must be able to reach a terminal outcome.
        val reachTerminal = mutableMapOf<String, Boolean>()
        for (id in states.keys) canReachTerminal(id, edges, reachTerminal, mutableSetOf())
        for (id in states.keys) {
            if (reachTerminal[id] != true) {
                violations += Violation("LOOP_NON_TERMINATING", "state '$id' can never reach a terminal outcome")
            }
        }
        // (b) irreversible submit actions may not sit on a cycle.
        val commitId = graph.optString("commitActionId").takeIf { !graph.isNull("commitActionId") && it.isNotBlank() }
        for (id in states.keys) {
            if (!onCycle(id, edges)) continue
            val state = states.getValue(id)
            val locator = state.optString("locatorRef").takeIf { !state.isNull("locatorRef") && it.isNotBlank() }
            if (locator != null && locator in RecipeContract.IRREVERSIBLE_LOCATORS) {
                violations += Violation("IRREVERSIBLE_IN_LOOP", "state '$id' taps irreversible locator '$locator' inside a retry loop")
            }
            if (id == commitId) {
                violations += Violation("IRREVERSIBLE_IN_LOOP", "commit state '$id' sits inside a retry loop; commits are single-shot")
            }
        }
        return violations
    }

    private fun canReachTerminal(
        id: String,
        edges: Map<String, Set<String>>,
        memo: MutableMap<String, Boolean>,
        visiting: MutableSet<String>,
    ): Boolean {
        when {
            id in TERMINALS -> return true
            memo.containsKey(id) -> return memo.getValue(id)
            id !in edges -> return false
            id in visiting -> return false // cycle edge — do not recurse
        }
        visiting += id
        val result = edges.getValue(id).any { canReachTerminal(it, edges, memo, visiting) }
        visiting -= id
        memo[id] = result
        return result
    }

    /** True when [id] lies on a graph cycle (self-loop or inside a strongly connected component of size >= 2). */
    private fun onCycle(id: String, edges: Map<String, Set<String>>): Boolean {
        // From id, can we return to id?
        val queue = ArrayDeque(edges[id] ?: emptySet())
        val seen = mutableSetOf<String>()
        while (queue.isNotEmpty()) {
            val next = queue.removeFirst()
            if (next == id) return true
            if (next in seen || next !in edges) continue
            seen += next
            queue += edges.getValue(next)
        }
        return false
    }

    private fun sha256Hex(value: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(value).joinToString("") { "%02x".format(it) }
}
