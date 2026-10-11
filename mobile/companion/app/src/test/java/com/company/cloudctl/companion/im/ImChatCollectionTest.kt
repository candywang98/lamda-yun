package com.company.cloudctl.companion.im

import com.company.cloudctl.companion.automation.*
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import kotlin.test.*

internal object CollectionFixture {
    val target = ImChatCollectionTarget("11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333",
        "小白", "小白", "44444444-4444-4444-8444-444444444444")
    val time: Instant = Instant.parse("2026-10-11T00:00:00Z")
    fun payload(epoch: Long = 7): JSONObject = JSONObject()
        .put("protocolVersion", "cloudctl.mobile/v1").put("taskId", "task-collect")
        .put("deviceId", target.deviceId).put("targetPackage", TargetLocatorRegistry.XIANYU_PACKAGE)
        .put("issuedAt", time.minusSeconds(1).toString()).put("expiresAt", time.plusSeconds(600).toString())
        .put("maxRunSeconds", 60).put("controlEpoch", epoch)
        .put("steps", JSONArray().put(JSONObject().put("stepId", "collect").put("action", "ui.collectImChat")
            .put("timeoutMs", 60000).put("target", target.toJson())))
    fun task() = AutomationTaskParser.parse(payload().toString())
    fun snapshot() = ImChatCollectionSnapshot.capture(target.peerName,
        listOf(ChatBubble("正文", 200f, 300, 80)), time)
}

class ImChatCollectionTest {
    @Test fun explicitTaskIsNotReplyAndPreservesCloudEpoch() {
        val task = CollectionFixture.task()
        assertEquals(7L, task.controlEpoch)
        assertNull(ImReplyTaskShape.peerNameOf(task))
        assertIs<AutomationStep.CollectImChat>(task.steps.single())
    }
    @Test fun mixedActionsAndUnknownActionFailBeforeExecution() {
        for (action in listOf("ui.input", "ui.tap", "future.collect")) {
            val value = CollectionFixture.payload()
            value.getJSONArray("steps").put(JSONObject().put("stepId", "extra").put("action", action).put("timeoutMs", 1000))
            assertFails { AutomationTaskParser.parse(value.toString()) }
        }
        val validExtra = JSONObject().put("stepId", "send").put("action", "ui.tap")
            .put("timeoutMs", 1000).put("locatorRef", "xianyu_chat_send")
        val mixed = CollectionFixture.payload().apply { getJSONArray("steps").put(validExtra) }
        assertFails { AutomationTaskParser.parse(mixed.toString()) }
    }
    @Test fun targetExtraFieldsAndFalseNoSendAreRejected() {
        for (change in listOf<(JSONObject) -> Unit>({ it.put("noSend", false) }, { it.put("extra", true) },
            { it.put("peerName", " ") }, { it.put("peerName", "a".repeat(129)) },
            { it.put("mobileBindingId", "not-uuid") }, { it.put("platform", "other") })) {
            val root = CollectionFixture.payload()
            change(root.getJSONArray("steps").getJSONObject(0).getJSONObject("target"))
            assertFails { AutomationTaskParser.parse(root.toString()) }
        }
    }
    @Test fun wrongDevicePackageTimeoutAndMissingEpochFailClosed() {
        for (change in listOf<(JSONObject) -> Unit>({ it.put("deviceId", "other") },
            { it.put("targetPackage", TargetLocatorRegistry.XHS_PACKAGE) }, { it.put("maxRunSeconds", 61) },
            { it.remove("controlEpoch") }, { it.put("controlEpoch", 0) }, { it.put("controlEpoch", "7") },
            { it.getJSONArray("steps").getJSONObject(0).put("timeoutMs", 1000) })) {
            val root = CollectionFixture.payload(); change(root)
            assertFails { AutomationTaskParser.parse(root.toString()) }
        }
    }
    @Test fun snapshotBoundsAreExplicitAndUtf8Bounded() {
        val bubbles = List(25) { ChatBubble("中".repeat(2100), if (it % 2 == 0) 200f else 800f, 300, 80) }
        val snapshot = ImChatCollectionSnapshot.capture("小白", bubbles, CollectionFixture.time).toJson()
        assertTrue(snapshot.toString().toByteArray(Charsets.UTF_8).size <= 64000)
        assertTrue(snapshot.getBoolean("truncated"))
        assertEquals("UNVERIFIED", snapshot.getString("accountIdentity"))
        val rows = snapshot.getJSONArray("messages")
        assertTrue(rows.length() in 1..20)
        for (i in 0 until rows.length()) {
            val row = rows.getJSONObject(i)
            assertEquals(i, row.getInt("visibleOrder"))
            assertEquals(2000, row.getString("text").length)
            assertTrue(row.isNull("occurredAt"))
        }
    }
    @Test fun emptySnapshotHasHonestScopeAndNoInventedMessage() {
        val value = ImChatCollectionSnapshot.capture("小白", emptyList(), CollectionFixture.time).toJson()
        assertEquals(0, value.getJSONArray("messages").length())
        assertEquals("VISIBLE_ONLY", value.getString("completeness"))
        assertFalse(value.getBoolean("truncated"))
    }
}

