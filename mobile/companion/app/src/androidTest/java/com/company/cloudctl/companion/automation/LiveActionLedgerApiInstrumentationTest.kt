package com.company.cloudctl.companion.automation

import android.content.Context
import android.content.ContextWrapper
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.company.cloudctl.companion.BuildConfig
import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.network.ActionCommitStatus
import com.company.cloudctl.companion.network.ActionIntentDecision
import com.company.cloudctl.companion.network.ActionIntentRequest
import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.CloudTaskClient
import com.company.cloudctl.companion.network.PinnedControlledActionLedger
import com.company.cloudctl.companion.network.PinnedHttpsTransport
import com.company.cloudctl.companion.security.SecretStore
import com.company.cloudctl.companion.service.ControlledActionExecutor
import com.company.cloudctl.companion.updates.RecipePackageManager
import com.company.cloudctl.companion.updates.RecipeReference
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Root-only, pre-created Companion probe tasks. Never invokes third-party UI. */
@RunWith(AndroidJUnit4::class)
class LiveActionLedgerApiInstrumentationTest {
    private data class Acceptance(
        val taskId: String, val directory: File, val context: Context,
        val connection: CloudConnection, val fault: Boolean,
    )

    private fun acceptance(mode: String): Acceptance {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        val task = args.getString("liveTaskId")
        assumeTrue("Root must opt in with a task and mode", task != null && args.getString("liveMode") == mode)
        require(Regex("^[a-f0-9-]{36}$").matches(task!!))
        val target = instrumentation.targetContext
        val binding = JSONObject(requireNotNull(target.getSharedPreferences("cloudctl_binding", Context.MODE_PRIVATE).getString("binding", null)))
        require(binding.getString("deviceId") == args.getString("liveDeviceId"))
        // Credentials stay in the app process, are never printed, exported, or changed.
        val connection = CloudConnection(binding.getString("cloudUrl"), requireNotNull(SecretStore(target).get("binding_token")), binding.getString("certificateSha256"))
        val directory = File(target.cacheDir, "p09-live-ledger-$task")
        val context = object : ContextWrapper(instrumentation.context) {
            override fun getDatabasePath(name: String): File {
                require(name == AutomationStore.DATABASE_NAME)
                return File(directory, name)
            }
            override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?): SQLiteDatabase =
                SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name), factory)
            override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?, errorHandler: DatabaseErrorHandler?): SQLiteDatabase =
                SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name).path, factory, errorHandler)
        }
        return Acceptance(task, directory, context, connection, args.getString("liveFault") == "true")
    }

    @Test fun executeOnceAgainstLiveLedger() = runBlocking {
        val a = acceptance("execute")
        check(!a.directory.exists()) { "Acceptance directory already exists; do not repeat the effect" }
        check(a.directory.mkdirs())
        val client = CloudTaskClient(a.connection)
        val claim = requireNotNull(client.claim())
        assertEquals(a.taskId, claim.taskId)
        val command = requireNotNull(ClaimedTaskInterpreter.commandOrNull(claim.taskPayload))
        assertEquals("device.probe_capabilities.v1", command.commandType)
        assertEquals("com.company.cloudctl.companion", command.targetPackage)
        client.heartbeat(claim.taskId, claim.leaseId, null)
        File(a.directory, "claim.json").writeText(claim.taskPayload)
        val identity = ControlledActionIdentity.from(command, "probe")
        File(a.directory, "identity.json").writeText(identity.toJson().toString())
        val keyJson = JSONObject(BuildConfig.RECIPE_SIGNING_PUBLIC_KEYS)
        val keys = keyJson.keys().asSequence().associateWith { keyJson.getString(it) }
        val downloaded = client.downloadRecipe(command.recipeVersionId)
        RecipePackageManager(File(a.directory, "recipes"), keys).install(
            RecipeReference(command.recipeVersionId, command.recipeSha256, command.engineMinVersion),
            downloaded.body.toString(Charsets.UTF_8),
        )
        val beforeEvidence = "android-test://${a.taskId}/counter/0"
        val afterEvidence = "android-test://${a.taskId}/counter/1"
        val counter = File(a.directory, "counter")
        val expectedCount = if (a.fault) "0" else "1"
        val remote = PinnedControlledActionLedger(a.connection)
        AutomationStore(a.context).use { store ->
            assertEquals(a.directory.canonicalFile, File(store.writableDatabase.path).canonicalFile.parentFile)
            store.enqueueTask(claim.taskId, claim.taskPayload, claim.leaseId, claim.lastSequence)
            assertNotNull(store.claimNext())
            val executor = ControlledActionExecutor(store, remote)
            val outcome = executor.execute(
                taskId = claim.taskId, actionId = "probe", beforeEvidence = beforeEvidence,
                timeoutMs = 30000,
                effect = {
                    val count = if (counter.exists()) counter.readText().toInt() else 0
                    counter.writeText((count + 1).toString())
                },
                postconditionEvidence = { check(counter.readText() == "1"); afterEvidence },
            )
            assertEquals(if (a.fault) "UNKNOWN" else "APPLIED", outcome.journalStatus)
            assertEquals(!a.fault, outcome.actionInvoked)
            assertEquals(expectedCount, if (counter.exists()) counter.readText() else "0")
            assertTrue(store.hasBlockingHead())
            assertFalse(executor.reconcile(identity.actionKey))
            val row = remote.get(claim.taskId, identity.actionKey)
            assertEquals(if (a.fault) ActionCommitStatus.INTENT else ActionCommitStatus.APPLIED, row.status)
            assertEquals(0L, row.resolutionRevision)
            val duplicate = remote.intent(claim.taskId, ActionIntentRequest(
                claim.leaseId, "probe", identity.actionKey, identity.parameterHash, beforeEvidence,
            ))
            assertEquals(200, duplicate.httpStatus)
            assertEquals(ActionIntentDecision.RECONCILE_REQUIRED, duplicate.decision)
            val changed = request(a.connection, "/companion/v2/tasks/${claim.taskId}/actions/intent", JSONObject()
                .put("leaseId", claim.leaseId).put("actionId", "probe").put("actionKey", identity.actionKey)
                .put("parameterHash", "0".repeat(64)).put("beforeEvidence", beforeEvidence))
            assertEquals(409, changed.first)
            assertEquals(expectedCount, if (counter.exists()) counter.readText() else "0")
        }
        println("P09_LIVE_LEDGER task=${a.taskId} action=${identity.actionKey} counter=$expectedCount blocked=true")
    }

    @Test fun applyExplicitServerResolutionWithoutReplay() = runBlocking {
        val a = acceptance("resolve")
        require(a.directory.isDirectory)
        val identity = ControlledActionIdentity.fromJson(JSONObject(File(a.directory, "identity.json").readText()))
        val counter = File(a.directory, "counter")
        val expectedCount = if (a.fault) "0" else "1"
        val remote = PinnedControlledActionLedger(a.connection)
        RecipeCatalog.clear() // Resolution must work from durable identity, not cached recipes.
        AutomationStore(a.context).use { store ->
            assertTrue(store.hasBlockingHead())
            val row = remote.get(a.taskId, identity.actionKey)
            assertTrue(row.resolutionRevision > 0)
            assertEquals(if (a.fault) ActionCommitStatus.NOT_SUBMITTED else ActionCommitStatus.APPLIED, row.status)
            val executor = ControlledActionExecutor(store, remote)
            assertTrue(executor.reconcile(identity.actionKey))
            assertFalse(store.hasBlockingHead())
            store.readableDatabase.rawQuery("SELECT state,terminal_state FROM task_inbox WHERE task_id=?", arrayOf(a.taskId)).use {
                check(it.moveToFirst())
                assertEquals("TERMINAL_CONFIRMED", it.getString(0))
                assertEquals(if (a.fault) "FAILED" else "SUCCEEDED", it.getString(1))
            }
            val replay = executor.execute(a.taskId, "probe", "android-test://${a.taskId}/counter/0",
                effect = { error("Resolved action must never be invoked again") },
                postconditionEvidence = { error("Resolved action must not rerun observation") })
            assertFalse(replay.actionInvoked)
            assertEquals(expectedCount, if (counter.exists()) counter.readText() else "0")
            assertTrue(store.pendingEvents().isEmpty())
            store.readableDatabase.rawQuery("SELECT count(*) FROM event_outbox WHERE delivered_at IS NOT NULL", emptyArray()).use {
                check(it.moveToFirst()); assertEquals(0, it.getInt(0))
            }
        }
        println("P09_LIVE_RESOLVED task=${a.taskId} counter=$expectedCount noReplay=true noForgedAck=true")
    }

    private fun request(connection: CloudConnection, path: String, body: JSONObject): Pair<Int, JSONObject> {
        val response = PinnedHttpsTransport.request(connection.baseUrl, path, connection.certificateSha256,
            "POST", mapOf("Authorization" to "Bearer ${connection.bearerToken}", "Content-Type" to "application/json", "Accept" to "application/json"),
            body.toString().toByteArray(Charsets.UTF_8), 10000, 15000)
        return response.first to JSONObject(response.second)
    }
}
