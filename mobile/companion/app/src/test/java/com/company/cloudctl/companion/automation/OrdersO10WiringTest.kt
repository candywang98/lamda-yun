package com.company.cloudctl.companion.automation

import com.company.cloudctl.companion.features.xianyu.orders.OrderPageReading
import com.company.cloudctl.companion.features.xianyu.orders.OrderPageSummary
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * O10 wiring (fleet-first-20260916.1) — the delivered pure modules pulled into
 * the executor: OrderSeenRegistry.absorbPage (cross-screen AND same-page
 * dedupe), OrderScrollPolicy.decide (empty/stagnant/max-screens three-stop),
 * OrderPageSummary (per-screen feed) and the OrderScreensReporter dual-write
 * port. v1 single-read tasks keep the frozen slice1 semantics untouched.
 */
class OrdersO10WiringTest {
    private val fixedNow = Instant.parse("2026-09-15T08:00:00Z")
    private val zwsp = "​"

    private fun row(nickname: String, title: String, price: String): List<String> = listOf(
        "订单信息, 退货运费险",
        "$nickname, $nickname",
        "交易成功, 交易成功",
        "$title, $title",
        "¥$zwsp",
        price,
    )

    /** A row with only a price segment: parsed (keyed) but partially visible. */
    private fun partialRow(price: String): List<String> = listOf("订单信息, 退货运费险", "¥$zwsp", price)

    private fun keyOf(nickname: String, title: String, cents: Long) = "SOLD|$nickname|$title|$cents"

    @Test
    fun multiScreenRunAbsorbsPagesAndDualWritesBothChannels() = runBlocking {
        val a = row("买家A", "商品A", "2${zwsp}5")
        val b = row("买家B", "商品B", "3${zwsp}0")
        val c = row("买家C", "商品C", "4${zwsp}0")
        // Screen 2 re-exposes B (cross-screen overlap) and adds C.
        val ui = ScreenScriptUi().apply { screens += listOf(listOf(a, b), listOf(b, c)) }
        val batch = RecordingBatchReporter()
        val screens = RecordingScreensReporter()
        val events = mutableListOf<String>()
        batch.onReport = { events += "batch:${batch.calls.last().screen}" }
        screens.onReport = { events += "screens:${screens.calls.last().page.screen}" }

        executor(ui, batch, screens).execute(
            task(
                AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-2", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
            ),
        ) { step, state -> events += "journal:${step.stepId}:$state" }

        // Old slice1 batch channel stays live (dual-write transition): it
        // carries only the reportable rows — new keys plus upserts.
        assertEquals(listOf(1, 2), batch.calls.map { it.screen })
        assertEquals(
            listOf(keyOf("买家A", "商品A", 2500), keyOf("买家B", "商品B", 3000)),
            batch.calls[0].collected.map { it.orderKey },
        )
        assertEquals(listOf(keyOf("买家C", "商品C", 4000)), batch.calls[1].collected.map { it.orderKey })

        // New screens channel: full page readings with absorb verdicts.
        assertEquals(listOf(1, 2), screens.calls.map { it.page.screen })
        val page1 = screens.calls[0].page
        val page2 = screens.calls[1].page
        assertEquals(2, page1.newKeyCount)
        assertEquals(0, page1.overlapCount)
        assertEquals(1, page2.newKeyCount)
        assertEquals(1, page2.overlapCount)
        assertTrue(!page1.empty && !page2.empty)

        // Summaries carry the frozen page facts with the executor clock.
        assertEquals(
            listOf(
                OrderPageSummary(
                    screen = 1, rowsSeen = 2, newKeys = 2, updatedKeys = 0, overlap = 0,
                    skipped = 0, partiallyVisible = 0, empty = false, collectedAt = fixedNow.toString(),
                ),
                OrderPageSummary(
                    screen = 2, rowsSeen = 2, newKeys = 1, updatedKeys = 0, overlap = 1,
                    skipped = 0, partiallyVisible = 0, empty = false, collectedAt = fixedNow.toString(),
                ),
            ),
            screens.calls.map { it.summary },
        )
        // The screens rows carry the screen's parsed rows in page order.
        assertEquals(
            listOf(keyOf("买家B", "商品B", 3000), keyOf("买家C", "商品C", 4000)),
            screens.calls[1].rows.map { it.orderKey },
        )
        // Both channels fire right after the screen's SUCCEEDED, batch first.
        assertEquals(
            listOf(
                "journal:read-orders:STARTED", "journal:read-orders:SUCCEEDED",
                "batch:1", "screens:1",
                "journal:swipe-up-2:STARTED", "journal:swipe-up-2:SUCCEEDED",
                "journal:read-orders-2:STARTED", "journal:read-orders-2:SUCCEEDED",
                "batch:2", "screens:2",
            ),
            events,
        )
    }

