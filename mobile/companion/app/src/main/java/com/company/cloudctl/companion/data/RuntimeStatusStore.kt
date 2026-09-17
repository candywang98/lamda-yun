package com.company.cloudctl.companion.data

import android.content.Context
import com.company.cloudctl.companion.model.AuthorizedTaskState
import com.company.cloudctl.companion.model.AuthorizedTaskStatus
import com.company.cloudctl.companion.model.LocalRunLog
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

data class RuntimeSnapshot(
    val task: AuthorizedTaskStatus?,
    val logs: List<LocalRunLog>,
    val presenceOnline: Boolean = false,
    /** B17 startup capability self-check (CAP_*), queryable from the device profile. */
    val capabilities: Map<String, CapabilityProbeStatus> = emptyMap(),
    /** B17 SUSPECT_ORPHANED alert (control-plane/v1 §3): reported, never locally cleared. */
    val suspectOrphanedAlert: SuspectOrphanedAlert? = null,
)

data class CapabilityProbeStatus(
    val capabilityId: String,
    /** null = detected/unknown (e.g. ADB motion injection cannot be probed in-process). */
    val detected: Boolean?,
    val detail: String? = null,
)

data class SuspectOrphanedAlert(
    val taskId: String,
    val detail: String,
    val raisedAt: Instant,
)

class RuntimeStatusStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    @Synchronized
    fun updateTask(
        taskId: String,
        state: AuthorizedTaskState,
        step: String,
        detailCode: String,
        stepId: String? = null,
    ) {
        val now = Instant.now()
        val logs = readLogs().toMutableList().apply {
            add(LocalRunLog(taskId, stepId, state.name, detailCode, now))
            while (size > MAX_LOGS) removeAt(0)
        }
        preferences.edit()
            .putString(
                TASK,
                JSONObject()
                    .put("taskId", taskId)
                    .put("state", state.name)
                    .put("step", step)
                    .put("updatedAt", now.toString())
                    .toString(),
            )
            .putString(LOGS, encodeLogs(logs).toString())
            .commit()
    }

    @Synchronized
    fun markPresence(online: Boolean) {
        preferences.edit().putBoolean(PRESENCE_ONLINE, online).commit()
    }

    /** B17 startup capability self-check; overwrites the previous probe result. */
    @Synchronized
    fun updateCapabilities(values: Map<String, CapabilityProbeStatus>) {
        val encoded = JSONObject()
        values.forEach { (id, status) ->
            encoded.put(
                id,
                JSONObject()
                    .put("detected", status.detected ?: JSONObject.NULL)
                    .put("detail", status.detail ?: JSONObject.NULL),
            )
        }
        preferences.edit().putString(CAPABILITIES, encoded.toString()).commit()
    }

    /**
     * B17 control-plane/v1 §3: SUSPECT_ORPHANED is an alert only — raising it
     * never mutates the mirror; only the server's authoritative events clear
     * the underlying PAUSED head, after which [clearSuspectOrphanedAlert] runs.
     */
    @Synchronized
    fun markSuspectOrphaned(taskId: String, detail: String) {
        preferences.edit()
            .putString(
                SUSPECT_ORPHANED,
                JSONObject()
                    .put("taskId", taskId)
                    .put("detail", detail)
                    .put("raisedAt", Instant.now().toString())
                    .toString(),
            )
            .commit()
    }

    @Synchronized
    fun clearSuspectOrphanedAlert() {
        preferences.edit().remove(SUSPECT_ORPHANED).commit()
    }

    fun snapshot(): RuntimeSnapshot = RuntimeSnapshot(
        task = readTask(),
        logs = readLogs(),
        presenceOnline = preferences.getBoolean(PRESENCE_ONLINE, false),
        capabilities = readCapabilities(),
        suspectOrphanedAlert = readSuspectOrphanedAlert(),
    )

    private fun readCapabilities(): Map<String, CapabilityProbeStatus> =
        preferences.getString(CAPABILITIES, null)?.let { encoded ->
            runCatching {
                val value = JSONObject(encoded)
                buildMap {
                    value.keys().forEach { id ->
                        val status = value.getJSONObject(id)
                        put(
                            id,
                            CapabilityProbeStatus(
                                capabilityId = id,
                                detected = if (status.isNull("detected")) null else status.getBoolean("detected"),
                                detail = status.optString("detail").takeIf { it.isNotBlank() },
                            ),
                        )
                    }
                }
            }.getOrDefault(emptyMap())
        } ?: emptyMap()

    private fun readSuspectOrphanedAlert(): SuspectOrphanedAlert? =
        preferences.getString(SUSPECT_ORPHANED, null)?.let { encoded ->
            runCatching {
                val value = JSONObject(encoded)
                SuspectOrphanedAlert(
                    taskId = value.getString("taskId"),
                    detail = value.getString("detail"),
                    raisedAt = Instant.parse(value.getString("raisedAt")),
                )
            }.getOrNull()
        }

    private fun readTask(): AuthorizedTaskStatus? = preferences.getString(TASK, null)?.let { encoded ->
        runCatching {
            val value = JSONObject(encoded)
            val state = enumValueOf<AuthorizedTaskState>(value.getString("state"))
            AuthorizedTaskStatus(
                taskRunId = value.getString("taskId"),
                state = state,
                step = value.getString("step"),
                cancellable = state == AuthorizedTaskState.Running,
            )
        }.getOrNull()
    }

    private fun readLogs(): List<LocalRunLog> = preferences.getString(LOGS, null)?.let { encoded ->
        runCatching {
            val values = JSONArray(encoded)
            List(values.length()) { index ->
                values.getJSONObject(index).let { value ->
                    LocalRunLog(
                        taskId = value.getString("taskId"),
                        stepId = value.optString("stepId").takeIf(String::isNotBlank),
                        state = value.getString("state"),
                        detailCode = value.getString("detailCode"),
                        occurredAt = Instant.parse(value.getString("occurredAt")),
                    )
                }
            }
        }.getOrDefault(emptyList())
    } ?: emptyList()

    private fun encodeLogs(logs: List<LocalRunLog>) = JSONArray().apply {
        logs.forEach { log ->
            put(
                JSONObject()
                    .put("taskId", log.taskId)
                    .put("stepId", log.stepId)
                    .put("state", log.state)
                    .put("detailCode", log.detailCode)
                    .put("occurredAt", log.occurredAt.toString()),
            )
        }
    }

    private companion object {
        const val PREFERENCES = "cloudctl_runtime_status"
        const val TASK = "task"
        const val LOGS = "logs"
        const val PRESENCE_ONLINE = "presence_online"
        const val CAPABILITIES = "capabilities"
        const val SUSPECT_ORPHANED = "suspect_orphaned_alert"
        const val MAX_LOGS = 50
    }
}
