package com.company.cloudctl.companion.network

import java.security.MessageDigest
import java.security.cert.X509Certificate

internal object VerifiedCloudLeafPinPolicy {
    const val PRODUCTION_HOST = "43.133.243.154.sslip.io"
    const val ENROLLED_OLD_PIN = "fe178c22ba4327c0a71cdd0c7561654fb76ff67c02aa5461f076bf2fc60622d1"
    const val VERIFIED_SUCCESSOR_PIN = "f2a9423e27fd8d6cdcd00d76e9da8918a402e118fe52656b84342dda6fb40725"

    private val sha256Pattern = Regex("^[a-f0-9]{64}$")

    fun verify(
        configuredPin: String,
        actualHost: String?,
        chain: Array<X509Certificate>,
        fingerprintOf: (X509Certificate) -> String = ::sha256Fingerprint,
    ) {
        require(chain.isNotEmpty()) { "Cloud certificate chain is empty" }
        require(sha256Pattern.matches(configuredPin)) { "Cloud certificate fingerprint is malformed" }

        val leaf = chain.first()
        val leafFingerprint = fingerprintOf(leaf)
        require(sha256Pattern.matches(leafFingerprint)) { "Cloud certificate fingerprint is malformed" }

        if (MessageDigest.isEqual(leafFingerprint.hexBytes(), configuredPin.hexBytes())) return

        check(
            actualHost == PRODUCTION_HOST &&
                configuredPin == ENROLLED_OLD_PIN &&
                leafFingerprint == VERIFIED_SUCCESSOR_PIN,
        ) { "Cloud certificate fingerprint mismatch" }
        leaf.checkValidity()
    }

    private fun sha256Fingerprint(certificate: X509Certificate): String =
        MessageDigest.getInstance("SHA-256")
            .digest(certificate.encoded)
            .joinToString("") { "%02x".format(it) }

    private fun String.hexBytes(): ByteArray =
        chunked(2).map { it.toInt(16).toByte() }.toByteArray()
}
