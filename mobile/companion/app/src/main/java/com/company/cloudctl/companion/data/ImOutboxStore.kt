package com.company.cloudctl.companion.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.util.Log
import com.company.cloudctl.companion.im.ImCanonicalText
import com.company.cloudctl.companion.im.ImDedupe
import com.company.cloudctl.companion.im.ImEnqueueOutcome
import com.company.cloudctl.companion.im.ImEnqueueResult
import com.company.cloudctl.companion.im.ImEvent
import com.company.cloudctl.companion.im.ImInboundEvent
import java.time.Instant

/**
 * Persistent IM inbound outbox (pa-im-m3/20260922.1 §4). Separate from the
 * task [AutomationStore] so IM durability does not bump that schema or share
 * its drop-oldest queue.
 *
 * A full outbox refuses the new event and keeps every unconfirmed row.
 * Nothing here deletes the oldest item to make room.
 */
class ImOutboxStore(context: Context) : SQLiteOpenHelper(
    context.applicationContext,
    DATABASE_NAME,
    null,
    VERSION,
) {
    override fun onConfigure(db: SQLiteDatabase) {
        db.enableWriteAheadLogging()
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            "CREATE TABLE im_outbox(" +
                "id INTEGER PRIMARY KEY AUTOINCREMENT," +
                "dedupe_key TEXT NOT NULL UNIQUE," +
                "device_id TEXT NOT NULL," +
                "platform TEXT NOT NULL," +
                "peer_key TEXT NOT NULL," +
                "peer_name TEXT NOT NULL," +
                "text TEXT NOT NULL," +
                "occurred_at TEXT NOT NULL," +
                "attempt_count INTEGER NOT NULL DEFAULT 0," +
                "next_attempt_at TEXT NOT NULL," +
                "last_error TEXT," +
                "permanent_failure_at TEXT," +
                "confirmed_at TEXT," +
                "created_at TEXT NOT NULL)",
        )
        db.execSQL(
            "CREATE TABLE im_outbox_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        )
        db.execSQL(
            "INSERT INTO im_outbox_meta(key, value) VALUES(?, ?)",
            arrayOf(META_UPLOAD_HOLD, "0"),
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        check(newVersion == VERSION) { "Unsupported IM outbox version $newVersion" }
    }

    /**
     * Persist one inbound before any network attempt. [boundDeviceId] null
     * means the binding was not readable: the row is stored under
     * [UNBOUND_DEVICE] and is not uploadable until [sealUnbound] binds it to
     * the device that is actually sending. That placeholder is not a real
     * device id, so the row cannot be confirmed against another phone.
     */
    @Synchronized
    fun enqueue(boundDeviceId: String?, event: ImEvent, now: Instant = Instant.now()): ImEnqueueOutcome {
        val platform = event.platform.trim()
        val peerName = event.peerName.trim()
        val peerKey = peerName
        val text = ImCanonicalText.canonical(event.text)
        if (platform != PLATFORM_XIANYU || peerKey.isEmpty() || peerKey.length > 128 || text.isEmpty()) {
            Log.w(TAG, "IM_OUTBOX_REJECTED platform=$platform peerLen=${peerKey.length}")
            return ImEnqueueOutcome(ImEnqueueResult.REJECTED, null)
        }
        val identity = boundDeviceId?.takeIf { it.isNotBlank() } ?: UNBOUND_DEVICE
        val canonicalEvent = event.copy(platform = platform, peerName = peerName, text = text)
        val dedupeKey = ImDedupe.key(identity, canonicalEvent)
        val db = writableDatabase
        db.beginTransaction()
        try {
            val existingId = lookupId(db, dedupeKey)
            if (existingId != null) {
                db.setTransactionSuccessful()
                return ImEnqueueOutcome(
                    ImEnqueueResult.DUPLICATE,
                    dedupeKey,
                    readById(db, existingId),
                )
            }
            val occupied = countUnconfirmed(db)
            if (occupied >= CAPACITY) {
                db.setTransactionSuccessful()
                Log.w(TAG, "IM_OUTBOX_OVERFLOW occupied=$occupied capacity=$CAPACITY")
                return ImEnqueueOutcome(ImEnqueueResult.OVERFLOW, dedupeKey)
            }
            val created = now.toString()
            val values = ContentValues().apply {
                put("dedupe_key", dedupeKey)
                put("device_id", identity)
                put("platform", platform)
                put("peer_key", peerKey)
                put("peer_name", peerName)
                put("text", text)
                put("occurred_at", event.occurredAt.toString())
                put("attempt_count", 0)
                put("next_attempt_at", created)
                put("created_at", created)
            }
            val id = db.insert("im_outbox", null, values)
            check(id > 0) { "IM outbox insert failed" }
            db.setTransactionSuccessful()
            return ImEnqueueOutcome(ImEnqueueResult.ENQUEUED, dedupeKey, readById(db, id))
        } finally {
            db.endTransaction()
        }
    }

    /**
     * Bind rows captured with no device id to [deviceId]. If that binding's
     * key already exists, the unbound copy is marked a permanent duplicate
     * instead of being uploaded as a second message.
     */
    @Synchronized
    fun sealUnbound(deviceId: String, now: Instant = Instant.now()): Int {
        if (deviceId.isBlank() || deviceId == UNBOUND_DEVICE) return 0
        val db = writableDatabase
        db.beginTransaction()
        try {
            val rows = query(
                db,
                "SELECT id, platform, peer_key, peer_name, text, occurred_at FROM im_outbox " +
                    "WHERE device_id=? AND confirmed_at IS NULL AND permanent_failure_at IS NULL ORDER BY id",
                arrayOf(UNBOUND_DEVICE),
            ) { cursor ->
                UnboundRow(
                    id = cursor.getLong(0),
                    platform = cursor.getString(1),
                    peerKey = cursor.getString(2),
                    peerName = cursor.getString(3),
                    text = cursor.getString(4),
                    occurredAt = cursor.getString(5),
                )
            }
            var sealed = 0
            for (row in rows) {
                val event = ImEvent(
                    platform = row.platform,
                    peerName = row.peerName,
                    text = row.text,
                    occurredAt = Instant.parse(row.occurredAt),
                )
                val sealedKey = ImDedupe.key(deviceId, event)
                val clash = lookupId(db, sealedKey)
                if (clash != null && clash != row.id) {
                    db.execSQL(
                        "UPDATE im_outbox SET permanent_failure_at=?, last_error=? WHERE id=? AND device_id=?",
                        arrayOf<Any>(now.toString(), "UNBOUND_DUPLICATE", row.id, UNBOUND_DEVICE),
                    )
                } else {
                    db.execSQL(
                        "UPDATE im_outbox SET device_id=?, dedupe_key=? WHERE id=? AND device_id=?",
                        arrayOf<Any>(deviceId, sealedKey, row.id, UNBOUND_DEVICE),
                    )
                    sealed += 1
                }
            }
            db.setTransactionSuccessful()
            return sealed
        } finally {
            db.endTransaction()
        }
    }

    @Synchronized
    fun due(now: Instant = Instant.now(), limit: Int = BATCH_LIMIT, deviceId: String? = null): List<ImInboundEvent> {
        val capped = limit.coerceIn(1, BATCH_LIMIT)
        val bindingFilter = if (deviceId != null) " AND device_id=?" else ""
        val args = mutableListOf(UNBOUND_DEVICE, now.toString())
        if (deviceId != null) args.add(deviceId)
        args.add(capped.toString())
        return query(
            readableDatabase,
            "SELECT $COLUMNS FROM im_outbox " +
                "WHERE confirmed_at IS NULL AND permanent_failure_at IS NULL " +
                "AND device_id<>? AND next_attempt_at<=?$bindingFilter ORDER BY id LIMIT ?",
            args.toTypedArray(),
            ::readEvent,
        )
    }

    @Synchronized
    fun unconfirmed(limit: Int = CAPACITY): List<ImInboundEvent> = query(
        readableDatabase,
        "SELECT $COLUMNS FROM im_outbox " +
            "WHERE confirmed_at IS NULL AND permanent_failure_at IS NULL ORDER BY id LIMIT ?",
        arrayOf(limit.coerceIn(1, CAPACITY).toString()),
        ::readEvent,
    )

    @Synchronized
    fun permanentFailures(): List<ImInboundEvent> = query(
        readableDatabase,
        "SELECT $COLUMNS FROM im_outbox WHERE permanent_failure_at IS NOT NULL ORDER BY id",
        emptyArray(),
        ::readEvent,
    )

    @Synchronized
    fun confirm(id: Long, now: Instant = Instant.now()): Boolean {
        val db = writableDatabase
        db.beginTransaction()
        try {
            val pending = db.rawQuery(
                "SELECT 1 FROM im_outbox WHERE id=? AND confirmed_at IS NULL AND permanent_failure_at IS NULL",
                arrayOf(id.toString()),
            ).use { it.moveToFirst() }
            if (!pending) {
                db.setTransactionSuccessful()
                return false
            }
            db.execSQL(
                "UPDATE im_outbox SET confirmed_at=?, last_error=NULL WHERE id=?",
                arrayOf<Any>(now.toString(), id),
            )
            db.setTransactionSuccessful()
            return true
        } finally {
            db.endTransaction()
        }
    }

    @Synchronized
    fun recordRetry(id: Long, error: String, nextAttemptAt: Instant) {
        writableDatabase.execSQL(
            "UPDATE im_outbox SET attempt_count=attempt_count+1, next_attempt_at=?, last_error=? " +
                "WHERE id=? AND confirmed_at IS NULL AND permanent_failure_at IS NULL",
            arrayOf<Any>(nextAttemptAt.toString(), error.take(MAX_ERROR), id),
        )
    }

    @Synchronized
    fun markPermanent(id: Long, error: String, now: Instant = Instant.now()) {
        writableDatabase.execSQL(
            "UPDATE im_outbox SET attempt_count=attempt_count+1, last_error=?, permanent_failure_at=? " +
                "WHERE id=? AND confirmed_at IS NULL AND permanent_failure_at IS NULL",
            arrayOf<Any>(error.take(MAX_ERROR), now.toString(), id),
        )
        Log.w(TAG, "IM_OUTBOX_PERMANENT id=$id error=${error.take(80)}")
    }

    @Synchronized
    fun uploadHeld(): Boolean =
        readableDatabase.row("SELECT value FROM im_outbox_meta WHERE key=?", arrayOf(META_UPLOAD_HOLD)) == "1"

    /** Default off. Survives process death because it lives in this database. */
    @Synchronized
    fun setUploadHeld(held: Boolean) {
        val db = writableDatabase
        val values = ContentValues().apply { put("value", if (held) "1" else "0") }
        if (db.update("im_outbox_meta", values, "key=?", arrayOf(META_UPLOAD_HOLD)) == 0) {
            values.put("key", META_UPLOAD_HOLD)
            check(db.insert("im_outbox_meta", null, values) > 0) { "IM outbox hold insert failed" }
        }
        Log.i(TAG, if (held) "IM_OUTBOX_HOLD enabled" else "IM_OUTBOX_HOLD cleared")
    }

    @Synchronized
    fun counts(): ImOutboxCounts {
        val db = readableDatabase
        return ImOutboxCounts(
            unconfirmed = countWhere(db, "confirmed_at IS NULL AND permanent_failure_at IS NULL"),
            confirmed = countWhere(db, "confirmed_at IS NOT NULL"),
            permanent = countWhere(db, "permanent_failure_at IS NOT NULL"),
            overflow = 0,
        )
    }

    private fun countUnconfirmed(db: SQLiteDatabase): Int =
        countWhere(db, "confirmed_at IS NULL AND permanent_failure_at IS NULL")

    private fun countWhere(db: SQLiteDatabase, where: String): Int =
        db.rawQuery("SELECT COUNT(*) FROM im_outbox WHERE $where", emptyArray()).use { cursor ->
            if (cursor.moveToFirst()) cursor.getInt(0) else 0
        }

    private fun lookupId(db: SQLiteDatabase, dedupeKey: String): Long? =
        db.rawQuery("SELECT id FROM im_outbox WHERE dedupe_key=?", arrayOf(dedupeKey)).use { cursor ->
            if (cursor.moveToFirst()) cursor.getLong(0) else null
        }

    private fun readById(db: SQLiteDatabase, id: Long): ImInboundEvent? =
        query(db, "SELECT $COLUMNS FROM im_outbox WHERE id=?", arrayOf(id.toString()), ::readEvent)
            .firstOrNull()

    private fun readEvent(cursor: android.database.Cursor): ImInboundEvent = ImInboundEvent(
        id = cursor.getLong(0),
        dedupeKey = cursor.getString(1),
        deviceId = cursor.getString(2),
        platform = cursor.getString(3),
        peerKey = cursor.getString(4),
        peerName = cursor.getString(5),
        text = cursor.getString(6),
        occurredAt = Instant.parse(cursor.getString(7)),
        attemptCount = cursor.getInt(8),
        nextAttemptAt = Instant.parse(cursor.getString(9)),
        lastError = cursor.getString(10),
        permanentFailureAt = cursor.getString(11)?.let(Instant::parse),
        confirmedAt = cursor.getString(12)?.let(Instant::parse),
    )

    private fun <T> query(
        db: SQLiteDatabase,
        sql: String,
        args: Array<String>,
        map: (android.database.Cursor) -> T,
    ): List<T> = db.rawQuery(sql, args).use { cursor ->
        buildList {
            while (cursor.moveToNext()) add(map(cursor))
        }
    }

    private fun SQLiteDatabase.row(sql: String, args: Array<String>): String? =
        rawQuery(sql, args).use { cursor -> if (cursor.moveToFirst()) cursor.getString(0) else null }

    private data class UnboundRow(
        val id: Long,
        val platform: String,
        val peerKey: String,
        val peerName: String,
        val text: String,
        val occurredAt: String,
    )

    companion object {
        const val DATABASE_NAME = "cloudctl-im-outbox.sqlite3"
        const val CAPACITY = 200
        const val BATCH_LIMIT = 20
        const val PLATFORM_XIANYU = "xianyu"

        /**
         * Not a binding id. Rows under this value stay out of [due] until
         * [sealUnbound] rewrites them with the device that owns the upload.
         */
        const val UNBOUND_DEVICE = ""
        private const val VERSION = 1
        private const val META_UPLOAD_HOLD = "upload_hold"
        private const val MAX_ERROR = 240
        private const val TAG = "ImOutbox"
        private const val COLUMNS =
            "id,dedupe_key,device_id,platform,peer_key,peer_name,text,occurred_at," +
                "attempt_count,next_attempt_at,last_error,permanent_failure_at,confirmed_at"
    }
}

data class ImOutboxCounts(
    val unconfirmed: Int,
    val confirmed: Int,
    val permanent: Int,
    val overflow: Int,
)
