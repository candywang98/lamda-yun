package com.company.cloudctl.companion.automation.recipes

import com.company.cloudctl.companion.automation.CanonicalJson
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest

/**
 * B16 template compiler: declarative template -> LocalRecipePackage JSON.
 *
 * The compiled graph is strictly linear (each step runs at most once; retries
 * live INSIDE a step's bounded wait budgets, never as graph cycles), so no
 * submit action can ever end up inside a loop and the total runtime is the
 * sum of the per-step deadlines — bounded by construction. The output is
 * statically validated with [RecipeStaticValidator] before it is handed out,
 * and its canonical hash is embedded in the manifest. Published recipe bytes
 * are immutable: compiling a template always produces a NEW recipeId; the
 * compiler refuses to emit an id that collides with a pinned builtin.
 */
object RecipeTemplateCompiler {

    data class Compiled(val encoded: String, val hash: String)

    fun compile(template: RecipeTemplate): Compiled {
        val states = JSONArray()
        template.steps.forEachIndexed { index, step ->
            val next = template.steps.getOrNull(index + 1)?.stepId ?: "SUCCEEDED"
            states.put(compileState(step, next))
        }
        val maxDurationMs = template.steps.sumOf { it.bounds.deadlineMs ?: DEFAULT_STEP_BUDGET_MS }
            .coerceIn(
                RecipeContract.GRAPH_MAX_DURATION_MS_RANGE.first,
                RecipeContract.GRAPH_MAX_DURATION_MS_RANGE.last,
            )
        val graph = JSONObject()
            .put("startStateId", template.steps.first().stepId)
            .put("maxIterations", template.steps.size + 1)
            .put("maxDurationMs", maxDurationMs)
            .put("states", states)
        val manifest = JSONObject()
            .put("id", template.recipeId)
            .put("version", template.version)
            .put("hash", "0".repeat(64))
            .put("signingKeyId", "template-compile")
            .put("minEngineVersion", template.minEngineVersion)
            .put("platform", template.platform)
            .put("app", template.app)
            .put("commandTypes", JSONArray(template.commandTypes))
        val root = JSONObject()
            .put("apiVersion", RecipeContract.PROTOCOL)
            .put("kind", RecipeContract.KIND)
            .put("manifest", manifest)
            .put("graph", graph)
            .put("signature", JSONObject().put("algorithm", "Ed25519").put("keyId", "template-compile").put("digest", "unsigned-template"))
        // The manifest hash is excluded from the canonical payload, so compute
        // first, embed, then run the full static validation over the final bytes.
        val hash = sha256Hex(CanonicalJson.recipeHashPayload(root))
        manifest.put("hash", hash)
        val encoded = root.toString()
        RecipeStaticValidator.requireValid(encoded)
        return Compiled(encoded = encoded, hash = hash)
    }

    private fun compileState(step: RecipeTemplate.TemplateStep, next: String): JSONObject {
        val state = JSONObject().put("stateId", step.stepId)
        val bounds = step.bounds
        fun putBounds() {
            bounds.maxAttempts?.let { state.put("maxAttempts", it) }
            bounds.noProgressBudget?.let { state.put("noProgressBudget", it) }
            bounds.deadlineMs?.let { state.put("deadlineMs", it) }
            bounds.onExhausted?.let { state.put("onExhausted", it) }
        }
        when (step.action) {
            "navigate" -> {
                state.put("action", "tap")
                state.put("locatorRef", requireNotNull(step.locatorRef))
                step.postcondition?.let { state.put("postcondition", it) }
                putBounds()
                // Exhaustion is fail-closed by construction: FAIL routes to the
                // FAILED terminal; WAITING_USER pauses through the engine's
                // onExhausted handling (the checkpoint, not a graph edge), so
                // the compiled graph stays acyclic and every step runs at most once.
                state.put("onSuccess", next)
                state.put("onFailure", "FAILED")
            }
            "wait" -> {
                state.put("action", "wait")
                state.put("locatorRef", requireNotNull(step.locatorRef))
                putBounds()
                state.put("onSuccess", next)
                state.put("onFailure", "FAILED")
            }
            "input" -> {
                state.put("action", "input")
                state.put("locatorRef", step.locatorRef)
                state.put("valueRef", requireNotNull(step.valueRef))
                state.put("onSuccess", next)
                state.put("onFailure", "FAILED")
            }
            "media" -> {
                state.put("action", "media")
                state.put("locatorRef", requireNotNull(step.locatorRef))
                putBounds()
                state.put("onSuccess", next)
                state.put("onFailure", "FAILED")
            }
            "checkpoint" -> {
                state.put("action", "checkpoint")
                state.put("onSuccess", "WAITING_USER")
                state.put("onFailure", JSONObject.NULL)
                state.put("onPause", "WAITING_USER")
                state.put("terminal", true)
            }
            else -> throw IllegalArgumentException("template action '${step.action}' cannot be compiled")
        }
        return state
    }

    private fun sha256Hex(value: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(value).joinToString("") { "%02x".format(it) }

    private const val DEFAULT_STEP_BUDGET_MS = 30_000L
}
