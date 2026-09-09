package com.company.cloudctl.companion.automation

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertTrue

private class FakeRecipeUi(
    private val unknown: Boolean = false,
    private val inspection: () -> LocalNodeState? = { LocalNodeState(true, true, true, true, "") },
) : LocalAutomationUi {
    val taps = mutableListOf<String>()
    override fun ensureReady(targetPackage: String) = Unit
    override fun inspect(targetPackage: String, locatorRef: String) = inspection()
    override suspend fun tap(targetPackage: String, locatorRef: String) {
        if (unknown) throw ExecutorFailure("UNKNOWN_PAGE", locatorRef)
        taps += locatorRef
    }
    override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit
    override suspend fun screenshot(taskId: String, label: String) = ScreenshotEvidence("x", 1, "a")
    override fun log(level: LogLevel, messageCode: String) = Unit
}

class RecipeEngineTest {
    private val elapsed = { 0L }

    @Test
    fun completesLocalGraphWithoutCloudClicks() = runBlocking {
        val ui = FakeRecipeUi()
        val engine = RecipeEngine(ui, elapsedMs = elapsed)
        val recipe = engine.parse(hashed(recipeJson()))
        val result = engine.execute(recipe, command(recipe.hash), journal = { _, _ -> })
        assertEquals("SUCCEEDED", result)
        assertEquals(listOf("xianyu_home_sell"), ui.taps)
    }

    @Test
    fun loopLimitAndUnknownPagePause() = runBlocking {
        val looping = RecipeEngine(FakeRecipeUi(), elapsedMs = elapsed).parse(
            hashed(recipeJson().replace("\"onSuccess\":\"fill\"", "\"onSuccess\":\"open\"").replace("\"maxIterations\":12", "\"maxIterations\":2")),
        )
        assertFailsWith<ExecutorFailure> {
            RecipeEngine(FakeRecipeUi(), elapsedMs = elapsed).execute(looping, command(looping.hash), journal = { _, _ -> })
        }
        val unknown = RecipeEngine(FakeRecipeUi(unknown = true), elapsedMs = elapsed)
        val hashedRecipe = hashed(recipeJson())
        val parsed = unknown.parse(hashedRecipe)
        val paused = unknown.execute(parsed, command(parsed.hash), journal = { _, _ -> })
        assertEquals("WAITING_USER", paused)
    }

    @Test
    fun rejectsWrongHashAndUnknownAction() {
        val engine = RecipeEngine(FakeRecipeUi(), elapsedMs = elapsed)
        assertFailsWith<IllegalArgumentException> {
            engine.parse(hashed(recipeJson()), expectedHash = "deadbeef")
        }
        assertFailsWith<IllegalArgumentException> {
            engine.parse(hashed(recipeJson().replace("\"tap\"", "\"shell\"")))
        }
    }

    @Test
    fun resumesFromNextUnexecutedStateWithoutReplayingCompletedTap() = runBlocking {
        val recipe = RecipeEngine(FakeRecipeUi(), elapsedMs = elapsed).parse(hashed(twoTapRecipeJson()))
        val cmd = command(recipe.hash)

        val freshUi = FakeRecipeUi()
        val fresh = RecipeEngine(freshUi, elapsedMs = elapsed).execute(recipe, cmd, journal = { _, _ -> })
        assertEquals("SUCCEEDED", fresh)
        assertEquals(listOf("locator_a", "locator_b"), freshUi.taps)

        val resumeUi = FakeRecipeUi()
        val resumed = RecipeEngine(resumeUi, elapsedMs = elapsed).execute(
            recipe,
            cmd,
            resumeFromStateId = "tapB",
            journal = { _, _ -> },
        )
        assertEquals("SUCCEEDED", resumed)
        assertEquals(listOf("locator_b"), resumeUi.taps)

        for (invalid in listOf("", " ", "missing", "SUCCEEDED", "FAILED", "WAITING_USER")) {
            val rejectUi = FakeRecipeUi()
            assertFailsWith<IllegalArgumentException> {
                RecipeEngine(rejectUi, elapsedMs = elapsed).execute(
                    recipe,
                    cmd,
                    resumeFromStateId = invalid,
                    journal = { _, _ -> },
                )
            }
            assertEquals(emptyList<String>(), rejectUi.taps)
        }
    }

