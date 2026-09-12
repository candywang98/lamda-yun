package com.company.cloudctl.companion.automation

import android.content.Context
import android.content.ContextWrapper
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.network.ActionCommit
import com.company.cloudctl.companion.network.ActionCommitStatus
import com.company.cloudctl.companion.network.ActionIntentDecision
import com.company.cloudctl.companion.network.ActionIntentRequest
import com.company.cloudctl.companion.network.ActionIntentResponse
import com.company.cloudctl.companion.network.ActionOutcomeRequest
import com.company.cloudctl.companion.network.ControlledActionLedger
import com.company.cloudctl.companion.service.ControlledActionExecutor
import com.company.cloudctl.companion.service.RecipeCommitAdapter
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.IOException
import java.nio.file.Files

/** Isolated Recipe commit wiring on device storage. Never opens a third-party app or live ledger. */
@RunWith(AndroidJUnit4::class)
class RecipeCommitWiringInstrumentationTest {
    private lateinit var directory: File
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
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        directory = Files.createTempDirectory(instrumentation.targetContext.cacheDir.toPath(), "p09-commit-").toFile()
        context = object : ContextWrapper(instrumentation.context) {
            override fun getDatabasePath(name: String): File {
                require(name == AutomationStore.DATABASE_NAME)
                return File(directory, name)
            }
            override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?): SQLiteDatabase =
                SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name), factory)
            override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?, errorHandler: DatabaseErrorHandler?): SQLiteDatabase =
                SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name).path, factory, errorHandler)
        }
        reopen()
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

    @After fun cleanup() {
        if (::store.isInitialized) store.close()
        RecipeCatalog.clear()
        if (::directory.isInitialized) directory.deleteRecursively()
    }

    @Test fun markedCommitUsesLedgerOnceAndStaysReconciling() = runBlocking {
        assertEquals("RECONCILING", execute())
        assertEquals(1, ui.taps)
        assertEquals(1, remote.intents)
        assertEquals(ActionCommitStatus.APPLIED, remote.row.status)
        assertTrue(store.hasBlockingHead())
        assertEquals(listOf(identity.actionKey), store.unresolvedControlledActionKeys())
        reopen()
        assertTrue(store.hasBlockingHead())
        assertEquals(1, ui.taps)
    }

    @Test fun lostGrantAndReopenNeverRepeatIntentOrEffect() = runBlocking {
        remote.loseIntent = true
        execute()
        assertEquals(0, ui.taps)
        reopen()
        execute()
        assertEquals(1, remote.intents)
        assertEquals(0, ui.taps)
        assertTrue(store.hasBlockingHead())
        remote.resolve(ActionCommitStatus.NOT_SUBMITTED)
        assertEquals(listOf(identity.actionKey), ControlledActionExecutor(store, remote).reconcilePending())
        assertFalse(store.hasBlockingHead())
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
        execute()
        assertEquals(1, ui.taps)
    }

    private suspend fun execute(): String {
        val adapter = RecipeCommitAdapter(ControlledActionExecutor(store, remote), ui)
        val control: () -> Unit = {}
        val commit: suspend (RecipeState) -> Unit = { state -> adapter.execute(command, state, control) }
        val journal: (String, String) -> Unit = { _, _ -> error("commit must not emit ordinary success journal") }
        return engine.execute(
            recipe = recipe,
            command = command,
            resumeFromStateId = null,
            controlCheckpoint = control,
            commitAction = commit,
            journal = journal,
        )
    }
    private fun reopen() {
        if (::store.isInitialized) store.close()
        store = AutomationStore(context)
        assertEquals(directory.canonicalFile, File(store.writableDatabase.path).canonicalFile.parentFile)
    }

    private fun rehash() {
        encoded.getJSONObject("manifest").put("hash", RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(encoded)))
    }

    private class Ui : LocalAutomationUi {
        var taps = 0
        var visible = false
        override fun ensureReady(targetPackage: String) {}
        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? =
            if (visible && locatorRef == "companion_home_root") LocalNodeState(true, true, false, false, "observed") else null
        override suspend fun tap(targetPackage: String, locatorRef: String) { error("fallback tap forbidden") }
        override suspend fun tapOnce(targetPackage: String, locatorRef: String) {
            taps++
            visible = true
        }
        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) { error("unexpected input") }
        override suspend fun screenshot(taskId: String, label: String) = ScreenshotEvidence(
            "test/$label", 100, (if (!visible) "a" else "b").repeat(64))
        override fun log(level: LogLevel, messageCode: String) {}
    }

    private inner class Ledger : ControlledActionLedger {
        var intents = 0
        var loseIntent = false
        var row = ActionCommit(identity.actionKey, identity.taskId, identity.deviceId, identity.accountId,
            identity.bindingVersion, identity.recipeVersionId, identity.recipeSha256, identity.snapshotSha256,
            identity.actionId, identity.parameterHash, ActionCommitStatus.INTENT, "", null, 0, null, null, NOW, NOW)
        override suspend fun intent(taskId: String, request: ActionIntentRequest): ActionIntentResponse {
            intents++
            assertTrue(store.hasBlockingHead())
            row = row.copy(beforeEvidence = request.beforeEvidence)
            if (loseIntent) throw IOException("lost response")
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
