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
    fun acceptsOptionalAccountBindingAndAttemptIdentity() {
        val parsed = AutomationTaskParser.parse(
            xianyuPublishJson().replace(
                "\"maxRunSeconds\":90",
                "\"maxRunSeconds\":90,\"accountId\":\"01a07a1c-572c-7ed5-83ad-a48ebbfed67a\",\"bindingVersion\":1,\"attemptId\":\"attempt-1\"",
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

    @Test
    fun parsesTapTextStepAndRejectsInvalidValues() {
        val base = xianyuPublishJson().replace(
            "\"maxRunSeconds\":90",
            "\"maxRunSeconds\":90",
        )
        val parsed = AutomationTaskParser.parse(
            base.replace(
                "{\"stepId\":\"find-home-sell\"",
                "{\"stepId\":\"tap-peer\",\"action\":\"ui.tapText\",\"value\":\"买家甲\",\"timeoutMs\":8000},{\"stepId\":\"find-home-sell\"",
            ),
        )
        val tap = parsed.steps.filterIsInstance<AutomationStep.TapText>().single()
        assertEquals("买家甲", tap.value)
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(
                base.replace(
                    "{\"stepId\":\"find-home-sell\"",
                    "{\"stepId\":\"tap-peer\",\"action\":\"ui.tapText\",\"value\":\"\",\"timeoutMs\":8000},{\"stepId\":\"find-home-sell\"",
                ),
            )
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(
                base.replace(
                    "{\"stepId\":\"find-home-sell\"",
                    "{\"stepId\":\"tap-peer\",\"action\":\"ui.tapText\",\"value\":\"${"x".repeat(65)}\",\"timeoutMs\":8000},{\"stepId\":\"find-home-sell\"",
                ),
            )
        }
    }

    @Test
    fun parsesMaintenanceLayoutAndBadgeSteps() {
        val task = AutomationTaskParser.parse(maintenanceJson())
        assertEquals(TargetLocatorRegistry.XIANYU_PACKAGE, task.targetPackage)

        val openMenu = task.steps[0] as AutomationStep.TapLayout
        assertEquals(XianyuMaintenanceLayout.Tab.ONSALE, openMenu.tab)
        assertEquals(XianyuMaintenanceLayout.LayoutAction.MORE, openMenu.layoutAction)
        assertEquals(0, openMenu.cardIndex)
        assertEquals(null, openMenu.value)

        val confirm = task.steps[1] as AutomationStep.TapLayout
        assertEquals(XianyuMaintenanceLayout.Tab.ONSALE, confirm.tab)
        assertEquals(XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELIST, confirm.layoutAction)
        assertEquals("受控下架确认", confirm.value)

        // 角标核验：相对（N-1）与绝对两种形态，二选一。
        val delta = task.steps[2] as AutomationStep.AssertBadge
        assertEquals("xianyu_pub_tab_onsale", delta.locatorRef)
        assertEquals(-1, delta.expectedDelta)
        assertEquals(null, delta.expectedValue)
        val absolute = task.steps[3] as AutomationStep.AssertBadge
        assertEquals("xianyu_pub_tab_delisted", absolute.locatorRef)
        assertEquals(null, absolute.expectedDelta)
        assertEquals(0, absolute.expectedValue)
    }

    @Test
    fun rejectsInvalidMaintenanceLayoutAndBadgeSteps() {
        // 未知 layoutAction / tab → 拒绝。
        assertFailsWith<IllegalStateException> {
            AutomationTaskParser.parse(maintenanceJson().replace("\"confirm_delist\"", "\"confirm_buy\""))
        }
        assertFailsWith<IllegalStateException> {
            AutomationTaskParser.parse(maintenanceJson().replace("\"tab\":\"onsale\"", "\"tab\":\"onsold\""))
        }
        // cardIndex 越界、未知字段 → 拒绝。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(maintenanceJson().replace("\"cardIndex\":0", "\"cardIndex\":10"))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(maintenanceJson().replace("\"cardIndex\":0", "\"cardIndex\":0,\"x\":1"))
        }
        // 角标 locator 只允许三个已发布 tab ref。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(maintenanceJson().replace("xianyu_pub_tab_onsale", "xianyu_home_sell"))
        }
        // expectedDelta 与 expectedValue 必须二选一。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(maintenanceJson().replace("\"expectedDelta\":-1", "\"expectedDelta\":-1,\"expectedValue\":2"))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(maintenanceJson().replace(",\"expectedDelta\":-1", ""))
        }
        // delta 越界 → 拒绝。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(maintenanceJson().replace("\"expectedDelta\":-1", "\"expectedDelta\":-51"))
        }
    }

    private fun maintenanceJson() = """
      {"protocolVersion":"cloudctl.mobile/v1","taskId":"task-xianyu-maintenance-001","deviceId":"device-1",
      "targetPackage":"com.taobao.idlefish","issuedAt":"2026-09-15T08:00:00Z",
      "expiresAt":"2026-09-15T08:10:00Z","maxRunSeconds":90,"commandType":"xianyu.delist.steps.v1","steps":[
      {"stepId":"open-more","action":"ui.tapLayout","timeoutMs":8000,"layoutAction":"more","tab":"onsale","cardIndex":0},
      {"stepId":"confirm-delist","action":"ui.tapLayout","timeoutMs":8000,"layoutAction":"confirm_delist","tab":"onsale","cardIndex":0,"value":"受控下架确认"},
      {"stepId":"verify-onsale","action":"ui.assertBadge","timeoutMs":8000,"locatorRef":"xianyu_pub_tab_onsale","expectedDelta":-1},
      {"stepId":"verify-delisted","action":"ui.assertBadge","timeoutMs":8000,"locatorRef":"xianyu_pub_tab_delisted","expectedValue":0}]}
    """.trimIndent()
}
