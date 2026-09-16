package com.company.cloudctl.companion.service

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.automation.CanonicalJson
import com.company.cloudctl.companion.automation.CommandV1
import com.company.cloudctl.companion.automation.CommandV1Parser
import com.company.cloudctl.companion.automation.ExecutorFailure
import com.company.cloudctl.companion.automation.LocalAutomationUi
import com.company.cloudctl.companion.automation.LocalNodeState
import com.company.cloudctl.companion.automation.LogLevel
import com.company.cloudctl.companion.automation.RecipeEngine
import com.company.cloudctl.companion.automation.ScreenshotEvidence
import com.company.cloudctl.companion.data.AutomationStore
import kotlinx.coroutines.runBlocking
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import org.json.JSONObject
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class RecipeResumeProgressTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(DATABASE_NAME)
        store = AutomationStore(context)
    }

    @AfterTest
    fun tearDown() {
        store.close()
        context.deleteDatabase(DATABASE_NAME)
    }

    @Test
    fun `same task reload resumes pending state without replaying completed tap`() = runBlocking {
        val firstUi = FakeUi(failUnknownAt = "locator_b")
        val firstEngine = RecipeEngine(firstUi, elapsedMs = { 0L })
        val recipe = firstEngine.parse(hashed(recipeJson()))
        val command = command(recipe.hash)
        val progress = RecipeResumeProgress.fresh(recipe)

        val outcome = firstEngine.execute(recipe, command) { stateId, state ->
            progress.record(recipe, stateId, state)
        }
        assertEquals("WAITING_USER", outcome)
        val paused = progress.checkpoint(recipe)
        assertEquals("tapB", paused.nextStateId)
        assertEquals("tapA", paused.lastSuccessfulStateId)

        store.enqueueTask(command.taskId, "payload", "lease-1", 0)
        store.claimNext()
        store.saveCheckpoint(
            command.taskId,
            command.attemptId,
            paused.nextStateId,
            command.snapshotSha256,
            command.recipeSha256,
            command.accountId,
            command.bindingVersion,
            paused.lastSuccessfulStateIndex,
            paused.lastSuccessfulStateId,
        )
        store.close()
        store = AutomationStore(context)

        val reloaded = store.latestCheckpoint(command.taskId)
        assertNotNull(reloaded)
        assertEquals("tapB", reloaded!!.getString("stateId"))
        assertEquals("tapA", reloaded.getString("itemId"))
        val resumedProgress = RecipeResumeProgress.resume(recipe, command, reloaded)
        val resumedUi = FakeUi()
        val resumed = RecipeEngine(resumedUi, elapsedMs = { 0L }).execute(
            recipe,
            command,
            resumeFromStateId = resumedProgress.nextStateId,
        ) { stateId, state ->
            resumedProgress.record(recipe, stateId, state)
        }

        assertEquals("SUCCEEDED", resumed)
        assertEquals(listOf("locator_b"), resumedUi.taps)
    }

    @Test
    fun `failed transition follows onFailure without marking action successful`() = runBlocking {
        val ui = FakeUi(failAt = "locator_a")
        val engine = RecipeEngine(ui, elapsedMs = { 0L })
        val recipe = engine.parse(hashed(recipeJson()))
        val progress = RecipeResumeProgress.fresh(recipe)
        val observations = mutableListOf<String>()

        val outcome = engine.execute(recipe, command(recipe.hash)) { stateId, state ->
            progress.record(recipe, stateId, state)
            observations += "$stateId:$state:${progress.lastSuccessfulStateId}:${progress.nextStateId}"
        }

        assertEquals("SUCCEEDED", outcome)
        assertEquals("tapA:FAILED:null:tapB", observations[1])
        assertEquals(listOf("locator_b"), ui.taps)
    }

    @Test
    fun `resume rejects incomplete or incompatible checkpoint identity`() {
        val engine = RecipeEngine(FakeUi(), elapsedMs = { 0L })
        val recipe = engine.parse(hashed(recipeJson()))
        val command = command(recipe.hash)
        val checkpoint = JSONObject()
            .put("stateId", "tapB")
            .put("itemId", "tapA")
            .put("recipeHash", recipe.hash)
            .put("accountId", command.accountId)
            .put("bindingVersion", command.bindingVersion)

        val missing = assertFailsWith<ExecutorFailure> {
            RecipeResumeProgress.resume(recipe, command, JSONObject(checkpoint.toString()).put("accountId", ""))
        }
        assertEquals("RESUME_IDENTITY_MISSING", missing.code)

        val incompatible = assertFailsWith<ExecutorFailure> {
            RecipeResumeProgress.resume(recipe, command, JSONObject(checkpoint.toString()).put("recipeHash", "b".repeat(64)))
        }
        assertEquals("RESUME_RECIPE_INCOMPATIBLE", incompatible.code)
    }

    @Test
    fun `terminal WAITING_USER checkpoint stays persistable without a successor`() = runBlocking {
        // Task db2d6347 shape: the whole graph succeeds and the final checkpoint
        // state is terminal WAITING_USER - checkpoint() must yield the state
        // itself, not RESUME_NO_PENDING_STATE.
        val engine = RecipeEngine(FakeUi(), elapsedMs = { 0L })
        val recipe = engine.parse(hashed(openOnlyCheckpointJson()))
        val progress = RecipeResumeProgress.fresh(recipe)
        val outcome = engine.execute(recipe, command(recipe.hash)) { stateId, state ->
            progress.record(recipe, stateId, state)
        }
        assertEquals("WAITING_USER", outcome)
        val paused = progress.checkpoint(recipe)
        assertEquals("await-confirm", paused.nextStateId)
        assertEquals("await-confirm", paused.lastSuccessfulStateId)
    }

    private class FakeUi(
        private val failUnknownAt: String? = null,
        private val failAt: String? = null,
    ) : LocalAutomationUi {
        val taps = mutableListOf<String>()
        override fun ensureReady(targetPackage: String) = Unit
        override fun inspect(targetPackage: String, locatorRef: String) = LocalNodeState(true, true, true, true, "")
        override suspend fun tap(targetPackage: String, locatorRef: String) {
            if (locatorRef == failUnknownAt) throw ExecutorFailure("UNKNOWN_PAGE", locatorRef)
            if (locatorRef == failAt) throw ExecutorFailure("CLICK_FAILED", locatorRef)
            taps += locatorRef
        }
        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit
        override suspend fun screenshot(taskId: String, label: String) = ScreenshotEvidence("x", 1, "a")
        override fun log(level: LogLevel, messageCode: String) = Unit
    }

    private fun command(recipeSha256: String) = CommandV1(
        protocolVersion = CommandV1Parser.PROTOCOL,
        taskId = "task-resume",
        attemptId = "attempt-1",
        commandType = "xianyu.publish_listing.v1",
        deviceId = "device-1",
        accountId = "account-1",
        bindingVersion = 1,
        snapshotId = "snapshot-1",
        snapshotSha256 = "a".repeat(64),
        recipeVersionId = "recipe-1",
        recipeSha256 = recipeSha256,
        engineMinVersion = 1,
        targetPackage = "com.taobao.idlefish",
        requiredCapabilities = listOf("accessibility"),
        controlEpoch = 1,
        leaseExpiresAt = "2026-09-09T23:59:59Z",
        mediaDeliveryId = null,
        legacyStepsEnabled = false,
        parameters = JSONObject(),
    )

    private fun hashed(json: String): String {
        val root = JSONObject(json)
        root.getJSONObject("manifest").put(
            "hash",
            RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(root)),
        )
        return root.toString()
    }

    private fun recipeJson() = """
        {
          "apiVersion":"cloudctl.recipe/v1",
          "kind":"LocalRecipePackage",
          "manifest":{"id":"recipe-1","version":"1.0.0","hash":"${"a".repeat(64)}","signingKeyId":"prod-1","minEngineVersion":1,"platform":"xianyu","app":"com.taobao.idlefish","commandTypes":["xianyu.publish_listing.v1"]},
          "graph":{"startStateId":"tapA","maxIterations":12,"maxDurationMs":90000,"states":[
            {"stateId":"tapA","action":"tap","locatorRef":"locator_a","onSuccess":"tapB","onFailure":"tapB"},
            {"stateId":"tapB","action":"tap","locatorRef":"locator_b","onSuccess":"SUCCEEDED","onFailure":"FAILED"}
          ]},
          "signature":{"algorithm":"Ed25519","keyId":"prod-1","digest":"unsigned"}
        }
    """.trimIndent()

    private fun openOnlyCheckpointJson() = """
        {
          "apiVersion":"cloudctl.recipe/v1",
          "kind":"LocalRecipePackage",
          "manifest":{"id":"recipe-2","version":"1.0.0","hash":"${"b".repeat(64)}","signingKeyId":"prod-1","minEngineVersion":1,"platform":"xianyu","app":"com.taobao.idlefish","commandTypes":["xianyu.publish_listing.v1"]},
          "graph":{"startStateId":"tapA","maxIterations":12,"maxDurationMs":90000,"states":[
            {"stateId":"tapA","action":"tap","locatorRef":"locator_a","onSuccess":"await-confirm","onFailure":"FAILED"},
            {"stateId":"await-confirm","action":"checkpoint","onSuccess":"WAITING_USER","onPause":"WAITING_USER","terminal":true}
          ]},
          "signature":{"algorithm":"Ed25519","keyId":"prod-1","digest":"unsigned"}
        }
    """.trimIndent()

    private companion object {
        const val DATABASE_NAME = "cloudctl_automation.db"
    }
}
