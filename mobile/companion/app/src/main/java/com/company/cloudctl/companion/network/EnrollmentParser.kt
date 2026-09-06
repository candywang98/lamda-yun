package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.model.EnrollmentPayload
import java.net.URI

object EnrollmentParser {
    private val codePattern = Regex("^[A-Z0-9-]{6,32}$")
    private val digestPattern = Regex("^[a-fA-F0-9]{64}$")

    fun parse(cloudUrl: String, code: String, certificateSha256: String): EnrollmentPayload {
        val uri = URI(cloudUrl.trim())
        require(uri.scheme == "https" && uri.host != null) { "Cloud URL must use HTTPS" }
        require(uri.userInfo == null && uri.query == null && uri.fragment == null) {
            "Control API URL cannot contain credentials, query or fragment"
        }
        require(uri.path.isNullOrBlank() || uri.path == "/") {
            "Control API URL cannot contain an API path"
        }
        require(uri.port != 65000) { "Companion cannot connect to the LAMDA device port" }
        val normalizedCode = code.trim().uppercase()
        require(
            codePattern.matches(normalizedCode) &&
                normalizedCode.first().isLetterOrDigit() &&
                normalizedCode.last().isLetterOrDigit() &&
                "--" !in normalizedCode
        ) { "Enrollment code is invalid" }
        val digest = certificateSha256.replace(":", "").trim().lowercase()
        require(digestPattern.matches(digest)) { "Certificate fingerprint is invalid" }
        return EnrollmentPayload(
            cloudUrl = uri.toString().trimEnd('/'),
            code = normalizedCode,
            certificateSha256 = digest,
        )
    }
}
