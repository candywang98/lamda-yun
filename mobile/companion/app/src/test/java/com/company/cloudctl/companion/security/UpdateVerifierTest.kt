package com.company.cloudctl.companion.security

import java.util.Base64
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class UpdateVerifierTest {
    @Test
    fun verifiesRfc8032Vector() {
        val signature = hex(
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155" +
                "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
        )
        assertTrue(UpdateVerifier.verifyPayload(byteArrayOf(), Base64.getEncoder().encodeToString(signature)))
        assertFalse(UpdateVerifier.verifyPayload(byteArrayOf(1), Base64.getEncoder().encodeToString(signature)))
    }

    private fun hex(value: String): ByteArray = value.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
}

