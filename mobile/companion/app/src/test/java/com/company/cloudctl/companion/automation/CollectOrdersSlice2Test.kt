package com.company.cloudctl.companion.automation

import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Order-sync slice 2 (contract order-sync-slice2/20260915.1，唯一事实源)：
 * steps v2 多屏采集执行器 —— ① v2 步骤序列解析（screens 2/3、非法形状安全拒绝）；
 * ② v1 回归不变（形状与单屏行为）；③ 分屏即报（每屏成功立即上报、后屏失败不影响
 * 前屏已报）；④ 跨屏 order_key 去重（重叠行吸收）；⑤ swipeUp 只作用于订单列表
 * 容器 bounds 内、禁止全屏滑；⑥ screen 序号只进日志，不进 steps 哈希敏感字段。
 * 行样本仿 slice1 ReadOrdersExecutorTest（真机 dump recon-20260915-2 语料）。
 */
class CollectOrdersSlice2Test {
    private val fixedNow = Instant.parse("2026-09-15T08:00:00Z")
    private val zwsp = "​"
    private val xianyu = TargetLocatorRegistry.XIANYU_PACKAGE

    // 08 dump SOLD 第 1 行变体：RUSHANG / 交易成功 / ¥10.80。
    private val rushangRow = listOf(
        "订单信息, 退货运费险\n好评\n中评\n差评",
        "RUSHANG, RUSHANG",
        "交易成功, 交易成功",
        "《黄同学漫画二战史2》个人闲置, 《黄同学漫画二战史2》个人闲置",
        "¥$zwsp",
        "1${zwsp}0$zwsp",
        ".$zwsp" + "8$zwsp" + "0$zwsp",
        "更多，按钮, 更多",
        "您${zwsp}对${zwsp}交${zwsp}易${zwsp}的${zwsp}满${zwsp}意${zwsp}度${zwsp}如${zwsp}何${zwsp}？$zwsp",
    )

    /** 与 [rushangRow] 同构的可参数化行：昵称/标题/价格三段唯一决定复合键。 */
    private fun row(nickname: String, title: String, price: String): List<String> = listOf(
        "订单信息, 退货运费险",
        "$nickname, $nickname",
        "交易成功, 交易成功",
        "$title, $title",
        "¥$zwsp",
        price,
    )

    private fun keyOf(nickname: String, title: String, cents: Long) =
        "SOLD|$nickname|$title|$cents"

    // ------------------------------------------------------------------
    // ① v2 步骤序列解析（形状镜像后端 build_collect_orders_steps_v2 冻结输出）
    // ------------------------------------------------------------------

    @Test
    fun parsesMultiScreenV2ShapesForTwoAndThreeScreens() {
        val two = AutomationTaskParser.parse(v2Json(screens = 2))
        assertEquals(xianyu, two.targetPackage)
        assertEquals(
            listOf("Tap", "Tap", "ReadOrders", "SwipeUp", "ReadOrders", "Screenshot", "Log"),
            two.steps.map { it::class.simpleName },
        )
        val firstSwipe = two.steps[3] as AutomationStep.SwipeUp
        assertEquals("swipe-up-2", firstSwipe.stepId)
        // swipeUp 与 readOrders 共用订单列表容器定位器（契约 §1：容器内上滑）。
        assertEquals("xianyu_orders_container", firstSwipe.locatorRef)
        val read1 = two.steps[2] as AutomationStep.ReadOrders
        val read2 = two.steps[4] as AutomationStep.ReadOrders
        assertEquals(read1.direction, read2.direction)
        assertEquals(read1.maxRows, read2.maxRows)
        assertEquals("xianyu_orders_container", read2.locatorRef)
        assertEquals("read-orders-2", read2.stepId)

        val three = AutomationTaskParser.parse(v2Json(screens = 3))
        assertEquals(9, three.steps.size)
        val secondSwipe = three.steps[5] as AutomationStep.SwipeUp
        assertEquals("swipe-up-3", secondSwipe.stepId)
        assertEquals("xianyu_orders_container", secondSwipe.locatorRef)
        assertEquals("read-orders-3", (three.steps[6] as AutomationStep.ReadOrders).stepId)
    }