    @Test
    fun waitPollsUntilLocatorIsVisibleAndEnabled() = runBlocking {
        val nodes = listOf(null, node(visible = false), node(enabled = false), node())
        var polls = 0
        var checkpoints = 0
        val ui = FakeRecipeUi(inspection = { nodes[polls++] })
        val engine = RecipeEngine(ui, elapsedMs = elapsed)
        val recipe = waitRecipe(engine)
        val journal = mutableListOf<String>()
        val result = engine.execute(
            recipe, command(recipe.hash), controlCheckpoint = { checkpoints++ },
        ) { state, status -> journal += "$state:$status" }
        assertEquals("SUCCEEDED", result)
        assertEquals(4, polls)
        assertEquals(polls, checkpoints)
        assertEquals(listOf("await:STARTED", "await:SUCCEEDED"), journal)
        assertTrue(ui.taps.isEmpty())
    }

    @Test
    fun waitUsesOverallDeadlineAndCannotTakeSuccessfulFailureTransition() = runBlocking {
        var now = 0L
        var polls = 0
        val engine = RecipeEngine(FakeRecipeUi(inspection = { polls++; null }), elapsedMs = {
            if (polls > 0) now++ else now
        })
        // Time already spent before the wait counts against the same recipe budget.
        val recipe = waitRecipe(engine, onFailure = "SUCCEEDED")
        val journal = mutableListOf<String>()
        val failure = assertFailsWith<ExecutorFailure> {
            engine.execute(recipe, command(recipe.hash)) { state, status ->
                journal += "$state:$status"
                if (status == "STARTED") now = recipe.maxDurationMs - 1
            }
        }
        assertEquals("STEP_TIMEOUT", failure.code)
        assertEquals(listOf("await:STARTED"), journal)
    }

    @Test
    fun waitRejectsLocatorFoundAfterDeadline() = runBlocking {
        var now = 0L
        val engine = RecipeEngine(FakeRecipeUi(inspection = { now = 1000L; node() }), elapsedMs = { now })
        val recipe = waitRecipe(engine)
        val failure = assertFailsWith<ExecutorFailure> {
            engine.execute(recipe, command(recipe.hash), journal = { _, _ -> })
        }
        assertEquals("STEP_TIMEOUT", failure.code)
    }

    @Test
    fun waitRejectsMissingBlankAndUnapprovedLocatorsWithoutInspecting() = runBlocking {
        var polls = 0
        val engine = RecipeEngine(FakeRecipeUi(inspection = { polls++; node() }), elapsedMs = elapsed)
        for (locator in listOf(null, "", " ", "unapproved", "companion_refresh")) {
            val recipe = waitRecipe(engine, locatorRef = locator)
            val failure = assertFailsWith<ExecutorFailure> {
                engine.execute(recipe, command(recipe.hash), journal = { _, _ -> })
            }
            assertEquals("LOCATOR_NOT_APPROVED", failure.code)
        }
        assertEquals(0, polls)
    }

    @Test
    fun waitDelayIsCoroutineCancellableEvenWithOnFailure() = runBlocking {
        val inspected = CompletableDeferred<Unit>()
        var polls = 0
        val engine = RecipeEngine(FakeRecipeUi(inspection = {
            polls++
            inspected.complete(Unit)
            null
        }), elapsedMs = elapsed)
        val recipe = waitRecipe(engine, onFailure = "SUCCEEDED")
        val journal = mutableListOf<String>()
        val job = launch {
            engine.execute(recipe, command(recipe.hash)) { state, status -> journal += "$state:$status" }
        }
        inspected.await()
        job.cancelAndJoin()
        assertTrue(job.isCancelled)
        assertEquals(1, polls)
        assertEquals(listOf("await:STARTED"), journal)
    }

    @Test
    fun waitPropagatesPauseOnNextPollWithoutTakingOnFailure() = runBlocking {
        for (onFailure in listOf(null, "SUCCEEDED")) {
            val paused = TaskPausedException(null, -1, "operator pause")
            assertWaitControlPropagation(paused, onFailure)
        }
    }

    @Test
    fun waitPropagatesCancelAndLeaseLossWithoutTakingOnFailure() = runBlocking {
        for (code in listOf("CANCELLED", "LEASE_FENCED")) {
            assertWaitControlPropagation(ExecutorFailure(code, "control interruption"), "SUCCEEDED")
        }
    }

