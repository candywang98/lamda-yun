package com.company.cloudctl.companion.im

import java.security.MessageDigest

/**
 * Device and server share one raw string
 * (pa-im-m3/20260922.1 §4):
 * `deviceId|platform|peerKey|occurredAtEpochSecond|canonicalText`.
 * [deviceId] is the binding id, never an ADB serial.
 */
object ImDedupe {
    fun raw(deviceId: String, event: ImEvent): String {
        val text = ImCanonicalText.canonical(event.text)
        return "$deviceId|${event.platform}|${event.peerKey}|${event.occurredAt.epochSecond}|$text"
    }

    fun key(deviceId: String, event: ImEvent): String = sha256(raw(deviceId, event))

    fun sha256(raw: String): String =
        MessageDigest.getInstance("SHA-256")
            .digest(raw.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
}
