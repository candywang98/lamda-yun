package com.company.cloudctl.companion.service

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.automation.*
import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.network.*
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.IOException
import kotlin.test.*

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class RecipeCommitAdapterTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore
    private lateinit var command: CommandV1
    private lateinit var identity: ControlledActionIdentity
    private lateinit var recipe: RecipePackage
    private lateinit var encoded: JSONObject
    private lateinit var remote: Ledger
    private val ui = Ui()
    private val engine = RecipeEngine(ui, elapsedMs = { 1L })

    @Before fun setup() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
        store = AutomationStore(context)
        encoded = JSONObject("""{"apiVersion":"cloudctl.recipe/v1","kind":"LocalRecipePackage",
            "manifest":{"id":"commit-probe","version":"2.0.0","hash":"","minEngineVersion":2,
            "signingKeyId":"test","platform":"companion","app":"com.company.cloudctl.companion",
            "commandTypes":["device.probe_capabilities.v1"]},
            "graph":{"startStateId":"commit","commitActionId":"commit","maxIterations":8,"maxDurationMs":30000,
            "states":[{"stateId":"commit","action":"tap","locatorRef":"companion_refresh",
            "postcondition":"companion_home_root","onSuccess":"SUCCEEDED","terminal":true}]}}""")
        rehash()
        recipe = engine.parse(encoded.toString())
        val json = JSONObject().put("protocolVersion", "cloudctl.command/v1").put("taskId", "commit-task")
            .put("attemptId", "attempt-1").put("commandType", "device.probe_capabilities.v1")
            .put("deviceId", "device-1").put("accountId", "account-1").put("bindingVersion", 1)
            .put("snapshot", JSONObject().put("id", "snapshot-1").put("sha256", "b".repeat(64)))
            .put("recipe", JSONObject().put("versionId", recipe.id).put("sha256", recipe.hash).put("engineMinVersion", 2))
            .put("targetPackage", recipe.app).put("requiredCapabilities", JSONArray())
            .put("lease", JSONObject().put("controlEpoch", 1).put("expiresAt", "2099-01-01T00:00:00Z"))
            .put("parameters", JSONObject())
        command = CommandV1Parser.parse(json.toString())
        identity = ControlledActionIdentity.from(command, "commit")
        RecipeCatalog.putVerified(recipe.id, encoded.toString())
        store.enqueueTask(command.taskId, JSONObject().put("deviceId", command.deviceId).put("command", json).toString(), "lease-1", 0)
        assertNotNull(store.claimNext())
        remote = Ledger()
    }

    @After fun teardown() { store.close(); context.deleteDatabase(AutomationStore.DATABASE_NAME); RecipeCatalog.clear() }

    @Test fun engineUsesLedgerAndStopsBeforeOrdinarySuccess() = runBlocking {
        assertEquals("RECONCILING", execute())
        assertEquals(1, ui.taps)
        assertEquals(1, remote.intents)
        assertEquals(ActionCommitStatus.APPLIED, remote.row.status)
        assertTrue(store.hasBlockingHead())
        assertEquals(listOf(identity.actionKey), store.unresolvedControlledActionKeys())
    }

    @Test fun missingAdapterRejectsBeforeAnyAction() = runBlocking {
        val error = assertFailsWith<ExecutorFailure> { engine.execute(recipe, command, journal = { _, _ -> }) }
        assertEquals("COMMIT_ADAPTER_REQUIRED", error.code)
        assertEquals(0, ui.taps)
        assertEquals(0, remote.intents)
    }

    @Test fun responseLossAndRestartNeverRepeatIntentOrEffect() = runBlocking {
        remote.loseIntent = true
        execute()
        assertEquals(0, ui.taps)
        reopen()
        execute()
        assertEquals(1, remote.intents)
        assertEquals(0, ui.taps)
        assertTrue(store.hasBlockingHead())
        remote.resolve(ActionCommitStatus.NOT_SUBMITTED)
        val executor = ControlledActionExecutor(store, remote)
        assertEquals(listOf(identity.actionKey), executor.reconcilePending())
        assertFalse(store.hasBlockingHead())
        assertTrue(store.unresolvedControlledActionKeys().isEmpty())
        execute()
        assertEquals(0, ui.taps)
    }

    @Test fun reportedAppliedWaitsForPositiveResolutionRevision() = runBlocking {
        execute(); reopen()
        val executor = ControlledActionExecutor(store, remote)
        assertTrue(executor.reconcilePending().isEmpty())
        assertTrue(store.hasBlockingHead())
        remote.resolve(ActionCommitStatus.APPLIED)
        assertEquals(listOf(identity.actionKey), executor.reconcilePending())
        assertFalse(store.hasBlockingHead())
        assertTrue(executor.reconcilePending().isEmpty())
        execute()
        assertEquals(1, ui.taps)
    }

    @Test fun controlRevokedAfterGrantDoesNotTap() = runBlocking {
        remote.afterGrant = { ui.revoked = true }
        execute()
        assertEquals(0, ui.taps)
        assertEquals(ActionCommitStatus.UNKNOWN, remote.row.status)
        assertTrue(store.hasBlockingHead())
    }

    @Test fun existingPostconditionNeverRequestsIntent() = runBlocking {
        ui.visible = true
        assertEquals("POSTCONDITION_ALREADY_MET", assertFailsWith<ExecutorFailure> { execute() }.code)
        assertEquals(0, remote.intents)
        assertEquals(0, ui.taps)
    }

    @Test fun identicalBeforeAndAfterEvidenceIsUnknown() = runBlocking {
        ui.sameScreenshot = true
        execute()
        assertEquals(1, ui.taps)
        assertEquals(ActionCommitStatus.UNKNOWN, remote.row.status)
        assertTrue(store.hasBlockingHead())
    }

    @Test fun singleShotFailureCannotUseFallbackOrGraphFailure() = runBlocking {
        ui.rejectTap = true
        execute(); execute()
        assertEquals(1, ui.taps)
        assertEquals(ActionCommitStatus.UNKNOWN, remote.row.status)
        assertTrue(store.hasBlockingHead())
    }

    @Test fun platformCommitFailsBeforeIntentAndUi() = runBlocking {
        val thirdParty = command.copy(commandType = "xianyu.publish_listing.v1", targetPackage = "com.taobao.idlefish")
        assertEquals("G3_NOT_ACCEPTED", assertFailsWith<ExecutorFailure> {
            RecipeCommitAdapter(ControlledActionExecutor(store, remote), ui).execute(thirdParty, recipe.states.getValue("commit")) {}
        }.code)
        assertEquals(0, remote.intents)
        assertEquals(0, ui.taps)
    }

    @Test fun oldEngineCannotParseCommitAndNewEngineRejectsOldMinimum() {
        assertFailsWith<IllegalArgumentException> { RecipeEngine(ui, engineVersion = 1, elapsedMs = { 0 }).parse(encoded.toString()) }
        encoded.getJSONObject("manifest").put("minEngineVersion", 1)
        rehash()
        assertFailsWith<IllegalArgumentException> { engine.parse(encoded.toString()) }
    }

    @Test fun malformedCommitAndUnguardedPublishAreRejected() {
        val original = encoded.toString()
        for (mutation in listOf<(JSONObject) -> Unit>(
            { it.put("commitActionId", "missing") },
            { it.getJSONArray("states").getJSONObject(0).put("onFailure", "commit") },
            { it.getJSONArray("states").getJSONObject(0).put("postcondition", "companion_refresh") },
            { it.getJSONArray("states").getJSONObject(0).remove("postcondition") },
            { it.remove("commitActionId"); it.getJSONArray("states").getJSONObject(0).put("locatorRef", "xianyu_publish_button") },
        )) {
            encoded = JSONObject(original)
            mutation(encoded.getJSONObject("graph")); rehash()
            assertFailsWith<IllegalArgumentException> { engine.parse(encoded.toString()) }
        }
    }

    private suspend fun execute(): String {
        val adapter = RecipeCommitAdapter(ControlledActionExecutor(store, remote), ui)
        val control = { if (ui.revoked) throw ExecutorFailure("LEASE_LOST", "test lease lost") }
        return engine.execute(recipe, command, controlCheckpoint = control,
            commitAction = { adapter.execute(command, it, control) },
            journal = { _, _ -> error("commit must not emit ordinary success journal") })
    }
    private fun reopen() { store.close(); store = AutomationStore(context) }
    private fun rehash() { encoded.getJSONObject("manifest").put("hash", RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(encoded))) }

    private class Ui : LocalAutomationUi {
        var taps = 0
        var visible = false
        var revoked = false
        var sameScreenshot = false
        var rejectTap = false
        override fun ensureReady(targetPackage: String) {}
        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? =
            if (visible && locatorRef == "companion_home_root") LocalNodeState(true, true, false, false, "observed") else null
        override suspend fun tap(targetPackage: String, locatorRef: String) { error("fallback tap forbidden") }
        override suspend fun tapOnce(targetPackage: String, locatorRef: String) {
            taps++
            if (rejectTap) throw ExecutorFailure("CLICK_UNCONFIRMED", "test")
            visible = true
        }
        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) { error("unexpected input") }
        override suspend fun screenshot(taskId: String, label: String) = ScreenshotEvidence(
            "test/$label", 100, (if (sameScreenshot || !visible) "a" else "b").repeat(64))
        override fun log(level: LogLevel, messageCode: String) {}
    }

    private inner class Ledger : ControlledActionLedger {
        var intents = 0
        var loseIntent = false
        var afterGrant: () -> Unit = {}
        var row = ActionCommit(identity.actionKey, identity.taskId, identity.deviceId, identity.accountId,
            identity.bindingVersion, identity.recipeVersionId, identity.recipeSha256, identity.snapshotSha256,
            identity.actionId, identity.parameterHash, ActionCommitStatus.INTENT, "", null, 0, null, null, NOW, NOW)
        override suspend fun intent(taskId: String, request: ActionIntentRequest): ActionIntentResponse {
            intents++
            assertTrue(store.hasBlockingHead())
            row = row.copy(beforeEvidence = request.beforeEvidence)
            if (loseIntent) throw IOException("lost response")
            afterGrant()
            return ActionIntentResponse(201, ActionIntentDecision.AUTHORIZED, row)
        }
        override suspend fun outcome(taskId: String, actionKey: String, request: ActionOutcomeRequest): ActionCommit {
            row = row.copy(status = request.status, reportedEvidence = request.evidence)
            return row
        }
        override suspend fun get(taskId: String, actionKey: String) = row
        fun resolve(status: ActionCommitStatus) { row = row.copy(status = status, resolutionRevision = 1,
            resolutionEvidence = "test-operator-evidence", resolvedAt = NOW) }
    }
    companion object { private const val NOW = "2026-09-12T00:00:00Z" }
}
