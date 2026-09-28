package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.features.xianyu.orders.orderConnectionScope
import java.math.BigInteger
import java.security.MessageDigest
import java.security.Principal
import java.security.PublicKey
import java.security.cert.CertificateExpiredException
import java.security.cert.CertificateNotYetValidException
import java.security.cert.X509Certificate
import java.util.Date
import javax.security.auth.x500.X500Principal
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class VerifiedCloudLeafPinPolicyTest {
    @Test
    fun preservesExactEnrolledLeafPinWithoutHostOrValidityFallback() {
        val certificate = SyntheticCertificate(
            encodedBytes = "enrolled-leaf".toByteArray(),
            notBefore = Date(0),
            notAfter = Date(1),
        )
        val pin = sha256(certificate.encoded)

        PinnedTrustManager(pin, null).checkServerTrusted(arrayOf(certificate), "RSA")
    }

    @Test
    fun acceptsVerifiedSuccessorOnlyForExactProductionHostAndOldPin() {
        val certificate = currentlyValidCertificate()

        verifySuccessor(VerifiedCloudLeafPinPolicy.PRODUCTION_HOST, certificate)

        listOf(
            null,
            "api.${VerifiedCloudLeafPinPolicy.PRODUCTION_HOST}",
            "${VerifiedCloudLeafPinPolicy.PRODUCTION_HOST}.example",
            "43.133.243.154",
        ).forEach { host ->
            assertFailsWith<IllegalStateException> {
                verifySuccessor(host, certificate)
            }
        }
        assertFailsWith<IllegalStateException> {
            VerifiedCloudLeafPinPolicy.verify(
                configuredPin = "a".repeat(64),
                actualHost = VerifiedCloudLeafPinPolicy.PRODUCTION_HOST,
                chain = arrayOf(certificate),
                fingerprintOf = { VerifiedCloudLeafPinPolicy.VERIFIED_SUCCESSOR_PIN },
            )
        }
    }

    @Test
    fun rejectsMalformedPinsAndEmptyChains() {
        val certificate = currentlyValidCertificate()
        listOf("", "a".repeat(63), "A".repeat(64), "g".repeat(64)).forEach { malformed ->
            assertFailsWith<IllegalArgumentException> {
                VerifiedCloudLeafPinPolicy.verify(
                    configuredPin = malformed,
                    actualHost = VerifiedCloudLeafPinPolicy.PRODUCTION_HOST,
                    chain = arrayOf(certificate),
                )
            }
        }
        assertFailsWith<IllegalArgumentException> {
            VerifiedCloudLeafPinPolicy.verify(
                configuredPin = VerifiedCloudLeafPinPolicy.ENROLLED_OLD_PIN,
                actualHost = VerifiedCloudLeafPinPolicy.PRODUCTION_HOST,
                chain = emptyArray(),
            )
        }
    }

    @Test
    fun rejectsUnknownLeafAndDoesNotSelectSuccessorFromIntermediate() {
        val leaf = currentlyValidCertificate("unknown-leaf")
        val intermediate = currentlyValidCertificate("successor-intermediate")

        assertFailsWith<IllegalStateException> {
            VerifiedCloudLeafPinPolicy.verify(
                configuredPin = VerifiedCloudLeafPinPolicy.ENROLLED_OLD_PIN,
                actualHost = VerifiedCloudLeafPinPolicy.PRODUCTION_HOST,
                chain = arrayOf(leaf, intermediate),
                fingerprintOf = { certificate ->
                    if (certificate === intermediate) {
                        VerifiedCloudLeafPinPolicy.VERIFIED_SUCCESSOR_PIN
                    } else {
                        "b".repeat(64)
                    }
                },
            )
        }
    }

    @Test
    fun rejectsExpiredAndNotYetValidSuccessorLeaf() {
        assertFailsWith<CertificateExpiredException> {
            verifySuccessor(
                VerifiedCloudLeafPinPolicy.PRODUCTION_HOST,
                SyntheticCertificate("expired".toByteArray(), Date(0), Date(1)),
            )
        }
        assertFailsWith<CertificateNotYetValidException> {
            verifySuccessor(
                VerifiedCloudLeafPinPolicy.PRODUCTION_HOST,
                SyntheticCertificate(
                    "future".toByteArray(),
                    Date(4_102_444_800_000L),
                    Date(4_105_036_800_000L),
                ),
            )
        }
    }

    @Test
    fun sharedTlsConfigurationUsesTheSamePolicyForHttpFileAndWebSocket() {
        val certificate = currentlyValidCertificate("shared-policy")
        val pin = sha256(certificate.encoded)

        val http = PinnedHttpsTransport.tlsConfiguration(pin, "http.example")
        val file = PinnedHttpsTransport.tlsConfiguration(pin, "file.example")
        val webSocket = PinnedHttpsTransport.tlsConfiguration(pin, "ws.example")

        listOf(http, file, webSocket).forEach { configuration ->
            configuration.trustManager.checkServerTrusted(arrayOf(certificate), "RSA")
        }
    }

    @Test
    fun successorTrustDoesNotChangeConnectionOrOrderScope() {
        val connection = CloudConnection(
            baseUrl = "https://${VerifiedCloudLeafPinPolicy.PRODUCTION_HOST}",
            bearerToken = "stored-token",
            certificateSha256 = VerifiedCloudLeafPinPolicy.ENROLLED_OLD_PIN,
        )
        val before = orderConnectionScope(connection, "stored-device")

        verifySuccessor(VerifiedCloudLeafPinPolicy.PRODUCTION_HOST, currentlyValidCertificate())

        assertEquals(VerifiedCloudLeafPinPolicy.ENROLLED_OLD_PIN, connection.certificateSha256)
        assertEquals("stored-token", connection.bearerToken)
        assertEquals(before, orderConnectionScope(connection, "stored-device"))
    }

    private fun verifySuccessor(host: String?, certificate: X509Certificate) {
        VerifiedCloudLeafPinPolicy.verify(
            configuredPin = VerifiedCloudLeafPinPolicy.ENROLLED_OLD_PIN,
            actualHost = host,
            chain = arrayOf(certificate),
            fingerprintOf = { VerifiedCloudLeafPinPolicy.VERIFIED_SUCCESSOR_PIN },
        )
    }

    private fun currentlyValidCertificate(encoded: String = "successor-leaf") = SyntheticCertificate(
        encodedBytes = encoded.toByteArray(),
        notBefore = Date(946_684_800_000L),
        notAfter = Date(4_102_444_800_000L),
    )

    private fun sha256(value: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(value)
        .joinToString("") { "%02x".format(it) }
}

private class SyntheticCertificate(
    private val encodedBytes: ByteArray,
    private val notBefore: Date,
    private val notAfter: Date,
) : X509Certificate() {
    override fun checkValidity() = checkValidity(Date())

    override fun checkValidity(date: Date) {
        if (date.before(notBefore)) throw CertificateNotYetValidException()
        if (date.after(notAfter)) throw CertificateExpiredException()
    }

    override fun getEncoded(): ByteArray = encodedBytes.copyOf()
    override fun getNotBefore(): Date = Date(notBefore.time)
    override fun getNotAfter(): Date = Date(notAfter.time)
    override fun getVersion(): Int = 3
    override fun getSerialNumber(): BigInteger = BigInteger.ONE
    override fun getIssuerDN(): Principal = X500Principal("CN=Synthetic Issuer")
    override fun getSubjectDN(): Principal = X500Principal("CN=Synthetic Leaf")
    override fun getTBSCertificate(): ByteArray = encoded
    override fun getSignature(): ByteArray = ByteArray(0)
    override fun getSigAlgName(): String = "NONE"
    override fun getSigAlgOID(): String = "0.0"
    override fun getSigAlgParams(): ByteArray? = null
    override fun getIssuerUniqueID(): BooleanArray? = null
    override fun getSubjectUniqueID(): BooleanArray? = null
    override fun getKeyUsage(): BooleanArray? = null
    override fun getBasicConstraints(): Int = -1
    override fun verify(key: PublicKey) = Unit
    override fun verify(key: PublicKey, sigProvider: String) = Unit
    override fun getPublicKey(): PublicKey? = null
    override fun hasUnsupportedCriticalExtension(): Boolean = false
    override fun getCriticalExtensionOIDs(): Set<String>? = null
    override fun getNonCriticalExtensionOIDs(): Set<String>? = null
    override fun getExtensionValue(oid: String): ByteArray? = null
    override fun toString(): String = "SyntheticCertificate"
}
