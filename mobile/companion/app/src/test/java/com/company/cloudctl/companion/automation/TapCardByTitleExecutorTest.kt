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
 *
 * 2026-09-16 错卡事故后的防线：手势成功 ≠ 目的地正确 —— 步骤成功前必须核验
 * 详情页标题（防线1，DETAIL_TITLE_MISMATCH fail-closed），错卡链条死在管理菜单
 * 与门控之前；tap 前 bounds 不稳（防线2）以 CARD_BOUNDS_UNSTABLE 直通，绝不重试。
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
        // 正常路径新增行为：标题核验通过才记步成功。
        assertTrue(ui.logs.contains(LogLevel.INFO to "DETAIL_TITLE_VERIFIED"))
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

    // ------------------------------------------------------------------
    // 2026-09-16 错卡防线：标题不匹配 → fail-closed，管理菜单/门控零执行。
    // ------------------------------------------------------------------

    @Test
    fun wrongDetailPageFailsClosedBeforeTheManageMenuAndTheGate() = runBlocking {
        // 事故重演：目标「如果历史是一群喵4」，tap 打开的是谈祥柏的详情页。
        val ui = TapCardFakeUi().apply {
            nodes["xianyu_pub_tab_delisted"] = tabNode("1\n已下架")
            detailLines = listOf("返回", "《你为什么解不开数学题》谈祥柏", "¥42.00")
        }
        val gate = RecordingSemanticGate()
        val journal = mutableListOf<String>()
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui, gate).execute(
                task(
                    AutomationStep.TapCardByTitle(
                        "open-card-by-title", 60_000,
                        XianyuMaintenanceLayout.Tab.DELISTED, "如果历史是一群喵4",
                    ),
                    AutomationStep.Tap("open-manage-menu", 1_000, "xianyu_detail_manage", null),
                    AutomationStep.Tap("tap-delete-item", 1_000, "xianyu_manage_delete", null),
                    AutomationStep.Tap("confirm-delete", 1_000, "xianyu_delete_confirm", null),
                ),
            ) { step, state -> journal += "${step.stepId}:$state" }
        }

        assertEquals("DETAIL_TITLE_MISMATCH", failure.code)
        // 日志记录 expected 与 actual 标题。
        assertTrue(failure.message!!.contains("如果历史是一群喵4"))
        assertTrue(failure.message!!.contains("谈祥柏"))
        assertTrue(ui.logs.contains(LogLevel.ERROR to "DETAIL_TITLE_MISMATCH"))
        // 事故链条死在第一步：管理菜单、删除项、门控确认零执行。
        assertEquals(listOf("open-card-by-title:STARTED"), journal)
        assertTrue(ui.locatorTaps.isEmpty())
        assertTrue(gate.semanticConfirms.isEmpty())
        // 错页不是暂态缺卡：绝不当 CARD_TITLE_NOT_FOUND 重试（只此一次手势）。
        assertEquals(1, ui.cardTaps.size)
    }

    @Test
    fun midRenderDetailReadDoesNotKillACorrectPage() = runBlocking {
        // 第一次读数还是过渡页（可读但无标题），第二次才是正确详情：必须通过。
        val ui = TapCardFakeUi().apply {
            nodes["xianyu_pub_tab_onsale"] = tabNode("3\n在卖")
            transientFirstRead = listOf("返回", "管理")
        }
        val journal = mutableListOf<String>()
        executor(ui).execute(
            task(
                AutomationStep.TapCardByTitle(
                    "open-card-by-title", 60_000,
                    XianyuMaintenanceLayout.Tab.ONSALE, "黄同学漫画二战史",
                ),
            ),
        ) { step, state -> journal += "${step.stepId}:$state" }

        assertEquals(listOf("open-card-by-title:STARTED", "open-card-by-title:SUCCEEDED"), journal)
        assertTrue(ui.logs.contains(LogLevel.INFO to "DETAIL_TITLE_VERIFIED"))
    }

    @Test
    fun unstableCardBoundsFailClosedWithoutRetry() = runBlocking {
        // 防线2（service 内 tap 前复核）的失败码直通执行器：不是暂态，绝不重试。
        val ui = TapCardFakeUi().apply {
            standingFailure = ExecutorFailure("CARD_BOUNDS_UNSTABLE", "bounds kept drifting")
        }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(
                    AutomationStep.TapCardByTitle(
                        "open-card-by-title", 60_000,
                        XianyuMaintenanceLayout.Tab.DELISTED, "如果历史是一群喵4",
                    ),
                ),
            ) { _, _ -> }
        }
        assertEquals("CARD_BOUNDS_UNSTABLE", failure.code)
        assertEquals(1, ui.cardTaps.size)
    }

    /** Records ledger confirmations; the wrong-card chain must never reach it. */
    private class RecordingSemanticGate : DestructiveClickGate {
        val semanticConfirms = mutableListOf<String>()

        override suspend fun confirmOnce(task: AutomationTask, step: AutomationStep.TapLayout): Int? =
            error("layout confirm is not part of this chain")

        override suspend fun confirmOnce(task: AutomationTask, locatorRef: String): Int? {
            semanticConfirms += locatorRef
            return null
        }
    }

    private fun executor(ui: TapCardFakeUi, gate: DestructiveClickGate? = null) = LocalAutomationExecutor(
        ui = ui,
        now = { fixedNow },
        elapsedMs = { 1_000L },
        sleep = { delay(1) },
        destructiveGate = gate,
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

        /** 详情页可见行；null 表示仍在列表页（列表行不参与标题核验）。 */
        var detailLines: List<String>? = null

        /** 首次 visibleTextLines 读数返回的过渡页内容（之后才读 detailLines）。 */
        var transientFirstRead: List<String>? = null
        private var detailReads = 0

        val cardTaps = mutableListOf<Triple<String, XianyuMaintenanceLayout.Tab, String>>()
        val locatorTaps = mutableListOf<String>()
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
            // 手势成功：页面离开列表进详情（tabs 从活树消失）。
            nodes.remove("xianyu_pub_tab_onsale")
            nodes.remove("xianyu_pub_tab_delisted")
            if (detailLines == null) {
                detailLines = listOf("《黄同学漫画二战史2》个人闲置", "¥45.00")
            }
        }

        override fun visibleTextLines(targetPackage: String): List<String> {
            detailReads += 1
            if (detailReads == 1) transientFirstRead?.let { return it }
            return detailLines ?: emptyList()
        }

        override suspend fun tap(targetPackage: String, locatorRef: String) {
            locatorTaps += locatorRef
        }

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit

        override suspend fun screenshot(taskId: String, label: String) =
            ScreenshotEvidence("/private/proof.png", 32, "a".repeat(64))

        override fun log(level: LogLevel, messageCode: String) {
            logs += level to messageCode
        }
    }
}
