package com.company.cloudctl.companion.im

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.data.ImOutboxStore
import com.company.cloudctl.companion.network.CloudHttpException
import java.time.Instant
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.json.JSONObject
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class ImNotificationPersistenceTest {
    private lateinit var context: Context
    private lateinit var store: ImOutboxStore
    private val now = Instant.parse("2026-09-26T08:00:00.123Z")
    private val metadata = ImNotificationMetadata(ImNotificationMetadata.XIANYU_PACKAGE, "feed", "msg")
    private val event = ImEvent("xianyu", "张起灵", "发来一条新消息", now, metadata)

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(ImOutboxStore.DATABASE_NAME)
        store = ImOutboxStore(context)
    }

    @AfterTest
    fun tearDown() {
        store.close()
        context.deleteDatabase(ImOutboxStore.DATABASE_NAME)
    }

    private fun reopen() {
        store.close()
        store = ImOutboxStore(context)
    }

    @Test
    fun retryAndReopenPreserveMetadataAndExactPayload() {
        val original = store.enqueue("device-1", event, now).event!!
        var firstPayload = ""
        val first = ImOutboxDelivery(store, { payload ->
            firstPayload = payload.toString()
            throw CloudHttpException(503, "unavailable")
        }, clock = { now }).deliverOnce("device-1")
        assertEquals(1, first.retried)
        val retried = store.unconfirmed().single()
        reopen()
        assertEquals(retried, store.unconfirmed().single())
        assertEquals(metadata, retried.notificationMetadata)
        assertEquals(original.dedupeKey, retried.dedupeKey)
        assertEquals(now, retried.occurredAt)
        assertEquals(1, retried.attemptCount)
        val second = ImOutboxDelivery(store, { payload ->
            assertEquals(firstPayload, payload.toString())
            JSONObject().put("accepted", 1).put("duplicates", 0)
        }, clock = { retried.nextAttemptAt }).deliverOnce("device-1")
        assertEquals(1, second.confirmed)
        reopen()
        assertEquals(1, store.counts().confirmed)
        assertEquals(ImEnqueueResult.DUPLICATE, store.enqueue("device-1", event, now).result)
    }

    @Test
    fun unboundMetadataSurvivesHoldReopenAndSeal() {
        val original = store.enqueue(null, event, now).event!!
        store.setUploadHeld(true)
        reopen()
        val held = ImOutboxDelivery(store, { error("Held rows must not upload") }, clock = { now })
            .deliverOnce("device-1")
        assertTrue(held.held)
        val sealed = store.unconfirmed().single()
        assertEquals(original.id, sealed.id)
        assertEquals(metadata, sealed.notificationMetadata)
        assertEquals(now, sealed.occurredAt)
        assertEquals(event.dedupeKey("device-1"), sealed.dedupeKey)
        store.setUploadHeld(false)
        reopen()
        assertEquals(sealed, store.due(now).single())
    }

    @Test
    fun boundsAreAppliedBeforePersistenceNotOnlyAtUpload() {
        val oversized = ImNotificationMetadata("invalid".repeat(50), "c".repeat(300), "k".repeat(100))
        store.enqueue("device-1", event.copy(notificationMetadata = oversized), now)
        reopen()
        val row = store.unconfirmed().single()
        assertEquals(oversized.bounded(), row.notificationMetadata)
        assertEquals(event.dedupeKey("device-1"), row.dedupeKey)
        val json = row.toUploadJson().getJSONObject("notificationMetadata")
        assertFalse(json.has("packageName"))
        assertEquals(256, json.getString("channelId").length)
        assertEquals(64, json.getString("category").length)
    }

    @Test
    fun missingAndEmptyMetadataBothRemainDeliverableAfterReopen() {
        store.enqueue("device-1", event.copy(notificationMetadata = null), now)
        store.enqueue("device-1", event.copy(peerName = "other", notificationMetadata = ImNotificationMetadata()), now)
        reopen()
        val rows = store.due(now)
        assertNull(rows[0].notificationMetadata)
        assertFalse(rows[0].toUploadJson().has("notificationMetadata"))
        assertEquals(ImNotificationMetadata(), rows[1].notificationMetadata)
        assertEquals(0, rows[1].toUploadJson().getJSONObject("notificationMetadata").length())
        assertEquals(2, ImOutboxDelivery(store, {
            JSONObject().put("accepted", 2).put("duplicates", 0)
        }, clock = { now }).deliverOnce("device-1").confirmed)
    }

    @Test
    fun versionOneMigrationPreservesEveryLegacyColumnAndDeliversPendingRows() {
        store.close()
        val path = context.getDatabasePath(ImOutboxStore.DATABASE_NAME)
        path.parentFile!!.mkdirs()
        val legacy = SQLiteDatabase.openOrCreateDatabase(path, null)
        legacy.execSQL(
            "CREATE TABLE im_outbox(" +
                "id INTEGER PRIMARY KEY AUTOINCREMENT,dedupe_key TEXT NOT NULL UNIQUE," +
                "device_id TEXT NOT NULL,platform TEXT NOT NULL,peer_key TEXT NOT NULL," +
                "peer_name TEXT NOT NULL,text TEXT NOT NULL,occurred_at TEXT NOT NULL," +
                "attempt_count INTEGER NOT NULL DEFAULT 0,next_attempt_at TEXT NOT NULL," +
                "last_error TEXT,permanent_failure_at TEXT,confirmed_at TEXT,created_at TEXT NOT NULL)",
        )
        legacy.execSQL("CREATE TABLE im_outbox_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        legacy.execSQL("INSERT INTO im_outbox_meta VALUES('upload_hold','1')")
        for (index in 1..4) {
            val device = if (index == 4) "" else "device-1"
            val sample = event.copy(peerName = "legacy-$index", notificationMetadata = null)
            legacy.execSQL(
                "INSERT INTO im_outbox VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                arrayOf<Any?>(
                    index, sample.dedupeKey(device), device, sample.platform, sample.peerKey,
                    sample.peerName, sample.text, now.toString(), 3, now.plusSeconds(60).toString(),
                    "HTTP_503", if (index == 3) now.toString() else null,
                    if (index == 2) now.toString() else null, now.minusSeconds(60).toString(),
                ),
            )
        }
        legacy.version = 1
        val before = legacyRows(legacy)
        legacy.close()

        store = ImOutboxStore(context)
        assertEquals(before, legacyRows(store.readableDatabase))
        assertEquals(2, store.readableDatabase.version)
        assertTrue(store.uploadHeld())
        assertEquals(2, store.counts().unconfirmed)
        assertEquals(1, store.counts().confirmed)
        assertEquals(1, store.counts().permanent)
        assertTrue(store.unconfirmed().all { it.notificationMetadata == null })
        assertNull(store.permanentFailures().single().notificationMetadata)
        assertTrue(store.due(now).isEmpty())
        assertEquals(1, store.due(now.plusSeconds(60)).size)
        reopen()
        assertEquals(before, legacyRows(store.readableDatabase))
        val duplicate = store.enqueue("device-1", event.copy(peerName = "legacy-1"), now)
        assertEquals(ImEnqueueResult.DUPLICATE, duplicate.result)
        assertNull(duplicate.event!!.notificationMetadata)
        assertEquals(before, legacyRows(store.readableDatabase))
        store.setUploadHeld(false)
        val report = ImOutboxDelivery(store, { payload ->
            val messages = payload.getJSONArray("messages")
            assertEquals(2, messages.length())
            repeat(messages.length()) {
                assertFalse(messages.getJSONObject(it).has("notificationMetadata"))
                assertEquals(now.toString(), messages.getJSONObject(it).getString("occurredAt"))
            }
            JSONObject().put("accepted", 2).put("duplicates", 0)
        }, clock = { now.plusSeconds(60) }).deliverOnce("device-1")
        assertEquals(2, report.confirmed)
        assertEquals(3, store.counts().confirmed)
        assertEquals(1, store.counts().permanent)
        val newRow = store.enqueue("device-1", event, now).event!!
        assertTrue(newRow.id > 4)
        assertEquals(metadata, newRow.notificationMetadata)
    }

    private fun legacyRows(db: SQLiteDatabase): List<List<String?>> =
        db.rawQuery(
            "SELECT id,dedupe_key,device_id,platform,peer_key,peer_name,text,occurred_at," +
                "attempt_count,next_attempt_at,last_error,permanent_failure_at,confirmed_at,created_at " +
                "FROM im_outbox ORDER BY id",
            emptyArray(),
        ).use { cursor ->
            buildList {
                while (cursor.moveToNext()) add((0 until cursor.columnCount).map { cursor.getString(it) })
            }
        }
}
