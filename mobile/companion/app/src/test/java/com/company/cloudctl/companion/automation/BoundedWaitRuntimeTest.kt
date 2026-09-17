package com.company.cloudctl.companion.automation

import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * B16 bounded runtime acceptance tests: configurable maxAttempts / deadline /
 * noProgressBudget / onExhausted on navigation/wait states with fail-closed
 * exhaustion, and the mathematical proof that every internal retry wait
 * counts against ONE deadline (the sleeps can never sum past it).
 */
class BoundedWaitRuntimeTest {

    /** Plain executor with a controllable clock and a page digest feed. */
    private class BoundedUi(
        private val inspection: () -> LocalNodeState?,
        private val digests: () -> String = { "page-a" },
        private val advancePerPollMs: Long = 0L,
    ) : LocalAutomationUi {
        var now = 0L
        val taps = mutableListOf<String>()
        override fun ensureReady(targetPackage: String) = Unit
        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? {
            now += advancePerPollMs
            return inspection()
        }
        override fun pageSummary(targetPackage: String): String = digests()
        override suspend fun tap(targetPackage: String, locatorRef: String) {
            taps += locatorRef
        }
        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit
        override suspend fun screenshot(taskId: String, label: String) = ScreenshotEvidence("x", 1, "a")
        override fun log(level: LogLevel, messageCode: String) = Unit
    }

