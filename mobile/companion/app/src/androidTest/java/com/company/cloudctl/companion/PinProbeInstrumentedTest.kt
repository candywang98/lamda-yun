package com.company.cloudctl.companion

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.company.cloudctl.companion.data.CompanionRepository
import com.company.cloudctl.companion.network.EnrollmentParser
import com.company.cloudctl.companion.network.PinnedHttpsCompanionCloudClient
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PinProbeInstrumentedTest {
    @Test
    fun repositoryEnrollExactlyLikeUi() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val repository = CompanionRepository(context, PinnedHttpsCompanionCloudClient())
        val payload = EnrollmentParser.parse(
            "https://43.133.243.154.sslip.io",
            "000000-000000",
            "fe178c22ba4327c0a71cdd0c7561654fb76ff67c02aa5461f076bf2fc60622d1",
        )
        val result = runCatching { kotlinx.coroutines.runBlocking { repository.enroll(payload) } }
        result.onSuccess {
            println("REPO_ENROLL_OK state=${it}")
        }.onFailure { e ->
            println("REPO_ENROLL_FAIL ${e.javaClass.name}: ${e.message}")
            e.printStackTrace()
            throw AssertionError("repository enroll failed", e)
        }
    }
}