    @Test
    fun sameScreenReplayIsAbsorbedAsOverlapInMultiScreenRuns() = runBlocking {
        val a = row("买家A", "商品A", "2${zwsp}5")
        // Same page re-exposes the same row twice (pinned orders, replay).
        val ui = ScreenScriptUi().apply { screens += listOf(listOf(a, a)) }
        val batch = RecordingBatchReporter()
        val screens = RecordingScreensReporter()

        executor(ui, batch, screens).execute(
            task(
                AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-2", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
            ),
        ) { _, _ -> }

        // The duplicate never re-reports through either channel.
        assertEquals(1, batch.calls[0].collected.size)
        val page1 = screens.calls[0].page
        assertEquals(1, page1.newKeyCount)
        assertEquals(1, page1.overlapCount)
        assertTrue(ui.logs.any { it == LogLevel.INFO to "ORDERS_OVERLAP_1" })
    }

    @Test
    fun partiallyVisibleRowIndicesReachTheScreensPort() = runBlocking {
        val a = row("买家A", "商品A", "2${zwsp}5")
        val partial = partialRow("9${zwsp}9")
        val ui = ScreenScriptUi().apply { screens += listOf(listOf(a, partial)) }
        val screens = RecordingScreensReporter()

        executor(ui, null, screens).execute(
            task(
                AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-2", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
            ),
        ) { _, _ -> }

        // Index 1 is the partially visible row (no nickname, no title). The
        // second screen reads empty from the exhausted script and also pages.
        assertEquals(listOf(1), screens.calls.first().partialRowIndices)
        assertEquals(1, screens.calls.first().summary.partiallyVisible)
        assertTrue(screens.calls.drop(1).all { it.partialRowIndices.isEmpty() })
    }

    @Test
    fun emptyPageStopsPaginationBeforeTheNextSwipe() = runBlocking {
        val a = row("买家A", "商品A", "2${zwsp}5")
        // Screen 2 reads zero rows (list ended): no swipe to screen 3, no
        // screen-3 read — the stop reason and skip are logged, the task
        // succeeds, and later non-orders steps still run.
        val ui = ScreenScriptUi().apply { screens += listOf(listOf(a), emptyList()) }
        val batch = RecordingBatchReporter()
        val journal = mutableListOf<String>()

        executor(ui, batch, null).execute(
            task(
                AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-2", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-3", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-3", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.Log("mark-done", 1_000, LogLevel.INFO, "DONE"),
            ),
        ) { step, state -> journal += "${step.stepId}:$state" }

        assertEquals(1, ui.containerSwipes.size) // only swipe-up-2 happened
        assertEquals(2, ui.readCalls.size) // screens 1 and 2
        assertTrue(ui.logs.any { it == LogLevel.INFO to OrderScrollDecisionReasons.EMPTY_PAGE })
        assertTrue(ui.logs.any { it == LogLevel.INFO to "ORDERS_STOPPED_SKIP_swipe-up-3" })
        assertTrue(ui.logs.any { it == LogLevel.INFO to "ORDERS_STOPPED_SKIP_read-orders-3" })
        // Skipped steps never reach the journal; the trailing Log step still runs.
        assertTrue(journal.none { it.startsWith("swipe-up-3:") || it.startsWith("read-orders-3:") })
        assertEquals("mark-done:SUCCEEDED", journal.last())
    }

    @Test
    fun stagnantScreensStopPagination() = runBlocking {
        val a = row("买家A", "商品A", "2${zwsp}5")
        // Screens 2..3 re-expose only known rows (non-empty, zero new keys):
        // two stagnant screens in a row end the pagination before screen 4.
        val ui = ScreenScriptUi().apply { screens += listOf(listOf(a), listOf(a), listOf(a)) }
        val journal = mutableListOf<String>()

        executor(ui, null, null).execute(
            task(
                AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-2", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-3", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-3", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-4", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-4", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
            ),
        ) { step, state -> journal += "${step.stepId}:$state" }

        assertTrue(ui.logs.any { it == LogLevel.INFO to OrderScrollDecisionReasons.STAGNANT })
        assertEquals(3, ui.readCalls.size) // screens 1..3 read, screen 4 skipped
        assertTrue(journal.none { it.startsWith("read-orders-4:") })
    }

