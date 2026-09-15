package com.company.cloudctl.companion.automation

import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * W4 维护动作 v2（契约 xianyu-anchors-20260915 §1/§2）：tapCardByTitle 执行语义 ——
 * 唯一命中卡 → 一次手势进详情；列表未渲染（tab/滚动容器/卡片缺）在步窗口内轮询；
 * 歧义多卡立刻失败零副作用；执行前在列表页采集受控确认所需的角标基线快照
 * （v2 无 tapLayout 首击，tapCardByTitle 就是 v2 的首击）。
 */
class TapCardByTitleExecutorTest {
    private val fixedNow = Instant.parse("2026-09-15T08:00:00Z")

    @Test
    fun tapsTheUniqueCardAndCapturesTheBadgeBaselineForTheGatedConfirm() = runBlocking {
        val ui = TapCardFakeUi().apply {
            nodes["xianyu_pub_tab_onsale"] = tabNode("3\n在卖")
        }
        val journal = mutableListOf<String>()

        executor(ui).execute(
            task(
                AutomationStep.TapCardByTitle(
                    "open-card-by-title", 1_000,
                    XianyuMaintenanceLayout.Tab.ONSALE, "黄同学漫画二战史",
                ),
            ),
        ) { step, state -> journal += "${step.stepId}:$state" }

        assertEquals(
            listOf(Triple(TargetLocatorRegistry.XIANYU_PACKAGE, XianyuMaintenanceLayout.Tab.ONSALE, "黄同学漫画二战史")),
            ui.cardTaps,
        )
        assertEquals(listOf("open-card-by-title:STARTED", "open-card-by-title:SUCCEEDED"), journal)
        // v2 首击基线：确认弹窗出现在详情页（tabs 不可见），受控确认从快照取基线。
        assertEquals(3, MaintenanceBadgeSnapshots.take("task-1", "xianyu_pub_tab_onsale"))
    }

    @Test
    fun delistedSearchesSnapshotTheDelistedTabBaseline() = runBlocking {
        val ui = TapCardFakeUi().apply {
            nodes["xianyu_pub_tab_delisted"] = tabNode("已下架")
        }
        executor(ui).execute(
            task(
                AutomationStep.TapCardByTitle(
                    "open-card-by-title", 1_000,
                    XianyuMaintenanceLayout.Tab.DELISTED, "二战史",
                ),
            ),
        ) { _, _ -> }
        // 已下架 tab 无数字角标（真机实证）：基线 0，与 v1 删除路径同构。
        assertEquals(0, MaintenanceBadgeSnapshots.take("task-1", "xianyu_pub_tab_delisted"))
    }

    @Test
    fun retriesTransientMissesWhileTheListRendersThenSucceeds() = runBlocking {
        val ui = TapCardFakeUi().apply {
            notFoundAttempts = 2
            nodes["xianyu_pub_tab_onsale"] = tabNode("5\n在卖")
        }
        executor(ui).execute(
            task(
                AutomationStep.TapCardByTitle(
                    "open-card-by-title", 60_000,
                    XianyuMaintenanceLayout.Tab.ONSALE, "二战史",
                ),
            ),
        ) { _, _ -> }
        assertEquals(3, ui.cardTaps.size)
    }

    @Test
    fun failsWithCardTitleNotFoundWhenTheStepWindowExpires() = runBlocking {
        val ui = TapCardFakeUi().apply { notFoundAttempts = Int.MAX_VALUE }
        var tick = 0L
        val bounded = LocalAutomationExecutor(
            ui = ui,
            now = { fixedNow },
            elapsedMs = { tick += 600; tick },
            sleep = { delay(1) },
        )
        val slackTask = AutomationTask(
            taskId = "task-1",
            deviceId = "device-1",
            targetPackage = TargetLocatorRegistry.XIANYU_PACKAGE,
            issuedAt = fixedNow.minusSeconds(30),
            expiresAt = fixedNow.plusSeconds(600),
            maxRunSeconds = 60,
            steps = listOf(
                AutomationStep.TapCardByTitle(
                    "open-card-by-title", 1_000,
                    XianyuMaintenanceLayout.Tab.ONSALE, "二战史",
                ),
            ),
        )
        val failure = assertFailsWith<ExecutorFailure> { bounded.execute(slackTask) { _, _ -> } }
        assertEquals("CARD_TITLE_NOT_FOUND", failure.code)
        assertTrue(ui.cardTaps.isNotEmpty())
    }

    @Test
    fun ambiguousMatchesFailImmediatelyWithoutRetry() = runBlocking {
        val ui = TapCardFakeUi().apply { standingFailure = ExecutorFailure("CARD_TITLE_AMBIGUOUS", "two cards") }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(
                    AutomationStep.TapCardByTitle(
                        "open-card-by-title", 60_000,
                        XianyuMaintenanceLayout.Tab.ONSALE, "二战史",
                    ),
                ),
            ) { _, _ -> }
        }
        assertEquals("CARD_TITLE_AMBIGUOUS", failure.code)
        // 歧义不是暂态：绝不轮询重试（重试可能点到另一张卡）。
        assertEquals(1, ui.cardTaps.size)
        assertTrue(ui.logs.contains(LogLevel.ERROR to "CARD_TITLE_AMBIGUOUS"))
    }

    @Test
    fun rejectsNonXianyuTargetsBeforeAnySearch() = runBlocking {
        val ui = TapCardFakeUi().apply { allowedPackage = TargetLocatorRegistry.COMPANION_PACKAGE }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(
                    TargetLocatorRegistry.COMPANION_PACKAGE,
                    AutomationStep.TapCardByTitle(
                        "open-card-by-title", 1_000,
                        XianyuMaintenanceLayout.Tab.ONSALE, "二战史",
                    ),
                ),
            ) { _, _ -> }
        }
        assertEquals("TARGET_PACKAGE_REJECTED", failure.code)
        assertTrue(ui.cardTaps.isEmpty())
    }

    private fun executor(ui: TapCardFakeUi) = LocalAutomationExecutor(
        ui = ui,
        now = { fixedNow },
        elapsedMs = { 1_000L },
        sleep = { delay(1) },
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

    private fun tabNode(description: String) = LocalNodeState(
        enabled = true,
        visible = true,
        clickable = true,
        editable = false,
        text = null,
        description = description,
    )

    private class TapCardFakeUi : LocalAutomationUi {
        var allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
        var notFoundAttempts = 0
        var standingFailure: ExecutorFailure? = null
        val cardTaps = mutableListOf<Triple<String, XianyuMaintenanceLayout.Tab, String>>()
        val nodes = mutableMapOf<String, LocalNodeState>()
        val logs = mutableListOf<Pair<LogLevel, String>>()

        override fun ensureReady(targetPackage: String) {
            check(targetPackage == allowedPackage)
        }

        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? = nodes[locatorRef]

        override suspend fun tapCardByTitle(
            targetPackage: String,
            tab: XianyuMaintenanceLayout.Tab,
            titleContains: String,
        ) {
            cardTaps += Triple(targetPackage, tab, titleContains)
            standingFailure?.let { throw it }
            if (notFoundAttempts > 0) {
                notFoundAttempts -= 1
                throw ExecutorFailure("CARD_TITLE_NOT_FOUND", "list still rendering")
            }
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
