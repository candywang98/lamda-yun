package com.company.cloudctl.companion.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONObject
import com.company.cloudctl.companion.updates.RecipeLifecycleStore
import com.company.cloudctl.companion.automation.CanonicalJson
import java.security.MessageDigest
import java.time.Instant

data class PendingTask(val taskId: String, val payload: String, val leaseId: String)
data class OutboxEvent(
    val id: Long,
    val path: String,
    val payload: String,
    val attemptCount: Int,
)
data class ActionJournalRecord(
    val actionKey: String,
    val taskId: String,
    val status: String,
    val parameterHash: String,
)

class AutomationStore(context: Context) : SQLiteOpenHelper(context, DATABASE_NAME, null, VERSION), RecipeLifecycleStore {
    override fun onConfigure(db: SQLiteDatabase) {
        db.enableWriteAheadLogging()
        db.execSQL("PRAGMA foreign_keys=ON")
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            "CREATE TABLE task_inbox(" +
                "task_id TEXT PRIMARY KEY,payload TEXT NOT NULL,payload_sha256 TEXT NOT NULL," +
                "lease_id TEXT NOT NULL,next_sequence INTEGER NOT NULL,state TEXT NOT NULL," +
                "terminal_state TEXT,received_at TEXT NOT NULL,updated_at TEXT NOT NULL)",
        )
        db.execSQL(
            "CREATE TABLE run_journal(" +
                "id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL,step_id TEXT," +
                "state TEXT NOT NULL,detail_code TEXT NOT NULL,occurred_at TEXT NOT NULL," +
                "FOREIGN KEY(task_id) REFERENCES task_inbox(task_id))",
        )
        db.execSQL(
            "CREATE TABLE event_outbox(" +
                "id INTEGER PRIMARY KEY AUTOINCREMENT,dedupe_key TEXT UNIQUE NOT NULL," +
                "task_id TEXT,path TEXT NOT NULL,payload TEXT NOT NULL,is_terminal INTEGER NOT NULL DEFAULT 0," +
                "attempt_count INTEGER NOT NULL DEFAULT 0,next_attempt_at TEXT NOT NULL," +
                "last_error TEXT,created_at TEXT NOT NULL,delivered_at TEXT,permanent_failure_at TEXT," +
                "FOREIGN KEY(task_id) REFERENCES task_inbox(task_id))",
        )
        createCheckpointAndJournalTables(db)
        createIndexes(db)
        createRecipeCatalogTable(db)
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) migrateVersion1To2(db)
        if (oldVersion < 3) createCheckpointAndJournalTables(db)
        if (oldVersion < 4) createRecipeCatalogTable(db)
        check(newVersion == VERSION) { "Unsupported automation database version $newVersion" }
    }

    override fun activeRecipeCatalog(): String = readableDatabase.row(
        "SELECT active FROM recipe_catalog WHERE id=1", emptyArray(),
    ) ?: EMPTY_RECIPE_CATALOG

    override fun pendingRecipeCatalog(): String? = readableDatabase.row(
        "SELECT pending FROM recipe_catalog WHERE id=1", emptyArray(),
    )

    override fun stageRecipeCatalog(encoded: String) = transaction {
        execSQL("UPDATE recipe_catalog SET pending=? WHERE id=1", arrayOf(encoded))
    }

    override fun activatePendingRecipeCatalog(): String = transaction {
        // Includes queued claims and unacknowledged terminal/reconciliation work. A task's
        // immutable payload remains the version source regardless of these catalog pointers.
        val busy = rawQuery(
            "SELECT 1 FROM task_inbox WHERE state NOT IN (?,?,?,?) LIMIT 1",
            arrayOf(STATE_TERMINAL_CONFIRMED, STATE_TERMINAL_REJECTED, "SUCCEEDED", "FAILED"),
        ).use { it.moveToFirst() } || rawQuery(
            "SELECT 1 FROM action_journal WHERE status IN ('INTENT','UNKNOWN') LIMIT 1",
            emptyArray(),
        ).use { it.moveToFirst() }
        if (!busy) execSQL("UPDATE recipe_catalog SET active=pending,pending=NULL WHERE id=1 AND pending IS NOT NULL")
        row("SELECT active FROM recipe_catalog WHERE id=1", emptyArray()) ?: EMPTY_RECIPE_CATALOG
    }

    private fun createRecipeCatalogTable(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE IF NOT EXISTS recipe_catalog(id INTEGER PRIMARY KEY CHECK(id=1),active TEXT NOT NULL,pending TEXT)")
        db.execSQL("INSERT OR IGNORE INTO recipe_catalog(id,active) VALUES(1,?)", arrayOf(EMPTY_RECIPE_CATALOG))
    }

    fun enqueueTask(taskId: String, payload: String, leaseId: String, lastSequence: Int): Boolean =
        transaction {
            val existing = rawQuery(
                "SELECT payload,lease_id,state,terminal_state FROM task_inbox WHERE task_id=?",
                arrayOf(taskId),
            ).use {
                if (it.moveToFirst()) {
                    ExistingTask(it.getString(0), it.getString(1), it.getString(2), it.getString(3))
                } else {
                    null
                }
            }
            if (existing != null) {
                require(sameExecutionPayload(existing.payload, payload)) {
                    "Task ID was reused with different content"
                }
                execSQL(
                    "UPDATE task_inbox SET payload_sha256=? WHERE task_id=? AND payload_sha256=''",
                    arrayOf(payload.sha256(), taskId),
                )
                if (existing.leaseId == leaseId) {
                    false
                } else {
                    val now = Instant.now().toString()
                    when (existing.state) {
                        STATE_QUEUED -> {
                            execSQL(
                                "UPDATE task_inbox SET lease_id=?,next_sequence=?,updated_at=? WHERE task_id=?",
                                arrayOf(leaseId, lastSequence + 1, now, taskId),
                            )
                            true
                        }

                        STATE_TERMINAL_PENDING, STATE_TERMINAL_CONFIRMED, STATE_TERMINAL_REJECTED,
                        "SUCCEEDED", "FAILED",
                        -> {
                            val terminalState = existing.terminalState ?: existing.state
                            execSQL(
                                "UPDATE task_inbox SET lease_id=?,next_sequence=?,state=?,terminal_state=?,updated_at=? WHERE task_id=?",
                                arrayOf(
                                    leaseId,
                                    lastSequence + 1,
                                    STATE_TERMINAL_PENDING,
                                    terminalState,
                                    now,
                                    taskId,
                                ),
                            )
                            enqueueTerminalForReplacementLease(
                                taskId,
                                leaseId,
                                succeeded = terminalState == TERMINAL_SUCCEEDED,
                            )
                            false
                        }

                        else -> error("A running task cannot accept a replacement lease")
                    }
                }
            } else {
                val now = Instant.now().toString()
                insertOrThrow("task_inbox", null, ContentValues().apply {
                    put("task_id", taskId)
                    put("payload", payload)
                    put("payload_sha256", payload.sha256())
                    put("lease_id", leaseId)
                    put("next_sequence", lastSequence + 1)
                    put("state", STATE_QUEUED)
                    putNull("terminal_state")
                    put("received_at", now)
                    put("updated_at", now)
                })
                true
            }
        }

    fun claimNext(): PendingTask? = transaction {
        val blocked = rawQuery(
            "SELECT 1 FROM task_inbox WHERE state IN (?,?,?) LIMIT 1",
            arrayOf(STATE_RUNNING, STATE_PAUSED, STATE_RESUME_CHECK),
        ).use { it.moveToFirst() }
        if (blocked) return@transaction null
        val task = rawQuery(
            "SELECT task_id,payload,lease_id FROM task_inbox WHERE state=? ORDER BY received_at,rowid LIMIT 1",
            arrayOf(STATE_QUEUED),
        ).use {
            if (it.moveToFirst()) PendingTask(it.getString(0), it.getString(1), it.getString(2)) else null
        }
        task?.let {
            val now = Instant.now().toString()
            execSQL(
                "UPDATE task_inbox SET state=?,updated_at=? WHERE task_id=? AND state=?",
                arrayOf(STATE_RUNNING, now, it.taskId, STATE_QUEUED),
            )
            insertJournalLocked(it.taskId, null, STATE_RUNNING, "TASK_CLAIMED_LOCAL", now)
        }
        task
    }

    fun record(taskId: String, stepId: String?, state: String, detailCode: String) {
        transaction { insertJournalLocked(taskId, stepId, state, detailCode, Instant.now().toString()) }
    }

    fun recordStepEvent(
        taskId: String,
        stepId: String?,
        state: String,
        detailCode: String,
        eventType: String,
        stepIndex: Int?,
        payload: JSONObject = JSONObject(),
    ) = transaction {
        val now = Instant.now().toString()
        insertJournalLocked(taskId, stepId, state, detailCode, now)
        enqueueStepEventLocked(taskId, eventType, stepIndex, payload, now)
    }

    fun enqueueStepEvent(
        taskId: String,
        eventType: String,
        stepIndex: Int?,
        payload: JSONObject = JSONObject(),
    ) = transaction {
        enqueueStepEventLocked(taskId, eventType, stepIndex, payload, Instant.now().toString())
    }

    fun markPaused(taskId: String, stepId: String?, stepIndex: Int, reason: String?) = transaction {
        val now = Instant.now().toString()
        val current = row("SELECT state FROM task_inbox WHERE task_id=?", arrayOf(taskId))
            ?: error("Unknown task")
        require(current == STATE_RUNNING) { "Task is not running" }
        enqueueStepEventLocked(
            taskId,
            "PAUSED_WAITING_USER",
            stepIndex.takeIf { it >= 0 },
            JSONObject().put("reason", reason ?: "operator pause"),
            now,
        )
        execSQL(
            "UPDATE task_inbox SET state=?,updated_at=? WHERE task_id=?",
            arrayOf(STATE_PAUSED, now, taskId),
        )
        insertJournalLocked(taskId, stepId, STATE_PAUSED, "PAUSED_WAITING_USER", now)
    }

    fun markResumeCheck(taskId: String, leaseId: String): Boolean = transaction {
        val current = rawQuery(
            "SELECT state,lease_id FROM task_inbox WHERE task_id=?",
            arrayOf(taskId),
        ).use {
            if (!it.moveToFirst()) return@transaction false
            it.getString(0) to it.getString(1)
        }
        if (current.first != STATE_PAUSED && current.first != STATE_RESUME_CHECK) return@transaction false
        val now = Instant.now().toString()
        execSQL(
            "UPDATE task_inbox SET state=?,lease_id=?,updated_at=? WHERE task_id=?",
            arrayOf(STATE_RESUME_CHECK, leaseId, now, taskId),
        )
        if (current.first == STATE_RESUME_CHECK && current.second == leaseId) return@transaction true
        enqueueStepEventLocked(
            taskId,
            "RESUME_CHECK",
            null,
            JSONObject().put("reason", "operator returned control"),
            now,
        )
        insertJournalLocked(taskId, null, STATE_RESUME_CHECK, "RESUME_CHECK", now)
        true
    }

    fun claimResume(taskId: String? = null): PendingTask? = transaction {
        if (row("SELECT 1 FROM task_inbox WHERE state=? LIMIT 1", arrayOf(STATE_RUNNING)) != null) {
            return@transaction null
        }
        val task = if (taskId == null) {
            rawQuery(
                "SELECT task_id,payload,lease_id FROM task_inbox WHERE state=? ORDER BY received_at,rowid LIMIT 1",
                arrayOf(STATE_RESUME_CHECK),
            ).use {
                if (it.moveToFirst()) PendingTask(it.getString(0), it.getString(1), it.getString(2)) else null
            }
        } else {
            rawQuery(
                "SELECT task_id,payload,lease_id FROM task_inbox WHERE task_id=? AND state=? LIMIT 1",
                arrayOf(taskId, STATE_RESUME_CHECK),
            ).use {
                if (it.moveToFirst()) PendingTask(it.getString(0), it.getString(1), it.getString(2)) else null
            }
        }
        task?.let {
            val now = Instant.now().toString()
            execSQL(
                "UPDATE task_inbox SET state=?,updated_at=? WHERE task_id=? AND state=?",
                arrayOf(STATE_RUNNING, now, it.taskId, STATE_RESUME_CHECK),
            )
            insertJournalLocked(it.taskId, null, STATE_RUNNING, "TASK_RESUME_CLAIMED_LOCAL", now)
        }
        task
    }

    fun hasBlockingHead(): Boolean = readableDatabase.rawQuery(
        "SELECT 1 FROM task_inbox WHERE state IN (?,?) LIMIT 1",
        arrayOf(STATE_PAUSED, STATE_RESUME_CHECK),
    ).use { it.moveToFirst() }

    fun finish(
        taskId: String,
        succeeded: Boolean,
        errorCode: String = "TASK_EXECUTION_FAILED",
        result: JSONObject = JSONObject(),
        detail: String = "Companion terminated the task safely",
    ) =
        transaction {
            val leaseId = row("SELECT lease_id FROM task_inbox WHERE task_id=?", arrayOf(taskId))
                ?: error("Unknown task")
            val now = Instant.now().toString()
            val terminalState = if (succeeded) TERMINAL_SUCCEEDED else TERMINAL_FAILED
            val terminalDetailCode = if (succeeded) "TASK_SUCCEEDED" else errorCode
            execSQL(
                "UPDATE task_inbox SET state=?,terminal_state=?,updated_at=? WHERE task_id=?",
                arrayOf(STATE_TERMINAL_PENDING, terminalState, now, taskId),
            )
            insertJournalLocked(taskId, null, terminalState, terminalDetailCode, now)
            enqueueTerminalLocked(taskId, leaseId, succeeded, errorCode, now, result, detail)
        }

    /** Returns only a contiguous due prefix so later records cannot overtake a delayed one. */
    fun pendingEvents(now: Instant = Instant.now(), limit: Int = 50): List<OutboxEvent> {
        val candidates = readableDatabase.rawQuery(
            "SELECT id,path,payload,attempt_count,next_attempt_at FROM event_outbox " +
                "WHERE delivered_at IS NULL AND permanent_failure_at IS NULL ORDER BY id LIMIT ?",
            arrayOf(limit.coerceIn(1, 100).toString()),
        ).use { cursor ->
            buildList {
                while (cursor.moveToNext()) {
                    add(
                        DueOutboxEvent(
                            OutboxEvent(
                                cursor.getLong(0),
                                cursor.getString(1),
                                cursor.getString(2),
                                cursor.getInt(3),
                            ),
                            Instant.parse(cursor.getString(4)),
                        ),
                    )
                }
            }
        }
        return candidates.takeWhile { !it.nextAttemptAt.isAfter(now) }.map(DueOutboxEvent::event)
    }

    fun markDelivered(id: Long) = transaction {
        val terminalTaskId = rawQuery(
            "SELECT task_id FROM event_outbox WHERE id=? AND is_terminal=1 AND delivered_at IS NULL",
            arrayOf(id.toString()),
        ).use { if (it.moveToFirst()) it.getString(0) else null }
        val now = Instant.now().toString()
        execSQL(
            "UPDATE event_outbox SET delivered_at=?,last_error=NULL WHERE id=? AND delivered_at IS NULL",
            arrayOf(now, id),
        )
        if (terminalTaskId != null) {
            execSQL(
                "UPDATE task_inbox SET state=?,updated_at=? WHERE task_id=? AND state=?",
                arrayOf(STATE_TERMINAL_CONFIRMED, now, terminalTaskId, STATE_TERMINAL_PENDING),
            )
        }
    }

    fun recordDeliveryFailure(id: Long, error: String, nextAttemptAt: Instant) =
        writableDatabase.execSQL(
            "UPDATE event_outbox SET attempt_count=attempt_count+1,next_attempt_at=?,last_error=? " +
                "WHERE id=? AND delivered_at IS NULL AND permanent_failure_at IS NULL",
            arrayOf(nextAttemptAt.toString(), error.take(MAX_ERROR_LENGTH), id),
        )

    fun markPermanentlyRejected(id: Long, error: String) = transaction {
        val rejected = rawQuery(
            "SELECT task_id,is_terminal FROM event_outbox WHERE id=? AND delivered_at IS NULL",
            arrayOf(id.toString()),
        ).use { if (it.moveToFirst()) it.getString(0) to (it.getInt(1) == 1) else null }
        val now = Instant.now().toString()
        execSQL(
            "UPDATE event_outbox SET attempt_count=attempt_count+1,last_error=?,permanent_failure_at=? " +
                "WHERE id=? AND delivered_at IS NULL AND permanent_failure_at IS NULL",
            arrayOf(error.take(MAX_ERROR_LENGTH), now, id),
        )
        if (rejected?.first != null) {
            // Once an ordered record is permanently rejected, later records for that task can no
            // longer be delivered without violating its event sequence.
            execSQL(
                "UPDATE event_outbox SET last_error=?,permanent_failure_at=? " +
                    "WHERE task_id=? AND id>? AND delivered_at IS NULL AND permanent_failure_at IS NULL",
                arrayOf("PREVIOUS_EVENT_REJECTED", now, rejected.first, id),
            )
        }
        if (rejected?.second == true || rejected?.first != null) {
            execSQL(
                "UPDATE task_inbox SET state=?,updated_at=? WHERE task_id=? AND state=?",
                arrayOf(STATE_TERMINAL_REJECTED, now, rejected.first, STATE_TERMINAL_PENDING),
            )
        }
    }

    fun recoverInterruptedRuns() = transaction {
        val interrupted = rawQuery(
            "SELECT task_id,lease_id FROM task_inbox WHERE state=?",
            arrayOf(STATE_RUNNING),
        ).use { buildList { while (it.moveToNext()) add(it.getString(0) to it.getString(1)) } }
        for ((taskId, leaseId) in interrupted) {
            val now = Instant.now().toString()
            execSQL(
                "UPDATE task_inbox SET state=?,updated_at=? WHERE task_id=?",
                arrayOf(STATE_RESUME_CHECK, now, taskId),
            )
            insertJournalLocked(taskId, null, STATE_RESUME_CHECK, "RESUME_CHECK", now)
        }
    }

    fun dueEventsByTask(now: Instant = Instant.now(), limitPerTask: Int = 20): List<OutboxEvent> {
        val grouped = linkedMapOf<String, MutableList<OutboxEvent>>()
        readableDatabase.rawQuery(
            "SELECT id,path,payload,attempt_count,next_attempt_at,IFNULL(task_id,'') FROM event_outbox " +
                "WHERE delivered_at IS NULL AND permanent_failure_at IS NULL ORDER BY id",
            emptyArray(),
        ).use { cursor ->
            while (cursor.moveToNext()) {
                val nextAttempt = Instant.parse(cursor.getString(4))
                if (nextAttempt.isAfter(now)) continue
                val taskId = cursor.getString(5).ifBlank { "_global" }
                val bucket = grouped.getOrPut(taskId) { mutableListOf() }
                if (bucket.size >= limitPerTask) continue
                bucket += OutboxEvent(
                    cursor.getLong(0),
                    cursor.getString(1),
                    cursor.getString(2),
                    cursor.getInt(3),
                )
            }
        }
        return grouped.values.flatten().sortedBy { it.id }
    }

    private fun SQLiteDatabase.enqueueStepEventLocked(
        taskId: String,
        eventType: String,
        stepIndex: Int?,
        payload: JSONObject,
        now: String,
    ) {
        val leaseAndSequence = rawQuery(
            "SELECT lease_id,next_sequence,state FROM task_inbox WHERE task_id=?",
            arrayOf(taskId),
        ).use {
            require(it.moveToFirst()) { "Unknown task" }
            Triple(it.getString(0), it.getInt(1), it.getString(2))
        }
        require(
            leaseAndSequence.third == STATE_RUNNING ||
                (
                    eventType in setOf("RESUME_CHECK", "PAUSED_WAITING_USER") &&
                        leaseAndSequence.third in setOf(STATE_RUNNING, STATE_PAUSED, STATE_RESUME_CHECK)
                    ),
        ) { "Task is not running" }
        val body = JSONObject().put("leaseId", leaseAndSequence.first)
            .put("sequence", leaseAndSequence.second)
            .put("eventType", eventType)
            .put("stepIndex", stepIndex)
            .put("payload", payload)
            .toString()
        enqueueLocked(
            "$taskId:${leaseAndSequence.first}:event:${leaseAndSequence.second}",
            taskId,
            "/companion/v2/tasks/$taskId/events",
            body,
            false,
            now,
        )
        execSQL(
            "UPDATE task_inbox SET next_sequence=?,updated_at=? WHERE task_id=?",
            arrayOf(leaseAndSequence.second + 1, now, taskId),
        )
    }

    private fun SQLiteDatabase.enqueueTerminalLocked(
        taskId: String,
        leaseId: String,
        succeeded: Boolean,
        errorCode: String,
        now: String,
        result: JSONObject = JSONObject(),
        detail: String = "Companion terminated the task safely",
    ) {
        val endpoint = if (succeeded) "complete" else "fail"
        val sanitizedResult = JSONObject()
        result.keys().forEach { key ->
            val lowered = key.lowercase()
            if (listOf("password", "token", "secret", "cookie").none { it in lowered }) {
                sanitizedResult.put(key, result.opt(key))
            }
        }
        if (succeeded && sanitizedResult.length() == 0) {
            sanitizedResult.put("outcome", "ok")
            sanitizedResult.put("resultType", resultTypeForPayload(taskId))
            sanitizedResult.put("schemaVersion", 1)
        }
        val body = if (succeeded) {
            JSONObject().put("leaseId", leaseId).put("result", sanitizedResult)
        } else {
            JSONObject().put("leaseId", leaseId).put("errorCode", errorCode)
                .put("detail", detail.take(MAX_ERROR_LENGTH))
        }
        enqueueLocked(
            "$taskId:$leaseId:$endpoint",
            taskId,
            "/companion/v2/tasks/$taskId/$endpoint",
            body.toString(),
            true,
            now,
        )
    }

    private fun SQLiteDatabase.enqueueTerminalForReplacementLease(
        taskId: String,
        leaseId: String,
        succeeded: Boolean,
    ) {
        val now = Instant.now().toString()
        if (succeeded) {
            enqueueTerminalLocked(taskId, leaseId, true, "TASK_SUCCEEDED", now)
        } else {
            val body = JSONObject().put("leaseId", leaseId)
                .put("errorCode", "TASK_PREVIOUSLY_TERMINATED")
                .put("detail", "Companion will not replay a previously terminated task")
            enqueueLocked(
                "$taskId:$leaseId:fail",
                taskId,
                "/companion/v2/tasks/$taskId/fail",
                body.toString(),
                true,
                now,
            )
        }
    }

    private fun SQLiteDatabase.resultTypeForPayload(taskId: String): String {
        val payload = row("SELECT payload FROM task_inbox WHERE task_id=?", arrayOf(taskId)).orEmpty()
        return resultTypeForClaimPayload(payload)
    }

    private fun SQLiteDatabase.enqueueLocked(
        key: String,
        taskId: String,
        path: String,
        payload: String,
        terminal: Boolean,
        now: String,
    ) {
        insertWithOnConflict("event_outbox", null, ContentValues().apply {
            put("dedupe_key", key)
            put("task_id", taskId)
            put("path", path)
            put("payload", payload)
            put("is_terminal", if (terminal) 1 else 0)
            put("attempt_count", 0)
            put("next_attempt_at", now)
            put("created_at", now)
        }, SQLiteDatabase.CONFLICT_IGNORE)
    }

    private fun SQLiteDatabase.insertJournalLocked(
        taskId: String,
        stepId: String?,
        state: String,
        detailCode: String,
        occurredAt: String,
    ) {
        insertOrThrow("run_journal", null, ContentValues().apply {
            put("task_id", taskId)
            put("step_id", stepId)
            put("state", state)
            put("detail_code", detailCode)
            put("occurred_at", occurredAt)
        })
    }

    fun saveCheckpoint(
        taskId: String,
        attemptId: String,
        stateId: String,
        snapshotHash: String,
        recipeHash: String,
        accountId: String,
        bindingVersion: Int,
        cursor: Int,
        itemId: String?,
    ) = transaction {
        val now = Instant.now().toString()
        val revision = (row("SELECT IFNULL(MAX(revision),0) FROM task_checkpoint WHERE task_id=?", arrayOf(taskId))?.toIntOrNull() ?: 0) + 1
        insertOrThrow("task_checkpoint", null, ContentValues().apply {
            put("task_id", taskId)
            put("attempt_id", attemptId)
            put("revision", revision)
            put("state_id", stateId)
            put("snapshot_hash", snapshotHash)
            put("recipe_hash", recipeHash)
            put("account_id", accountId)
            put("binding_version", bindingVersion)
            put("loop_cursor", cursor)
            put("item_id", itemId)
            put("created_at", now)
        })
        insertJournalLocked(taskId, stateId, "CHECKPOINT", "CHECKPOINT_$revision", now)
    }

    fun latestCheckpoint(taskId: String): JSONObject? = readableDatabase.rawQuery(
        "SELECT attempt_id,revision,state_id,snapshot_hash,recipe_hash,account_id,binding_version,loop_cursor,item_id " +
            "FROM task_checkpoint WHERE task_id=? ORDER BY revision DESC LIMIT 1",
        arrayOf(taskId),
    ).use {
        if (!it.moveToFirst()) return@use null
        JSONObject()
            .put("attemptId", it.getString(0))
            .put("revision", it.getInt(1))
            .put("stateId", it.getString(2))
            .put("snapshotHash", it.getString(3))
            .put("recipeHash", it.getString(4))
            .put("accountId", it.getString(5))
            .put("bindingVersion", it.getInt(6))
            .put("loopCursor", it.getInt(7))
            .put("itemId", it.getString(8))
    }

    private fun createCheckpointAndJournalTables(db: SQLiteDatabase) {
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS task_checkpoint(" +
                "id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL,attempt_id TEXT NOT NULL," +
                "revision INTEGER NOT NULL,state_id TEXT NOT NULL,snapshot_hash TEXT NOT NULL," +
                "recipe_hash TEXT NOT NULL,account_id TEXT NOT NULL,binding_version INTEGER NOT NULL," +
                "loop_cursor INTEGER NOT NULL DEFAULT 0,item_id TEXT,created_at TEXT NOT NULL," +
                "FOREIGN KEY(task_id) REFERENCES task_inbox(task_id)," +
                "UNIQUE(task_id,attempt_id,revision))",
        )
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS action_journal(" +
                "action_key TEXT PRIMARY KEY,task_id TEXT NOT NULL,status TEXT NOT NULL," +
                "parameter_hash TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL," +
                "FOREIGN KEY(task_id) REFERENCES task_inbox(task_id))",
        )
    }

    fun actionJournal(actionKey: String): ActionJournalRecord? =
        readableDatabase.rawQuery(
            "SELECT action_key,task_id,status,parameter_hash FROM action_journal WHERE action_key=?",
            arrayOf(actionKey),
        ).use { cursor ->
            if (!cursor.moveToFirst()) {
                null
            } else {
                ActionJournalRecord(
                    actionKey = cursor.getString(0),
                    taskId = cursor.getString(1),
                    status = cursor.getString(2),
                    parameterHash = cursor.getString(3),
                )
            }
        }

    fun recordActionIntent(actionKey: String, taskId: String, parameterHash: String): String = transaction {
        val existing = actionJournalLocked(actionKey)
        if (existing == null) {
            val now = Instant.now().toString()
            insertOrThrow("action_journal", null, ContentValues().apply {
                put("action_key", actionKey)
                put("task_id", taskId)
                put("status", "INTENT")
                put("parameter_hash", parameterHash)
                put("created_at", now)
                put("updated_at", now)
            })
            return@transaction "INTENT"
        }
        require(existing.taskId == taskId && existing.parameterHash == parameterHash) {
            "Action journal identity mismatch for $actionKey"
        }
        when (existing.status) {
            "APPLIED" -> "APPLIED"
            "INTENT", "UNKNOWN" -> "UNKNOWN"
            else -> error("Illegal action journal status ${existing.status} for $actionKey")
        }
    }

    fun markActionApplied(actionKey: String) = transaction {
        val existing = actionJournalLocked(actionKey)
            ?: error("Cannot mark APPLIED for missing action key $actionKey")
        when (existing.status) {
            "APPLIED" -> Unit
            "INTENT" -> execSQL(
                "UPDATE action_journal SET status=?,updated_at=? WHERE action_key=?",
                arrayOf("APPLIED", Instant.now().toString(), actionKey),
            )
            else -> error("Illegal action journal transition ${existing.status} -> APPLIED for $actionKey")
        }
    }

    fun markActionUnknown(actionKey: String) = transaction {
        val existing = actionJournalLocked(actionKey)
            ?: error("Cannot mark UNKNOWN for missing action key $actionKey")
        when (existing.status) {
            "UNKNOWN" -> Unit
            "INTENT" -> execSQL(
                "UPDATE action_journal SET status=?,updated_at=? WHERE action_key=?",
                arrayOf("UNKNOWN", Instant.now().toString(), actionKey),
            )
            else -> error("Illegal action journal transition ${existing.status} -> UNKNOWN for $actionKey")
        }
    }

    private fun SQLiteDatabase.actionJournalLocked(actionKey: String): ActionJournalRecord? =
        rawQuery(
            "SELECT action_key,task_id,status,parameter_hash FROM action_journal WHERE action_key=?",
            arrayOf(actionKey),
        ).use { cursor ->
            if (!cursor.moveToFirst()) {
                null
            } else {
                ActionJournalRecord(
                    actionKey = cursor.getString(0),
                    taskId = cursor.getString(1),
                    status = cursor.getString(2),
                    parameterHash = cursor.getString(3),
                )
            }
        }

    private fun migrateVersion1To2(db: SQLiteDatabase) {
        db.execSQL("ALTER TABLE task_inbox ADD COLUMN payload_sha256 TEXT NOT NULL DEFAULT ''")
        db.execSQL("ALTER TABLE task_inbox ADD COLUMN terminal_state TEXT")
        db.execSQL("ALTER TABLE event_outbox ADD COLUMN task_id TEXT")
        db.execSQL("ALTER TABLE event_outbox ADD COLUMN is_terminal INTEGER NOT NULL DEFAULT 0")
        db.execSQL("ALTER TABLE event_outbox ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
        db.execSQL("ALTER TABLE event_outbox ADD COLUMN next_attempt_at TEXT NOT NULL DEFAULT ''")
        db.execSQL("ALTER TABLE event_outbox ADD COLUMN last_error TEXT")
        db.execSQL("ALTER TABLE event_outbox ADD COLUMN permanent_failure_at TEXT")
        db.execSQL("UPDATE event_outbox SET next_attempt_at=created_at WHERE next_attempt_at=''")
        db.execSQL(
            "UPDATE event_outbox SET is_terminal=1 WHERE path LIKE '%/complete' OR path LIKE '%/fail'",
        )
        db.execSQL(
            "UPDATE event_outbox SET task_id=(SELECT task_id FROM task_inbox " +
                "WHERE event_outbox.path LIKE '/companion/v2/tasks/' || task_inbox.task_id || '/%')",
        )
        db.execSQL("UPDATE task_inbox SET terminal_state=state WHERE state IN ('SUCCEEDED','FAILED')")
        db.execSQL(
            "UPDATE task_inbox SET state=CASE WHEN EXISTS(" +
                "SELECT 1 FROM event_outbox WHERE event_outbox.task_id=task_inbox.task_id " +
                "AND event_outbox.is_terminal=1 AND event_outbox.delivered_at IS NOT NULL" +
                ") THEN '$STATE_TERMINAL_CONFIRMED' ELSE '$STATE_TERMINAL_PENDING' END " +
                "WHERE state IN ('SUCCEEDED','FAILED')",
        )
        createIndexes(db)
    }

    private fun createIndexes(db: SQLiteDatabase) {
        db.execSQL(
            "CREATE INDEX IF NOT EXISTS event_outbox_delivery_idx " +
                "ON event_outbox(delivered_at,permanent_failure_at,id)",
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS run_journal_task_idx ON run_journal(task_id,id)")
    }

    private fun SQLiteDatabase.row(sql: String, args: Array<String>): String? =
        rawQuery(sql, args).use { if (it.moveToFirst()) it.getString(0) else null }

    private fun <T> transaction(block: SQLiteDatabase.() -> T): T {
        val db = writableDatabase
        db.beginTransaction()
        return try {
            db.block().also { db.setTransactionSuccessful() }
        } finally {
            db.endTransaction()
        }
    }

    private data class ExistingTask(
        val payload: String,
        val leaseId: String,
        val state: String,
        val terminalState: String?,
    )

    private data class DueOutboxEvent(val event: OutboxEvent, val nextAttemptAt: Instant)

    private fun String.sha256(): String = MessageDigest.getInstance("SHA-256")
        .digest(toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }

    companion object {
        internal const val EMPTY_RECIPE_CATALOG = "{\"protocolVersion\":\"cloudctl.recipe/v1\",\"items\":[]}"
        internal const val DATABASE_NAME = "cloudctl-automation.sqlite3"
        private const val VERSION = 4

        internal fun resultTypeForClaimPayload(payload: String): String {
            if (payload.isBlank() || !payload.trimStart().startsWith("{")) {
                return "DeviceProbeResult"
            }
            val json = runCatching { JSONObject(payload) }.getOrNull() ?: return "DeviceProbeResult"
            return when (json.optString("commandType")) {
                "xianyu.publish_listing.v1" -> "XianyuPublishListingResult"
                "xianyu.collect_orders.v1" -> "XianyuCollectOrdersResult"
                "xiaohongshu.publish_note.v1" -> "XiaohongshuPublishNoteResult"
                "device.probe_capabilities.v1" -> "DeviceProbeResult"
                else -> when (json.optString("targetPackage")) {
                    "com.taobao.idlefish" -> "XianyuPublishListingResult"
                    "com.xingin.xhs" -> "XiaohongshuPublishNoteResult"
                    else -> "DeviceProbeResult"
                }
            }
        }

        internal fun sameExecutionPayload(left: String, right: String): Boolean {
            if (left == right) return true
            val leftJson = runCatching { JSONObject(left) }.getOrNull() ?: return false
            val rightJson = runCatching { JSONObject(right) }.getOrNull() ?: return false
            return executionFingerprint(leftJson) == executionFingerprint(rightJson)
        }

        private fun executionFingerprint(value: JSONObject): String {
            val command = value.optJSONObject("command") ?: value.takeIf {
                it.optString("protocolVersion") == "cloudctl.command/v1"
            }
            if (command != null) {
                val normalized = JSONObject(command.toString())
                normalized.remove("attemptId")
                normalized.remove("lease")
                // Recipe version/hash/engine, snapshot and all execution parameters stay frozen.
                return CanonicalJson.dumps(normalized)
            }
            val steps = value.optJSONArray("steps") ?: org.json.JSONArray()
            val normalizedSteps = org.json.JSONArray()
            for (index in 0 until steps.length()) {
                val step = steps.optJSONObject(index) ?: continue
                val copy = JSONObject(step.toString())
                copy.remove("controlEpoch")
                normalizedSteps.put(copy)
            }
            return CanonicalJson.dumps(JSONObject()
                .put("recipe", value.optJSONObject("recipe") ?: JSONObject.NULL)
                .put("taskId", value.optString("taskId"))
                .put("deviceId", value.optString("deviceId"))
                .put("targetPackage", value.optString("targetPackage"))
                .put("steps", normalizedSteps)
                .put("mediaDelivery", value.optJSONObject("mediaDelivery") ?: JSONObject.NULL))
        }
        const val STATE_QUEUED = "QUEUED"
        const val STATE_RUNNING = "RUNNING"
        const val STATE_PAUSED = "PAUSED_WAITING_USER"
        const val STATE_RESUME_CHECK = "RESUME_CHECK"
        const val STATE_TERMINAL_PENDING = "TERMINAL_PENDING_UPLOAD"
        const val STATE_TERMINAL_CONFIRMED = "TERMINAL_CONFIRMED"
        const val STATE_TERMINAL_REJECTED = "TERMINAL_REJECTED"
        const val TERMINAL_SUCCEEDED = "SUCCEEDED"
        const val TERMINAL_FAILED = "FAILED"
        const val MAX_ERROR_LENGTH = 1_000
    }
}