    private fun packageOf(maxDurationMs: Long = 600_000, stateJson: JSONObject.() -> Unit = {}): String {
        val state = JSONObject()
            .put("stateId", "await")
            .put("action", "wait")
            .put("locatorRef", "xianyu_publish_page")
            .put("onSuccess", "SUCCEEDED")
            .put("onFailure", "FAILED")
            .apply(stateJson)
        val root = JSONObject()
            .put("apiVersion", "cloudctl.recipe/v1")
            .put("kind", "LocalRecipePackage")
            .put(
                "manifest",
                JSONObject()
                    .put("id", "recipe-bounded-test")
                    .put("version", "1.0.0")
                    .put("hash", "0".repeat(64))
                    .put("signingKeyId", "test")
                    .put("minEngineVersion", 1)
                    .put("platform", "xianyu")
                    .put("app", "com.taobao.idlefish")
                    .put("commandTypes", JSONArray(listOf("xianyu.publish_listing.v1"))),
            )
            .put(
                "graph",
                JSONObject()
                    .put("startStateId", "await")
                    .put("maxIterations", 8)
                    .put("maxDurationMs", maxDurationMs)
                    .put("states", JSONArray().put(state)),
            )
            .put("signature", JSONObject().put("algorithm", "Ed25519").put("keyId", "test").put("digest", "unsigned"))
        val hash = RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(root))
        root.getJSONObject("manifest").put("hash", hash)
        return root.toString()
    }

    private fun command(hash: String, parameters: JSONObject = JSONObject()) = CommandV1(
        protocolVersion = CommandV1Parser.PROTOCOL,
        taskId = "task-bounded",
        attemptId = "attempt-1",
        commandType = "xianyu.publish_listing.v1",
        deviceId = "device-1",
        accountId = "account-1",
        bindingVersion = 1,
        snapshotId = "snap",
        snapshotSha256 = "a".repeat(64),
        recipeVersionId = "recipe-bounded-test",
        recipeSha256 = hash,
        engineMinVersion = 1,
        targetPackage = "com.taobao.idlefish",
        requiredCapabilities = listOf("accessibility"),
        controlEpoch = 1,
        leaseExpiresAt = "2026-09-07T00:00:00Z",
        mediaDeliveryId = null,
        legacyStepsEnabled = false,
        parameters = parameters,
    )

    @Test
    fun maxAttemptsExhaustionFailsClosedThroughTheGraphFailureEdge() = runBlocking {
        var polls = 0
        val ui = BoundedUi(inspection = { polls++; null })
        val engine = RecipeEngine(ui, elapsedMs = { ui.now })
        val recipe = engine.parse(packageOf { put("maxAttempts", 3) })
        val journal = mutableListOf<String>()
        val outcome = engine.execute(recipe, command(recipe.hash)) { id, state -> journal += "$id:$state" }
        assertEquals("FAILED", outcome, "default onExhausted=FAIL must terminate through the failure edge")
        assertEquals(3, polls, "exactly maxAttempts polls may run")
        assertEquals(listOf("await:STARTED", "await:FAILED"), journal)
    }

    @Test
    fun noProgressBudgetExhaustionFailsClosed() = runBlocking {
        var polls = 0
        // Constant page digest "page-a": poll 1 sets the baseline, polls 2 and 3
        // count against the budget of 2 -> exhaustion after exactly 3 polls.
        val ui = BoundedUi(inspection = { polls++; null })
        val engine = RecipeEngine(ui, elapsedMs = { ui.now })
        val recipe = engine.parse(packageOf { put("noProgressBudget", 2); put("maxAttempts", 10) })
        val journal = mutableListOf<String>()
        val outcome = engine.execute(recipe, command(recipe.hash)) { id, state -> journal += "$id:$state" }
        assertEquals("FAILED", outcome)
        assertEquals(3, polls, "exhaustion must come from the no-progress budget, not maxAttempts")
        assertEquals(listOf("await:STARTED", "await:FAILED"), journal)
    }

    @Test
    fun onExhaustedWaitingUserPausesInsteadOfFailing() = runBlocking {
        val ui = BoundedUi(inspection = { null })
        val engine = RecipeEngine(ui, elapsedMs = { ui.now })
        val recipe = engine.parse(packageOf {
            put("maxAttempts", 2)
            put("onExhausted", "WAITING_USER")
        })
        val journal = mutableListOf<String>()
        val outcome = engine.execute(recipe, command(recipe.hash)) { id, state -> journal += "$id:$state" }
        assertEquals("WAITING_USER", outcome, "onExhausted=WAITING_USER must hand control to the operator")
        assertEquals(listOf("await:STARTED", "await:WAITING_USER"), journal)
    }

    @Test
    fun stateDeadlineBoundsAllInternalRetriesAndReportsStateDeadline() = runBlocking {
        var polls = 0
        // The virtual clock advances 600ms per poll; the state deadline of
        // 1000ms expires after the second poll even though the recipe-wide
        // budget (600s) is nowhere near exhausted — proof the state cap, not
        // the graph budget, terminated the retries.
        val ui = BoundedUi(inspection = { polls++; null }, advancePerPollMs = 600)
        val engine = RecipeEngine(ui, elapsedMs = { ui.now })
        val recipe = engine.parse(packageOf {
            put("deadlineMs", 1000)
            put("maxAttempts", 50)
        })
        val journal = mutableListOf<String>()
        val outcome = runCatching {
            engine.execute(recipe, command(recipe.hash)) { id, state -> journal += "$id:$state" }
        }
        // FAIL default: routed through the graph failure edge -> FAILED outcome.
        assertEquals("FAILED", outcome.getOrNull())
        assertTrue(polls < 50, "the state deadline must cut the retries short (polls=$polls)")
        assertEquals(listOf("await:STARTED", "await:FAILED"), journal)
    }

    @Test
    fun stateDeadlineWithWaitingUserSemanticsPausesAtTheCap() = runBlocking {
        val ui = BoundedUi(inspection = { null }, advancePerPollMs = 600)
        val engine = RecipeEngine(ui, elapsedMs = { ui.now })
        val recipe = engine.parse(packageOf {
            put("deadlineMs", 1000)
            put("onExhausted", "WAITING_USER")
        })
        val outcome = engine.execute(recipe, command(recipe.hash)) { _, _ -> }
        assertEquals("WAITING_USER", outcome)
    }

    @Test
    fun unboundedWaitStatesKeepTheirExactP14Semantics() = runBlocking {
        // No new fields: the wait must obey ONLY the recipe deadline, exactly
        // as before B16 (P14 non-regression). Clock advances 120s per poll so
        // the 600s recipe budget expires after 5 polls.
        var polls = 0
        val ui = BoundedUi(inspection = { polls++; null }, advancePerPollMs = 120_000)
        val engine = RecipeEngine(ui, elapsedMs = { ui.now })
        val recipe = engine.parse(packageOf())
        val failure = kotlin.test.assertFailsWith<ExecutorFailure> {
            engine.execute(recipe, command(recipe.hash)) { _, _ -> }
        }
        assertEquals("STEP_TIMEOUT", failure.code)
        assertTrue(polls > 3, "an unbounded wait polls until the recipe deadline, not a B16 budget (polls=$polls)")
    }

    @Test
    fun inputTextLengthCapIsEnforcedAtBindTime() = runBlocking {
        val ui = BoundedUi(inspection = { LocalNodeState(true, true, true, true, "") })
        val engine = RecipeEngine(ui, elapsedMs = { ui.now })
        val state = JSONObject()
            .put("stateId", "fill")
            .put("action", "input")
            .put("locatorRef", "xianyu_description")
            .put("valueRef", "listingBody")
            .put("onSuccess", "SUCCEEDED")
            .put("onFailure", "FAILED")
        val root = JSONObject(packageOf())
        root.getJSONObject("graph")
            .put("startStateId", "fill")
            .put("states", JSONArray().put(state))
        val hash = RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(root))
        root.getJSONObject("manifest").put("hash", hash)
        val recipe = engine.parse(root.toString())
        val tooLong = "x".repeat(1025)
        val outcome = engine.execute(
            recipe,
            command(recipe.hash, JSONObject().put("listingBody", tooLong)),
        ) { _, _ -> }
        assertEquals("FAILED", outcome, "over-cap parameters must fail closed through the graph")
    }

    /**
     * The mathematical acceptance proof: for every admissible budget
     * combination, the engine's internal retry sleeps sum to at most
     * min(attempts * poll, deadline) — all waits share ONE deadline instant,
     * so no compounding into an unbounded wait is possible.
     */
    @Test
    fun deadlineSumHasAProvableClosedFormUpperBound() {
        val polls = listOf(100L, 250L, 400L, 670L, 1000L)
        val attemptsGrid = listOf(1, 2, 3, 5, 8, 13, 21, 40, 80)
        val deadlines = listOf(1000L, 2500L, 10_000L, 60_000L, 600_000L)
        for (attempts in attemptsGrid) {
            for (poll in polls) {
                for (deadline in deadlines) {
                    val bound = BoundedRetryPlan.totalSleepUpperBoundMs(attempts, poll, deadline)
                    val simulated = BoundedRetryPlan.simulatedTotalSleepMs(attempts, poll, deadline)
                    assertTrue(
                        simulated <= bound,
                        "simulated $simulated > bound $bound for attempts=$attempts poll=$poll deadline=$deadline",
                    )
                    assertEquals(minOf(attempts.toLong() * poll, deadline), bound)
                    // Whichever budget is smaller decides — never both stacked.
                    assertEquals(minOf(attempts.toLong() * poll, deadline), simulated)
                }
            }
        }
    }
}
