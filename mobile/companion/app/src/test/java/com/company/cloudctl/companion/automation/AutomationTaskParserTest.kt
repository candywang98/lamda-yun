package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class AutomationTaskParserTest {

    @Test
    fun parsesAllCompanionStructuredActions() {
        val task = AutomationTaskParser.parse(taskJson())
        assertEquals(7, task.steps.size)
        assertEquals("com.company.cloudctl.companion", task.targetPackage)
    }

    @Test
    fun rejectsUnknownActionCoordinatesAndExtraFields() {
        assertFailsWith<IllegalStateException> {
            AutomationTaskParser.parse(taskJson().replace("run.log", "shell.exec"))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(taskJson().replace("com.company.cloudctl.companion", "com.example.target"))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(taskJson().replace("\"timeoutMs\":1000", "\"timeoutMs\":1000,\"x\":1"))
        }
    }

    @Test
    fun acceptsSharedLocatorSyntaxAndRejectsInvalidLocator() {
        val parsed = AutomationTaskParser.parse(taskJson().replace("login_button", "Login.Button-1"))
        assertEquals("Login.Button-1", (parsed.steps.first() as AutomationStep.Find).locatorRef)
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(taskJson().replace("login_button", "Login/Button"))
        }
    }

    @Test
    fun parsesIdlefishTextPublishContract() {
        val task = AutomationTaskParser.parse(xianyuPublishJson())
        assertEquals(TargetLocatorRegistry.XIANYU_PACKAGE, task.targetPackage)
        assertEquals(11, task.steps.size)
        assertEquals("xianyu_description", (task.steps[5] as AutomationStep.Input).locatorRef)
        assertEquals("自用闲置，功能正常，支持当面交易", (task.steps[5] as AutomationStep.Input).value)
        assertEquals("xianyu_price", (task.steps[8] as AutomationStep.Input).locatorRef)
        assertEquals("128", (task.steps[8] as AutomationStep.Input).value)
        assertFailsWith<IllegalStateException> {
            AutomationTaskParser.parse(xianyuPublishJson().replace("run.log", "media.deliver"))
        }
        val withNullPostcondition = AutomationTaskParser.parse(
            xianyuPublishJson().replace(
                "\"locatorRef\":\"xianyu_composer_done\"",
                "\"locatorRef\":\"xianyu_composer_done\",\"postconditionLocatorRef\":null",
            ),
        )
        assertEquals(
            null,
            (withNullPostcondition.steps[6] as AutomationStep.Tap).postconditionLocatorRef,
        )
    }

    @Test
    fun acceptsOptionalCommandTypeOnClaimedTask() {
        val parsed = AutomationTaskParser.parse(
            xianyuPublishJson().replace(
                "\"maxRunSeconds\":90",
                "\"maxRunSeconds\":90,\"commandType\":\"xianyu.publish_listing.v1\"",
            ),
        )
        assertEquals(TargetLocatorRegistry.XIANYU_PACKAGE, parsed.targetPackage)
    }

    @Test
    fun acceptsAndValidatesOptionalMediaDeliveryMetadata() {
        val task = AutomationTaskParser.parse(
            xianyuPublishJson().replace(
                "\"steps\":[",
                "\"mediaDelivery\":{\"deliveryId\":\"delivery-1\",\"assetIds\":[\"asset-1\"]},\"steps\":[",
            ),
        )
        assertEquals(TargetLocatorRegistry.XIANYU_PACKAGE, task.targetPackage)
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(
                xianyuPublishJson().replace(
                    "\"steps\":[",
                    "\"mediaDelivery\":{\"deliveryId\":\"delivery-1\",\"assetIds\":[\"asset-1\",\"asset-1\"]},\"steps\":[",
                ),
            )
        }
    }

    private fun xianyuPublishJson() = """{
      "protocolVersion":"cloudctl.mobile/v1","taskId":"task-xianyu-publish-text-001","deviceId":"device-1",
      "targetPackage":"com.taobao.idlefish","issuedAt":"2026-09-04T08:00:00Z",
      "expiresAt":"2026-09-04T08:10:00Z","maxRunSeconds":90,"steps":[
      {"stepId":"find-home-sell","action":"ui.find","timeoutMs":8000,"locatorRef":"xianyu_home_sell"},
      {"stepId":"open-sell","action":"ui.tap","timeoutMs":8000,"locatorRef":"xianyu_home_sell","postconditionLocatorRef":"xianyu_publish_entry"},
      {"stepId":"open-publish","action":"ui.tap","timeoutMs":8000,"locatorRef":"xianyu_publish_entry","postconditionLocatorRef":"xianyu_publish_page"},
      {"stepId":"wait-publish-page","action":"ui.wait","timeoutMs":8000,"locatorRef":"xianyu_publish_page","condition":"EXISTS","pollMs":200},
      {"stepId":"wait-description","action":"ui.wait","timeoutMs":8000,"locatorRef":"xianyu_description","condition":"EXISTS","pollMs":200},
      {"stepId":"fill-description","action":"ui.input","timeoutMs":20000,"locatorRef":"xianyu_description","value":"自用闲置，功能正常，支持当面交易","replace":true},
      {"stepId":"confirm-description","action":"ui.tap","timeoutMs":5000,"locatorRef":"xianyu_composer_done"},
      {"stepId":"wait-price","action":"ui.wait","timeoutMs":12000,"locatorRef":"xianyu_price","condition":"EXISTS","pollMs":200},
      {"stepId":"fill-price","action":"ui.input","timeoutMs":20000,"locatorRef":"xianyu_price","value":"128","replace":true},
      {"stepId":"capture-form","action":"ui.screenshot","timeoutMs":15000,"label":"xianyu_publish_form"},
      {"stepId":"mark-ready","action":"run.log","timeoutMs":1000,"level":"INFO","messageCode":"XIANYU_PUBLISH_FORM_READY"}]}
    """.trimIndent()

    private fun taskJson() = """{
      "protocolVersion":"cloudctl.mobile/v1","taskId":"task-1","deviceId":"device-1",
      "targetPackage":"com.company.cloudctl.companion","issuedAt":"2026-09-01T06:00:00Z",
      "expiresAt":"2026-09-01T06:10:00Z","maxRunSeconds":600,"steps":[
      {"stepId":"1","action":"ui.find","timeoutMs":1000,"locatorRef":"login_button"},
      {"stepId":"2","action":"ui.tap","timeoutMs":1000,"locatorRef":"login_button","postconditionLocatorRef":"username"},
      {"stepId":"3","action":"ui.input","timeoutMs":1000,"locatorRef":"username","value":"operator","replace":true,"sensitive":false},
      {"stepId":"4","action":"ui.wait","timeoutMs":1000,"locatorRef":"username","condition":"ENABLED","pollMs":100},
      {"stepId":"5","action":"ui.screenshot","timeoutMs":1000,"label":"after_login"},
      {"stepId":"6","action":"ui.assert","timeoutMs":1000,"locatorRef":"username","predicate":"EXISTS"},
      {"stepId":"7","action":"run.log","timeoutMs":1000,"level":"INFO","messageCode":"LOGIN_READY"}]}
    """.trimIndent()
}