    @Test
    fun rejectsIllegalV2StepShapesBeforeAnyExecution() {
        // readOrders 步携带 screen 序号字段 → 键集校验拒绝（哈希红线）。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(
                v2Json(screens = 2).replace(
                    "\"maxRows\":5,\"locatorRef\":\"xianyu_orders_container\"",
                    "\"maxRows\":5,\"locatorRef\":\"xianyu_orders_container\",\"screen\":2",
                ),
            )
        }
        // swipeUp 缺 locatorRef → 拒绝。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(
                v2Json(screens = 2).replace(
                    "\"action\":\"ui.swipeUp\",\"timeoutMs\":8000,\"locatorRef\":\"xianyu_orders_container\"",
                    "\"action\":\"ui.swipeUp\",\"timeoutMs\":8000",
                ),
            )
        }
        // swipeUp locatorRef 非法字符 → 拒绝。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(
                v2Json(screens = 2).replace(
                    "\"action\":\"ui.swipeUp\",\"timeoutMs\":8000,\"locatorRef\":\"xianyu_orders_container\"",
                    "\"action\":\"ui.swipeUp\",\"timeoutMs\":8000,\"locatorRef\":\"xianyu/orders\"",
                ),
            )
        }
        // 重复 stepId → 拒绝（v2 每屏 read-orders-N 必须唯一）。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(
                v2Json(screens = 2).replace("\"stepId\":\"read-orders-2\"", "\"stepId\":\"read-orders\""),
            )
        }
        // maxRows 越界 → 拒绝。
        assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(v2Json(screens = 2).replace("\"maxRows\":5", "\"maxRows\":11"))
        }
    }

    // ------------------------------------------------------------------
    // ② v1 回归不变
    // ------------------------------------------------------------------

    @Test
    fun v1ShapeAndSingleScreenBehaviorAreUnchanged() = runBlocking {
        // v1 五步冻结形状照旧解析（screens=1 永远发 v1，契约 §1）。
        val v1 = AutomationTaskParser.parse(v1Json())
        assertEquals(
            listOf("Tap", "Tap", "ReadOrders", "Screenshot", "Log"),
            v1.steps.map { it::class.simpleName },
        )
        assertEquals("read-orders", (v1.steps[2] as AutomationStep.ReadOrders).stepId)

        // 单屏执行行为不变：同屏重复键不去重（slice1 语义：都上报、服务端幂等吸收），
        // 日志保持 slice1 字节级形状（无 SCREEN / OVERLAP 行）。
        val ui = Slice2FakeUi().apply { screens += listOf(listOf(rushangRow, rushangRow)) }
        val reporter = RecordingReporter()
        executor(ui, reporter).execute(task(AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 5, "xianyu_orders_container"))) { _, _ -> }

        assertEquals(1, reporter.calls.size)
        assertEquals(2, reporter.calls.single().collected.size)
        assertEquals(1, reporter.calls.single().screen)
        assertTrue(ui.logs.any { it == LogLevel.INFO to "ORDERS_READ_2" })
        assertTrue(ui.logs.none { it.second.startsWith("ORDERS_READ_SCREEN_") })
        assertTrue(ui.logs.none { it.second.startsWith("ORDERS_OVERLAP_") })
    }

    // ------------------------------------------------------------------
    // ③ 分屏即报（断点续传语义）
    // ------------------------------------------------------------------

    @Test
    fun reportsEveryScreenImmediatelyAfterItsStepSucceeds() = runBlocking {
        val a = row("买家A", "商品A", "2${zwsp}5")
        val b = row("买家B", "商品B", "3${zwsp}0")
        val c = row("买家C", "商品C", "4${zwsp}0")
        val ui = Slice2FakeUi().apply { screens += listOf(listOf(a), listOf(b), listOf(c)) }
        val reporter = RecordingReporter()
        val events = mutableListOf<String>()
        reporter.onReport = { events += "report:screen-${reporter.calls.last().screen}" }

        executor(ui, reporter).execute(
            task(
                AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-2", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-3", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-3", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
            ),
        ) { step, state -> events += "journal:${step.stepId}:$state" }

        // 每屏读完成即报：上报紧跟该屏 SUCCEEDED、先于下一屏任何步骤。
        assertEquals(
            listOf(
                "journal:read-orders:STARTED", "journal:read-orders:SUCCEEDED", "report:screen-1",
                "journal:swipe-up-2:STARTED", "journal:swipe-up-2:SUCCEEDED",
                "journal:read-orders-2:STARTED", "journal:read-orders-2:SUCCEEDED", "report:screen-2",
                "journal:swipe-up-3:STARTED", "journal:swipe-up-3:SUCCEEDED",
                "journal:read-orders-3:STARTED", "journal:read-orders-3:SUCCEEDED", "report:screen-3",
            ),
            events,
        )
        assertEquals(listOf(1, 2, 3), reporter.calls.map { it.screen })
        assertEquals(listOf(keyOf("买家A", "商品A", 2500), keyOf("买家B", "商品B", 3000), keyOf("买家C", "商品C", 4000)), reporter.calls.map { it.collected.single().orderKey })
    }

    @Test
    fun keepsEarlierScreenReportsWhenALaterScreenFails() = runBlocking {
        val a = row("买家A", "商品A", "2${zwsp}5")
        val b = row("买家B", "商品B", "3${zwsp}0")

        // 后屏读取失败：第 1 屏已上报落库。
        val readFails = Slice2FakeUi().apply {
            screens += listOf(listOf(a))
            failReadOnScreen = 2
        }
        val readReporter = RecordingReporter()
        val readFailure = assertFailsWith<ExecutorFailure> {
            executor(readFails, readReporter).execute(
                task(
                    AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                    AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                    AutomationStep.ReadOrders("read-orders-2", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                ),
            ) { _, _ -> }
        }
        assertEquals("LOCATOR_NOT_FOUND", readFailure.code)
        assertEquals(1, readReporter.calls.size)
        assertEquals(1, readReporter.calls.single().screen)
        assertEquals(keyOf("买家A", "商品A", 2500), readReporter.calls.single().collected.single().orderKey)

        // 后屏滑动失败：第 1 屏同样已上报（通往第 2 屏的那次滑动即第 1 次滑动）。
        val swipeFails = Slice2FakeUi().apply {
            screens += listOf(listOf(b))
            failSwipeOnScreen = 1
        }
        val swipeReporter = RecordingReporter()
        val swipeFailure = assertFailsWith<ExecutorFailure> {
            executor(swipeFails, swipeReporter).execute(
                task(
                    AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                    AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                    AutomationStep.ReadOrders("read-orders-2", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                ),
            ) { _, _ -> }
        }
        assertEquals("LOCATOR_NOT_FOUND", swipeFailure.code)
        assertEquals(1, swipeReporter.calls.size)
        assertEquals(keyOf("买家B", "商品B", 3000), swipeReporter.calls.single().collected.single().orderKey)
    }

    // ------------------------------------------------------------------
    // ④ 跨屏 order_key 去重（滚动重叠吸收）
    // ------------------------------------------------------------------

    @Test
    fun absorbsCrossScreenOverlapRowsByOrderKey() = runBlocking {
        val a = row("买家A", "商品A", "2${zwsp}5")
        val b = row("买家B", "商品B", "3${zwsp}0")
        val c = row("买家C", "商品C", "4${zwsp}0")
        // 惯性重叠：第 2 屏重新暴露 B 与 A，只有 C 是新行。
        val ui = Slice2FakeUi().apply { screens += listOf(listOf(a, b), listOf(b, a, c)) }
        val reporter = RecordingReporter()

        executor(ui, reporter).execute(
            task(
                AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-2", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
            ),
        ) { _, _ -> }

        assertEquals(2, reporter.calls.size)
        assertEquals(2, reporter.calls[0].collected.size)
        // 重叠行不重复上报、不计 duplicates、不进 skipped。
        assertEquals(listOf(keyOf("买家C", "商品C", 4000)), reporter.calls[1].collected.map { it.orderKey })
        assertTrue(reporter.calls[1].skipped.isEmpty())
        assertTrue(ui.logs.any { it == LogLevel.INFO to "ORDERS_OVERLAP_2" })
        assertTrue(ui.logs.any { it == LogLevel.INFO to "ORDERS_READ_1" })
        assertTrue(ui.logs.any { it == LogLevel.INFO to "ORDERS_READ_SCREEN_2" })
        // 同一 run 内合计只上报 3 个唯一键。
        assertEquals(3, reporter.calls.flatMap { it.collected }.map { it.orderKey }.toSet().size)
    }

    // ------------------------------------------------------------------
    // ⑤ swipeUp 限制在容器 bounds 内（禁止全屏滑）
    // ------------------------------------------------------------------

    @Test
    fun swipesOnlyInsideTheResolvedContainerAndNeverFullScreen() = runBlocking {
        val a = row("买家A", "商品A", "2${zwsp}5")
        val b = row("买家B", "商品B", "3${zwsp}0")
        val ui = Slice2FakeUi().apply { screens += listOf(listOf(a), listOf(b)) }

        executor(ui).execute(
            task(
                AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-2", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
            ),
        ) { _, _ -> }

        // 执行器只调容器内滑动原语（带定位器），从不触碰全屏 swipeUp。
        assertEquals(listOf(xianyu to "xianyu_orders_container"), ui.containerSwipes)
        assertEquals(0, ui.fullScreenSwipes)
    }

    @Test
    fun containerSwipeGeometryStaysInsideTheContainerBounds() {
        // recon-20260915-2 量级容器：rows 在 tabs（885）之下、屏底之上。
        val bounds = OrderSwipeGeometry.Bounds(left = 0, top = 487, right = 1080, bottom = 1728)
        val stroke = OrderSwipeGeometry.oneScreenSwipe(bounds)
        kotlin.test.assertNotNull(stroke)
        assertEquals(bounds.left + (bounds.right - bounds.left) / 2f, stroke.startX)
        // 起止点严格落在容器竖直范围内（上下留 20% 余量 → 一屏 60% 行程 + 重叠）。
        assertTrue(stroke.startY < bounds.bottom && stroke.startY > bounds.top)
        assertTrue(stroke.endY < bounds.bottom && stroke.endY > bounds.top)
        assertTrue(stroke.startY > stroke.endY)
        // 任意容器映射出的行程都必须在自身 bounds 内（禁全屏、禁越界）。
        listOf(
            OrderSwipeGeometry.Bounds(0, 900, 1080, 1500),
            OrderSwipeGeometry.Bounds(24, 500, 1056, 2200),
        ).forEach { container ->
            val s = OrderSwipeGeometry.oneScreenSwipe(container)
            kotlin.test.assertNotNull(s)
            assertTrue(s.startY >= container.top && s.startY <= container.bottom)
            assertTrue(s.endY >= container.top && s.endY <= container.bottom)
            assertTrue(s.startX >= container.left && s.startX <= container.right)
        }
        // 退化 bounds → null（fail-closed，绝不放大成全屏滑）。
        assertNull(OrderSwipeGeometry.oneScreenSwipe(OrderSwipeGeometry.Bounds(0, 900, 1080, 1000)))
        assertNull(OrderSwipeGeometry.oneScreenSwipe(OrderSwipeGeometry.Bounds(0, 500, 0, 900)))
    }

    @Test
    fun failsSwipeUpClosedOnUnverifiedLocatorOrForeignTarget() = runBlocking {
        // §7 fail-closed：预注册未勘测容器 → LOCATOR_UNVERIFIED，零滑动零读取。
        val unverified = Slice2FakeUi()
        val failure = assertFailsWith<ExecutorFailure> {
            executor(unverified).execute(
                task(
                    AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_order_detail_container"),
                ),
            ) { _, _ -> }
        }
        assertEquals("LOCATOR_UNVERIFIED", failure.code)
        assertEquals(0, unverified.containerSwipes.size)
        assertEquals(0, unverified.readCalls.size)

        // 非 xianyu 目标 → TARGET_PACKAGE_REJECTED（readOrders 同款守卫）。
        val foreign = Slice2FakeUi().apply { allowedPackage = TargetLocatorRegistry.COMPANION_PACKAGE }
        val rejected = assertFailsWith<ExecutorFailure> {
            executor(foreign).execute(
                task(
                    TargetLocatorRegistry.COMPANION_PACKAGE,
                    AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                ),
            ) { _, _ -> }
        }
        assertEquals("TARGET_PACKAGE_REJECTED", rejected.code)
        assertEquals(0, foreign.containerSwipes.size)
    }

    // ------------------------------------------------------------------
    // ⑥ screen 序号只进日志，不进哈希敏感字段
    // ------------------------------------------------------------------

    @Test
    fun screenOrdinalReachesLogsOnlyAndNeverStepBodiesOrReports() = runBlocking {
        val a = row("买家A", "商品A", "2${zwsp}5")
        val b = row("买家B", "商品B", "3${zwsp}0")
        val ui = Slice2FakeUi().apply { screens += listOf(listOf(a), listOf(b)) }
        val reporter = RecordingReporter()

        executor(ui, reporter).execute(
            task(
                AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-2", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
            ),
        ) { _, _ -> }

        // 序号进日志：每屏一条 ORDERS_READ_SCREEN_N。
        assertTrue(ui.logs.any { it == LogLevel.INFO to "ORDERS_READ_SCREEN_1" })
        assertTrue(ui.logs.any { it == LogLevel.INFO to "ORDERS_READ_SCREEN_2" })
        // 上报载荷与步骤模型无 screen 通道：行快照字段就是 slice1 六件套 + rawLines，
        // readCalls 只带 (package, locatorRef, maxRows)——序号无处可藏。
        reporter.calls.forEach { call ->
            assertEquals("task-1", call.taskId)
            call.collected.forEach { row ->
                assertEquals(6, row.rawLines.size)
            }
        }
        ui.readCalls.forEach { (_, _, maxRows) -> assertEquals(10, maxRows) }
        ui.containerSwipes.forEach { (_, ref) -> assertEquals("xianyu_orders_container", ref) }
        // 步骤体携带 screen 字段的任务在解析期即被拒绝（见 rejectsIllegalV2StepShapes）。
    }

    // ------------------------------------------------------------------
    // helpers
    // ------------------------------------------------------------------

    private fun executor(ui: Slice2FakeUi, reporter: OrderReporter? = null): LocalAutomationExecutor {
        var tick = 0L
        return LocalAutomationExecutor(
            ui = ui,
            now = { fixedNow },
            elapsedMs = { tick += 500; tick },
            sleep = { delay(1) },
            orderReporter = reporter,
        )
    }

    private fun task(vararg steps: AutomationStep) = task(xianyu, *steps)

    private fun task(targetPackage: String, vararg steps: AutomationStep) = AutomationTask(
        taskId = "task-1",
        deviceId = "device-1",
        targetPackage = targetPackage,
        issuedAt = fixedNow.minusSeconds(60),
        expiresAt = fixedNow.plusSeconds(600),
        maxRunSeconds = 60,
        steps = steps.toList(),
    )

    private class Call(
        val taskId: String,
        val direction: OrderDirection,
        val collected: List<OrderRowSnapshot>,
        val skipped: List<SkippedOrderRow>,
        val screen: Int,
    )

    private class RecordingReporter : OrderReporter {
        val calls = mutableListOf<Call>()
        var onReport: (() -> Unit)? = null
        override suspend fun reportOrders(
            taskId: String,
            direction: OrderDirection,
            collected: List<OrderRowSnapshot>,
            skipped: List<SkippedOrderRow>,
            screen: Int,
        ) {
            calls += Call(taskId, direction, collected, skipped, screen)
            onReport?.invoke()
        }
    }

    /** 按屏脚本化的假 UI：screens 队列按 readOrders 调用顺序出队。 */
    private class Slice2FakeUi : LocalAutomationUi {
        val screens = ArrayDeque<List<List<String>>>()
        var failReadOnScreen: Int? = null
        var failSwipeOnScreen: Int? = null
        var allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
        val readCalls = mutableListOf<Triple<String, String, Int>>()
        val containerSwipes = mutableListOf<Pair<String, String>>()
        var fullScreenSwipes = 0
            private set
        val logs = mutableListOf<Pair<LogLevel, String>>()
        private var readCount = 0
        private var swipeCount = 0

        override fun ensureReady(targetPackage: String) {
            check(targetPackage == allowedPackage)
        }

        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? = null

        override fun readOrderRows(targetPackage: String, locatorRef: String, maxRows: Int): List<List<String>> {
            readCount += 1
            readCalls += Triple(targetPackage, locatorRef, maxRows)
            val failFrom = failReadOnScreen
            if (failFrom != null && readCount >= failFrom) {
                throw ExecutorFailure("LOCATOR_NOT_FOUND", "screen $readCount never renders")
            }
            return (screens.removeFirstOrNull() ?: emptyList()).take(maxRows)
        }

        override suspend fun swipeUpWithin(targetPackage: String, locatorRef: String) {
            swipeCount += 1
            val failFrom = failSwipeOnScreen
            if (failFrom != null && swipeCount >= failFrom) {
                throw ExecutorFailure("LOCATOR_NOT_FOUND", "container unresolved before swipe $swipeCount")
            }
            containerSwipes += targetPackage to locatorRef
        }

        override suspend fun swipeUp() {
            fullScreenSwipes += 1
        }

        override suspend fun tap(targetPackage: String, locatorRef: String) = Unit

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit

        override suspend fun screenshot(taskId: String, label: String) =
            ScreenshotEvidence("/private/proof.png", 32, "a".repeat(64))

        override fun log(level: LogLevel, messageCode: String) {
            logs += level to messageCode
        }
    }

    /** 后端 build_collect_orders_steps_v2 的冻结输出形状（screens≥2 才发 v2）。 */
    private fun v2Json(screens: Int) = """
      {"protocolVersion":"cloudctl.mobile/v1","taskId":"task-xianyu-orders-v2-001","deviceId":"device-1",
      "targetPackage":"com.taobao.idlefish","issuedAt":"2026-09-15T08:00:00Z",
      "expiresAt":"2026-09-15T08:10:00Z","maxRunSeconds":90,"commandType":"xianyu.collect_orders.steps.v2","steps":[
      {"stepId":"open-profile","action":"ui.tap","timeoutMs":8000,"locatorRef":"xianyu_profile_tab"},
      {"stepId":"open-order-list","action":"ui.tap","timeoutMs":8000,"locatorRef":"xianyu_order_list_sold"},
      {"stepId":"read-orders","action":"ui.readOrders","timeoutMs":20000,"direction":"SOLD","maxRows":5,"locatorRef":"xianyu_orders_container"},
      {"stepId":"swipe-up-2","action":"ui.swipeUp","timeoutMs":8000,"locatorRef":"xianyu_orders_container"},
      {"stepId":"read-orders-2","action":"ui.readOrders","timeoutMs":20000,"direction":"SOLD","maxRows":5,"locatorRef":"xianyu_orders_container"}${if (screens >= 3) """,
      {"stepId":"swipe-up-3","action":"ui.swipeUp","timeoutMs":8000,"locatorRef":"xianyu_orders_container"},
      {"stepId":"read-orders-3","action":"ui.readOrders","timeoutMs":20000,"direction":"SOLD","maxRows":5,"locatorRef":"xianyu_orders_container"}""" else ""},
      {"stepId":"capture-xianyu_collect_orders","action":"ui.screenshot","timeoutMs":8000,"label":"xianyu_collect_orders"},
      {"stepId":"mark-done","action":"run.log","timeoutMs":1000,"level":"INFO","messageCode":"XIANYU_COLLECT_ORDERS_DONE"}]}
    """.trimIndent()

    /** 后端 build_collect_orders_steps（v1）冻结形状，screens=1 永远保持。 */
    private fun v1Json() = """
      {"protocolVersion":"cloudctl.mobile/v1","taskId":"task-xianyu-orders-001","deviceId":"device-1",
      "targetPackage":"com.taobao.idlefish","issuedAt":"2026-09-15T08:00:00Z",
      "expiresAt":"2026-09-15T08:10:00Z","maxRunSeconds":90,"commandType":"xianyu.collect_orders.steps.v1","steps":[
      {"stepId":"open-profile","action":"ui.tap","timeoutMs":8000,"locatorRef":"xianyu_profile_tab"},
      {"stepId":"open-order-list","action":"ui.tap","timeoutMs":8000,"locatorRef":"xianyu_order_list_sold"},
      {"stepId":"read-orders","action":"ui.readOrders","timeoutMs":20000,"direction":"SOLD","maxRows":5,"locatorRef":"xianyu_orders_container"},
      {"stepId":"capture-xianyu_collect_orders","action":"ui.screenshot","timeoutMs":8000,"label":"xianyu_collect_orders"},
      {"stepId":"mark-done","action":"run.log","timeoutMs":1000,"level":"INFO","messageCode":"XIANYU_COLLECT_ORDERS_DONE"}]}
    """.trimIndent()
}
