package com.company.cloudctl.companion.features.xianyu.orders

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.automation.*
import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.CloudHttpException
import com.company.cloudctl.companion.network.ClaimedTask
import com.company.cloudctl.companion.network.addOrderDeliveryCapability
import com.company.cloudctl.companion.network.buildClaimedTaskPayload
import com.company.cloudctl.companion.service.acceptedClaimDeviceId
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.time.Instant
import kotlin.test.*

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class OrderDeliveryIntegrationTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore
    private val fixed = Instant.parse("2026-09-26T08:00:00Z")
    private var deliveryTime = Instant.parse("2099-01-01T00:00:00Z")
    private val scope = "scope-original"
    private val a = listOf("buyer-a", "item-a", "25")
    private val b = listOf("buyer-b", "item-b", "30")
    private val locator = "xianyu_orders_container"

    @BeforeTest fun setup() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
        store = AutomationStore(context)
    }

    @AfterTest fun teardown() {
        store.close()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
    }

    private fun task(id: String = "task-1", screens: Int = 2): AutomationTask = AutomationTask(
        id, "device-1", "com.taobao.idlefish", fixed, fixed.plusSeconds(600), 120,
        buildList {
            repeat(screens) { index ->
                if (index > 0) add(AutomationStep.SwipeUp("swipe-${index + 1}", 1000, locator))
                add(AutomationStep.ReadOrders("read-${index + 1}", 1000, OrderDirection.SOLD, 10, locator))
            }
        },
    )

    private fun payload(task: AutomationTask): JSONObject = JSONObject()
        .put("protocolVersion", "cloudctl.mobile/v1").put("taskId", task.taskId)
        .put("deviceId", task.deviceId).put("targetPackage", task.targetPackage)
        .put("issuedAt", task.issuedAt.toString()).put("expiresAt", task.expiresAt.toString())
        .put("maxRunSeconds", task.maxRunSeconds).put("accountId", "account-1").put("bindingVersion", 7)
        .put("orderDelivery", JSONObject().put("protocolVersion", ORDER_DELIVERY_PROTOCOL)
            .put("mobileBindingId", "mobile-1").put("direction", "SOLD")
            .put("maxScreens", task.steps.count { it is AutomationStep.ReadOrders }))
        .put("steps", JSONArray(task.steps.map { step ->
            JSONObject().put("stepId", step.stepId).put("timeoutMs", step.timeoutMs)
                .put("action", if (step is AutomationStep.ReadOrders) "ui.readOrders" else "ui.swipeUp")
                .put("locatorRef", locator).apply {
                    if (step is AutomationStep.ReadOrders) put("direction", "SOLD").put("maxRows", 10)
                }
        }))

    private fun identity(task: AutomationTask) = OrderDeliveryIdentity.fromTask(payload(task), task)!!

    private fun enroll(task: AutomationTask): OrderDeliveryIdentity {
        store.enqueueTask(task.taskId, payload(task).toString(), "lease-1", 0)
        assertEquals(task.taskId, store.claimNext()?.taskId)
        store.openOrderRun(identity(task), scope, false)
        return identity(task)
    }

    private fun session(task: AutomationTask, resume: Boolean = false): OrderDeliverySession {
        val identity = identity(task)
        return OrderDeliverySession(identity, store.openOrderRun(identity, scope, resume),
            { store.commitOrderRead(identity, it) }, { store.recordOrderStop(task.taskId, it) })
    }

    private fun journal(task: AutomationTask): (AutomationStep, String) -> Unit = { step, state ->
        store.recordStepEvent(task.taskId, step.stepId, state, "STEP_$state", "STEP_$state",
            task.steps.indexOf(step), JSONObject().put("detailCode", "STEP_$state"))
    }

    private fun executor(ui: Ui, session: OrderDeliverySession) = LocalAutomationExecutor(
        ui, now = { fixed }, elapsedMs = { 0 }, sleep = {},
        orderReporter = OrderReporter { _, _, _, _, _ -> error("Legacy batch must not run") },
        orderScreensReporter = OrderScreensReporter { _, _, _, _, _, _ -> error("Legacy screens must not run") },
        orderDelivery = session,
    )

    private fun read(screen: Int = 1, rows: List<List<String>> = listOf(a)) =
        SavedOrderRead(screen, "read-$screen", (screen - 1) * 2, fixed.toString(), rows)

    private fun count(table: String, where: String = "1=1"): Int =
        store.readableDatabase.rawQuery("SELECT count(*) FROM $table WHERE $where", null).use {
            it.moveToFirst(); it.getInt(0)
        }

    private fun ack(envelope: JSONObject, replayed: Boolean = false) = JSONObject()
        .put("protocolVersion", envelope.getString("protocolVersion"))
        .put("taskId", envelope.getString("taskId")).put("kind", envelope.getString("kind"))
        .put("screen", envelope.getInt("screen")).put("payloadSha256", envelope.getString("payloadSha256"))
        .put("accepted", true).put("replayed", replayed)

    private suspend fun flush(send: suspend (JSONObject) -> JSONObject) {
        OrderDeliverySender(store) { deliveryTime }.flush(scope, send)
    }

    @Test fun singleScreenUsesDurableChannelAndAtomicComplete() = runBlocking {
        val task = task(screens = 1)
        enroll(task)
        executor(Ui(listOf(listOf(a))), session(task)).execute(task, journal = journal(task))
        assertEquals(1, count("order_delivery_outbox"))
        assertEquals(1, count("run_journal", "state='SUCCEEDED'"))
        store.finish(task.taskId, true)
        assertEquals(2, count("order_delivery_outbox"))
        val sent = mutableListOf<JSONObject>()
        repeat(2) { flush { sent += it; ack(it) } }
        assertEquals(listOf("SCREEN", "COMPLETE"), sent.map { it.getString("kind") })
        val complete = JSONObject(sent.last().getString("payloadJson"))
        assertEquals(1, complete.getInt("totalScreens"))
        assertEquals("PLAN_FINISHED", complete.getString("stopReason"))
    }

    @Test fun multiScreenPersistsBeforeScrollAndNeverDualWrites() = runBlocking {
        val task = task()
        enroll(task)
        val ui = Ui(listOf(listOf(a), listOf(a, b)))
        ui.onSwipe = {
            assertEquals(1, count("order_delivery_outbox"))
            assertEquals(1, count("run_journal", "state='SUCCEEDED' AND step_id='read-1'"))
        }
        executor(ui, session(task)).execute(task, journal = journal(task))
        store.finish(task.taskId, true)
        assertEquals(1, ui.swipes)
        val sent = mutableListOf<Int>()
        repeat(3) { flush { sent += it.getInt("screen"); ack(it) } }
        assertEquals(listOf(1, 2, 0), sent)
        assertEquals(3, count("order_delivery_outbox", "delivery_state='ACKED'"))
    }

    @Test fun failedSuccessJournalRollsBackCaptureAndDoesNotScroll() = runBlocking {
        val task = task()
        enroll(task)
        store.writableDatabase.execSQL("CREATE TRIGGER fail_read BEFORE INSERT ON run_journal " +
            "WHEN NEW.state='SUCCEEDED' BEGIN SELECT RAISE(ABORT,'fault'); END")
        val ui = Ui(listOf(listOf(a), listOf(b)))
        assertFails { executor(ui, session(task)).execute(task, journal = journal(task)) }
        assertEquals(0, ui.swipes)
        assertEquals(0, count("order_delivery_outbox"))
        assertEquals(0, count("run_journal", "state='SUCCEEDED'"))
        assertEquals(1, store.openOrderRun(identity(task), scope, true).inFlightStepIndex?.let { 1 })
    }

    @Test fun terminalEventFailureRollsBackCompleteAndTaskSuccess() {
        val task = task(screens = 1)
        val identity = enroll(task)
        store.commitOrderRead(identity, read())
        store.writableDatabase.execSQL("CREATE TRIGGER fail_terminal BEFORE INSERT ON event_outbox " +
            "WHEN NEW.is_terminal=1 BEGIN SELECT RAISE(ABORT,'fault'); END")
        assertFails { store.finish(task.taskId, true) }
        assertEquals(0, count("order_delivery_outbox", "kind='COMPLETE'"))
        assertEquals(0, count("run_journal", "state='SUCCEEDED' AND step_id IS NULL"))
        assertEquals(0, count("task_inbox", "terminal_state='SUCCEEDED'"))
    }

    @Test fun processReopenAndAckLossPreserveExactPayload() = runBlocking {
        val task = task(screens = 1)
        store.commitOrderRead(enroll(task), read(rows = listOf(listOf("buyer", "item", "42"))))
        var first = ""
        flush { first = it.toString(); throw java.io.IOException("ACK lost") }
        store.close()
        store = AutomationStore(context)
        deliveryTime = deliveryTime.plusSeconds(301)
        flush { assertEquals(first, it.toString()); ack(it, replayed = true) }
        assertEquals(1, count("order_delivery_outbox", "delivery_state='ACKED'"))
    }

    @Test fun retries429And503WithoutLettingLaterScreensOvertake() = runBlocking {
        val task = task()
        val identity = enroll(task)
        store.commitOrderRead(identity, read())
        store.commitOrderRead(identity, read(2))
        for (status in listOf(429, 503)) {
            flush { assertEquals(1, it.getInt("screen")); throw CloudHttpException(status, "ignored") }
            assertTrue(store.dueOrderDeliveries(scope, deliveryTime).isEmpty())
            deliveryTime = deliveryTime.plusSeconds(301)
        }
        flush { assertEquals(1, it.getInt("screen")); ack(it) }
        flush { assertEquals(2, it.getInt("screen")); ack(it) }
    }

    @Test fun everyAckIdentityFieldIsValidated() = runBlocking {
        val task = task(screens = 1)
        store.commitOrderRead(enroll(task), read())
        val mismatches = mapOf<String, Any>(
            "protocolVersion" to "other", "taskId" to "other", "kind" to "COMPLETE",
            "screen" to 2, "payloadSha256" to "b".repeat(64), "accepted" to false, "replayed" to "true",
        )
        for ((field, value) in mismatches) {
            flush { ack(it).put(field, value) }
            assertEquals(0, count("order_delivery_outbox", "delivery_state='ACKED'"))
            deliveryTime = deliveryTime.plusSeconds(301)
        }
        flush { JSONObject() }
        assertEquals(0, count("order_delivery_outbox", "delivery_state='ACKED'"))
    }

    @Test fun conflictBlocksOnlyItsRunAndKeepsAllRecords() = runBlocking {
        val first = task("first")
        val second = task("second", 1)
        val identity = enroll(first)
        store.commitOrderRead(identity, read())
        store.commitOrderRead(identity, read(2))
        store.finish(first.taskId, false)
        store.commitOrderRead(enroll(second), read())
        flush {
            if (it.getString("taskId") == "first") throw CloudHttpException(409, "private conflict")
            ack(it)
        }
        assertEquals(1, count("order_delivery_outbox", "delivery_state='BLOCKED'"))
        assertEquals(1, count("order_delivery_outbox", "delivery_state='ACKED'"))
        assertEquals(3, count("order_delivery_outbox"))
        assertTrue(store.dueOrderDeliveries(scope, deliveryTime.plusSeconds(600)).isEmpty())
    }

    @Test fun authRejectionPausesUntilSameScopeAuthenticationSucceeds() = runBlocking {
        val task = task(screens = 1)
        store.commitOrderRead(enroll(task), read())
        flush { throw CloudHttpException(401, "private") }
        deliveryTime = deliveryTime.plusSeconds(600)
        assertTrue(store.dueOrderDeliveries(scope, deliveryTime).isEmpty())
        store.resumeOrderAuthentication("reenrolled")
        assertTrue(store.dueOrderDeliveries(scope, deliveryTime).isEmpty())
        store.resumeOrderAuthentication(scope)
        flush { ack(it) }
        assertEquals(1, count("order_delivery_outbox", "delivery_state='ACKED'"))
    }

    @Test fun newEnrollmentCannotUploadOrResumeOldData() {
        val task = task(screens = 1)
        store.commitOrderRead(enroll(task), read())
        assertTrue(store.dueOrderDeliveries("reenrolled", deliveryTime).isEmpty())
        assertFails { store.openOrderRun(identity(task), "reenrolled", true) }
        val c = CloudConnection("https://example.invalid", "original", "a".repeat(64))
        assertNotEquals(orderConnectionScope(c, "device-1"),
            orderConnectionScope(c.copy(bearerToken = "new"), "device-1"))
        assertEquals(1, count("order_delivery_outbox"))
    }

    @Test fun resumeRestoresSecondOrdinalAndSeenRegistry() = runBlocking {
        val task = task()
        store.commitOrderRead(enroll(task), read())
        store.close()
        store = AutomationStore(context)
        store.recoverInterruptedRuns()
        assertNull(store.claimNext())
        assertEquals(task.taskId, store.claimResume(task.taskId)?.taskId)
        assertNull(store.latestCheckpoint(task.taskId))
        // First read verifies the retained physical page, next read is after the authorized swipe.
        val ui = Ui(listOf(listOf(a), listOf(a, b)))
        executor(ui, session(task, true)).execute(task, startAfterIndex = 0, journal = journal(task))
        val restored = store.openOrderRun(identity(task), scope, true)
        assertEquals(listOf(1, 2), restored.reads.map { it.screen })
        assertTrue(ui.logs.contains("ORDERS_OVERLAP_1"))
        assertEquals(listOf(a, b), restored.reads.last().rawRows)
    }

    @Test fun resumeRestoresStagnationPolicyBeforeAnyExtraSwipe() = runBlocking {
        val task = task(screens = 3)
        val identity = enroll(task)
        store.commitOrderRead(identity, read())
        store.commitOrderRead(identity, read(2))
        val ui = Ui(listOf(listOf(a), listOf(a)))
        executor(ui, session(task, true)).execute(task, startAfterIndex = 2, journal = journal(task))
        assertTrue(ui.logs.contains("ORDERS_OVERLAP_1"))
        assertEquals(3, store.openOrderRun(identity, scope, true).reads.size)
    }

    @Test fun resumedUnknownPhysicalPageDoesNotReadNextScreenOrSwipe() = runBlocking {
        val task = task()
        store.commitOrderRead(enroll(task), read())
        val ui = Ui(listOf(listOf(b)))
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui, session(task, true)).execute(task, startAfterIndex = 0, journal = journal(task))
        }
        assertEquals("RESUME_PAGE_UNVERIFIED", failure.code)
        assertEquals(0, ui.swipes)
        assertEquals(1, count("order_delivery_outbox"))
    }

    @Test fun interruptedSwipeAndMissingRecoveryStateFailClosed() = runBlocking {
        val task = task()
        store.commitOrderRead(enroll(task), read())
        journal(task)(task.steps[1], "STARTED")
        val ui = Ui(listOf(listOf(a)))
        assertFailsWith<ExecutorFailure> {
            executor(ui, session(task, true)).execute(task, startAfterIndex = 0, journal = journal(task))
        }
        assertEquals(0, ui.reads)
        assertEquals(0, ui.swipes)
        assertFails { store.openOrderRun(identity(task("missing")), scope, true) }
        Unit
    }

    @Test fun completedSwipeWithoutSavedNewPageFailsClosed() = runBlocking {
        val task = task()
        store.commitOrderRead(enroll(task), read())
        journal(task)(task.steps[1], "SUCCEEDED")
        val ui = Ui(listOf(listOf(b)))
        assertFailsWith<ExecutorFailure> {
            executor(ui, session(task, true)).execute(task, startAfterIndex = 1, journal = journal(task))
        }
        assertEquals(0, ui.reads)
    }

    @Test fun emptyVisiblePagePersistsAndCompletesWithStopReason() = runBlocking {
        val task = task()
        enroll(task)
        val ui = Ui(listOf(emptyList()))
        executor(ui, session(task)).execute(task, journal = journal(task))
        store.finish(task.taskId, true)
        assertEquals(0, ui.swipes)
        val sent = mutableListOf<JSONObject>()
        repeat(2) { flush { sent += JSONObject(it.getString("payloadJson")); ack(it) } }
        assertEquals(0, sent.first().getJSONArray("rows").length())
        assertEquals("STOP_EMPTY_PAGE", sent.last().getString("stopReason"))
        assertEquals(1, sent.last().getInt("totalScreens"))
    }

    @Test fun failedTaskRetainsScreensButNeverCreatesComplete() {
        val task = task()
        store.commitOrderRead(enroll(task), read())
        store.finish(task.taskId, false, "CANCELLED")
        assertEquals(1, count("order_delivery_outbox"))
        assertEquals(0, count("order_delivery_outbox", "kind='COMPLETE'"))
    }

    @Test fun exactReadReplayIsIdempotentButChangedReadIsRejected() {
        val task = task(screens = 1)
        val identity = enroll(task)
        store.commitOrderRead(identity, read())
        store.commitOrderRead(identity, read())
        assertFails { store.commitOrderRead(identity, read(rows = listOf(b))) }
        assertEquals(1, count("order_delivery_outbox"))
        assertEquals(1, count("run_journal", "state='SUCCEEDED'"))
    }

    @Test fun capabilityClaimSidecarAndLegacySelection() {
        val task = task(screens = 1)
        val response = payload(task)
        val claimed = buildClaimedTaskPayload(response)
        assertNull(orderAwareCommandOrNull(claimed.toString()))
        assertEquals(task, parseOrderAwareTask(claimed.toString()))
        assertNotNull(OrderDeliveryIdentity.fromTask(claimed, task))
        assertEquals(ORDER_DELIVERY_PROTOCOL, addOrderDeliveryCapability(JSONObject(), false).getString("orderDeliveryProtocol"))
        assertFalse(addOrderDeliveryCapability(JSONObject(), true).has("orderDeliveryProtocol"))
        response.remove("orderDelivery")
        assertNull(OrderDeliveryIdentity.fromTask(buildClaimedTaskPayload(response), task))
    }

    @Test fun serviceAdmissionAcceptsDurableClaimBeforeEnqueue() {
        val task = task(screens = 1)
        val claim = ClaimedTask(
            buildClaimedTaskPayload(payload(task)).toString(),
            task.taskId, task.deviceId, "lease-1", 0,
        )
        assertEquals(task.deviceId, acceptedClaimDeviceId(claim, task.deviceId))
    }

    @Test fun serviceAdmissionKeepsLegacyTasksCompatible() {
        val task = task(screens = 1)
        val response = payload(task).apply { remove("orderDelivery") }
        val claim = ClaimedTask(
            buildClaimedTaskPayload(response).toString(),
            task.taskId, task.deviceId, "lease-1", 0,
        )
        assertEquals(task.deviceId, acceptedClaimDeviceId(claim, task.deviceId))
    }

    @Test fun serviceAdmissionRejectsMalformedDurableIdentity() {
        val task = task(screens = 1)
        for (key in listOf("accountId", "bindingVersion")) {
            val response = payload(task).apply { remove(key) }
            val claim = ClaimedTask(
                buildClaimedTaskPayload(response).toString(),
                task.taskId, task.deviceId, "lease-1", 0,
            )
            assertFails { acceptedClaimDeviceId(claim, task.deviceId) }
        }
    }

    @Test fun serviceAdmissionRejectsMixedCommandAndUnknownFields() {
        val task = task(screens = 1)
        val mixed = buildClaimedTaskPayload(payload(task)).put("command", JSONObject())
        val unknown = buildClaimedTaskPayload(payload(task)).put("unknownInstruction", true)
        for (value in listOf(mixed, unknown)) {
            val claim = ClaimedTask(value.toString(), task.taskId, task.deviceId, "lease-1", 0)
            assertFails { acceptedClaimDeviceId(claim, task.deviceId) }
        }
    }

    @Test fun serviceAdmissionRejectsWrongPayloadOrEnvelopeDevice() {
        val task = task(screens = 1)
        val claim = ClaimedTask(
            buildClaimedTaskPayload(payload(task)).toString(),
            task.taskId, task.deviceId, "lease-1", 0,
        )
        assertFails { acceptedClaimDeviceId(claim, "another-device") }
        assertFails { acceptedClaimDeviceId(claim.copy(deviceId = "another-device"), task.deviceId) }
    }

    @Test fun mixedDurableCommandCannotBypassTheOrderExecutionPath() {
        val value = payload(task(screens = 1)).put("command", JSONObject())
        assertFails { orderAwareCommandOrNull(value.toString()) }
        value.remove("command")
        value.put("protocolVersion", "cloudctl.command/v1")
        assertFails { orderAwareCommandOrNull(value.toString()) }
    }

    @Test fun missingOrIncompatibleIdentityNeverFallsBackToLegacy() {
        val task = task(screens = 1)
        for (key in listOf("accountId", "bindingVersion")) {
            val value = payload(task).apply { remove(key) }
            assertFails { OrderDeliveryIdentity.fromTask(value, task) }
        }
        for (key in listOf("protocolVersion", "mobileBindingId", "direction", "maxScreens")) {
            val value = payload(task)
            value.getJSONObject("orderDelivery").remove(key)
            assertFails { OrderDeliveryIdentity.fromTask(value, task) }
        }
        val value = payload(task)
        value.getJSONObject("orderDelivery").put("protocolVersion", "future")
        assertFails { OrderDeliveryIdentity.fromTask(value, task) }
    }

    @Test fun openingOldSchemaAddsTablesWithoutDroppingLegacyQueues() {
        store.enqueueTask("legacy", "legacy-payload", "old-lease", 0)
        assertNotNull(store.claimNext())
        store.recordStepEvent("legacy", "step", "SUCCEEDED", "STEP_SUCCEEDED", "STEP_SUCCEEDED", 0)
        val events = store.pendingEvents().map { it.payload }
        val journalCount = count("run_journal")
        store.writableDatabase.execSQL("DROP TABLE order_delivery_outbox")
        store.writableDatabase.execSQL("DROP TABLE order_delivery_run")
        store.close()
        store = AutomationStore(context)
        assertEquals(events, store.pendingEvents().map { it.payload })
        assertEquals(1, count("task_inbox"))
        assertEquals(journalCount, count("run_journal"))
        assertEquals(0, count("order_delivery_outbox"))
        assertEquals(5, store.readableDatabase.version)
    }

    @Test fun cancellationNeverAcknowledgesOrDeletesPendingRecord() = runBlocking {
        val task = task(screens = 1)
        store.commitOrderRead(enroll(task), read())
        assertFailsWith<CancellationException> { flush { throw CancellationException("cancel") } }
        assertEquals(1, count("order_delivery_outbox", "delivery_state='PENDING' AND attempt_count=0"))
    }

    @Test fun oversizedUtf8PayloadRollsBackEverything() {
        val task = task(screens = 1)
        val identity = enroll(task)
        assertFails {
            store.commitOrderRead(identity, read(rows = listOf(listOf("buyer", "item", "25", "x".repeat(200_001)))))
        }
        assertEquals(0, count("order_delivery_outbox"))
        assertEquals(0, count("run_journal", "state='SUCCEEDED'"))
    }

    @Test fun corruptRecoveryStateBlocksResumeWithoutDeletingUpload() {
        val task = task(screens = 1)
        store.commitOrderRead(enroll(task), read())
        store.writableDatabase.execSQL(
            "UPDATE order_delivery_outbox SET read_json=replace(read_json,'buyer-a','changed')",
        )
        assertFails { store.openOrderRun(identity(task), scope, true) }
        assertEquals(1, count("order_delivery_outbox"))
    }

    @Test fun incompletePlanCannotCommitSuccessfulTerminalOrComplete() {
        val task = task()
        store.commitOrderRead(enroll(task), read())
        assertFails { store.finish(task.taskId, true) }
        assertEquals(0, count("order_delivery_outbox", "kind='COMPLETE'"))
        assertEquals(0, count("task_inbox", "terminal_state='SUCCEEDED'"))
    }

    @Test fun forbiddenWaitsForAuthenticationAndUnprocessablePayloadBlocks() = runBlocking {
        val task = task(screens = 1)
        store.commitOrderRead(enroll(task), read())
        flush { throw CloudHttpException(403, "private") }
        assertEquals(1, count("order_delivery_outbox", "delivery_state='AUTH_REQUIRED'"))
        store.resumeOrderAuthentication(scope)
        deliveryTime = deliveryTime.plusSeconds(301)
        flush { throw CloudHttpException(422, "private") }
        assertEquals(1, count("order_delivery_outbox", "delivery_state='BLOCKED'"))
        store.resumeOrderAuthentication(scope)
        assertTrue(store.dueOrderDeliveries(scope, deliveryTime.plusSeconds(600)).isEmpty())
    }

    private class Ui(pages: List<List<List<String>>>) : LocalAutomationUi {
        private val pages = ArrayDeque(pages)
        var swipes = 0
        var reads = 0
        val logs = mutableListOf<String>()
        var onSwipe: () -> Unit = {}
        override fun ensureReady(targetPackage: String) = Unit
        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? = null
        override fun readOrderRows(targetPackage: String, locatorRef: String, maxRows: Int): List<List<String>> {
            reads++
            return pages.removeFirst()
        }
        override suspend fun swipeUpWithin(targetPackage: String, locatorRef: String) { onSwipe(); swipes++ }
        override suspend fun tap(targetPackage: String, locatorRef: String) = Unit
        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit
        override suspend fun screenshot(taskId: String, label: String) = ScreenshotEvidence("/unused", 0, "")
        override fun log(level: LogLevel, messageCode: String) { logs += messageCode }
    }
}
