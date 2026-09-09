package com.company.cloudctl.companion.automation

import org.json.JSONObject
import java.security.MessageDigest

data class RecipeState(
    val stateId: String,
    val action: String,
    val locatorRef: String?,
    val onSuccess: String,
    val onFailure: String?,
    val terminal: Boolean,
)

data class RecipePackage(
    val id: String,
    val hash: String,
    val minEngineVersion: Int,
    val app: String,
    val commandTypes: Set<String>,
    val startStateId: String,
    val maxIterations: Int,
    val maxDurationMs: Long,
    val states: Map<String, RecipeState>,
)

class RecipeEngine(
    private val ui: LocalAutomationUi,
    private val engineVersion: Int = VERSION,
    private val elapsedMs: () -> Long,
) {
    fun parse(encoded: String, expectedHash: String? = null): RecipePackage {
        val root = JSONObject(encoded)
        require(root.getString("apiVersion") == "cloudctl.recipe/v1") { CommandV1Parser.UNSUPPORTED_PROTOCOL }
        require(root.getString("kind") == "LocalRecipePackage") { CommandV1Parser.UNSUPPORTED_RECIPE }
        val manifest = root.getJSONObject("manifest")
        val graph = root.getJSONObject("graph")
        val hash = manifest.getString("hash")
        val computed = sha256Bytes(CanonicalJson.recipeHashPayload(root))
        require(hash == computed) { "recipe hash does not match canonical graph" }
        require(expectedHash == null || expectedHash == hash) { "recipe hash mismatch" }
        val minEngine = manifest.getInt("minEngineVersion")
        require(minEngine in 1..engineVersion) { CommandV1Parser.UNSUPPORTED_RECIPE }
        val statesJson = graph.getJSONArray("states")
        val states = LinkedHashMap<String, RecipeState>()
        for (index in 0 until statesJson.length()) {
            val item = statesJson.getJSONObject(index)
            val action = item.getString("action")
            require(action in ALLOWED_ACTIONS) { "action is not on the APK whitelist" }
            val state = RecipeState(
                stateId = item.getString("stateId"),
                action = action,
                locatorRef = item.optString("locatorRef").takeIf(String::isNotBlank),
                onSuccess = item.getString("onSuccess"),
                onFailure = item.optString("onFailure").takeIf(String::isNotBlank),
                terminal = item.optBoolean("terminal"),
            )
            states[state.stateId] = state
        }
        require(states.containsKey(graph.getString("startStateId"))) { "startStateId is missing" }
        return RecipePackage(
            id = manifest.getString("id"),
            hash = hash,
            minEngineVersion = minEngine,
            app = manifest.getString("app"),
            commandTypes = manifest.getJSONArray("commandTypes").let { types ->
                (0 until types.length()).map { types.getString(it) }.toSet()
            },
            startStateId = graph.getString("startStateId"),
            maxIterations = graph.getInt("maxIterations").also { require(it in 1..200) },
            maxDurationMs = graph.getLong("maxDurationMs"),
            states = states,
        )
    }

    suspend fun execute(
        recipe: RecipePackage,
        command: CommandV1,
        resumeFromStateId: String? = null,
        journal: (String, String) -> Unit,
    ): String {
        require(recipe.hash == command.recipeSha256) { "recipe hash mismatch" }
        require(recipe.app == command.targetPackage) { "recipe app does not match command" }
        val currentStart = resolveResumeStart(recipe, resumeFromStateId)
        ui.ensureReady(command.targetPackage)
        val deadline = elapsedMs() + recipe.maxDurationMs
        var current = currentStart
        var iterations = 0
        while (current !in TERMINAL) {
            if (elapsedMs() >= deadline) throw ExecutorFailure("STEP_TIMEOUT", "recipe exceeded maxDuration")
            if (iterations++ >= recipe.maxIterations) throw ExecutorFailure("LOOP_LIMIT", "recipe exceeded maxIterations")
            val state = recipe.states[current] ?: throw ExecutorFailure("UNKNOWN_STATE", current)
            journal(state.stateId, "STARTED")
            var journalState = "SUCCEEDED"
            current = try {
                runAction(command.targetPackage, state)
                if (state.terminal || state.onSuccess in TERMINAL) state.onSuccess else state.onSuccess
            } catch (failure: ExecutorFailure) {
                if (failure.code == "UNKNOWN_PAGE") {
                    journal(state.stateId, "WAITING_USER")
                    return "WAITING_USER"
                }
                journalState = "FAILED"
                state.onFailure ?: throw failure
            }
            journal(state.stateId, journalState)
            if (current in TERMINAL) return current
        }
        return current
    }

    private fun resolveResumeStart(recipe: RecipePackage, resumeFromStateId: String?): String {
        if (resumeFromStateId == null) return recipe.startStateId
        require(resumeFromStateId.isNotBlank()) { "resumeFromStateId is blank" }
        require(resumeFromStateId !in TERMINAL) { "resumeFromStateId is terminal" }
        require(recipe.states.containsKey(resumeFromStateId)) { "resumeFromStateId is unknown" }
        return resumeFromStateId
    }

    private suspend fun runAction(targetPackage: String, state: RecipeState) {
        when (state.action) {
            "tap" -> ui.tap(targetPackage, state.locatorRef ?: error("locator required"))
            "input" -> ui.replaceText(targetPackage, state.locatorRef ?: error("locator required"), "")
            "wait", "checkpoint", "log", "extract", "media", "launch", "scroll" -> ui.log(LogLevel.INFO, state.action.uppercase())
            else -> error("action is not on the APK whitelist")
        }
    }

    companion object {
        const val VERSION = 1
        private val ALLOWED_ACTIONS = setOf("tap", "input", "scroll", "extract", "wait", "launch", "media", "log", "checkpoint")
        private val TERMINAL = setOf("SUCCEEDED", "FAILED", "WAITING_USER")
        fun sha256(value: String): String = sha256Bytes(value.toByteArray(Charsets.UTF_8))

        fun sha256Bytes(value: ByteArray): String {
            val digest = MessageDigest.getInstance("SHA-256").digest(value)
            return digest.joinToString("") { "%02x".format(it) }
        }
    }
}
