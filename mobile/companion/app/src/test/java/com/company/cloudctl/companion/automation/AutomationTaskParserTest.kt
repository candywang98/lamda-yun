package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

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

    // order-sync/20260915.1 §5 + W1 冻结五步形状：ui.tap(profile) → ui.tap(方向入口)
    // → ui.readOrders → ui.screenshot → run.log（导航用 ui.tap+定位器，非 tapText）。
    @Test
    fun parsesReadOrdersStepAndRejectsInvalidParameters() {
        val task = AutomationTaskParser.parse(collectOrdersJson())
        assertEquals(TargetLocatorRegistry.XIANYU_PACKAGE, task.targetPackage)
        assertEquals(5, task.steps.size)

        // 导航两步走既有 ui.tap + 定位器名（fail-closed 见 TargetLocatorRegistry §7）。
        assertEquals("xianyu_profile_tab", (task.steps[0] as AutomationStep.Tap).locatorRef)
        assertEquals("xianyu_order_list_sold", (task.steps[1] as AutomationStep.Tap).locatorRef)

        val read = task.steps[2] as AutomationStep.ReadOrders
        assertEquals(OrderDirection.SOLD, read.direction)
        assertEquals(5, read.maxRows)
        assertEquals("xianyu_orders_container", read.locatorRef)
        assertEquals("read-orders", read.stepId)

        val bought = AutomationTaskParser.parse(collectOrdersJson().replace("\"SOLD\"", "\"BOUGHT\"").replace("xianyu_order_list_sold", "xianyu_order_list_bought"))
        assertEquals(OrderDirection.BOUGHT, (bought.steps[2] as AutomationStep.ReadOrders).direction)
        assertEquals("xianyu_order_list_bought", (bought.steps[1] as AutomationStep.Tap).locatorRef)

        // direction 非 SOLD/BOUGHT → 拒绝。
        assertFailsWith<IllegalStateException> {
            AutomationTaskParser.parse(collectOrdersJson().replace("\"SOLD\"", "\"sold\""))
        }
        // maxRows 0 / 11 → 拒绝。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(collectOrdersJson().replace("\"maxRows\":5", "\"maxRows\":0"))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(collectOrdersJson().replace("\"maxRows\":5", "\"maxRows\":11"))
        }
        // 缺 direction、未知字段、非法 locatorRef → 拒绝。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(collectOrdersJson().replace("\"direction\":\"SOLD\",", ""))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(collectOrdersJson().replace("\"maxRows\":5", "\"maxRows\":5,\"x\":1"))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(collectOrdersJson().replace("xianyu_orders_container", "xianyu/orders"))
        }
    }

    private fun collectOrdersJson() = """
      {"protocolVersion":"cloudctl.mobile/v1","taskId":"task-xianyu-orders-001","deviceId":"device-1",
      "targetPackage":"com.taobao.idlefish","issuedAt":"2026-09-15T08:00:00Z",
      "expiresAt":"2026-09-15T08:10:00Z","maxRunSeconds":90,"commandType":"xianyu.collect_orders.steps.v1","steps":[
      {"stepId":"open-profile","action":"ui.tap","timeoutMs":8000,"locatorRef":"xianyu_profile_tab"},
      {"stepId":"open-sold-list","action":"ui.tap","timeoutMs":8000,"locatorRef":"xianyu_order_list_sold"},
      {"stepId":"read-orders","action":"ui.readOrders","timeoutMs":15000,"direction":"SOLD","maxRows":5,"locatorRef":"xianyu_orders_container"},
      {"stepId":"capture-orders","action":"ui.screenshot","timeoutMs":8000,"label":"xianyu_orders_screen"},
      {"stepId":"mark-done","action":"run.log","timeoutMs":1000,"level":"INFO","messageCode":"XIANYU_ORDERS_COLLECTED"}]}
    """.trimIndent()

    // W4 维护动作 v2：ui.tapCardByTitle（标题定位 → 详情页）。参数 titleContains
    // 1..64 必填、tab 仅 onsale/delisted（草稿无标定卡片）。
    @Test
    fun parsesTapCardByTitleStepAndRejectsInvalidParameters() {
        val task = AutomationTaskParser.parse(tapCardByTitleJson())
        val onsale = task.steps[0] as AutomationStep.TapCardByTitle
        assertEquals(XianyuMaintenanceLayout.Tab.ONSALE, onsale.tab)
        assertEquals("黄同学漫画二战史", onsale.titleContains)
        assertEquals("open-card-by-title", onsale.stepId)

        val delisted = AutomationTaskParser.parse(
            tapCardByTitleJson().replace("\"tab\":\"onsale\"", "\"tab\":\"delisted\""),
        )
        assertEquals(XianyuMaintenanceLayout.Tab.DELISTED, (delisted.steps[0] as AutomationStep.TapCardByTitle).tab)

        // 草稿 tab（契约 §1：无已标定卡片）→ 拒绝；未知 tab → 拒绝。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(tapCardByTitleJson().replace("\"tab\":\"onsale\"", "\"tab\":\"draft\""))
        }
        assertFailsWith<IllegalStateException> {
            AutomationTaskParser.parse(tapCardByTitleJson().replace("\"tab\":\"onsale\"", "\"tab\":\"onsold\""))
        }
        // 空标题 / 65 字符 / 缺 tab / 缺 titleContains / 未知字段 → 拒绝。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(tapCardByTitleJson().replace("黄同学漫画二战史", ""))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(tapCardByTitleJson().replace("黄同学漫画二战史", "标".repeat(65)))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(tapCardByTitleJson().replace(",\"tab\":\"onsale\"", ""))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(tapCardByTitleJson().replace("\"titleContains\":\"黄同学漫画二战史\",", ""))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(tapCardByTitleJson().replace("\"tab\":\"onsale\"", "\"tab\":\"onsale\",\"cardIndex\":0"))
        }
    }

    @Test
    fun parsesReviewOrdersContractAndRejectsDrift() {
        val task = AutomationTaskParser.parse(reviewOrdersJson())
        assertEquals(TargetLocatorRegistry.XIANYU_PACKAGE, task.targetPackage)
        val loop = task.steps[3] as AutomationStep.ReviewOrders
        assertEquals("review-all", loop.stepId)
        assertEquals(10, loop.maxOrders)
        assertEquals("宝贝很好，交易愉快！", loop.comment)
        assertTrue(loop.dryRun)
        assertEquals(300_000L, loop.timeoutMs)

        // 键集漂移 / maxOrders 越界 / 空 comment / 缺 dryRun → 拒绝。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(reviewOrdersJson().replace("\"dryRun\":true", "\"dryRun\":true,\"x\":1"))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(reviewOrdersJson().replace("\"maxOrders\":10", "\"maxOrders\":51"))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(reviewOrdersJson().replace("宝贝很好，交易愉快！", ""))
        }
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(reviewOrdersJson().replace(",\"dryRun\":true", ""))
        }
        // 任务级 900s 窗口越界 → 拒绝。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(reviewOrdersJson().replace("\"timeoutMs\":300000", "\"timeoutMs\":900001"))
        }
    }

    private fun reviewOrdersJson() = """
      {"protocolVersion":"cloudctl.mobile/v1","taskId":"task-xianyu-review-001","deviceId":"device-1",
      "targetPackage":"com.taobao.idlefish","issuedAt":"2026-09-21T08:00:00Z",
      "expiresAt":"2026-09-21T08:15:00Z","maxRunSeconds":900,"commandType":"xianyu.review_orders.steps.v1","steps":[
      {"stepId":"open-profile","action":"ui.tap","timeoutMs":30000,"locatorRef":"xianyu_profile_tab"},
      {"stepId":"open-sold","action":"ui.tap","timeoutMs":30000,"locatorRef":"xianyu_order_list_sold"},
      {"stepId":"open-pending","action":"ui.tap","timeoutMs":30000,"locatorRef":"xianyu_orders_tab_pending"},
      {"stepId":"review-all","action":"xianyu.reviewOrders","timeoutMs":300000,"maxOrders":10,"comment":"宝贝很好，交易愉快！","dryRun":true},
      {"stepId":"shot","action":"ui.screenshot","timeoutMs":15000,"label":"xianyu_review"},
      {"stepId":"done","action":"run.log","timeoutMs":1000,"level":"INFO","messageCode":"XIANYU_REVIEW_DONE"}]}
    """.trimIndent()

    private fun tapCardByTitleJson() = """
      {"protocolVersion":"cloudctl.mobile/v1","taskId":"task-xianyu-maint-v2-001","deviceId":"device-1",
      "targetPackage":"com.taobao.idlefish","issuedAt":"2026-09-15T08:00:00Z",
      "expiresAt":"2026-09-15T08:10:00Z","maxRunSeconds":90,"commandType":"xianyu.delist.steps.v2","steps":[
      {"stepId":"open-card-by-title","action":"ui.tapCardByTitle","timeoutMs":10000,"titleContains":"黄同学漫画二战史","tab":"onsale"}]}
    """.trimIndent()
}
