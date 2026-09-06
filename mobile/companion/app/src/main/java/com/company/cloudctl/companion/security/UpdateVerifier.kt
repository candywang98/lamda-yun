package com.company.cloudctl.companion.security

import com.company.cloudctl.companion.BuildConfig
import java.security.KeyFactory
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.util.Base64

object UpdateVerifier {
    fun verify(version: String, sha256: String, downloadUrl: String, signature: String): Boolean {
        if (!Regex("^[a-fA-F0-9]{64}$").matches(sha256)) return false
        val payload = "$version\n${sha256.lowercase()}\n$downloadUrl".toByteArray(Charsets.UTF_8)
        return verifyPayload(payload, signature)
    }

    fun verifyPayload(payload: ByteArray, signature: String): Boolean = runCatching {
        val key = KeyFactory.getInstance("Ed25519").generatePublic(
            X509EncodedKeySpec(Base64.getDecoder().decode(BuildConfig.APP_UPDATE_PUBLIC_KEY)),
        )
        Signature.getInstance("Ed25519").run {
            initVerify(key)
            update(payload)
            verify(Base64.getDecoder().decode(signature))
        }
    }.getOrDefault(false)
}

