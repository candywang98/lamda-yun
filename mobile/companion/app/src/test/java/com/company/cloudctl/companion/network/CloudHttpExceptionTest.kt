package com.company.cloudctl.companion.network

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class CloudHttpExceptionTest {
    @Test
    fun classifiesAuthenticationAndTransientFailures() {
        assertTrue(CloudHttpException(401, "unauthorized").authenticationRejected)
        assertTrue(CloudHttpException(403, "forbidden").authenticationRejected)
        assertFalse(CloudHttpException(409, "lease conflict").retryable)
        assertTrue(CloudHttpException(429, "slow down").retryable)
        assertTrue(CloudHttpException(503, "unavailable").retryable)
        assertFalse(CloudHttpException(422, "invalid").retryable)
    }
}
