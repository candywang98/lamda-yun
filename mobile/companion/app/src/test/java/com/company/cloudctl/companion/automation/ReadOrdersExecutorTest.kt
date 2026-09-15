package com.company.cloudctl.companion.automation

import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * order-sync/20260915.1 §5/§7 + addendum 20260915.2：readOrders 执行语义 ——
 * 行不足/空列表成功、无键行 NO_KEY 不算失败、verified=false 定位器
 * LOCATOR_UNVERIFIED 安全终止零副作用。行样本取自真机 dump recon-20260915-2。
 */
class ReadOrdersExecutorTest {
    private val fixedNow = Instant.parse("2026-09-15T08:00:00Z")

    private val zwsp = "​"

    // 08 dump SOLD 第 1 行：RUSHANG / 交易成功 / 二战史2 / ¥10.80。
    private val keyedRow = listOf(
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

    // 结构行 + 状态行：昵称/标题/价格三段全缺 → NO_KEY。
    private val keylessRow = listOf("订单信息, 退货运费险", "交易成功, 交易成功")

    @Test
    fun failsClosedOnUnverifiedContainerLocatorBeforeAnyRead() = runBlocking {
        val ui = ReadOrdersFakeUi().apply { orderRows = listOf(keyedRow) }
        val reporter = RecordingReporter()
        val journal = mutableListOf<String>()

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui, reporter).execute(
                task(AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 5, "xianyu_orders_container")),
            ) { step, state -> journal += "${step.stepId}:$state" }
        }

        assertEquals("LOCATOR_UNVERIFIED", failure.code)
        // 零副作用：容器未被读取，上报未被触发，日志留痕后安全终止。
        assertTrue(ui.readCalls.isEmpty())
        assertTrue(reporter.calls.isEmpty())
        assertEquals(listOf("read-orders:STARTED"), journal)
        assertTrue(ui.logs.contains(LogLevel.ERROR to "LOCATOR_UNVERIFIED"))
    }

    @Test
    fun rejectsNonXianyuTargets() = runBlocking {
        val ui = ReadOrdersFakeUi().apply { allowedPackage = TargetLocatorRegistry.COMPANION_PACKAGE }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(
                    TargetLocatorRegistry.COMPANION_PACKAGE,
                    AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.BOUGHT, 3, "some_container"),
                ),
            ) { _, _ -> }
        }
        assertEquals("TARGET_PACKAGE_REJECTED", failure.code)
        assertTrue(ui.readCalls.isEmpty())
    }

    @Test
    fun collectsKeyedRowsAndSkipsKeylessRowsWithoutFailing() = runBlocking {
        val ui = ReadOrdersFakeUi().apply { orderRows = listOf(keyedRow, keylessRow) }
        val reporter = RecordingReporter()
        val events = mutableListOf<String>()
        reporter.onReport = { events += "report" }

        executor(ui, reporter).execute(
            task(
                AutomationStep.Log("1", 1_000, LogLevel.INFO, "BEFORE"),
                AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "orders"),
                AutomationStep.Log("3", 1_000, LogLevel.INFO, "AFTER"),
            ),
        ) { step, state -> events += "journal:${step.stepId}:$state" }

        // 读到的行数就是成绩：不足 maxRows 不补、不失败。
        assertEquals(listOf(Triple(TargetLocatorRegistry.XIANYU_PACKAGE, "orders", 10)), ui.readCalls)
        val (taskId, direction, rows) = reporter.calls.single()
        assertEquals("task-1", taskId)
        assertEquals(OrderDirection.SOLD, direction)
        val collected = rows.first
        val skipped = rows.second
        assertEquals(1, collected.size)
        assertEquals("SOLD|RUSHANG|《黄同学漫画二战史2》个人闲置|1080", collected.single().orderKey)
        assertEquals(OrderDirection.SOLD, collected.single().direction)
        assertEquals("《黄同学漫画二战史2》个人闲置", collected.single().itemTitle)
        assertEquals("RUSHANG", collected.single().buyerName)
        assertEquals(1_080L, collected.single().amountCents)
        assertEquals("交易成功", collected.single().statusText)
        assertEquals(keyedRow, collected.single().rawLines)
        assertEquals(listOf(SkippedOrderRow(1, OrderRowParser.REASON_NO_KEY)), skipped)
        // §5：上报发生在 readOrders 步 SUCCEEDED 之后、后续步骤之前。
        assertEquals(
            listOf(
                "journal:1:STARTED", "journal:1:SUCCEEDED",
                "journal:read-orders:STARTED", "journal:read-orders:SUCCEEDED", "report",
                "journal:3:STARTED", "journal:3:SUCCEEDED",
            ),
            events,
        )
        assertTrue(ui.logs.contains(LogLevel.INFO to "ORDERS_READ_1"))
        assertTrue(ui.logs.contains(LogLevel.WARN to "ORDERS_SKIPPED_1"))
    }

    @Test
    fun emptyListSucceedsAndReportsZeroRows() = runBlocking {
        val ui = ReadOrdersFakeUi().apply { orderRows = emptyList() }
        val reporter = RecordingReporter()
        val journal = mutableListOf<String>()

        executor(ui, reporter).execute(
            task(AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.BOUGHT, 4, "orders")),
        ) { step, state -> journal += "${step.stepId}:$state" }

        assertEquals(listOf("read-orders:STARTED", "read-orders:SUCCEEDED"), journal)
        val (_, direction, rows) = reporter.calls.single()
        assertEquals(OrderDirection.BOUGHT, direction)
        assertTrue(rows.first.isEmpty())
        assertTrue(rows.second.isEmpty())
        assertTrue(ui.logs.contains(LogLevel.INFO to "ORDERS_READ_0"))
    }

    @Test
    fun runsWithoutReporterAndNeverUploadsTwice() = runBlocking {
        val ui = ReadOrdersFakeUi().apply { orderRows = listOf(keyedRow, keyedRow) }
        executor(ui, null).execute(
            task(AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 5, "orders")),
        ) { _, _ -> }
        assertTrue(ui.logs.contains(LogLevel.INFO to "ORDERS_READ_2"))
        assertTrue(ui.logs.none { it.second == "LOCATOR_UNVERIFIED" })
    }

    private fun executor(ui: ReadOrdersFakeUi, reporter: OrderReporter? = null) = LocalAutomationExecutor(
        ui = ui,
        now = { fixedNow },
        elapsedMs = { 1_000L },
        sleep = { delay(1) },
        orderReporter = reporter,
    )

    private fun task(vararg steps: AutomationStep) = task(TargetLocatorRegistry.XIANYU_PACKAGE, *steps)

    private fun task(targetPackage: String, vararg steps: AutomationStep) = AutomationTask(
        taskId = "task-1",
        deviceId = "device-1",
        targetPackage = targetPackage,
        issuedAt = fixedNow.minusSeconds(60),
        expiresAt = fixedNow.plusSeconds(600),
        maxRunSeconds = 60,
        steps = steps.toList(),
    )

    private class RecordingReporter : OrderReporter {
        val calls = mutableListOf<Triple<String, OrderDirection, Pair<List<OrderRowSnapshot>, List<SkippedOrderRow>>>>()
        var onReport: (() -> Unit)? = null
        override suspend fun reportOrders(
            taskId: String,
            direction: OrderDirection,
            collected: List<OrderRowSnapshot>,
            skipped: List<SkippedOrderRow>,
        ) {
            calls += Triple(taskId, direction, collected to skipped)
            onReport?.invoke()
        }
    }

    private class ReadOrdersFakeUi : LocalAutomationUi {
        var orderRows: List<List<String>> = emptyList()
        var allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
        val readCalls = mutableListOf<Triple<String, String, Int>>()
        val logs = mutableListOf<Pair<LogLevel, String>>()

        override fun ensureReady(targetPackage: String) {
            check(targetPackage == allowedPackage)
        }

        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? = null

        override fun readOrderRows(targetPackage: String, locatorRef: String, maxRows: Int): List<List<String>> {
            readCalls += Triple(targetPackage, locatorRef, maxRows)
            return orderRows.take(maxRows)
        }

        override suspend fun tap(targetPackage: String, locatorRef: String) = Unit

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit

        override suspend fun screenshot(taskId: String, label: String) =
            ScreenshotEvidence("/private/proof.png", 32, "a".repeat(64))

        override fun log(level: LogLevel, messageCode: String) {
            logs += level to messageCode
        }
    }
}
