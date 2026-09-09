package com.company.cloudctl.companion.service

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.automation.*
import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.network.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File
import java.io.IOException
import kotlin.test.*

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class ControlledActionExecutorTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore
    private lateinit var remote: FakeLedger
    private lateinit var executor: ControlledActionExecutor
    private lateinit var identity: ControlledActionIdentity
    private var effects = 0
    private var evidenceCalls = 0

    @Before fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
        store = AutomationStore(context)
        RecipeCatalog.putVerified(VERSION, RecipeCatalogTest.SIGNED_PROBE)
        val command = command()
        identity = ControlledActionIdentity.from(CommandV1Parser.parse(command.toString()), "probe")
        store.enqueueTask("task-1", JSONObject().put("deviceId", "device-1").put("command", command).toString(), "lease-1", 0)
        assertNotNull(store.claimNext())
        remote = FakeLedger()
        executor = ControlledActionExecutor(store, remote)
    }
    @After fun tearDown() { store.close(); context.deleteDatabase(AutomationStore.DATABASE_NAME); RecipeCatalog.clear() }

    @Test fun goldenIdentityMatchesFrozenFixture() {
        val root = generateSequence(File(".").canonicalFile) { it.parentFile }
            .first { File(it, "contracts/phase1/p09-action-identity-golden.json").isFile }
        val fixture = JSONObject(File(root, "contracts/phase1/p09-action-identity-golden.json").readText())
        val value = ControlledActionIdentity.fromJson(JSONObject(fixture.toString())
            .put("deviceId", "device-1").put("recipeVersionId", VERSION))
        assertEquals("p09-ledger/20260910.1", fixture.getString("contract"))
        assertEquals(fixture.getString("actionKey"), value.actionKey)
        assertEquals(fixture.getString("parameterHash"), value.parameterHash)
        assertEquals(value, ControlledActionIdentity.fromJson(value.toJson()))
        assertFailsWith<IllegalArgumentException> { value.copy(taskId = "task\n1") }
        assertFailsWith<IllegalArgumentException> { value.copy(actionId = "bad/action") }
        assertFailsWith<IllegalArgumentException> { value.copy(snapshotSha256 = "B".repeat(64)) }
    }

    @Test fun firstGrantReportsAppliedButRevisionZeroKeepsTaskBlocked() = runBlocking {
        val outcome = execute()
        assertEquals("APPLIED", outcome.journalStatus)
        assertTrue(outcome.actionInvoked)
        assertEquals(1, effects)
        assertEquals(1, evidenceCalls)
        assertEquals(listOf(ActionCommitStatus.APPLIED), remote.reports)
        assertFalse(executor.reconcile(identity.actionKey))
        assertBlocked()
        assertEquals(identity, store.controlledActionIdentity(identity.actionKey))
    }

    @Test fun localDuplicateNeverRequestsAnotherIntentOrEffect() = runBlocking {
        execute(); execute()
        assertEquals(1, effects)
        assertEquals(1, remote.intents)
        assertEquals(1, remote.reads)
        assertBlocked()
    }

    @Test fun duplicateServerDecisionNeverInvokesEffect() = runBlocking {
        remote.decision = ActionIntentDecision.RECONCILE_REQUIRED
        remote.httpStatus = 200
        assertFalse(execute().actionInvoked)
        assertEquals(0, effects)
        assertEquals(0, evidenceCalls)
        assertTrue(remote.reports.isEmpty())
        assertBlocked()
    }

    @Test fun authorizedOnHttp200IsNotAnExecutionGrant() = runBlocking {
        remote.httpStatus = 200
        assertFalse(execute().actionInvoked)
        assertBlocked()
    }

    @Test fun authorizedWithMismatchedIdentityIsNotAnExecutionGrant() = runBlocking {
        remote.row = remote.row.copy(deviceId = "other-device")
        assertFalse(execute().actionInvoked)
        assertBlocked()
    }

    @Test fun intentResponseLossNeverRepeatsEvenAfterRestart() = runBlocking {
        remote.loseIntent = true
        execute()
        assertEquals("UNKNOWN", store.actionJournal(identity.actionKey)?.status)
        reopen()
        execute()
        assertEquals(0, effects)
        assertEquals(1, remote.intents)
        assertEquals(1, remote.reads)
        assertBlocked()
    }

    @Test fun appliedResponseLossNeverReportsConflictingUnknownOrRepeats() = runBlocking {
        remote.loseOutcome = true
        execute(); reopen(); execute()
        assertEquals(1, effects)
        assertEquals(listOf(ActionCommitStatus.APPLIED), remote.reports)
        assertEquals("UNKNOWN", store.actionJournal(identity.actionKey)?.status)
        assertBlocked()
    }

    @Test fun processDeathAfterPersistedIntentUsesGetOnly() = runBlocking {
        store.recordActionIntent(identity.actionKey, identity.taskId, identity.parameterHash, identity)
        reopen(); execute()
        assertEquals(0, remote.intents)
        assertEquals(1, remote.reads)
        assertEquals(0, effects)
        assertBlocked()
    }

    @Test fun missingEvidenceReportsUnknownAndNeverRepeats() = runBlocking {
        execute(evidence = { null }); execute()
        assertEquals(1, effects)
        assertEquals(listOf(ActionCommitStatus.UNKNOWN), remote.reports)
        assertEquals("UNKNOWN", store.actionJournal(identity.actionKey)?.status)
        assertBlocked()
    }

    @Test fun evidenceFailureAfterEffectRemainsUnknown() = runBlocking {
        execute(evidence = { throw IOException("evidence unavailable") })
        assertEquals(1, effects)
        assertEquals(listOf(ActionCommitStatus.UNKNOWN), remote.reports)
        assertBlocked()
    }

    @Test fun effectFailureReportsUnknownWithoutCallingEvidence() = runBlocking {
        executor.execute("task-1", "probe", "before", effect = { throw IOException("effect failed") },
            postconditionEvidence = { evidenceCalls++; "post" })
        assertEquals(0, evidenceCalls)
        assertEquals(listOf(ActionCommitStatus.UNKNOWN), remote.reports)
        assertBlocked()
    }

    @Test fun cancellationAfterIntentPersistsUnknownBeforePropagating() = runBlocking {
        assertFailsWith<CancellationException> {
            executor.execute("task-1", "probe", "before", effect = { throw CancellationException("cancel") },
                postconditionEvidence = { "post" })
        }
        assertEquals("UNKNOWN", store.actionJournal(identity.actionKey)?.status)
        reopen(); assertBlocked()
    }

    @Test fun timeoutAfterIntentPersistsUnknownAndPropagates() = runBlocking {
        assertFailsWith<CancellationException> {
            executor.execute("task-1", "probe", "before", timeoutMs = 50,
                effect = { delay(5000) }, postconditionEvidence = { "post" })
        }
        assertEquals("UNKNOWN", store.actionJournal(identity.actionKey)?.status)
        assertBlocked()
    }

    @Test fun eachImmutableResolutionMismatchRemainsBlocked() = runBlocking {
        execute()
        val resolved = remote.row.copy(resolutionRevision = 1, resolutionEvidence = "operator", resolvedAt = NOW)
        val mismatches = listOf(
            resolved.copy(actionKey = "f".repeat(64)), resolved.copy(parameterHash = "f".repeat(64)),
            resolved.copy(taskId = "other-task"), resolved.copy(deviceId = "other-device"),
            resolved.copy(accountId = "other-account"), resolved.copy(bindingVersion = 2),
            resolved.copy(recipeVersionId = "other-version"), resolved.copy(recipeSha256 = "f".repeat(64)),
            resolved.copy(snapshotSha256 = "f".repeat(64)), resolved.copy(actionId = "other-action"),
        )
        for (row in mismatches) { remote.row = row; assertFalse(executor.reconcile(identity.actionKey)); assertBlocked() }
    }

    @Test fun resolutionRequiresPositiveRevisionEvidenceTimeAndTerminalStatus() = runBlocking {
        execute()
        val resolved = remote.row.copy(resolutionRevision = 1, resolutionEvidence = "operator", resolvedAt = NOW)
        for (row in listOf(resolved.copy(resolutionRevision = 0), resolved.copy(resolutionEvidence = null),
            resolved.copy(resolvedAt = null), resolved.copy(status = ActionCommitStatus.UNKNOWN))) {
            remote.row = row; assertFalse(executor.reconcile(identity.actionKey)); assertBlocked()
        }
    }

    @Test fun appliedResolutionAtomicallyConfirmsInboxAndSupersedesWithoutForgedAck() = runBlocking {
        store.enqueueStepEvent("task-1", "STEP_STARTED", 0)
        execute()
        remote.resolve(ActionCommitStatus.APPLIED)
        assertTrue(executor.reconcile(identity.actionKey))
        assertResolved("SUCCEEDED", "APPLIED")
        assertTrue(executor.reconcile(identity.actionKey))
        execute(); assertEquals(1, effects)
        reopen(); assertResolved("SUCCEEDED", "APPLIED")
    }

    @Test fun notSubmittedResolutionIsTerminalAndNeverExecutable() = runBlocking {
        remote.loseIntent = true
        execute()
        remote.resolve(ActionCommitStatus.NOT_SUBMITTED)
        assertTrue(executor.reconcile(identity.actionKey))
        assertResolved("FAILED", "NOT_SUBMITTED")
        reopen(); execute()
        assertEquals(0, effects)
        assertEquals(1, remote.intents)
        assertResolved("FAILED", "NOT_SUBMITTED")
        val result = IrreversibleActionGate(store).executeOnce(identity.actionKey, identity.taskId, identity.parameterHash) {
            error("resolved old key must not execute")
        }
        assertFalse(result.actionInvoked)
        assertEquals("NOT_SUBMITTED", result.journalStatus)
    }

    @Test fun notSubmittedCannotContradictLocalAppliedObservation() = runBlocking {
        execute(); remote.resolve(ActionCommitStatus.NOT_SUBMITTED)
        assertFalse(executor.reconcile(identity.actionKey)); assertBlocked()
    }

    @Test fun reportedAppliedSurvivesReopenAndBlocksFinishReplacementLeaseAndCatalog() = runBlocking {
        execute(); reopen()
        store.finish("task-1", true)
        val task = store.persistedTask("task-1")!!
        assertFalse(store.enqueueTask(task.taskId, task.payload, "replacement", 5))
        store.stageRecipeCatalog("{\"new\":\"version\"}")
        assertNotEquals("{\"new\":\"version\"}", store.activatePendingRecipeCatalog())
        assertBlocked()
    }

    @Test fun invalidActionAndThirdPartyCommandFailBeforeIntent() = runBlocking {
        assertFailsWith<IllegalArgumentException> { executor.execute("task-1", "missing", "before", effect = {}, postconditionEvidence = { "post" }) }
        store.writableDatabase.execSQL("UPDATE task_inbox SET payload=? WHERE task_id='task-1'", arrayOf(
            JSONObject().put("deviceId", "device-1").put("command", command().put("commandType", "xianyu.publish_listing.v1")
                .put("targetPackage", "com.taobao.idlefish")).toString()))
        assertFailsWith<IllegalArgumentException> { execute() }
        assertEquals(0, remote.intents)
        assertNull(store.actionJournal(identity.actionKey))
    }

    private suspend fun execute(evidence: suspend () -> String? = { evidenceCalls++; "post" }) =
        executor.execute("task-1", "probe", "before", effect = { effects++ }, postconditionEvidence = evidence)

    private fun reopen() { store.close(); store = AutomationStore(context); executor = ControlledActionExecutor(store, remote) }
    private fun taskState(): String = store.readableDatabase.rawQuery(
        "SELECT state FROM task_inbox WHERE task_id='task-1'", emptyArray(),
    ).use { check(it.moveToFirst()); it.getString(0) }
    private fun assertBlocked() {
        assertEquals(AutomationStore.STATE_RECONCILING, taskState())
        assertTrue(store.hasBlockingHead()); assertNull(store.claimNext())
    }
    private fun assertResolved(terminal: String, journal: String) {
        assertEquals(AutomationStore.STATE_TERMINAL_CONFIRMED, taskState())
        assertEquals(journal, store.actionJournal(identity.actionKey)?.status)
        assertFalse(store.hasBlockingHead()); assertTrue(store.pendingEvents().isEmpty())
        store.readableDatabase.rawQuery("SELECT terminal_state FROM task_inbox WHERE task_id='task-1'", emptyArray()).use {
            assertTrue(it.moveToFirst()); assertEquals(terminal, it.getString(0))
        }
        store.readableDatabase.rawQuery("SELECT id,delivered_at,superseded_at,superseded_reason FROM event_outbox", emptyArray()).use {
            while (it.moveToNext()) {
                assertTrue(it.isNull(1)); assertFalse(it.isNull(2)); assertEquals("SERVER_ACTION_RESOLUTION:1", it.getString(3))
                store.markDelivered(it.getLong(0)) // A stale upload response must not forge delivery after resolution.
            }
        }
        store.readableDatabase.rawQuery("SELECT COUNT(*) FROM event_outbox WHERE delivered_at IS NOT NULL", emptyArray()).use {
            assertTrue(it.moveToFirst()); assertEquals(0, it.getInt(0))
        }
    }

    private fun command() = JSONObject()
        .put("protocolVersion", "cloudctl.command/v1").put("taskId", "task-1").put("attemptId", "attempt-1")
        .put("commandType", "device.probe_capabilities.v1").put("deviceId", "device-1")
        .put("accountId", "account-1").put("bindingVersion", 1)
        .put("snapshot", JSONObject().put("id", "snapshot-1").put("sha256", "b".repeat(64)))
        .put("recipe", JSONObject().put("versionId", VERSION).put("sha256", HASH).put("engineMinVersion", 1))
        .put("targetPackage", "com.company.cloudctl.companion").put("requiredCapabilities", JSONArray())
        .put("lease", JSONObject().put("controlEpoch", 1).put("expiresAt", "2099-01-01T00:00:00Z"))
        .put("parameters", JSONObject())

    private inner class FakeLedger : ControlledActionLedger {
        var row = ActionCommit(identity.actionKey, identity.taskId, identity.deviceId, identity.accountId,
            identity.bindingVersion, identity.recipeVersionId, identity.recipeSha256, identity.snapshotSha256,
            identity.actionId, identity.parameterHash, ActionCommitStatus.INTENT, "before", null, 0, null, null, NOW, NOW)
        var decision = ActionIntentDecision.AUTHORIZED
        var httpStatus = 201
        var intents = 0
        var reads = 0
        var loseIntent = false
        var loseOutcome = false
        val reports = mutableListOf<ActionCommitStatus>()
        override suspend fun intent(taskId: String, request: ActionIntentRequest): ActionIntentResponse {
            intents++
            assertEquals(identity, store.controlledActionIdentity(identity.actionKey))
            assertEquals("INTENT", store.actionJournal(identity.actionKey)?.status)
            assertBlocked()
            if (loseIntent) throw IOException("response lost")
            return ActionIntentResponse(httpStatus, decision, row)
        }
        override suspend fun outcome(taskId: String, actionKey: String, request: ActionOutcomeRequest): ActionCommit {
            reports += request.status
            row = row.copy(status = request.status, reportedEvidence = request.evidence)
            if (loseOutcome) throw IOException("response lost")
            return row
        }
        override suspend fun get(taskId: String, actionKey: String): ActionCommit { reads++; return row }
        fun resolve(status: ActionCommitStatus) { row = row.copy(status = status, resolutionRevision = 1,
            resolutionEvidence = "operator", resolvedAt = NOW) }
    }
    companion object {
        private const val VERSION = "11111111-1111-7111-8111-111111111111"
        private const val HASH = "c37e24bc039a9d9048424a785b2a641d8d47b1f53d67af8cf0410b574448064e"
        private const val NOW = "2026-09-10T00:00:00Z"
    }
}
