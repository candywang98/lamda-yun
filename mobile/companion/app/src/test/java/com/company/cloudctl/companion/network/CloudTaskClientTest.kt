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
