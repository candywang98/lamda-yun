package com.company.cloudctl.companion.automation

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.company.cloudctl.companion.model.EnrollmentPayload
import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.CloudTaskClient
import com.company.cloudctl.companion.network.PinnedHttpsCompanionCloudClient
import com.company.cloudctl.companion.security.SecretStore
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Explicit Root-only recovery through the normal enrollment API; no direct server DB edits. */
@RunWith(AndroidJUnit4::class)
class BindingRecoveryInstrumentationTest {
    @Test fun renewCurrentDeviceInstance() = runBlocking {
        assumeTrue(InstrumentationRegistry.getArguments().getString("recoverBinding") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val input = File(context.cacheDir, "p09-binding-recovery.json")
        require(input.isFile)
        try {
            val request = JSONObject(input.readText())
            val preferences = context.getSharedPreferences("cloudctl_binding", Context.MODE_PRIVATE)
            val before = JSONObject(requireNotNull(preferences.getString("binding", null)))
            val instance = requireNotNull(preferences.getString("app_instance_id", null))
            assertEquals(before.getString("deviceId"), request.getString("deviceId"))
            val result = PinnedHttpsCompanionCloudClient().enroll(
                EnrollmentPayload(before.getString("cloudUrl"), request.getString("code"), before.getString("certificateSha256")),
                instance,
            )
            assertEquals(before.getString("deviceId"), result.binding.deviceId)
            SecretStore(context).put("binding_token", result.bindingToken)
            assertTrue(context.getSharedPreferences("cloudctl_secrets", Context.MODE_PRIVATE).edit().commit())
            before.put("bindingId", result.binding.bindingId)
            assertTrue(preferences.edit().putString("binding", before.toString()).commit())
            CloudTaskClient(CloudConnection(result.binding.cloudUrl, result.bindingToken, result.binding.certificateSha256)).listActiveRecipes()
            println("P09_REENROLLED device=${result.binding.deviceId} binding=${result.binding.bindingId}")
        } finally {
            input.delete()
        }
    }
}
