package com.company.cloudctl.companion.im

import org.json.JSONObject

/** Untrusted, allowlisted notification context; never part of message identity. */
data class ImNotificationMetadata(
    val packageName: String? = null,
    val channelId: String? = null,
    val category: String? = null,
) {
    fun bounded(): ImNotificationMetadata = copy(
        // Production intake is xianyu only. Invalid context must not lose a message.
        packageName = packageName?.takeIf { it == XIANYU_PACKAGE },
        channelId = channelId?.let { ImCanonicalText.takeCodePoints(it, 256) },
        category = category?.let { ImCanonicalText.takeCodePoints(it, 64) },
    )

    fun toJson(): JSONObject = bounded().let {
        JSONObject()
            .put("packageName", it.packageName)
            .put("channelId", it.channelId)
            .put("category", it.category)
    }

    companion object {
        // This exact package is also within the contract's 128-character bound.
        const val XIANYU_PACKAGE = "com.taobao.idlefish"

        fun fromJson(json: JSONObject): ImNotificationMetadata = ImNotificationMetadata(
            packageName = json.nullableString("packageName"),
            channelId = json.nullableString("channelId"),
            category = json.nullableString("category"),
        ).bounded()

        private fun JSONObject.nullableString(key: String): String? =
            if (isNull(key)) null else getString(key)
    }
}