internal class CollectionUi : LocalAutomationUi {
    var foreground = true
    var chat = true
    var peer: String? = "小白"
    var root = true
    var uniquePeer = true
    var reads = 0
    var backs = 0
    var taps = mutableListOf<String>()
    var onRead: () -> Unit = {}
    var onEvidence: () -> Unit = {}
    var onTap: () -> Unit = {}
    var readBody = listOf(ChatBubble("正文", 200f, 300, 80))
    override fun ensureReady(targetPackage: String) { check(foreground) }
    override fun isTargetForeground(targetPackage: String) = foreground
    override fun atRootPage(targetPackage: String) = root
    override fun inspect(targetPackage: String, locatorRef: String) = LocalNodeState(true, true, true, false, "")
    override suspend fun tap(targetPackage: String, locatorRef: String) {
        check(locatorRef == "xianyu_messages_tab"); taps += locatorRef; onTap()
    }
    override suspend fun tapText(targetPackage: String, value: String) {
        check(uniquePeer) { "ambiguous" }; taps += value; chat = true; onTap()
    }
    override suspend fun goBack() { backs++ }
    override fun imChatEvidence(targetPackage: String, expectedPeer: String?): ImReplyBoundary.ChatEvidence {
        assertNull(expectedPeer) // Never bias header resolution toward the supplied target.
        onEvidence(); return ImReplyBoundary.ChatEvidence(peer, chat, false)
    }
    override fun visibleImChatBubbles(targetPackage: String): List<ChatBubble> { reads++; onRead(); return readBody }
    override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String): Unit = error("No input allowed")
    override suspend fun screenshot(taskId: String, label: String): ScreenshotEvidence = error("No screenshot required")
    override fun log(level: LogLevel, messageCode: String) {}
}

