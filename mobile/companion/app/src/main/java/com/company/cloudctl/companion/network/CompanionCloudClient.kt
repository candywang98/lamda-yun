package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.BuildConfig
import com.company.cloudctl.companion.model.DeviceBinding
import com.company.cloudctl.companion.model.EnrollmentPayload
import com.company.cloudctl.companion.model.AccountAuthorizationStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.json.JSONArray

data class EnrollmentResult(val binding: DeviceBinding, val bindingToken: String)

interface CompanionCloudClient {
    suspend fun enroll(payload: EnrollmentPayload, appInstanceId: String): EnrollmentResult
    suspend fun unbind(binding: DeviceBinding, token: String)
    suspend fun accountStatus(binding: DeviceBinding, token: String): List<AccountAuthorizationStatus>
}

class PinnedHttpsCompanionCloudClient : CompanionCloudClient {
    override suspend fun enroll(payload: EnrollmentPayload, appInstanceId: String): EnrollmentResult = withContext(Dispatchers.IO) {
        val response = request(
            payload.cloudUrl,
            "/companion/v2/enroll",
            payload.certificateSha256,
            JSONObject().put("code", payload.code)
                .put("appInstanceId", appInstanceId)
                .put("companionVersion", BuildConfig.VERSION_NAME),
            null,
        )
        EnrollmentResult(
            DeviceBinding(
                bindingId = response.getString("bindingId"),
                deviceId = response.getString("deviceId"),
                tenantName = "CloudCtl",
                siteName = "Direct cloud",
                cloudUrl = payload.cloudUrl,
                certificateSha256 = payload.certificateSha256,
            ),
            response.getString("bindingToken"),
        )
    }

    override suspend fun unbind(binding: DeviceBinding, token: String) {
        withContext(Dispatchers.IO) {
            request(binding.cloudUrl, "/companion/v2/binding", binding.certificateSha256, null, token, "DELETE")
        }
    }

    override suspend fun accountStatus(binding: DeviceBinding, token: String): List<AccountAuthorizationStatus> = withContext(Dispatchers.IO) {
        val values = requestArray(binding.cloudUrl, "/companion/v2/accounts/status", binding.certificateSha256, token)
        List(values.length()) { index ->
            values.getJSONObject(index).let { value ->
                AccountAuthorizationStatus(
                    accountId = value.getString("accountId"),
                    platform = value.getString("platform"),
                    displayLabel = value.getString("displayLabel"),
                    status = value.getString("status"),
                    authorized = value.getBoolean("authorized"),
                    expiresAt = value.optString("expiresAt").takeIf(String::isNotBlank),
                    lastCheckedAt = value.optString("lastCheckedAt").takeIf(String::isNotBlank),
                    boundToDevice = value.getBoolean("boundToDevice"),
                )
            }
        }
    }

    private fun request(
        baseUrl: String,
        path: String,
        pin: String,
        body: JSONObject?,
        token: String?,
        method: String = "POST",
    ): JSONObject {
        val headers = linkedMapOf("Accept" to "application/json")
        token?.let { headers["Authorization"] = "Bearer $it" }
        val payload = body?.toString()?.toByteArray(Charsets.UTF_8)
        if (payload != null) headers["Content-Type"] = "application/json"
        val (status, response) = PinnedHttpsTransport.request(
            baseUrl = baseUrl,
            path = path,
            pin = pin,
            method = method,
            headers = headers,
            body = payload,
            connectTimeoutMs = 10_000,
            readTimeoutMs = 20_000,
        )
        check(status in 200..299) { "Cloud request failed with HTTP $status" }
        return if (response.isBlank()) JSONObject() else JSONObject(response)
    }

    private fun requestArray(baseUrl: String, path: String, pin: String, token: String): JSONArray {
        val response = PinnedHttpsTransport.request(
            baseUrl = baseUrl,
            path = path,
            pin = pin,
            method = "GET",
            headers = mapOf("Accept" to "application/json", "Authorization" to "Bearer $token"),
            body = null,
            connectTimeoutMs = 10_000,
            readTimeoutMs = 20_000,
        )
        if (response.first !in 200..299) throw IllegalStateException("Cloud request failed with HTTP ${response.first}")
        return if (response.second.isBlank()) JSONArray() else JSONArray(response.second)
    }
}
