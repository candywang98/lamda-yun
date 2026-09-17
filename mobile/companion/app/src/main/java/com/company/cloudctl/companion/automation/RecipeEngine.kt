package com.company.cloudctl.companion.automation

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import com.company.cloudctl.companion.automation.recipes.RecipeContract
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
    /**
     * B16 bounded runtime (fleet-first-20260916.1): optional per-state budgets
     * for navigation/wait states. Every field is additive and optional — a
     * recipe without them keeps the exact P14 behavior. Exhaustion is always
     * fail-closed: [onExhausted] may only route to FAILED (via the graph's
     * failure edge) or pause as WAITING_USER; it can never continue.
     */
    val maxAttempts: Int? = null,
    val noProgressBudget: Int? = null,
    val deadlineMs: Long? = null,
    val onExhausted: String? = null,
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
        rejectForbiddenFields(root)
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
            val valueRef = item.optString("valueRef").takeIf { !item.isNull("valueRef") && it.isNotBlank() }
            if (valueRef != null) {
                require(RecipeContract.VALUE_REF_PATTERN.matches(valueRef)) {
                    "valueRef must be a short static parameter key"
                }
            }
            val bounds = parseBounds(item, action, graph.getLong("maxDurationMs"))
            val state = RecipeState(
                stateId = item.getString("stateId"),
                action = action,
                locatorRef = item.optString("locatorRef").takeIf { !item.isNull("locatorRef") && it.isNotBlank() },
                onSuccess = item.getString("onSuccess"),
                onFailure = item.optString("onFailure").takeIf { !item.isNull("onFailure") && it.isNotBlank() },
                terminal = item.optBoolean("terminal"),
                postcondition = item.optString("postcondition").takeIf { !item.isNull("postcondition") && it.isNotBlank() },
                valueRef = valueRef,
                maxAttempts = bounds.maxAttempts,
                noProgressBudget = bounds.noProgressBudget,
                deadlineMs = bounds.deadlineMs,
                onExhausted = bounds.onExhausted,
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

    /** Rejects any forbidden key anywhere in the package (signature is provenance, not a sandbox). */
    private fun rejectForbiddenFields(root: JSONObject) {
        fun walk(value: Any?, path: String) {
            when (value) {
                is JSONObject -> value.keys().asSequence().forEach { key ->
                    val lowered = key.lowercase()
                    require(RecipeContract.FORBIDDEN_FIELD_FRAGMENTS.none { it in lowered }) {
                        "recipe contains forbidden field '$key' at $path"
                    }
                    walk(value.get(key), "$path.$key")
                }
                is org.json.JSONArray -> for (index in 0 until value.length()) walk(value.get(index), "$path[$index]")
                else -> Unit
            }
        }
        walk(root, "$")
    }

    /**
     * B16: per-state bounds only exist on navigation/wait/media states (the
     * ones with internal retry loops). A submit/commit state can never carry
     * them — irreversible actions are single-shot, not retryable.
     */
    private fun parseBounds(item: JSONObject, action: String, graphMaxDurationMs: Long): BoundedStateFields {
        val maxAttempts = optionalInt(item, "maxAttempts")
        val noProgressBudget = optionalInt(item, "noProgressBudget")
        val deadlineMs = optionalLong(item, "deadlineMs")
        val onExhausted = item.optString("onExhausted").takeIf { !item.isNull("onExhausted") && it.isNotBlank() }
        val bounded = maxAttempts != null || noProgressBudget != null || deadlineMs != null || onExhausted != null
        if (!bounded) return BoundedStateFields(null, null, null, null)
        require(action in BOUNDED_ACTIONS) { "bounded retry fields require a wait/navigate/media action" }
        maxAttempts?.let { require(it in 1..RecipeContract.MAX_WAIT_ATTEMPTS) { "maxAttempts exceeds the cap" } }
        noProgressBudget?.let {
            require(it in 1..RecipeContract.MAX_NO_PROGRESS_POLLS) { "noProgressBudget exceeds the cap" }
            require(maxAttempts == null || it <= maxAttempts) { "noProgressBudget must fit inside maxAttempts" }
        }
        deadlineMs?.let {
            require(it in RecipeContract.MIN_STATE_DEADLINE_MS..graphMaxDurationMs) {
                "deadlineMs must fit inside the graph budget"
            }
        }
        onExhausted?.let {
            require(it in RecipeContract.ON_EXHAUSTED_VALUES) { "onExhausted must be FAIL or WAITING_USER" }
        }
        return BoundedStateFields(maxAttempts, noProgressBudget, deadlineMs, onExhausted)
    }

    private fun optionalInt(item: JSONObject, key: String): Int? {
        if (!item.has(key) || item.isNull(key)) return null
        return item.getInt(key)
    }

    private fun optionalLong(item: JSONObject, key: String): Long? {
        if (!item.has(key) || item.isNull(key)) return null
        return item.getLong(key)
    }

    private data class BoundedStateFields(
        val maxAttempts: Int?,
        val noProgressBudget: Int?,
        val deadlineMs: Long?,
        val onExhausted: String?,
    )

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
                // FLEET-21 note (2026-09-17): the commit strike deliberately emits no step
                // journal here — the durable action ledger is its audit trail. Emitting a
                // journal STARTED would need the frozen RecipeCommitAdapterTest contract
                // ("commit must not emit ordinary success journal") updated first.
                requireNotNull(commitAction)(state)
                return "RECONCILING"
            }
            journal(state.stateId, "STARTED")
            var journalState = "SUCCEEDED"
            val stateDeadline = stateDeadline(state, deadline)
            current = try {
                if (state.action == "wait") {
                    waitForLocator(command.targetPackage, state, stateDeadline, controlCheckpoint)
                } else {
                    runAction(command.targetPackage, state, command, stateDeadline, controlCheckpoint)
                }
                if (state.terminal || state.onSuccess in TERMINAL) state.onSuccess else state.onSuccess
            } catch (interrupted: ControlCheckpointFailure) {
                throw interrupted.failure
            } catch (failure: ExecutorFailure) {
                if (failure.code == "WAIT_EXHAUSTED" || failure.code == "STATE_DEADLINE") {
                    if (state.onExhausted == "WAITING_USER") {
                        journal(state.stateId, "WAITING_USER")
                        return "WAITING_USER"
                    }
                    // Default onExhausted=FAIL: fail closed through the graph's
                    // failure edge, or terminate hard when none exists.
                    journalState = "FAILED"
                    state.onFailure ?: throw failure
                    state.onFailure
                } else {
                    if (state.action == "wait" && failure.code == "STEP_TIMEOUT") throw failure
                    if (failure.code == "UNKNOWN_PAGE") {
                        journal(state.stateId, "WAITING_USER")
                        return "WAITING_USER"
                    }
                    journalState = "FAILED"
                    state.onFailure ?: throw failure
                    state.onFailure
                }
            }
            journal(state.stateId, journalState)
            if (current in TERMINAL) return current
        }
        return current
    }

    /**
     * B16: a state-scoped deadline is carved out of the SAME recipe budget —
     * it never extends it. All internal retries of the state (poll loops,
     * no-progress waits) share this single instant, so their waits can only
     * sum up to it (see [BoundedRetryPlan]).
     */
    private fun stateDeadline(state: RecipeState, recipeDeadline: Long): Long {
        val cap = state.deadlineMs ?: return recipeDeadline
        return minOf(recipeDeadline, elapsedMs() + cap)
    }

    private fun hasBounds(state: RecipeState): Boolean =
        state.maxAttempts != null || state.noProgressBudget != null ||
            state.deadlineMs != null || state.onExhausted != null

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
        // B16 bounded wait state: attempts, no-progress budget and the state
        // deadline all count against the SAME single instant — every retry
        // sleeps at most (deadline - now), so the internal waits sum to at
        // most the state budget (proof: BoundedRetryPlan).
        var attempts = 0
        var noProgress = 0
        var lastDigest: String? = null
        while (true) {
            currentCoroutineContext().ensureActive()
            try {
                controlCheckpoint()
            } catch (failure: ExecutorFailure) {
                throw ControlCheckpointFailure(failure)
            }
            ensureBeforeDeadline(deadline, state)
            val cap = state.maxAttempts
            if (cap != null && attempts >= cap) {
                throw ExecutorFailure(
                    "WAIT_EXHAUSTED",
                    "wait '${state.stateId}' exhausted its maxAttempts budget of $cap",
                )
            }
            attempts += 1
            // The accessibility service rebinds itself every few minutes under
            // load (4x observed 2026-09-16, ~1s each): a poll landing inside a
            // rebind window must keep polling until the deadline, not fail the
            // wait state (task e22395db was killed exactly this way).
            val node = try {
                ui.inspect(targetPackage, locatorRef)
            } catch (failure: CancellationException) {
                throw failure
            } catch (transient: ExecutorFailure) {
                // Only rebind-window transients keep polling; anything that
                // names a different package or an unapproved locator fails now.
                if (transient.code == "ACTIVE_WINDOW_MISSING" ||
                    transient.code == "WINDOW_CONTENT_DENIED"
                ) {
                    null
                } else {
                    throw transient
                }
            } catch (error: RuntimeException) {
                null
            }
            ensureBeforeDeadline(deadline, state)
            if (node?.visible == true && node.enabled) return
            val budget = state.noProgressBudget
            if (budget != null) {
                val digest = ui.pageSummary(targetPackage)
                if (digest == lastDigest) {
                    noProgress += 1
                    if (noProgress >= budget) {
                        throw ExecutorFailure(
                            "WAIT_EXHAUSTED",
                            "wait '${state.stateId}' exhausted its noProgressBudget of $budget polls",
                        )
                    }
                } else {
                    noProgress = 0
                    lastDigest = digest
                }
            }
            delay(minOf(WAIT_POLL_MS, deadline - elapsedMs()).coerceAtLeast(1L))
        }
    }

    private fun ensureBeforeDeadline(deadline: Long, state: RecipeState? = null) {
        if (elapsedMs() >= deadline) {
            // A state-scoped cap is distinct from the recipe-wide budget so the
            // caller can route it through the onExhausted semantics.
            if (state?.deadlineMs != null) {
                throw ExecutorFailure(
                    "STATE_DEADLINE",
                    "state '${state.stateId}' exceeded its deadlineMs budget of ${state.deadlineMs}",
                )
            }
            throw ExecutorFailure("STEP_TIMEOUT", "recipe exceeded maxDuration")
        }
    }

    private suspend fun runAction(
        targetPackage: String,
        state: RecipeState,
        command: CommandV1,
        deadline: Long,
        controlCheckpoint: () -> Unit,
    ) {
        when (state.action) {
            "tap" -> {
                ui.tap(targetPackage, state.locatorRef ?: error("locator required"))
                // B16: a bounded navigation tap verifies its postcondition inside
                // the SAME budgets (maxAttempts/noProgress/deadline). Without
                // bounds the postcondition stays metadata, exactly as in P14.
                val postcondition = state.postcondition
                if (postcondition != null && hasBounds(state)) {
                    waitForLocator(
                        targetPackage,
                        state.copy(action = "wait", locatorRef = postcondition),
                        deadline,
                        controlCheckpoint,
                    )
                }
            }
            "input" -> {
                // Graph bytes stay parameter-free: the value is bound at execution
                // time from CommandV1 parameters through the static valueRef key.
                val key = state.valueRef
                    ?: throw ExecutorFailure("PARAMETER_REQUIRED", "input state ${state.stateId} has no valueRef")
                val raw = command.parameters.opt(key)
                val value = (raw as? String)?.trim().takeIf { !it.isNullOrBlank() }
                    ?: throw ExecutorFailure("PARAMETER_REQUIRED", "parameter $key is missing or blank")
                if (value.length > RecipeContract.MAX_INPUT_TEXT_LENGTH) {
                    throw ExecutorFailure(
                        "PARAMETER_REJECTED",
                        "parameter $key exceeds the ${RecipeContract.MAX_INPUT_TEXT_LENGTH}-char cap",
                    )
                }
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

        /** B16: the only actions whose internal retry loops may carry bounded budgets. */
        private val BOUNDED_ACTIONS = setOf("wait", "tap", "media")
        private val TERMINAL = setOf("SUCCEEDED", "FAILED", "WAITING_USER")
        fun sha256(value: String): String = sha256Bytes(value.toByteArray(Charsets.UTF_8))

        fun sha256Bytes(value: ByteArray): String {
            val digest = MessageDigest.getInstance("SHA-256").digest(value)
            return digest.joinToString("") { "%02x".format(it) }
        }
    }
}

/**
 * B16 bounded-wait budget math. Pure and test-visible: the acceptance proof
 * that every internal retry wait counts against ONE deadline and the sleeps
 * cannot sum past it lives in the unit tests over these two functions.
 */
object BoundedRetryPlan {
    /**
     * Closed-form upper bound for the engine's bounded wait loop: [attempts]
     * polls of [pollMs] under one hard [deadlineMs]. Every sleep is at most
     * `min(pollMs, deadline - now)` and the clock only moves forward, so the
     * total sleep is at most `min(attempts * pollMs, deadlineMs)`.
     */
    fun totalSleepUpperBoundMs(attempts: Int, pollMs: Long, deadlineMs: Long): Long =
        minOf(attempts.toLong() * pollMs, deadlineMs)

    /**
     * Faithful simulation of RecipeEngine.waitForLocator's sleep schedule:
     * attempt i sleeps `min(pollMs, remaining)`; the loop ends when the
     * attempts budget or the deadline is exhausted — whichever comes first.
     */
    fun simulatedTotalSleepMs(attempts: Int, pollMs: Long, deadlineMs: Long): Long {
        require(attempts >= 0 && pollMs >= 0 && deadlineMs >= 0)
        var slept = 0L
        var used = 0
        while (used < attempts && slept < deadlineMs) {
            slept += minOf(pollMs, deadlineMs - slept)
            used += 1
        }
        return slept
    }
}