class ImChatCollectorTest {
    private suspend fun execute(ui: CollectionUi, start: Int = -1,
        reporter: (ImChatCollectionTarget, ImChatCollectionSnapshot) -> Unit) {
        LocalAutomationExecutor(ui, now = { CollectionFixture.time }, elapsedMs = { 0L }, sleep = {},
            imCollectionReporter = reporter).execute(CollectionFixture.task(), startAfterIndex = start) { _, _ -> }
    }
    @Test fun currentMatchingChatReadsOncePersistsAndNeverNavigatesOrSends() = runBlocking {
        val ui = CollectionUi(); var persisted = 0
        execute(ui) { target, snapshot ->
            assertEquals(CollectionFixture.target, target)
            assertEquals("正文", snapshot.toJson().getJSONArray("messages").getJSONObject(0).getString("text"))
            persisted++
        }
        assertEquals(1, persisted); assertEquals(1, ui.reads); assertEquals(0, ui.backs); assertTrue(ui.taps.isEmpty())
    }
    @Test fun rootListNavigationUsesExactUniquePeerOnly() = runBlocking {
        val ui = CollectionUi().apply { chat = false }
        execute(ui) { _, _ -> }
        assertEquals(listOf("xianyu_messages_tab", "小白"), ui.taps)
    }
    @Test fun ambiguousPeerNeverReadsOrPersists() = runBlocking {
        val ui = CollectionUi().apply { chat = false; uniquePeer = false }
        assertFails { execute(ui) { _, _ -> error("must not persist") } }
        assertEquals(0, ui.reads)
    }
    @Test fun wrongOrUnknownInitialPeerNeverNavigates() = runBlocking {
        for (peer in listOf("大白", null, "")) {
            val ui = CollectionUi().apply { this.peer = peer }
            assertFails { execute(ui) { _, _ -> error("must not persist") } }
            assertTrue(ui.taps.isEmpty()); assertEquals(0, ui.backs); assertEquals(0, ui.reads)
        }
    }
    @Test fun readDriftStopsWithoutRestoreOrPersist() = runBlocking {
        val ui = CollectionUi().apply { onRead = { peer = "大白" } }
        assertFails { execute(ui) { _, _ -> error("must not persist") } }
        assertEquals(1, ui.reads); assertEquals(0, ui.backs); assertTrue(ui.taps.isEmpty())
    }
    @Test fun foregroundLossAfterNavigationStopsBeforePeerTap() = runBlocking {
        val ui = CollectionUi().apply { chat = false; onTap = { foreground = false } }
        assertFails { execute(ui) { _, _ -> error("must not persist") } }
        assertEquals(listOf("xianyu_messages_tab"), ui.taps); assertEquals(0, ui.reads)
    }
    @Test fun navigationIsBoundedToThreeBacks() = runBlocking {
        val ui = CollectionUi().apply { chat = false; root = false }
        assertFails { execute(ui) { _, _ -> error("must not persist") } }
        assertEquals(3, ui.backs); assertTrue(ui.taps.isEmpty())
    }
    @Test fun skippedCollectorCannotCreateSuccessOrReRead() = runBlocking {
        val ui = CollectionUi()
        val error = assertFailsWith<ExecutorFailure> { execute(ui, 0) { _, _ -> error("must not persist") } }
        assertEquals("IM_COLLECTION_SNAPSHOT_MISSING", error.code); assertEquals(0, ui.reads)
    }
    @Test fun finalEvidenceDriftPreventsPersistence() = runBlocking {
        val ui = CollectionUi()
        var evidenceAfterRead = 0
        ui.onEvidence = {
            if (ui.reads > 0 && ++evidenceAfterRead == 2) ui.peer = "大白"
        }
        assertFails { execute(ui) { _, _ -> error("must not persist") } }
        assertEquals(1, ui.reads); assertTrue(ui.taps.isEmpty())
    }
    @Test fun pauseAndCancelDuringReadPreventPersistence() = runBlocking {
        for (pause in listOf(true, false)) {
            val control = ExecutionControl()
            val ui = CollectionUi().apply {
                onRead = { if (pause) control.requestPause() else control.requestCancel() }
            }
            var persisted = false
            assertFails {
                LocalAutomationExecutor(ui, now = { CollectionFixture.time }, elapsedMs = { 0L }, sleep = {},
                    imCollectionReporter = { _, _ -> persisted = true })
                    .execute(CollectionFixture.task(), control) { _, _ -> }
            }
            assertFalse(persisted); assertEquals(1, ui.reads)
        }
    }
    @Test fun evidenceExceptionFailsClosedWithoutReading() = runBlocking {
        val ui = CollectionUi().apply { onEvidence = { error("unavailable") } }
        assertFails { execute(ui) { _, _ -> error("must not persist") } }
        assertEquals(0, ui.reads); assertTrue(ui.taps.isEmpty())
    }
    @Test fun missingReporterFailsBeforeReadOrNavigation() = runBlocking {
        val ui = CollectionUi()
        assertFails { LocalAutomationExecutor(ui, now = { CollectionFixture.time }, elapsedMs = { 0L })
            .execute(CollectionFixture.task()) { _, _ -> } }
        assertEquals(0, ui.reads); assertTrue(ui.taps.isEmpty())
    }
}
