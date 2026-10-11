package com.company.cloudctl.companion.im

import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

const val IM_CHAT_COLLECTION_PROTOCOL = "im-chat-collection/1"

data class ImChatCollectionTarget(
    val tenantId: String, val deviceId: String, val threadId: String,
    val peerKey: String, val peerName: String, val mobileBindingId: String,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("protocolVersion", IM_CHAT_COLLECTION_PROTOCOL).put("tenantId", tenantId)
        .put("deviceId", deviceId).put("threadId", threadId).put("platform", "xianyu")
        .put("peerKey", peerKey).put("peerName", peerName).put("mobileBindingId", mobileBindingId)
        .put("scope", "VISIBLE_SCREEN").put("noSend", true)

    companion object {
        fun parse(value: JSONObject): ImChatCollectionTarget {
            require(value.keys().asSequence().toSet() == setOf("protocolVersion", "tenantId", "deviceId",
                "threadId", "platform", "peerKey", "peerName", "mobileBindingId", "scope", "noSend"))
            require(value.getString("protocolVersion") == IM_CHAT_COLLECTION_PROTOCOL)
            require(value.getString("platform") == "xianyu" && value.getString("scope") == "VISIBLE_SCREEN")
            require(value.opt("noSend") == true)
            fun text(key: String): String = (value.get(key) as String).also {
                require(it.isNotBlank() && it == it.trim() && it.codePointCount(0, it.length) <= 128 && '\u0000' !in it)
            }
            fun uuid(key: String): String = text(key).also {
                require(Regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$").matches(it))
            }
            return ImChatCollectionTarget(uuid("tenantId"), uuid("deviceId"), uuid("threadId"),
                text("peerKey"), text("peerName"), uuid("mobileBindingId"))
        }
    }
}

/** Immutable serialized snapshot: a retry reuses this exact capture, never reads another screen. */
class ImChatCollectionSnapshot private constructor(private val encoded: String) {
    fun toJson(): JSONObject = JSONObject(encoded)
    companion object {
        fun capture(peer: String, bubbles: List<ChatBubble>, now: Instant): ImChatCollectionSnapshot {
            val messages = JSONArray()
            val readable = bubbles.filter { it.text.isNotBlank() }
            var truncated = readable.size > 20
            readable.take(20).forEachIndexed { index, bubble ->
                val text = bubble.text.trim()
                val count = text.codePointCount(0, text.length)
                if (count > 2000) truncated = true
                val bounded = text.substring(0, text.offsetByCodePoints(0, minOf(count, 2000)))
                messages.put(JSONObject().put("direction", if (bubble.inbound) "IN" else "OUT")
                    .put("text", bounded).put("visibleOrder", index).put("occurredAt", JSONObject.NULL))
            }
            val value = JSONObject().put("capturedAt", now.toString()).put("scope", "VISIBLE_SCREEN")
                .put("completeness", "VISIBLE_ONLY").put("accountIdentity", "UNVERIFIED")
                .put("peerIdentity", JSONObject().put("status", "DISPLAY_NAME_MATCH")
                    .put("observedName", peer.trim()).put("basis", "CHAT_HEADER"))
                .put("messages", messages).put("truncated", truncated)
            while (value.toString().toByteArray(Charsets.UTF_8).size > 64000) {
                messages.remove(messages.length() - 1)
                value.put("truncated", true)
            }
            return ImChatCollectionSnapshot(value.toString())
        }
    }
}