    private suspend fun assertWaitControlPropagation(interruption: Exception, onFailure: String?) {
        var polls = 0
        var checkpoints = 0
        val engine = RecipeEngine(FakeRecipeUi(inspection = { polls++; null }), elapsedMs = elapsed)
        val recipe = waitRecipe(engine, onFailure = onFailure)
        val journal = mutableListOf<String>()
        val caught = assertFailsWith<Exception> {
            engine.execute(recipe, command(recipe.hash), controlCheckpoint = {
                if (++checkpoints == 2) throw interruption
            }) { state, status -> journal += "$state:$status" }
        }
        assertSame(interruption, caught)
        assertEquals(2, checkpoints)
        assertEquals(1, polls)
        assertEquals(listOf("await:STARTED"), journal)
    }

    private fun node(enabled: Boolean = true, visible: Boolean = true) =
        LocalNodeState(enabled, visible, false, false, null)

    private fun waitRecipe(
        engine: RecipeEngine,
        locatorRef: String? = "xianyu_publish_page",
        onFailure: String? = null,
    ): RecipePackage {
        val root = org.json.JSONObject(recipeJson())
        val state = org.json.JSONObject()
            .put("stateId", "await").put("action", "wait").put("onSuccess", "SUCCEEDED")
        locatorRef?.let { state.put("locatorRef", it) }
        onFailure?.let { state.put("onFailure", it) }
        root.getJSONObject("graph")
            .put("startStateId", "await").put("maxDurationMs", 1000)
            .put("states", org.json.JSONArray().put(state))
        return engine.parse(hashed(root.toString()))
    }

    private fun hashed(json: String): String {
        val root = org.json.JSONObject(json)
        val computed = RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(root))
        root.getJSONObject("manifest").put("hash", computed)
        return root.toString()
    }

    private fun command(recipeSha256: String) = CommandV1(
        protocolVersion = CommandV1Parser.PROTOCOL,
        taskId = "task-1",
        attemptId = "attempt-1",
        commandType = "xianyu.publish_listing.v1",
        deviceId = "device-1",
        accountId = "account-1",
        bindingVersion = 1,
        snapshotId = "snap",
        snapshotSha256 = "a".repeat(64),
        recipeVersionId = "recipe-xianyu-publish-1",
        recipeSha256 = recipeSha256,
        engineMinVersion = 1,
        targetPackage = "com.taobao.idlefish",
        requiredCapabilities = listOf("accessibility"),
        controlEpoch = 1,
        leaseExpiresAt = "2026-09-07T00:00:00Z",
        mediaDeliveryId = null,
        legacyStepsEnabled = false,
        parameters = org.json.JSONObject(),
    )

    private fun twoTapRecipeJson() = """
      {
        "apiVersion":"cloudctl.recipe/v1",
        "kind":"LocalRecipePackage",
        "manifest":{"id":"recipe-xianyu-publish-1","version":"1.0.0","hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","signingKeyId":"prod-1","minEngineVersion":1,"platform":"xianyu","app":"com.taobao.idlefish","commandTypes":["xianyu.publish_listing.v1"]},
        "graph":{"startStateId":"tapA","maxIterations":12,"maxDurationMs":90000,"states":[
          {"stateId":"tapA","action":"tap","locatorRef":"locator_a","onSuccess":"tapB","onFailure":"FAILED"},
          {"stateId":"tapB","action":"tap","locatorRef":"locator_b","onSuccess":"SUCCEEDED","onFailure":"FAILED"}
        ]},
        "signature":{"algorithm":"Ed25519","keyId":"prod-1","digest":"unsigned"}
      }
    """.trimIndent()

    private fun recipeJson() = """
      {
        "apiVersion":"cloudctl.recipe/v1",
        "kind":"LocalRecipePackage",
        "manifest":{"id":"recipe-xianyu-publish-1","version":"1.0.0","hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","signingKeyId":"prod-1","minEngineVersion":1,"platform":"xianyu","app":"com.taobao.idlefish","commandTypes":["xianyu.publish_listing.v1"]},
        "graph":{"startStateId":"open","maxIterations":12,"maxDurationMs":90000,"states":[
          {"stateId":"open","action":"tap","locatorRef":"xianyu_home_sell","onSuccess":"fill","onFailure":"FAILED","onPause":"WAITING_USER"},
          {"stateId":"fill","action":"checkpoint","onSuccess":"SUCCEEDED","terminal":true}
        ]},
        "signature":{"algorithm":"Ed25519","keyId":"prod-1","digest":"unsigned"}
      }
    """.trimIndent()
}
