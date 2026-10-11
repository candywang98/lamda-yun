package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.BuildConfig
import com.company.cloudctl.companion.automation.AutomationTaskParser
import com.company.cloudctl.companion.automation.AutomationStep
import com.company.cloudctl.companion.im.IM_CHAT_COLLECTION_PROTOCOL
import org.json.JSONObject
import kotlin.test.*

/** Exact synthetic release HTTP response goes through the real claim adapter and strict parser. */
class ImChatCollectionReleaseCompatibilityTest {
    private fun fixture(name: String): JSONObject = JSONObject(checkNotNull(javaClass.classLoader)
        .getResourceAsStream("im-chat-collection-release/$name")!!.bufferedReader().use { it.readText() })

    @Test fun releaseClaimParsesWithoutWeakeningStrictStepContract() {
        val response = fixture("claim-example.json")
        val payload = buildClaimedTaskPayload(response)
        assertEquals(60, payload.getInt("maxRunSeconds"))
        assertEquals(2L, payload.getLong("controlEpoch"))
        assertFalse(payload.has("totalTimeoutMs"))
        val step = payload.getJSONArray("steps").getJSONObject(0)
        assertEquals(setOf("stepId", "action", "timeoutMs", "target"), step.keys().asSequence().toSet())
        val parsed = AutomationTaskParser.parse(payload.toString())
        val collection = assertIs<AutomationStep.CollectImChat>(parsed.steps.single())
        val completion = fixture("complete-example.json")
        assertEquals(IM_CHAT_COLLECTION_PROTOCOL, completion.getString("protocolVersion"))
        assertEquals(response.getString("leaseId"), completion.getString("leaseId"))
        assertEquals(parsed.controlEpoch, completion.getLong("controlEpoch"))
        assertTrue(collection.target.toJson().similar(completion.getJSONObject("target")))
        assertEquals("UNVERIFIED", completion.getJSONObject("snapshot").getString("accountIdentity"))
        step.put("controlEpoch", 2)
        assertFails { AutomationTaskParser.parse(payload.toString()) }
    }

    @Test fun businessAcceptanceVersionIsTen() {
        if (BuildConfig.BUILD_TYPE == "businessAcceptance") {
            assertEquals(10, BuildConfig.VERSION_CODE)
            assertEquals("0.1.0-business-acceptance.10", BuildConfig.VERSION_NAME)
            assertEquals("com.company.cloudctl.companion", BuildConfig.APPLICATION_ID)
        }
    }
}
