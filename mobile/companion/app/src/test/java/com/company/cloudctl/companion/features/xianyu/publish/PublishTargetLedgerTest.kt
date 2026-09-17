package com.company.cloudctl.companion.features.xianyu.publish

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * P10 验收用例（Android 侧）——发布目标与任务身份分离 + 单件串行推进：
 * IN_FLIGHT 时不发下一目标；结果确认后才前进；已确认成功项绝不重做；
 * 未确认失败可重发（重试铸造新 taskId，目标身份不变）。
 */
class PublishTargetLedgerTest {

    private fun ledgerWithQueue(vararg boundaries: PublishCompletionBoundary): PublishTargetLedger {
        val ledger = PublishTargetLedger()
        boundaries.forEachIndexed { index, boundary ->
            ledger.enqueue("target-${index + 1}", "queue-1", boundary)
        }
        return ledger
    }

    @Test
    fun inFlightTargetBlocksSerialAdvance() {
        val ledger = ledgerWithQueue(
            PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE,
            PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE,
        )
        val first = ledger.nextTarget("queue-1")!!
        ledger.markInFlight(first.targetId, "task-100")
        // 单件串行：目标 1 未确认前，不发放目标 2。
        assertNull(ledger.nextTarget("queue-1"))
    }

    @Test
    fun confirmedResultUnblocksTheNextTarget() {
        val ledger = ledgerWithQueue(
            PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE,
            PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE,
        )
        val first = ledger.nextTarget("queue-1")!!
        ledger.markInFlight(first.targetId, "task-100")
        ledger.confirmSuccess(
            first.targetId,
            externalItemId = "xy-item-9001",
            recordedBoundary = PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT,
            boundaryDowngraded = true,
        )
        val second = ledger.nextTarget("queue-1")!!
        assertEquals("target-2", second.targetId)
    }

    @Test
    fun batchPartialSuccessNeverRedoesConfirmedItems() {
        // 批量 3 件：t1 成功、t2 失败（未确认→重发→确认失败）、t3 未开始。
        val ledger = ledgerWithQueue(
            PublishCompletionBoundary.FULL_AUTO,
            PublishCompletionBoundary.FULL_AUTO,
            PublishCompletionBoundary.FULL_AUTO,
        )
        val t1 = ledger.nextTarget("queue-1")!!
        ledger.markInFlight(t1.targetId, "task-1")
        ledger.confirmSuccess(
            t1.targetId,
            externalItemId = "xy-1",
            recordedBoundary = PublishCompletionBoundary.FULL_AUTO,
            boundaryDowngraded = false,
        )

        val t2 = ledger.nextTarget("queue-1")!!
        assertEquals("target-2", t2.targetId)
        ledger.markInFlight(t2.targetId, "task-2")
        ledger.markFailedUnconfirmed(t2.targetId)

        // 队列推进只取未确认失败/未开始项：t2（未确认失败）优先于 t3（未开始）。
        val retry = ledger.nextTarget("queue-1")!!
        assertEquals("target-2", retry.targetId)
        // 重发铸造新任务，目标身份不变（taskIds 累积）。
        ledger.markInFlight(t2.targetId, "task-2b")
        assertEquals(listOf("task-2", "task-2b"), ledger.record("target-2")!!.taskIds)

        // t2 确认失败（终态）后队列才前进到 t3；t1/t2 都不再返回。
        ledger.confirmFailure(t2.targetId)
        val t3 = ledger.nextTarget("queue-1")!!
        assertEquals("target-3", t3.targetId)
        ledger.markInFlight(t3.targetId, "task-3")
        ledger.confirmSuccess(
            t3.targetId,
            externalItemId = "xy-3",
            recordedBoundary = PublishCompletionBoundary.FULL_AUTO,
            boundaryDowngraded = false,
        )
        assertNull(ledger.nextTarget("queue-1"))
    }

    @Test
    fun confirmedSuccessCannotBeReissuedOrOverwritten() {
        val ledger = ledgerWithQueue(PublishCompletionBoundary.FULL_AUTO)
        ledger.markInFlight("target-1", "task-1")
        ledger.confirmSuccess(
            "target-1",
            externalItemId = "xy-1",
            recordedBoundary = PublishCompletionBoundary.FULL_AUTO,
            boundaryDowngraded = false,
        )
        assertNull(ledger.nextTarget("queue-1"))
        assertFailsWith<IllegalStateException> { ledger.markInFlight("target-1", "task-1b") }
        assertFailsWith<IllegalStateException> { ledger.confirmFailure("target-1") }
        assertFailsWith<IllegalStateException> { ledger.cancel("target-1") }
    }

    @Test
    fun externalIdentityIsRecordedOnTheTargetNotTheTask() {
        val ledger = ledgerWithQueue(PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE)
        ledger.markInFlight("target-1", "task-1")
        val confirmed = ledger.confirmSuccess(
            "target-1",
            externalItemId = "xy-item-42",
            recordedBoundary = PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE,
            boundaryDowngraded = false,
        )
        // 外部身份挂在目标上；任务只是 attempts 之一。
        assertEquals("xy-item-42", confirmed.externalItemId)
        assertEquals(listOf("task-1"), confirmed.taskIds)
        assertTrue(confirmed.terminal)
    }

    @Test
    fun enqueueIsIdempotentPerTargetIdentity() {
        val ledger = PublishTargetLedger()
        ledger.enqueue("target-1", "queue-1", PublishCompletionBoundary.FULL_AUTO)
        assertFailsWith<IllegalArgumentException> {
            ledger.enqueue("target-1", "queue-1", PublishCompletionBoundary.FULL_AUTO)
        }
    }

    @Test
    fun queuesAreIsolated() {
        val ledger = PublishTargetLedger()
        ledger.enqueue("q1-t1", "queue-1", PublishCompletionBoundary.FULL_AUTO)
        ledger.enqueue("q2-t1", "queue-2", PublishCompletionBoundary.FULL_AUTO)
        ledger.markInFlight("q1-t1", "task-a")
        // queue-1 在跑不影响 queue-2 的推进判断。
        assertEquals("q2-t1", ledger.nextTarget("queue-2")!!.targetId)
        assertNull(ledger.nextTarget("queue-1"))
    }
}