    @Test
    fun maxScreensStopRefusesTheFourthSwipeEvenWithFreshKeys() = runBlocking {
        val a = row("买家A", "商品A", "2${zwsp}5")
        val b = row("买家B", "商品B", "3${zwsp}0")
        val c = row("买家C", "商品C", "4${zwsp}0")
        val ui = ScreenScriptUi().apply { screens += listOf(listOf(a), listOf(b), listOf(c)) }

        executor(ui, null, null).execute(
            task(
                AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-2", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-2", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-3", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-3", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
                AutomationStep.SwipeUp("swipe-up-4", 1_000, "xianyu_orders_container"),
                AutomationStep.ReadOrders("read-orders-4", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container"),
            ),
        ) { _, _ -> }

        // All three screens carried new keys — only the MAX_SCREENS cap ends it.
        assertTrue(ui.logs.any { it == LogLevel.INFO to OrderScrollDecisionReasons.MAX_SCREENS })
        assertEquals(2, ui.containerSwipes.size) // swipe-up-2 and swipe-up-3
        assertEquals(3, ui.readCalls.size)
    }

    @Test
    fun singleReadTaskKeepsSlice1SemanticsAndNeverFiresTheScreensPort() = runBlocking {
        val a = row("买家A", "商品A", "2${zwsp}5")
        // Same-screen duplicates keep the frozen slice1 rule: every row
        // reports through the batch channel, no registry, no screens push.
        val ui = ScreenScriptUi().apply { screens += listOf(listOf(a, a)) }
        val batch = RecordingBatchReporter()
        val screens = RecordingScreensReporter()

        executor(ui, batch, screens).execute(
            task(AutomationStep.ReadOrders("read-orders", 1_000, OrderDirection.SOLD, 10, "xianyu_orders_container")),
        ) { _, _ -> }

        assertEquals(1, batch.calls.size)
        assertEquals(2, batch.calls.single().collected.size)
        assertTrue(screens.calls.isEmpty())
        assertTrue(ui.logs.none { it.second.startsWith("ORDERS_OVERLAP_") })
        assertTrue(ui.logs.none { it.second.startsWith("ORDERS_READ_SCREEN_") })
    }

    // ------------------------------------------------------------------
    // helpers
    // ------------------------------------------------------------------

    /** Stable reason codes mirrored from OrderScrollDecision for readability. */
    private object OrderScrollDecisionReasons {
        const val EMPTY_PAGE = "STOP_EMPTY_PAGE"
        const val STAGNANT = "STOP_STAGNANT"
        const val MAX_SCREENS = "STOP_MAX_SCREENS"
    }

    private fun executor(
        ui: ScreenScriptUi,
        batch: OrderReporter?,
        screens: OrderScreensReporter?,
    ): LocalAutomationExecutor {
        var tick = 0L
        return LocalAutomationExecutor(
            ui = ui,
            now = { fixedNow },
            elapsedMs = { tick += 500; tick },
            sleep = { delay(1) },
            orderReporter = batch,
            orderScreensReporter = screens,
        )
    }

    private fun task(vararg steps: AutomationStep) = AutomationTask(
        taskId = "task-1",
        deviceId = "device-1",
        targetPackage = TargetLocatorRegistry.XIANYU_PACKAGE,
        issuedAt = fixedNow.minusSeconds(60),
        expiresAt = fixedNow.plusSeconds(600),
        maxRunSeconds = 60,
        steps = steps.toList(),
    )

    private class BatchCall(
        val taskId: String,
        val direction: OrderDirection,
        val collected: List<OrderRowSnapshot>,
        val skipped: List<SkippedOrderRow>,
        val screen: Int,
    )

    private class RecordingBatchReporter : OrderReporter {
        val calls = mutableListOf<BatchCall>()
        var onReport: (() -> Unit)? = null

        override suspend fun reportOrders(
            taskId: String,
            direction: OrderDirection,
            collected: List<OrderRowSnapshot>,
            skipped: List<SkippedOrderRow>,
            screen: Int,
        ) {
            calls += BatchCall(taskId, direction, collected, skipped, screen)
            onReport?.invoke()
        }
    }

    private class ScreensCall(
        val taskId: String,
        val direction: OrderDirection,
        val page: OrderPageReading,
        val summary: OrderPageSummary,
        val rows: List<OrderRowSnapshot>,
        val partialRowIndices: List<Int>,
    )

    private class RecordingScreensReporter : OrderScreensReporter {
        val calls = mutableListOf<ScreensCall>()
        var onReport: (() -> Unit)? = null

        override suspend fun reportScreen(
            taskId: String,
            direction: OrderDirection,
            page: OrderPageReading,
            summary: OrderPageSummary,
            rows: List<OrderRowSnapshot>,
            partialRowIndices: List<Int>,
        ) {
            calls += ScreensCall(taskId, direction, page, summary, rows, partialRowIndices)
            onReport?.invoke()
        }
    }

    /** 按屏脚本化的假 UI：screens 队列按 readOrders 调用顺序出队。 */
    private class ScreenScriptUi : LocalAutomationUi {
        val screens = ArrayDeque<List<List<String>>>()
        val readCalls = mutableListOf<Triple<String, String, Int>>()
        val containerSwipes = mutableListOf<Pair<String, String>>()
        val logs = mutableListOf<Pair<LogLevel, String>>()

        override fun ensureReady(targetPackage: String) = Unit

        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? = null

        override fun readOrderRows(targetPackage: String, locatorRef: String, maxRows: Int): List<List<String>> {
            readCalls += Triple(targetPackage, locatorRef, maxRows)
            return (screens.removeFirstOrNull() ?: emptyList()).take(maxRows)
        }

        override suspend fun swipeUpWithin(targetPackage: String, locatorRef: String) {
            containerSwipes += targetPackage to locatorRef
        }

        override suspend fun swipeUp() = Unit

        override suspend fun tap(targetPackage: String, locatorRef: String) = Unit

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit

        override suspend fun screenshot(taskId: String, label: String) =
            ScreenshotEvidence("/private/proof.png", 32, "a".repeat(64))

        override fun log(level: LogLevel, messageCode: String) {
            logs += level to messageCode
        }
    }
}
