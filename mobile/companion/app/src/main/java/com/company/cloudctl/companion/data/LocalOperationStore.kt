package com.company.cloudctl.companion.data

import android.content.Context
import com.company.cloudctl.companion.operations.OperationDefinition
import com.company.cloudctl.companion.operations.OperationReceipt
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

/** Persists placeholder button presses until a real executor is wired. */
class LocalOperationStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    @Synchronized
    fun enqueue(
        definition: OperationDefinition,
        parameters: Map<String, String> = emptyMap(),
        state: String = "PLACEHOLDER",
        detail: String? = null,
    ): OperationReceipt {
        val receipt = OperationReceipt(
            id = "local-${UUID.randomUUID()}",
            operationKey = definition.key,
            title = definition.title,
            module = definition.module,
            state = state,
            detail = detail ?: if (parameters.isEmpty()) "待接入真实自动化逻辑" else "待接入真实自动化逻辑 · 参数已保存",
            createdAt = Instant.now().toString(),
        )
        val values = read().toMutableList()
        values.add(receipt)
        while (values.size > MAX_ITEMS) values.removeAt(0)
        preferences.edit().putString(ITEMS, encode(values).toString()).commit()
        return receipt
    }

    fun snapshot(): List<OperationReceipt> = read().asReversed()

    @Synchronized
    fun toggleState(key: String): Boolean = preferences.getBoolean(toggleKey(key), false)

    @Synchronized
    fun setToggleState(key: String, enabled: Boolean) {
        preferences.edit().putBoolean(toggleKey(key), enabled).commit()
    }

    private fun read(): List<OperationReceipt> = preferences.getString(ITEMS, null)?.let { encoded ->
        runCatching {
            val values = JSONArray(encoded)
            List(values.length()) { index ->
                values.getJSONObject(index).let { value ->
                    OperationReceipt(
                        id = value.getString("id"),
                        operationKey = value.getString("operationKey"),
                        title = value.getString("title"),
                        module = value.getString("module"),
                        state = value.getString("state"),
                        detail = value.getString("detail"),
                        createdAt = value.getString("createdAt"),
                    )
                }
            }
        }.getOrDefault(emptyList())
    } ?: emptyList()

    private fun encode(items: List<OperationReceipt>) = JSONArray().apply {
        items.forEach { item ->
            put(
                JSONObject()
                    .put("id", item.id)
                    .put("operationKey", item.operationKey)
                    .put("title", item.title)
                    .put("module", item.module)
                    .put("state", item.state)
                    .put("detail", item.detail)
                    .put("createdAt", item.createdAt),
            )
        }
    }

    private fun toggleKey(key: String): String = "toggle.$key"

    private companion object {
        const val PREFERENCES = "cloudctl_local_operations"
        const val ITEMS = "items"
        const val MAX_ITEMS = 50
    }
}
