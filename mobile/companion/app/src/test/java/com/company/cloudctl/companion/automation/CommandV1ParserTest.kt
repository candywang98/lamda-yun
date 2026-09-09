package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class CommandV1ParserTest {

    @Test
    fun parsesValidXianyuPublishCommand() {
        val command = CommandV1Parser.parse(validJson())
        assertEquals("cloudctl.command/v1", command.protocolVersion)
        assertEquals("xianyu.publish_listing.v1", command.commandType)
        assertEquals("account-jia", command.accountId)
        assertEquals(3, command.bindingVersion)
        assertEquals("com.taobao.idlefish", command.targetPackage)
        assertEquals(7, command.controlEpoch)
    }

    @Test
    fun rejectsUnknownProtocolAndUnauthorizedFields() {
        assertFailsWith<IllegalArgumentException> {
            CommandV1Parser.parse(validJson().replace("cloudctl.command/v1", "cloudctl.command/v0"))
        }
        assertFailsWith<IllegalArgumentException> {
            CommandV1Parser.parse(validJson().replace("\"parameters\":", "\"dexPayload\":\"no\",\"parameters\":"))
        }
        assertFailsWith<IllegalArgumentException> {
            CommandV1Parser.parse(validJson().replace("account-jia", ""))
        }
    }

    private fun validJson() = """
      {
        "protocolVersion":"cloudctl.command/v1",
        "taskId":"task-001",
        "attemptId":"attempt-001",
        "commandType":"xianyu.publish_listing.v1",
        "deviceId":"device-001",
        "accountId":"account-jia",
        "bindingVersion":3,
        "snapshot":{"id":"snap-001","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        "recipe":{"versionId":"recipe-xianyu-publish-1","sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","engineMinVersion":1},
        "targetPackage":"com.taobao.idlefish",
        "requiredCapabilities":["accessibility","network"],
        "lease":{"controlEpoch":7,"expiresAt":"2026-09-06T12:00:00Z"},
        "mediaDeliveryId":"delivery-001",
        "legacyStepsEnabled":false,
        "parameters":{"listingBody":"自用闲置，功能正常，支持当面交易","price":"128","mediaAssetIds":["asset-1","asset-2"]}
      }
    """.trimIndent()
}
