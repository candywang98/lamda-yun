package com.company.cloudctl.companion.data

import android.content.Context
import com.company.cloudctl.companion.model.ArtifactDeliveryState
import com.company.cloudctl.companion.model.ArtifactDeliveryStatus
import com.company.cloudctl.companion.model.ArtifactKind
import org.json.JSONArray
import org.json.JSONObject

class ArtifactDeliveryStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    @Synchronized
    fun upsert(status: ArtifactDeliveryStatus) {
        val values = read().filterNot { key(it) == key(status) }.toMutableList()
        values += status
        while (values.size > MAX_ITEMS) values.removeAt(0)
        preferences.edit().putString(ITEMS, encode(values).toString()).commit()
    }

    fun snapshot(): List<ArtifactDeliveryStatus> = read().asReversed()

    private fun read(): List<ArtifactDeliveryStatus> = preferences.getString(ITEMS, null)?.let { encoded ->
        runCatching {
            val values = JSONArray(encoded)
            List(values.length()) { index ->
                val value = values.getJSONObject(index)
                ArtifactDeliveryStatus(
                    artifactId = value.getString("artifactId"),
                    deliveryId = value.optString("deliveryId"),
                    kind = enumValueOf<ArtifactKind>(value.optString("kind", ArtifactKind.Unknown.name)),
                    state = enumValueOf<ArtifactDeliveryState>(value.optString("state", ArtifactDeliveryState.Unknown.name)),
                    bytesReceived = value.optLong("bytesReceived"),
                    sizeBytes = value.optLong("sizeBytes"),
                    progressPercent = value.optInt("progressPercent"),
                    errorCode = value.optString("errorCode").takeIf(String::isNotBlank),
                    localUri = value.optString("localUri").takeIf(String::isNotBlank),
                )
            }
        }.getOrDefault(emptyList())
    } ?: emptyList()

    private fun encode(items: List<ArtifactDeliveryStatus>) = JSONArray().apply {
        items.forEach { item ->
            put(JSONObject()
                .put("artifactId", item.artifactId)
                .put("deliveryId", item.deliveryId)
                .put("kind", item.kind.name)
                .put("state", item.state.name)
                .put("bytesReceived", item.bytesReceived)
                .put("sizeBytes", item.sizeBytes)
                .put("progressPercent", item.progressPercent)
                .put("errorCode", item.errorCode)
                .put("localUri", item.localUri))
        }
    }

    private companion object {
        const val PREFERENCES = "cloudctl_artifact_deliveries"
        const val ITEMS = "items"
        const val MAX_ITEMS = 100
    }

    private fun key(status: ArtifactDeliveryStatus): String = "${status.deliveryId}\u0000${status.artifactId}"
}
