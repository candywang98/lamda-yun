package com.company.cloudctl.companion.service

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.automation.AutomationStep
import com.company.cloudctl.companion.automation.AutomationTask
import com.company.cloudctl.companion.automation.ControlledActionIdentity
import com.company.cloudctl.companion.automation.LocalAutomationUi
import com.company.cloudctl.companion.automation.LocalNodeState
import com.company.cloudctl.companion.automation.LogLevel
import com.company.cloudctl.companion.automation.ScreenshotEvidence
import com.company.cloudctl.companion.automation.TargetLocatorRegistry
import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.network.ActionCommit
import com.company.cloudctl.companion.network.ActionCommitStatus
import com.company.cloudctl.companion.network.ActionIntentDecision
import com.company.cloudctl.companion.network.ActionIntentRequest
import com.company.cloudctl.companion.network.ActionIntentResponse
import com.company.cloudctl.companion.network.ActionOutcomeRequest
import com.company.cloudctl.companion.network.ControlledActionLedger
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.time.Instant
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class XianyuMaintenanceCommitGateTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
        store = AutomationStore(context)
    }

    @After
    fun tearDown() {
        store.close()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
    }

    @Test
    fun semanticDeleteStrikesOnceThenOnlyReconcilesUnknown() = runBlocking {
        val payload = payload()
        store.enqueueTask(TASK_ID, payload.toString(), LEASE_ID, 0)
        assertNotNull(store.claimNext())
        val identity = ControlledActionIdentity.fromMaintenanceStepsPayload(
            payload,
            XianyuMaintenanceCommitGate.ACTION_CONFIRM_DELETE,
        )
        val remote = FakeLedger(identity)
        val ui = FakeUi()
        val gate = XianyuMaintenanceCommitGate(ControlledActionExecutor(store, remote), ui)
        val task = task()

        gate.confirmOnce(task, XianyuMaintenanceCommitGate.DELETE_CONFIRM_LOCATOR)
        gate.confirmOnce(task, XianyuMaintenanceCommitGate.DELETE_CONFIRM_LOCATOR)

        assertEquals(1, ui.singleShotTaps)
        assertEquals(1, remote.intents)
        assertEquals(listOf(ActionCommitStatus.UNKNOWN), remote.reports)
        assertEquals(1, remote.reads)
        assertEquals("UNKNOWN", store.actionJournal(identity.actionKey)?.status)
    }

    private fun payload() = JSONObject()
        .put("taskId", TASK_ID)
        .put("deviceId", DEVICE_ID)
        .put("targetPackage", TargetLocatorRegistry.XIANYU_PACKAGE)
        .put("commandType", "xianyu.delete_delisted.steps.v2")
        .put(
            "steps",
            JSONArray().put(
                JSONObject()
                    .put("stepId", "confirm-delete")
                    .put("action", "ui.tap")
                    .put("locatorRef", XianyuMaintenanceCommitGate.DELETE_CONFIRM_LOCATOR)
                    .put("timeoutMs", 8_000),
            ),
        )

    private fun task() = AutomationTask(
        taskId = TASK_ID,
        deviceId = DEVICE_ID,
        targetPackage = TargetLocatorRegistry.XIANYU_PACKAGE,
        issuedAt = Instant.parse("2026-09-16T00:00:00Z"),
        expiresAt = Instant.parse("2099-01-01T00:00:00Z"),
        maxRunSeconds = 60,
        steps = listOf(
            AutomationStep.Tap(
                "confirm-delete",
                8_000,
                XianyuMaintenanceCommitGate.DELETE_CONFIRM_LOCATOR,
                null,
            ),
        ),
    )

    private class FakeUi : LocalAutomationUi {
        var singleShotTaps = 0

        override fun ensureReady(targetPackage: String) {
            check(targetPackage == TargetLocatorRegistry.XIANYU_PACKAGE)
        }

        override fun inspect(targetPackage: String, locatorRef: String) = LocalNodeState(
            enabled = true,
            visible = true,
            clickable = true,
            editable = false,
            text = "确定",
        )

        override suspend fun tapOnce(targetPackage: String, locatorRef: String) {
            check(locatorRef == XianyuMaintenanceCommitGate.DELETE_CONFIRM_LOCATOR)
            singleShotTaps++
        }

        override suspend fun tap(targetPackage: String, locatorRef: String) = error("unexpected ordinary tap")
        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) =
            error("unexpected input")

        override suspend fun screenshot(taskId: String, label: String) =
            ScreenshotEvidence("/private/$label.png", 32, "a".repeat(64))

        override fun log(level: LogLevel, messageCode: String) = Unit
    }

    private class FakeLedger(private val identity: ControlledActionIdentity) : ControlledActionLedger {
        var intents = 0
        var reads = 0
        val reports = mutableListOf<ActionCommitStatus>()
        private var row = commit(ActionCommitStatus.INTENT)

        override suspend fun intent(taskId: String, request: ActionIntentRequest): ActionIntentResponse {
            intents++
            row = row.copy(beforeEvidence = request.beforeEvidence)
            return ActionIntentResponse(201, ActionIntentDecision.AUTHORIZED, row)
        }

        override suspend fun outcome(
            taskId: String,
            actionKey: String,
            request: ActionOutcomeRequest,
        ): ActionCommit {
            reports += request.status
            row = row.copy(status = request.status, reportedEvidence = request.evidence)
            return row
        }

        override suspend fun get(taskId: String, actionKey: String): ActionCommit {
            reads++
            return row
        }

        private fun commit(status: ActionCommitStatus) = ActionCommit(
            actionKey = identity.actionKey,
            taskId = identity.taskId,
            deviceId = identity.deviceId,
            accountId = identity.accountId,
            bindingVersion = identity.bindingVersion,
            recipeVersionId = identity.recipeVersionId,
            recipeSha256 = identity.recipeSha256,
            snapshotSha256 = identity.snapshotSha256,
            actionId = identity.actionId,
            parameterHash = identity.parameterHash,
            status = status,
            beforeEvidence = "sha256:${"b".repeat(64)}",
            reportedEvidence = null,
            resolutionRevision = 0,
            resolutionEvidence = null,
            resolvedAt = null,
            createdAt = "2026-09-16T00:00:00Z",
            updatedAt = "2026-09-16T00:00:00Z",
        )
    }

    companion object {
        private const val TASK_ID = "task-delete-v2"
        private const val DEVICE_ID = "device-oneplus"
        private const val LEASE_ID = "lease-delete-v2"
    }
}
