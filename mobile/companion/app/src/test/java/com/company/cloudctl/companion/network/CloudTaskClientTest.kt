package com.company.cloudctl.companion.network

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class CloudTaskClientTest {
    @Test
    fun preservesMediaDeliveryWhenBuildingClaimedAutomationPayload() {
        val payload = buildClaimedTaskPayload(JSONObject(BASE_RESPONSE).put(
            "mediaDelivery",
            JSONObject().put("deliveryId", "delivery-1").put("assetIds", listOf("asset-1")),
        ))

        val delivery = payload.getJSONObject("mediaDelivery")
        assertEquals("delivery-1", delivery.getString("deliveryId"))
        assertEquals("asset-1", delivery.getJSONArray("assetIds").getString(0))
        assertTrue(payload.has("steps"))
    }

    @Test
    fun preservesCommandTypeWhenBuildingClaimedAutomationPayload() {
        val payload = buildClaimedTaskPayload(
            JSONObject(BASE_RESPONSE).put("commandType", "xianyu.publish_listing.v1"),
        )
        assertEquals("xianyu.publish_listing.v1", payload.getString("commandType"))
    }

    @Test
    fun preservesCommandV1WithoutRequiringLegacySteps() {
        val command = JSONObject(
            """
            {
              "protocolVersion":"cloudctl.command/v1",
              "taskId":"task-1",
              "attemptId":"attempt-1",
              "commandType":"device.probe_capabilities.v1",
              "deviceId":"device-1",
              "accountId":"account-1",
              "bindingVersion":1,
              "snapshot":{"id":"snap-1","sha256":"${"a".repeat(64)}"},
              "recipe":{"versionId":"recipe-device-probe-1","sha256":"${"b".repeat(64)}","engineMinVersion":1},
              "targetPackage":"com.company.cloudctl.companion",
              "requiredCapabilities":["accessibility","network"],
              "lease":{"controlEpoch":2,"expiresAt":"2026-09-08T12:00:00Z"},
              "legacyStepsEnabled":false,
              "parameters":{}
            }
            """.trimIndent(),
        )
        val payload = buildClaimedTaskPayload(
            JSONObject()
                .put("protocolVersion", "cloudctl.command/v1")
                .put("taskId", "task-1")
                .put("deviceId", "device-1")
                .put("targetPackage", "com.company.cloudctl.companion")
                .put("command", command)
                .put("issuedAt", "2026-09-05T08:00:00Z")
                .put("expiresAt", "2026-09-05T08:10:00Z")
                .put("maxRunSeconds", 30),
        )
        assertEquals("cloudctl.command/v1", payload.getString("protocolVersion"))
        assertEquals("task-1", payload.getJSONObject("command").getString("taskId"))
        assertEquals("b".repeat(64), payload.getString("recipeHash"))
        assertTrue(!payload.has("steps"))
    }

    @Test
    fun parsesPauseRequestedFromHeartbeatView() {
        val heartbeat = parseTaskHeartbeat(
            JSONObject()
                .put("status", "RUNNING")
                .put("businessState", "PAUSE_REQUESTED")
                .put("controlMode", "AUTO")
                .put("stallReason", "operator taking over")
                .put("currentStep", 4),
        )
        assertEquals("PAUSE_REQUESTED", heartbeat.businessState)
        assertEquals("AUTO", heartbeat.controlMode)
        assertEquals("operator taking over", heartbeat.stallReason)
        assertEquals(4, heartbeat.currentStep)
    }

    private companion object {
        const val BASE_RESPONSE = """{
          "protocolVersion":"cloudctl.mobile/v1",
          "taskId":"task-1",
          "deviceId":"device-1",
          "targetPackage":"com.taobao.idlefish",
          "issuedAt":"2026-09-05T08:00:00Z",
          "expiresAt":"2026-09-05T08:10:00Z",
          "maxRunSeconds":90,
          "steps":[]
        }"""
    }
}
