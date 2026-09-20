package com.company.cloudctl.companion.automation

import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * P34 xy-review/20260921：xianyu.reviewOrders 执行语义 —— dry-run 填完不提交、
 * 真实模式逐单 提交+确认、无待评价即成功、maxOrders 截断、编辑页未开/提交
 * 未确认 fail-closed、非闲鱼目标拒绝。
 */
class ReviewOrdersExecutorTest {
    private val fixedNow = Instant.parse("2026-09-21T08:00:00Z")

    @Test
    fun dryRunFillsOneOrderAndNeverSubmits() = runBlocking {
        val ui = ReviewFakeUi().apply { pendingOrders = 3 }
        val journal = mutableListOf<String>()

        executor(ui).execute(
            task(AutomationStep.ReviewOrders("review", 60_000, 5, "宝贝很好，卖家很赞！", true)),
        ) { step, state -> journal += "${step.stepId}:$state" }

        // dry-run：进第一单、好评、填文案、截图，然后停 —— 零提交。
        assertEquals(1, ui.entryTaps)
        assertEquals(1, ui.ratingTaps)
        assertEquals(1, ui.commentFills.size)
        assertEquals(0, ui.submitTaps)
        assertTrue(ui.filledComments.all { it == "宝贝很好，卖家很赞！" })
        assertTrue(ui.screenshotLabels.contains("review-order-1-filled"))
        assertTrue(ui.logs.contains(LogLevel.INFO to "REVIEW_DRY_RUN_STOP order=1"))
        assertTrue(ui.logs.contains(LogLevel.INFO to "REVIEW_DONE processed=0 dryRun=true"))
        assertEquals(listOf("review:STARTED", "review:SUCCEEDED"), journal)
    }

    @Test
    fun submitsEveryPendingOrderUntilNoneRemains() = runBlocking {
        val ui = ReviewFakeUi().apply { pendingOrders = 2 }

        executor(ui).execute(
            task(AutomationStep.ReviewOrders("review", 60_000, 5, "好评", false)),
        ) { _, _ -> }

        assertEquals(3, ui.entryTaps) // 2 单 + 1 次空检查
        assertEquals(2, ui.submitTaps)
        assertTrue(ui.screenshotLabels.contains("review-order-1-filled"))
        assertTrue(ui.screenshotLabels.contains("review-order-1-submitted"))
        assertTrue(ui.screenshotLabels.contains("review-order-2-submitted"))
        assertTrue(ui.logs.contains(LogLevel.INFO to "REVIEW_DONE processed=2 dryRun=false"))
    }

    @Test
    fun zeroPendingOrdersSucceedsWithoutGestures() = runBlocking {
        val ui = ReviewFakeUi().apply { pendingOrders = 0 }

        executor(ui).execute(
            task(AutomationStep.ReviewOrders("review", 60_000, 5, "好评", false)),
        ) { _, _ -> }

        assertEquals(1, ui.entryTaps)
        assertEquals(0, ui.ratingTaps)
        assertEquals(0, ui.submitTaps)
        assertTrue(ui.logs.contains(LogLevel.INFO to "REVIEW_NO_PENDING_STOP"))
        assertTrue(ui.logs.contains(LogLevel.INFO to "REVIEW_DONE processed=0 dryRun=false"))
    }

    @Test
    fun maxOrdersCapsTheLoop() = runBlocking {
        val ui = ReviewFakeUi().apply { pendingOrders = 5 }

        executor(ui).execute(
            task(AutomationStep.ReviewOrders("review", 60_000, 2, "好评", false)),
        ) { _, _ -> }

        assertEquals(2, ui.submitTaps)
        assertTrue(ui.logs.contains(LogLevel.INFO to "REVIEW_DONE processed=2 dryRun=false"))
    }

    @Test
    fun rejectsNonXianyuTargets() = runBlocking {
        val ui = ReviewFakeUi().apply { allowedPackage = TargetLocatorRegistry.COMPANION_PACKAGE }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(
                    TargetLocatorRegistry.COMPANION_PACKAGE,
                    AutomationStep.ReviewOrders("review", 60_000, 5, "好评", true),
                ),
            ) { _, _ -> }
        }
        assertEquals("TARGET_PACKAGE_REJECTED", failure.code)
        assertEquals(0, ui.entryTaps)
    }

    @Test
    fun failsClosedWhenEditorNeverOpens() = runBlocking {
        val ui = ReviewFakeUi().apply {
            pendingOrders = 1
            editorOpens = false
        }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(AutomationStep.ReviewOrders("review", 60_000, 5, "好评", false)),
            ) { _, _ -> }
        }
        assertEquals("REVIEW_EDITOR_NOT_OPEN", failure.code)
        assertEquals(0, ui.submitTaps)
    }

    @Test
    fun failsClosedWhenSubmitIsUnconfirmed() = runBlocking {
        val ui = ReviewFakeUi().apply {
            pendingOrders = 1
            submitLeavesEditor = true
        }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(AutomationStep.ReviewOrders("review", 60_000, 5, "好评", false)),
            ) { _, _ -> }
        }
        assertEquals("REVIEW_SUBMIT_UNCONFIRMED", failure.code)
        assertEquals(1, ui.submitTaps)
    }

    private fun executor(ui: ReviewFakeUi): LocalAutomationExecutor {
        // 递增时钟:轮询等待(awaitReviewEditor/Gone)依赖 elapsedMs 前进,
        // 恒定值会让 fail-closed 用例死循环到真实超时。
        var tick = 0L
        return LocalAutomationExecutor(
            ui = ui,
            now = { fixedNow },
            elapsedMs = { tick += 300; tick },
            sleep = { kotlinx.coroutines.delay(1) },
        )
    }

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

    private class ReviewFakeUi : LocalAutomationUi {
        var pendingOrders = 0
        var editorOpens = true
        var submitLeavesEditor = false
        var allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE

        var entryTaps = 0
        var ratingTaps = 0
        var submitTaps = 0
        val commentFills = mutableListOf<String>()
        val filledComments = mutableListOf<String>()
        val screenshotLabels = mutableListOf<String>()
        val logs = mutableListOf<Pair<LogLevel, String>>()
        private var submitted = 0
        private var editorVisible = false

        override fun ensureReady(targetPackage: String) {
            check(targetPackage == allowedPackage)
        }

        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? = null

        override suspend fun tap(targetPackage: String, locatorRef: String) = Unit

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit

        override suspend fun screenshot(taskId: String, label: String): ScreenshotEvidence {
            screenshotLabels += label
            return ScreenshotEvidence("/private/review.png", 32, "a".repeat(64))
        }

        override fun log(level: LogLevel, messageCode: String) {
            logs += level to messageCode
        }

        override suspend fun openPendingReviewEntry(targetPackage: String): Boolean {
            if (pendingOrders > 0) {
                pendingOrders -= 1
                entryTaps += 1
                editorVisible = editorOpens
                return true
            }
            entryTaps += 1 // the probe of an empty list
            return false
        }

        override fun isReviewEditorVisible(targetPackage: String): Boolean = editorVisible

        override suspend fun tapReviewRatingGood(targetPackage: String) {
            ratingTaps += 1
        }

        override suspend fun setReviewComment(targetPackage: String, value: String) {
            commentFills += value
            filledComments += value
        }

        override suspend fun tapReviewSubmit(targetPackage: String) {
            submitTaps += 1
            submitted += 1
            if (!submitLeavesEditor) editorVisible = false
        }
    }
}
