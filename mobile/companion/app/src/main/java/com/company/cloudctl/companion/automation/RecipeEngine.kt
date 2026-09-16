package com.company.cloudctl.companion.automation

import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import org.json.JSONObject
import java.security.MessageDigest

data class RecipeState(
    val stateId: String,
    val action: String,
    val locatorRef: String?,
    val onSuccess: String,
    val onFailure: String?,
    val terminal: Boolean,
    val postcondition: String? = null,
    val valueRef: String? = null,
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
    val commitActionId: String? = null,
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
                locatorRef = item.optString("locatorRef").takeIf { !item.isNull("locatorRef") && it.isNotBlank() },
                onSuccess = item.getString("onSuccess"),
                onFailure = item.optString("onFailure").takeIf { !item.isNull("onFailure") && it.isNotBlank() },
                terminal = item.optBoolean("terminal"),
                postcondition = item.optString("postcondition").takeIf { !item.isNull("postcondition") && it.isNotBlank() },
                valueRef = item.optString("valueRef").takeIf { !item.isNull("valueRef") && it.isNotBlank() },
            )
            require(!states.containsKey(state.stateId)) { "stateId values must be unique" }
            states[state.stateId] = state
        }
        require(states.containsKey(graph.getString("startStateId"))) { "startStateId is missing" }
        val commitId = if (graph.isNull("commitActionId")) null else graph.getString("commitActionId")
        if (commitId != null) {
            require(minEngine >= 2) { "commitActionId requires engine version 2" }
            val commit = requireNotNull(states[commitId]) { "commitActionId is missing" }
            require(Regex("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}").matches(commitId)) { "invalid commitActionId" }
            require(commit.action == "tap" && commit.locatorRef != null && commit.postcondition != null &&
                commit.postcondition != commit.locatorRef && commit.onSuccess == "SUCCEEDED" && commit.onFailure == null) {
                "commit requires a single tap, distinct postcondition and terminal success without a failure branch"
            }
        }
        require(states.values.none { it.locatorRef == "xianyu_publish_button" && it.stateId != commitId }) {
            "publish locator requires commitActionId"
        }
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
            commitActionId = commitId,
        )
    }

    suspend fun execute(
        recipe: RecipePackage,
        command: CommandV1,
        resumeFromStateId: String? = null,
        journal: (String, String) -> Unit,
    ): String = execute(recipe, command, resumeFromStateId, controlCheckpoint = {}, journal = journal)

    suspend fun execute(
        recipe: RecipePackage,
        command: CommandV1,
        resumeFromStateId: String? = null,
        controlCheckpoint: () -> Unit,
        commitAction: (suspend (RecipeState) -> Unit)? = null,
        journal: (String, String) -> Unit,
    ): String {
        require(recipe.hash == command.recipeSha256) { "recipe hash mismatch" }
        require(recipe.app == command.targetPackage) { "recipe app does not match command" }
        require(command.commandType in recipe.commandTypes) { "recipe command type mismatch" }
        if (recipe.commitActionId != null && commitAction == null) {
            throw ExecutorFailure("COMMIT_ADAPTER_REQUIRED", "commit requires the durable ledger")
        }
        val currentStart = resolveResumeStart(recipe, resumeFromStateId)
        ui.ensureReady(command.targetPackage)
        val deadline = elapsedMs() + recipe.maxDurationMs
        var current = currentStart
        var iterations = 0
        while (current !in TERMINAL) {
            if (elapsedMs() >= deadline) throw ExecutorFailure("STEP_TIMEOUT", "recipe exceeded maxDuration")
            if (iterations++ >= recipe.maxIterations) throw ExecutorFailure("LOOP_LIMIT", "recipe exceeded maxIterations")
            val state = recipe.states[current] ?: throw ExecutorFailure("UNKNOWN_STATE", current)
            currentCoroutineContext().ensureActive()
            if (state.action != "wait") controlCheckpoint()
            if (state.stateId == recipe.commitActionId) {
                // Never route commit failures through an ordinary graph retry/failure branch.
                requireNotNull(commitAction)(state)
                return "RECONCILING"
            }
            journal(state.stateId, "STARTED")
            var journalState = "SUCCEEDED"
            current = try {
                if (state.action == "wait") {
                    waitForLocator(command.targetPackage, state, deadline, controlCheckpoint)
                } else {
                    runAction(command.targetPackage, state, command, deadline, controlCheckpoint)
                }
                if (state.terminal || state.onSuccess in TERMINAL) state.onSuccess else state.onSuccess
            } catch (interrupted: ControlCheckpointFailure) {
                throw interrupted.failure
            } catch (failure: ExecutorFailure) {
                if (state.action == "wait" && failure.code == "STEP_TIMEOUT") throw failure
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

    // Keep control failures out of the graph's action-failure transitions.
    private class ControlCheckpointFailure(val failure: ExecutorFailure) : Exception(failure)

    private suspend fun waitForLocator(
        targetPackage: String,
        state: RecipeState,
        deadline: Long,
        controlCheckpoint: () -> Unit,
    ) {
        val locatorRef = state.locatorRef?.takeIf(String::isNotBlank)
            ?: throw ExecutorFailure("LOCATOR_NOT_APPROVED", "wait requires an approved locatorRef")
        try {
            TargetLocatorRegistry.resolve(targetPackage, locatorRef)
        } catch (failure: IllegalArgumentException) {
            throw ExecutorFailure("LOCATOR_NOT_APPROVED", "Locator is not approved for this target", failure)
        }
        while (true) {
            currentCoroutineContext().ensureActive()
            try {
                controlCheckpoint()
            } catch (failure: ExecutorFailure) {
                throw ControlCheckpointFailure(failure)
            }
            ensureBeforeDeadline(deadline)
            val node = ui.inspect(targetPackage, locatorRef)
            ensureBeforeDeadline(deadline)
            if (node?.visible == true && node.enabled) return
            delay(minOf(WAIT_POLL_MS, deadline - elapsedMs()).coerceAtLeast(1L))
        }
    }

    private fun ensureBeforeDeadline(deadline: Long) {
        if (elapsedMs() >= deadline) throw ExecutorFailure("STEP_TIMEOUT", "recipe exceeded maxDuration")
    }

    private suspend fun runAction(
        targetPackage: String,
        state: RecipeState,
        command: CommandV1,
        deadline: Long,
        controlCheckpoint: () -> Unit,
    ) {
        when (state.action) {
            "tap" -> ui.tap(targetPackage, state.locatorRef ?: error("locator required"))
            "input" -> {
                // Graph bytes stay parameter-free: the value is bound at execution
                // time from CommandV1 parameters through the static valueRef key.
                val key = state.valueRef
                    ?: throw ExecutorFailure("PARAMETER_REQUIRED", "input state ${state.stateId} has no valueRef")
                val raw = command.parameters.opt(key)
                val value = (raw as? String)?.trim().takeIf { !it.isNullOrBlank() }
                    ?: throw ExecutorFailure("PARAMETER_REQUIRED", "parameter $key is missing or blank")
                ui.replaceText(targetPackage, state.locatorRef ?: error("locator required"), value)
            }
            "media" -> {
                // Mirror of the frozen dispatch-xianyu steps sequence: tap the add-image
                // entry, wait for the gallery, tap ordered cover tiles (tile 0 is the
                // camera shutter and is never referenced), then confirm via Next.
                val count = command.parameters.opt("mediaAssetIds").let { entry ->
                    when (entry) {
                        is org.json.JSONArray -> entry.length()
                        is List<*> -> entry.size
                        else -> -1
                    }
                }
                // Tile generator resolves xianyu_gallery_select_0..49 (0 = shutter),
                // so at most 49 covers are selectable per listing.
                if (count < 1 || count > 49) {
                    throw ExecutorFailure("PARAMETER_REQUIRED", "mediaAssetIds must contain 1..49 entries")
                }
                ui.tap(targetPackage, state.locatorRef ?: error("locator required"))
                waitForLocator(
                    targetPackage,
                    state.copy(locatorRef = "xianyu_gallery_select_0"),
                    deadline,
                    controlCheckpoint,
                )
                for (index in 1..count) {
                    ui.tap(targetPackage, "xianyu_gallery_select_$index")
                }
                ui.tap(targetPackage, "xianyu_gallery_next")
            }
            "checkpoint", "log", "extract", "launch", "scroll" -> ui.log(LogLevel.INFO, state.action.uppercase())
            else -> error("action is not on the APK whitelist")
        }
    }

    companion object {
        const val VERSION = 2
        private const val WAIT_POLL_MS = 250L
        private val ALLOWED_ACTIONS = setOf("tap", "input", "scroll", "extract", "wait", "launch", "media", "log", "checkpoint")
        private val TERMINAL = setOf("SUCCEEDED", "FAILED", "WAITING_USER")
        fun sha256(value: String): String = sha256Bytes(value.toByteArray(Charsets.UTF_8))

        fun sha256Bytes(value: ByteArray): String {
            val digest = MessageDigest.getInstance("SHA-256").digest(value)
            return digest.joinToString("") { "%02x".format(it) }
        }
    }
}
