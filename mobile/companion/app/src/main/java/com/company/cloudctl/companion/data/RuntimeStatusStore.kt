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

    fun snapshot(): RuntimeSnapshot = RuntimeSnapshot(readTask(), readLogs(), preferences.getBoolean(PRESENCE_ONLINE, false))

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
        const val MAX_LOGS = 50
    }
}
