package com.company.cloudctl.companion.im

import android.content.Context
import android.content.Intent
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.data.ImOutboxStore
import com.company.cloudctl.companion.network.CloudHttpException
import com.company.cloudctl.companion.network.requireImUploadHasPlatform
import java.io.IOException
import java.time.Instant
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.json.JSONObject
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class ImOutboxStoreTest {
    private lateinit var context: Context
    private lateinit var store: ImOutboxStore
    private val now = Instant.parse("2026-09-22T08:00:00Z")

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(ImOutboxStore.DATABASE_NAME)
        store = ImOutboxStore(context)
        ImMonitor.resetForTest()
    }

    @AfterTest
    fun tearDown() {
        store.close()
        context.deleteDatabase(ImOutboxStore.DATABASE_NAME)
        ImMonitor.resetForTest()
    }

    private fun event(
        peer: String = "买家甲",
        text: String = "在吗",
        at: Instant = Instant.ofEpochSecond(1_800_000_000),
        platform: String = "xianyu",
    ) = ImEvent(platform, peer, text, at)

    @Test
    fun platformIsStoredAndOnlyXianyuIsAccepted() {
        val accepted = store.enqueue("device-1", event(), now)
        assertEquals(ImEnqueueResult.ENQUEUED, accepted.result)
        assertEquals("xianyu", accepted.event!!.platform)
        val payload = accepted.event.toUploadJson()
        assertEquals("xianyu", payload.getString("platform"))
        assertEquals("买家甲", payload.getString("peerKey"))
        assertEquals("买家甲", payload.getString("peerName"))
        assertEquals("在吗", payload.getString("text"))
        assertEquals(Instant.ofEpochSecond(1_800_000_000).toString(), payload.getString("occurredAt"))
        assertFalse(payload.has("deviceId"))
        requireImUploadHasPlatform(JSONObject().put("messages", org.json.JSONArray().put(payload)))

        assertEquals(ImEnqueueResult.REJECTED, store.enqueue("device-1", event(platform = "xhs"), now).result)
        assertEquals(1, store.counts().unconfirmed)
    }

    @Test
    fun canonicalOverlongTextIsIdempotentAcrossReplay() {
        val raw = "测".repeat(2500) + "\uD83D\uDE00"
        val first = store.enqueue("device-1", event(text = raw), now)
        val canonical = ImCanonicalText.canonical(raw)
        assertEquals(ImEnqueueResult.ENQUEUED, first.result)
        assertEquals(canonical, first.event!!.text)
        assertTrue(canonical.startsWith("TRUNCATED "))
        assertFalse(canonical.startsWith("TRUNCATED TRUNCATED "))

        val replayRaw = store.enqueue("device-1", event(text = raw), now.plusSeconds(5))
        val replayCanonical = store.enqueue("device-1", event(text = canonical), now.plusSeconds(9))
        assertEquals(ImEnqueueResult.DUPLICATE, replayRaw.result)
        assertEquals(ImEnqueueResult.DUPLICATE, replayCanonical.result)
        assertEquals(first.dedupeKey, replayRaw.dedupeKey)
        assertEquals(first.dedupeKey, replayCanonical.dedupeKey)
        assertEquals(1, store.unconfirmed().size)
    }

    @Test
    fun duplicateNotificationDoesNotCreateASecondRow() {
        assertEquals(ImEnqueueResult.ENQUEUED, store.enqueue("device-1", event(), now).result)
        assertEquals(ImEnqueueResult.DUPLICATE, store.enqueue("device-1", event(), now.plusSeconds(1)).result)
        assertEquals(1, store.unconfirmed().size)
    }

    @Test
    fun dedupeKeyIncludesBindingDeviceIdNotAdbSerial() {
        val left = store.enqueue("4aabc387-6e4b-4b59-a525-b1c119ec7f5b", event(), now)
        val right = store.enqueue("other-binding", event(), now)
        assertEquals(ImEnqueueResult.ENQUEUED, left.result)
        assertEquals(ImEnqueueResult.ENQUEUED, right.result)
        assertNotEquals(left.dedupeKey, right.dedupeKey)
        assertEquals(
            ImDedupe.key("4aabc387-6e4b-4b59-a525-b1c119ec7f5b", event()),
            left.dedupeKey,
        )
        val serial = "b0644fb5"
        assertNotEquals(ImDedupe.key(serial, event()), left.dedupeKey)
    }

    @Test
    fun deliveryNeverUploadsRowsFromAnotherBinding() {
        store.enqueue("old-binding", event(text = "旧身份"), now)
        store.enqueue("new-binding", event(text = "新身份"), now)
        var uploaded = ""
        val delivery = ImOutboxDelivery(store, { payload ->
            val batch = payload.getJSONArray("messages")
            assertEquals(1, batch.length())
            uploaded = batch.getJSONObject(0).getString("text")
            JSONObject().put("accepted", 1).put("duplicates", 0)
        }, clock = { now })
        assertEquals(1, delivery.deliverOnce("new-binding").confirmed)
        assertEquals("新身份", uploaded)
        assertEquals("old-binding", store.unconfirmed().single().deviceId)
        assertEquals(0, delivery.deliverOnce("new-binding").sent)
    }

    @Test
    fun successConfirmsAndRestartKeepsUnconfirmed() {
        val outcome = store.enqueue("device-1", event(text = "待确认"), now)
        store.close()
        store = ImOutboxStore(context)
        val restored = store.unconfirmed().single()
        assertEquals(outcome.dedupeKey, restored.dedupeKey)
        assertEquals("待确认", restored.text)

        val delivery = ImOutboxDelivery(store, {
            JSONObject().put("accepted", 1).put("duplicates", 0)
        }, clock = { now.plusSeconds(30) })
        val report = delivery.deliverOnce("device-1")
        assertEquals(1, report.confirmed)
        assertEquals(0, store.unconfirmed().size)
        assertEquals(1, store.counts().confirmed)

        store.close()
        store = ImOutboxStore(context)
        assertEquals(0, store.unconfirmed().size)
        assertEquals(1, store.counts().confirmed)
    }

    @Test
    fun retryableFailureUsesExistingBackoffAndStaysPending() {
        store.enqueue("device-1", event(text = "网络失败"), now)
        val delivery = ImOutboxDelivery(store, {
            throw CloudHttpException(503, "unavailable")
        }, clock = { now })
        val report = delivery.deliverOnce("device-1")
        assertEquals(1, report.retried)
        assertEquals(0, report.confirmed)
        val row = store.unconfirmed().single()
        assertEquals(1, row.attemptCount)
        assertEquals("HTTP_503", row.lastError)
        assertEquals(
            com.company.cloudctl.companion.network.OutboxRetryPolicy.nextAttemptAt(row.id, 1, now),
            row.nextAttemptAt,
        )
        assertTrue(row.nextAttemptAt.isAfter(now))
        assertTrue(store.due(now).isEmpty())
        assertEquals(1, store.due(row.nextAttemptAt).size)
    }

    @Test
    fun permanentRejectionStaysQueryableAndIsNotRetried() {
        store.enqueue("device-1", event(text = "坏载荷"), now)
        var calls = 0
        val delivery = ImOutboxDelivery(store, {
            calls += 1
            throw CloudHttpException(422, "invalid")
        }, clock = { now })
        val first = delivery.deliverOnce("device-1")
        val second = delivery.deliverOnce("device-1")
        assertEquals(1, first.permanent)
        assertEquals(0, second.sent)
        assertEquals(1, calls)
        assertTrue(store.unconfirmed().isEmpty())
        val failed = store.permanentFailures().single()
        assertEquals("HTTP_422", failed.lastError)
        assertEquals(now, failed.permanentFailureAt)
        assertNull(failed.confirmedAt)
        assertEquals(1, store.counts().permanent)
    }

    @Test
    fun taskLeaseErrorDoesNotConfirmImMessage() {
        store.enqueue("device-1", event(), now)
        val report = ImOutboxDelivery(store, {
            throw CloudHttpException(409, "mobile task lease expired")
        }, clock = { now }).deliverOnce("device-1")
        assertEquals(0, report.confirmed)
        assertEquals(1, report.permanent)
        assertEquals(0, store.counts().confirmed)
        assertEquals(1, store.permanentFailures().size)
    }

    @Test
    fun explicitDuplicateConfirmsWithoutASecondRow() {
        store.enqueue("device-1", event(), now)
        val delivery = ImOutboxDelivery(store, {
            JSONObject().put("accepted", 0).put("duplicates", 1)
        }, clock = { now })
        val report = delivery.deliverOnce("device-1")
        assertEquals(1, report.confirmed)
        assertEquals(1, report.duplicates)
        assertEquals(0, store.unconfirmed().size)
    }

    @Test
    fun partialOrEmptyAckDoesNotConfirmAnyRow() {
        store.enqueue("device-1", event(text = "甲", at = Instant.ofEpochSecond(1_800_000_000)), now)
        store.enqueue("device-1", event(text = "乙", at = Instant.ofEpochSecond(1_800_000_001)), now)
        val partial = ImOutboxDelivery(store, {
            JSONObject().put("accepted", 1).put("duplicates", 0)
        }, clock = { now })
        val partialReport = partial.deliverOnce("device-1")
        assertEquals(0, partialReport.confirmed)
        assertEquals(2, partialReport.retried)
        assertEquals(2, store.unconfirmed().size)
        assertEquals(listOf("IM_OUTBOX_UNACCOUNTED", "IM_OUTBOX_UNACCOUNTED"), store.unconfirmed().map { it.lastError })

        val empty = ImOutboxDelivery(store, { JSONObject() }, clock = { store.unconfirmed().first().nextAttemptAt })
        assertEquals(0, empty.deliverOnce("device-1").confirmed)
        assertEquals(2, store.unconfirmed().size)
        assertEquals(0, store.counts().confirmed)
    }

    @Test
    fun ioFailureAndRetryableStatusesStayPending() {
        store.enqueue("device-1", event(text = "断网"), now)
        val io = ImOutboxDelivery(store, { throw IOException("offline") }, clock = { now })
        assertEquals(1, io.deliverOnce("device-1").retried)
        assertEquals("IOException", store.unconfirmed().single().lastError)

        for (status in listOf(408, 425, 429)) {
            val dueAt = store.unconfirmed().single().nextAttemptAt
            val delivery = ImOutboxDelivery(store, { throw CloudHttpException(status, "retry") }, clock = { dueAt })
            assertEquals(1, delivery.deliverOnce("device-1").retried, "status=$status")
            assertEquals("HTTP_$status", store.unconfirmed().single().lastError)
        }
        assertEquals(0, store.counts().confirmed)
        assertEquals(0, store.counts().permanent)
    }

    @Test
    fun overflowRejectsTheNewEventAndKeepsExistingFifo() {
        repeat(ImOutboxStore.CAPACITY) { index ->
            val outcome = store.enqueue("device-1", event(text = "m$index", at = Instant.ofEpochSecond(1_800_000_000L + index)), now)
            assertEquals(ImEnqueueResult.ENQUEUED, outcome.result)
        }
        val overflow = store.enqueue("device-1", event(text = "溢出", at = Instant.ofEpochSecond(1_900_000_000)), now)
        assertEquals(ImEnqueueResult.OVERFLOW, overflow.result)
        val pending = store.unconfirmed()
        assertEquals(ImOutboxStore.CAPACITY, pending.size)
        assertEquals("m0", pending.first().text)
        assertEquals("m${ImOutboxStore.CAPACITY - 1}", pending.last().text)
        assertFalse(pending.any { it.text == "溢出" })
        assertEquals(listOf("m0", "m1"), store.due(now, 2).map { it.text })
        assertTrue(shadowLogs().any { it.contains("IM_OUTBOX_OVERFLOW") })
    }

    @Test
    fun holdLogsAndIsOperatorVisibleOnlyInDebug() {
        store.setUploadHeld(true)
        store.enqueue("device-1", event(text = "暂停中"), now)
        val held = ImOutboxDelivery(store, { JSONObject().put("accepted", 1).put("duplicates", 0) }, clock = { now })
        assertTrue(held.deliverOnce("device-1").held)
        assertEquals(1, store.unconfirmed().size)
        assertTrue(shadowLogs().any { it.contains("IM_OUTBOX_HOLD") })

        val release = ImUploadHold.apply(store, held = true, allowed = false)
        assertFalse(release)
        assertTrue(store.uploadHeld())
        val cleared = ImUploadHold.apply(store, held = false, allowed = false)
        assertTrue(cleared)
        assertFalse(store.uploadHeld())

        val intent = Intent(ImUploadHold.ACTION).putExtra(ImUploadHold.EXTRA_HELD, true)
        assertTrue(ImUploadHold.applyIntent(store, intent, allowed = true))
        assertTrue(store.uploadHeld())
        assertFalse(ImUploadHold.applyIntent(store, Intent("other"), allowed = true))
    }

    private fun shadowLogs(): List<String> {
        val shadow = org.robolectric.shadows.ShadowLog.getLogs()
        return shadow.map { "${it.tag} ${it.msg}" }
    }

    @Test
    fun holdPersistsAcrossRestartAndBlocksConfirm() {
        assertFalse(store.uploadHeld())
        store.setUploadHeld(true)
        store.enqueue("device-1", event(text = "暂停中"), now)
        var calls = 0
        val held = ImOutboxDelivery(store, {
            calls += 1
            JSONObject()
        }, clock = { now })
        assertTrue(held.deliverOnce("device-1").held)
        assertEquals(0, calls)
        assertEquals(1, store.unconfirmed().size)

        store.close()
        store = ImOutboxStore(context)
        assertTrue(store.uploadHeld())
        assertEquals("暂停中", store.unconfirmed().single().text)
        assertEquals(0, store.counts().confirmed)

        store.setUploadHeld(false)
        assertFalse(store.uploadHeld())
        ImOutboxDelivery(store, {
            JSONObject().put("accepted", 1).put("duplicates", 0)
        }, clock = { now }).deliverOnce("device-1")
        assertEquals(0, store.unconfirmed().size)
    }

    @Test
    fun missingBindingDoesNotAttachAnotherDeviceUntilSeal() {
        val outcome = store.enqueue(null, event(text = "未绑定"), now)
        assertEquals(ImEnqueueResult.ENQUEUED, outcome.result)
        assertEquals("", outcome.event!!.deviceId)
        assertTrue(store.due(now).isEmpty())
        assertEquals(0, ImOutboxDelivery(store, { JSONObject() }, clock = { now }).deliverOnce("").sent)

        store.sealUnbound("device-9", now)
        val sealed = store.due(now).single()
        assertEquals("device-9", sealed.deviceId)
        assertEquals(ImDedupe.key("device-9", event(text = "未绑定")), sealed.dedupeKey)
        assertNotEquals(outcome.dedupeKey, sealed.dedupeKey)
    }

    @Test
    fun uploadWithoutPlatformIsRefused() {
        val bare = JSONObject().put("peerKey", "买家甲").put("peerName", "买家甲").put("text", "在吗")
        assertFailsWith<IllegalStateException> {
            requireImUploadHasPlatform(JSONObject().put("messages", org.json.JSONArray().put(bare)))
        }
    }
}
