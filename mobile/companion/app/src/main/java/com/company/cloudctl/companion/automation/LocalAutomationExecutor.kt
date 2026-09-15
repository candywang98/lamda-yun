package com.company.cloudctl.companion.automation

import kotlinx.coroutines.delay
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.withTimeout
import java.time.Instant

data class LocalNodeState(
    val enabled: Boolean,
    val visible: Boolean,
    val clickable: Boolean,
    val editable: Boolean,
    val text: String?,
    val description: String? = null,
)

data class ScreenshotEvidence(val path: String, val size: Long, val sha256: String)

class ExecutorFailure(
    val code: String,
    message: String,
    cause: Throwable? = null,
) : IllegalStateException(message, cause)

interface LocalAutomationUi {
    fun ensureReady(targetPackage: String)
    fun inspect(targetPackage: String, locatorRef: String): LocalNodeState?
    fun visibleTextContains(expected: String): Boolean = false
    suspend fun tapText(targetPackage: String, value: String) {
        error("tapText is not supported by this executor")
    }

    suspend fun tap(targetPackage: String, locatorRef: String)
    suspend fun tapOnce(targetPackage: String, locatorRef: String) {
        throw ExecutorFailure("SINGLE_SHOT_UNAVAILABLE", "UI does not provide a single-shot tap")
    }
    suspend fun replaceText(targetPackage: String, locatorRef: String, value: String)
    suspend fun screenshot(taskId: String, label: String): ScreenshotEvidence
    suspend fun swipeUp() {}
    fun log(level: LogLevel, messageCode: String)

    // Navigation reset primitive (im-live slice 2, gap 1): defaults are inert so
    // plain executors keep running without back/relaunch support.

    /** True when the target package currently owns the active accessibility window. */
    fun isTargetForeground(targetPackage: String): Boolean = true

    /** True when a root-page anchor (for example the bottom tab bar) is visible. */
    fun atRootPage(targetPackage: String): Boolean = true

    /** Returns the safe label only after a confirmed allowlisted dialog gesture; no generic dismissal. */
    suspend fun dismissBlockedDialog(targetPackage: String): String? = null

    /** One system BACK press; implementations settle before returning. */
    suspend fun goBack() {}

    /** Forced relaunch of the target that lands on its root activity. */
    suspend fun restartTargetApp(targetPackage: String) {}

    // Conversation-list scrolling (im-live slice 2, gap 3): tapText retry support.

    /** True when the visible list container can still scroll forward. */
    fun canScrollTextList(targetPackage: String): Boolean = false

    /** Scrolls the visible list forward; implementations settle before returning. */
    suspend fun scrollTextListForward(targetPackage: String) {}

    // Structured xianyu maintenance coordinates (contract
    // xianyu-maintenance-anchors-20260915): the live screen size feeds the
    // 1080x2400 resolution guard, and taps go through one dispatchGesture only.

    /** Live screen size for the layout guard; null fails the coordinate path closed. */
    fun screenSize(targetPackage: String): Pair<Int, Int>? = null

    /** Single-shot coordinate tap; no fallback path, an unconfirmed gesture fails closed. */
    suspend fun tapScreenAt(targetPackage: String, x: Int, y: Int) {
        throw ExecutorFailure("COORDINATE_TAP_UNAVAILABLE", "UI does not provide single-shot coordinate taps")
    }

    // Order-sync slice 1 (contract order-sync/20260915.1 §5): read the current
    // screen's order rows out of the list container resolved from [locatorRef].
    // A row is one clickable child of the container; its entry is the ordered
    // text/content-desc lines of that child's subtree. At most [maxRows] rows
    // come back; an empty list is a successful read of zero rows.

    fun readOrderRows(targetPackage: String, locatorRef: String, maxRows: Int): List<List<String>> =
        error("readOrders is not supported by this executor")

    // W4 maintenance v2 (contract xianyu-anchors-20260915 §1/§2): open a
    // published-list card by its title text. Implementations resolve the live
    // tab-strip bottom edge (never a hardcoded y), search the visible cards of
    // the scrollable list below it, and tap the unique matching card's bounds
    // center with one gesture. Zero matches -> CARD_TITLE_NOT_FOUND, several
    // distinct cards -> CARD_TITLE_AMBIGUOUS, list still rendering ->
    // LIST_TAB_NOT_FOUND / SCROLL_CONTAINER_MISSING; all before any gesture.

    suspend fun tapCardByTitle(targetPackage: String, tab: XianyuMaintenanceLayout.Tab, titleContains: String) {
        error("tapCardByTitle is not supported by this executor")
    }
}

private val GATED_PUBLISH_LOCATORS = setOf("xianyu_publish_button", "xhs_publish_button", "dy_publish_button")
private const val GATED_XIANYU_DELETE_CONFIRM = "xianyu_delete_confirm"

/** Container-resolution poll interval while the Flutter order list renders. */
private const val ORDER_ROW_POLL_MS = 700L

private class PendingOrderReport(
    val direction: OrderDirection,
    val collected: List<OrderRowSnapshot>,
    val skipped: List<SkippedOrderRow>,
)

class LocalAutomationExecutor(
    private val ui: LocalAutomationUi,
    private val now: () -> Instant = Instant::now,
    private val elapsedMs: () -> Long = { android.os.SystemClock.elapsedRealtime() },
    private val sleep: suspend (Long) -> Unit = { delay(it) },
    private val commitGate: CommitGate? = null,
    private val destructiveGate: DestructiveClickGate? = null,
    private val orderReporter: OrderReporter? = null,
) {
    /** Badge baselines (tab locator -> count at the strike) captured during one run. */
    private val badgeBaselines = mutableMapOf<String, Int>()

    /** Collected orders awaiting the post-step §5 batch report (one readOrders step per run). */
    private var pendingOrderReport: PendingOrderReport? = null

    suspend fun execute(
        task: AutomationTask,
        control: ExecutionControl? = null,
        startAfterIndex: Int = -1,
        journal: (AutomationStep, String) -> Unit,
    ) {
        badgeBaselines.clear()
        pendingOrderReport = null
        MaintenanceBadgeSnapshots.clear(task.taskId)
        if (!task.expiresAt.isAfter(now())) throw ExecutorFailure("TASK_EXPIRED", "Task has expired")
        val runDeadline = elapsedMs() + task.maxRunSeconds * 1_000L
        // Fresh runs start from the target root page; resumed runs keep their
        // verified in-page state (ResumeValidator guards those separately).
        if (startAfterIndex < 0) normalizeToRootPage(task, runDeadline, control)
        var lastCompleted: AutomationStep? = task.steps.getOrNull(startAfterIndex)
        var lastCompletedIndex = startAfterIndex
        for ((index, step) in task.steps.withIndex()) {
            if (index <= startAfterIndex) continue
            ensureWithinTaskDeadline(task, runDeadline)
            throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
            journal(step, "STARTED")
            var stepControl = StepControl.CONTINUE
            try {
                val remaining = (runDeadline - elapsedMs()).coerceAtLeast(1L)
                    withTimeout(minOf(step.timeoutMs, remaining)) {
                    ui.ensureReady(task.targetPackage)
                    stepControl = executeStep(
                        task,
                        step,
                        minOf(runDeadline, elapsedMs() + step.timeoutMs),
                        control,
                        lastCompleted,
                        lastCompletedIndex,
                    )
                }
            } catch (paused: TaskPausedException) {
                throw TaskPausedException(lastCompleted?.stepId, lastCompletedIndex, paused.message)
            } catch (failure: ExecutorFailure) {
                ui.log(LogLevel.ERROR, failure.code)
                throw failure
            } catch (failure: TimeoutCancellationException) {
                ui.log(LogLevel.ERROR, "STEP_TIMEOUT")
                throw ExecutorFailure("STEP_TIMEOUT", "Step ${step.stepId} exceeded its timeout", failure)
            } catch (failure: Exception) {
                ui.log(LogLevel.ERROR, "STEP_EXECUTION_FAILED")
                throw ExecutorFailure("STEP_EXECUTION_FAILED", "Step ${step.stepId} failed safely", failure)
            }
            if (stepControl == StepControl.STOP_RECONCILING) return
            journal(step, "SUCCEEDED")
            lastCompleted = step
            lastCompletedIndex = index
            // §5: the collected-order batch report fires immediately after the
            // readOrders step is journaled SUCCEEDED — outside the step's UI
            // timeout, so upload latency can never surface as STEP_TIMEOUT.
            reportPendingOrders(task)
            throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
            if (stepControl == StepControl.STOP_AFTER_SUCCESS) return
        }
    }

    private suspend fun executeStep(
        task: AutomationTask,
        step: AutomationStep,
        runDeadline: Long,
        control: ExecutionControl?,
        lastCompleted: AutomationStep? = null,
        lastCompletedIndex: Int = -1,
    ): StepControl {
        when (step) {
            is AutomationStep.Find -> waitFor(
                task, step.locatorRef, NodeCondition.EXISTS, step.pollInterval(), runDeadline, control,
                lastCompleted, lastCompletedIndex,
            )
            is AutomationStep.Tap -> {
                waitFor(
                    task, step.locatorRef, NodeCondition.EXISTS, step.pollInterval(), runDeadline, control,
                    lastCompleted, lastCompletedIndex,
                )
                throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
                val node = requireNode(task, step.locatorRef)
                // A disabled clickable control must never be tapped, but Douyin gallery
                // cells expose passive (enabled=false, unclickable) marks over
                // gesture-tappable images; those remain legitimate targets.
                if (!node.visible || (node.clickable && !node.enabled)) {
                    throw ExecutorFailure("NODE_NOT_CLICKABLE", "Approved locator is not safely clickable")
                }
                if (step.postconditionLocatorRef != null && matches(task, step.postconditionLocatorRef, NodeCondition.EXISTS)) {
                    throw ExecutorFailure("POSTCONDITION_ALREADY_MET", "Click postcondition was already present")
                }
                if (step.locatorRef in GATED_PUBLISH_LOCATORS && commitGate != null) {
                    // Irreversible submit: durable intent, one tap, then stop the run.
                    commitGate.publishOnce(task, step.locatorRef)
                    return StepControl.STOP_AFTER_SUCCESS
                }
                if (step.locatorRef == GATED_XIANYU_DELETE_CONFIRM) {
                    val gate = destructiveGate
                        ?: throw ExecutorFailure("G3_NOT_ACCEPTED", "Destructive confirm requires the controlled ledger")
                    // The durable ledger owns the post-strike outcome. Stop here even
                    // when that outcome is UNKNOWN so later steps cannot imply success.
                    gate.confirmOnce(task, step.locatorRef)
                    return StepControl.STOP_RECONCILING
                }
                ui.tap(task.targetPackage, step.locatorRef)
                step.postconditionLocatorRef?.let {
                    waitFor(task, it, NodeCondition.EXISTS, step.pollInterval(), runDeadline, control, lastCompleted, lastCompletedIndex)
                }
            }
            is AutomationStep.Input -> {
                waitFor(
                    task, step.locatorRef, NodeCondition.EXISTS, step.pollInterval(), runDeadline, control,
                    lastCompleted, lastCompletedIndex,
                )
                throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
                val node = requireNode(task, step.locatorRef)
                if (!node.visible || !node.enabled) {
                    throw ExecutorFailure("NODE_NOT_EDITABLE", "Approved locator is not safely editable")
                }
                ui.replaceText(task.targetPackage, step.locatorRef, step.value)
                waitForText(task, step.locatorRef, step.value, step.pollInterval(), runDeadline)
            }
            is AutomationStep.TapText -> {
                throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
                tapTextWithScroll(task, step, runDeadline, control, lastCompleted, lastCompletedIndex)
            }
            is AutomationStep.Wait -> waitFor(
                task, step.locatorRef, step.condition, step.pollMs, runDeadline, control,
                lastCompleted, lastCompletedIndex,
            )
            is AutomationStep.Screenshot -> {
                throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
                captureScreenshot(task, step.label)
            }
            is AutomationStep.Assert -> if (!matches(task, step.locatorRef, step.predicate)) {
                throw ExecutorFailure("ASSERTION_FAILED", "UI assertion failed")
            }
            is AutomationStep.Log -> ui.log(step.level, step.messageCode)
            is AutomationStep.TapLayout -> executeTapLayout(
                task, step, runDeadline, control, lastCompleted, lastCompletedIndex,
            )
            is AutomationStep.AssertBadge -> awaitBadgeAssertion(task, step, runDeadline)
            is AutomationStep.ReadOrders -> executeReadOrders(task, step, runDeadline)
            is AutomationStep.TapCardByTitle -> executeTapCardByTitle(
                task, step, runDeadline, control, lastCompleted, lastCompletedIndex,
            )
        }
        return StepControl.CONTINUE
    }

    private enum class StepControl {
        CONTINUE,
        STOP_AFTER_SUCCESS,
        STOP_RECONCILING,
    }

    /**
     * Order-sync slice 1 §5: read the current screen's order rows and parse
     * them. Rows without a parseable order key land in skipped (NO_KEY /
     * AMBIGUOUS_KEY) and never fail the task — short reads and empty lists are
     * successes (0 rows reported). §7 fail-closed: an unverified container
     * locator aborts with LOCATOR_UNVERIFIED before anything is read, leaving
     * zero side effects.
     */
    private suspend fun executeReadOrders(task: AutomationTask, step: AutomationStep.ReadOrders, runDeadline: Long) {
        if (task.targetPackage != TargetLocatorRegistry.XIANYU_PACKAGE) {
            throw ExecutorFailure("TARGET_PACKAGE_REJECTED", "readOrders is approved for xianyu only")
        }
        ui.ensureReady(task.targetPackage)
        if (TargetLocatorRegistry.isUnverifiedLocator(task.targetPackage, step.locatorRef)) {
            throw ExecutorFailure(
                "LOCATOR_UNVERIFIED",
                "Order container locator '${step.locatorRef}' is not device-verified; failing closed",
            )
        }
        // The Flutter order list keeps rendering after the navigation tap lands;
        // poll the container resolution inside the step window with the same
        // semantics as waitFor() above, then fail with LOCATOR_NOT_FOUND. The
        // caller passes runDeadline = min(task deadline, elapsed+step.timeoutMs),
        // which IS this step's retry window. An empty read (container resolved,
        // zero rows) is NOT retried — it is a successful 0-row collection per
        // contract §5.
        var rows: List<List<String>>? = null
        while (rows == null) {
            rows = try {
                ui.readOrderRows(task.targetPackage, step.locatorRef, step.maxRows)
            } catch (failure: ExecutorFailure) {
                if (failure.code != "LOCATOR_NOT_FOUND" || elapsedMs() >= runDeadline) throw failure
                sleep(ORDER_ROW_POLL_MS)
                null
            }
        }
        val collected = mutableListOf<OrderRowSnapshot>()
        val skipped = mutableListOf<SkippedOrderRow>()
        rows.forEachIndexed { index, lines ->
            when (val outcome = OrderRowParser.parse(step.direction, lines)) {
                is OrderRowParseOutcome.Parsed -> collected += outcome.toSnapshot(step.direction, lines)
                is OrderRowParseOutcome.Skipped -> skipped += SkippedOrderRow(index, outcome.reason)
            }
        }
        ui.log(LogLevel.INFO, "ORDERS_READ_${collected.size}")
        if (skipped.isNotEmpty()) ui.log(LogLevel.WARN, "ORDERS_SKIPPED_${skipped.size}")
        pendingOrderReport = PendingOrderReport(step.direction, collected, skipped)
    }

    /** Flushes the readOrders collection to the §5 reporter, exactly once per run. */
    private suspend fun reportPendingOrders(task: AutomationTask) {
        val report = pendingOrderReport ?: return
        pendingOrderReport = null
        orderReporter?.reportOrders(task.taskId, report.direction, report.collected, report.skipped)
    }

    /**
     * Structured coordinate tap on the frozen xianyu maintenance layout. The
     * resolution guard rejects anything but 1080x2400 (fail-safe, no guessing);
     * the destructive confirm actions route through the controlled ledger
     * (one authorization -> one tap -> badge verification), while every other
     * layout click is evidence-screenshotted before and after but never
     * enters the ledger.
     */
    private suspend fun executeTapLayout(
        task: AutomationTask,
        step: AutomationStep.TapLayout,
        runDeadline: Long,
        control: ExecutionControl?,
        lastCompleted: AutomationStep?,
        lastCompletedIndex: Int,
    ) {
        throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
        ensureWithinTaskDeadline(task, runDeadline)
        if (task.targetPackage != TargetLocatorRegistry.XIANYU_PACKAGE) {
            throw ExecutorFailure("TARGET_PACKAGE_REJECTED", "Layout actions are approved for xianyu only")
        }
        ui.ensureReady(task.targetPackage)
        val size = ui.screenSize(task.targetPackage)
            ?: throw ExecutorFailure("LAYOUT_GUARD_REJECTED", "Screen size unavailable; coordinate path fails closed")
        val point = XianyuMaintenanceLayout.resolve(size.first, size.second, step.tab, step.layoutAction, step.cardIndex)
            ?: throw ExecutorFailure(
                "LAYOUT_ACTION_UNMAPPED",
                "Layout ${step.layoutAction} on ${step.tab}#${step.cardIndex} has no guarded coordinate " +
                    "for ${size.first}x${size.second}",
            )
        ui.log(LogLevel.INFO, "LAYOUT_GUARD_PASSED")

        if (step.layoutAction in XianyuMaintenanceLayout.GATED_DESTRUCTIVE_CONFIRM_ACTIONS) {
            // Destructive second strike: stop-and-wait happens inside the ledger
            // (intent -> one authorization); a prior recorded intent only reconciles.
            val gate = destructiveGate
                ?: throw ExecutorFailure("G3_NOT_ACCEPTED", "Destructive confirm requires the controlled ledger")
            val badgeRef = XianyuMaintenanceLayout.badgeLocatorFor(step.layoutAction)
                ?: throw ExecutorFailure("G3_NOT_ACCEPTED", "No badge verification signal for ${step.layoutAction}")
            val baseline = gate.confirmOnce(task, step)
            // Null means a prior intent reconciled: no fresh strike, no valid delta baseline.
            if (baseline != null) badgeBaselines[badgeRef] = baseline
            return
        }

        // First strike / light-risk write: capture the badge baseline of the
        // affected tab, then screenshot-click-screenshot so the coordinate and
        // the resulting UI state are both evidenced.
        XianyuMaintenanceLayout.badgeLocatorFor(step.layoutAction)?.let { badgeRef ->
            XianyuMaintenanceLayout.parseBadge(ui.inspect(task.targetPackage, badgeRef)?.description)
                ?.let { badge ->
                    badgeBaselines.putIfAbsent(badgeRef, badge)
                    MaintenanceBadgeSnapshots.record(task.taskId, badgeRef, badge)
                }
        }
        captureScreenshot(task, layoutEvidenceLabel(step, "before"))
        ui.tapScreenAt(task.targetPackage, point.x, point.y)
        captureScreenshot(task, layoutEvidenceLabel(step, "after"))
    }

    /**
     * W4 maintenance v2 (contract xianyu-anchors-20260915 §1/§2): open the
     * published-list card whose text contains the title fragment, entering the
     * detail page. This is the v2 first strike: the onsale/delisted tab badge
     * is captured while the list tabs are still the live page, because the
     * gated confirm later runs on the detail page where the tabs are gone
     * (the gate resolves its baseline from MaintenanceBadgeSnapshots first).
     * List rendering misses (tab/scrollable/card absent) retry inside the step
     * window; an ambiguous title match fails immediately — a guess tap would
     * risk the wrong listing, zero side effects instead.
     */
    private suspend fun executeTapCardByTitle(
        task: AutomationTask,
        step: AutomationStep.TapCardByTitle,
        runDeadline: Long,
        control: ExecutionControl?,
        lastCompleted: AutomationStep?,
        lastCompletedIndex: Int,
    ) {
        throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
        if (task.targetPackage != TargetLocatorRegistry.XIANYU_PACKAGE) {
            throw ExecutorFailure("TARGET_PACKAGE_REJECTED", "Card title taps are approved for xianyu only")
        }
        ui.ensureReady(task.targetPackage)
        // Best-effort gated-confirm baseline: the tab must be visible for the
        // card search anyway, so a readable badge here is the last chance before
        // the detail page covers the tab strip.
        XianyuMaintenanceLayout.publishedTabLocator(step.tab)?.let { badgeRef ->
            runCatching {
                XianyuMaintenanceLayout.parseBadge(ui.inspect(task.targetPackage, badgeRef)?.description)
            }.getOrNull()?.let { badge ->
                badgeBaselines.putIfAbsent(badgeRef, badge)
                MaintenanceBadgeSnapshots.record(task.taskId, badgeRef, badge)
            }
        }
        val deadline = minOf(runDeadline, elapsedMs() + step.timeoutMs)
        while (true) {
            throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
            // No ensureWithinTaskDeadline here (readOrders pattern): the caller
            // passes runDeadline already capped to this step's window, so the
            // exhausted window must surface as the step failure below, never
            // as a task-wide TASK_TIMEOUT.
            ui.ensureReady(task.targetPackage)
            try {
                ui.tapCardByTitle(task.targetPackage, step.tab, step.titleContains)
                return
            } catch (failure: ExecutorFailure) {
                if (failure.code != "CARD_TITLE_NOT_FOUND" && failure.code != "LIST_TAB_NOT_FOUND" &&
                    failure.code != "SCROLL_CONTAINER_MISSING"
                ) {
                    throw failure
                }
                if (elapsedMs() >= deadline) throw failure
                sleep(CARD_SEARCH_POLL_MS)
            }
        }
    }

    /** Polls a published-goods tab badge until the expected value or delta holds. */
    private suspend fun awaitBadgeAssertion(
        task: AutomationTask,
        step: AutomationStep.AssertBadge,
        runDeadline: Long,
    ) {
        try {
            TargetLocatorRegistry.resolve(task.targetPackage, step.locatorRef)
        } catch (failure: IllegalArgumentException) {
            throw ExecutorFailure("LOCATOR_NOT_APPROVED", "Locator is not approved for this target", failure)
        }
        val deadline = elapsedMs() + step.timeoutMs
        while (true) {
            // The step-scoped badge deadline must surface as the assertion
            // failure itself, not as a task-wide TASK_TIMEOUT, so it is checked
            // before the task deadline guard (same ordering as tapText).
            if (elapsedMs() >= deadline) {
                throw ExecutorFailure(
                    "ASSERTION_FAILED",
                    "Badge '${step.locatorRef}' did not reach the expected value before the step deadline",
                )
            }
            ensureWithinTaskDeadline(task, runDeadline)
            ui.ensureReady(task.targetPackage)
            val parsed = XianyuMaintenanceLayout.parseBadge(ui.inspect(task.targetPackage, step.locatorRef)?.description)
            if (parsed != null) {
                val satisfied = if (step.expectedValue != null) {
                    parsed == step.expectedValue
                } else {
                    val baseline = badgeBaselines[step.locatorRef]
                        ?: throw ExecutorFailure(
                            "BADGE_BASELINE_MISSING",
                            "No in-run badge baseline for '${step.locatorRef}'; delta cannot be verified",
                        )
                    parsed == baseline + requireNotNull(step.expectedDelta)
                }
                if (satisfied) return
            }
            sleep(minOf(200L, step.timeoutMs))
        }
    }

    private suspend fun captureScreenshot(task: AutomationTask, label: String) {
        val evidence = ui.screenshot(task.taskId, label)
        if (evidence.size <= 0L || !SHA256.matches(evidence.sha256) || evidence.path.isBlank()) {
            throw ExecutorFailure("SCREENSHOT_INVALID", "Screenshot evidence is incomplete")
        }
        ui.log(LogLevel.INFO, "SCREENSHOT_CAPTURED")
    }

    private fun layoutEvidenceLabel(step: AutomationStep.TapLayout, stage: String): String {
        // Evidence labels stay stepId-based: the id charset is path-safe, the
        // free-form backup value never reaches a file name.
        return "layout-${step.stepId}-$stage"
    }

    /** Fresh runs recover allowlisted blocking dialogs before bounded BACK/relaunch navigation. */
    private suspend fun normalizeToRootPage(task: AutomationTask, runDeadline: Long, control: ExecutionControl?) {
        NavigationReset(object : NavigationReset.Port {
            override fun atRootPage() = ui.atRootPage(task.targetPackage)
            override fun isTargetForeground() = ui.isTargetForeground(task.targetPackage)
            override suspend fun dismissBlockedDialog() = ui.dismissBlockedDialog(task.targetPackage)
            override suspend fun goBack() = ui.goBack()
            override suspend fun relaunch() = ui.restartTargetApp(task.targetPackage)
            override suspend fun settle(ms: Long) = sleep(ms)
            override fun checkpoint() {
                throwIfControlRequested(control)
                ensureWithinTaskDeadline(task, runDeadline)
            }
            override fun event(code: String) = ui.log(
                if (code.startsWith("NAV_DIALOG_DISMISSED")) LogLevel.INFO else LogLevel.WARN,
                code,
            )
        }).execute()
    }

    /**
     * Conversation-list scrolling (im-live slice 2, gap 3): tapText only matches
     * first-screen nodes, so scroll the visible list forward until the value
     * appears or the bounded scroll budget runs out.
     */
    private suspend fun tapTextWithScroll(
        task: AutomationTask,
        step: AutomationStep.TapText,
        runDeadline: Long,
        control: ExecutionControl?,
        lastCompleted: AutomationStep?,
        lastCompletedIndex: Int,
    ) {
        val deadline = minOf(runDeadline, elapsedMs() + step.timeoutMs)
        var scrolls = 0
        while (true) {
            throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
            // The step-scoped scroll deadline must surface as the tap failure
            // itself, not as a task-wide TASK_TIMEOUT, so it is checked before
            // the task deadline guard (only after a first attempt was made).
            if (scrolls > 0 && elapsedMs() >= deadline) {
                throw ExecutorFailure(
                    "TAP_TEXT_NOT_FOUND",
                    "tapText value '${step.value}' never became visible before the step deadline",
                )
            }
            ensureWithinTaskDeadline(task, runDeadline)
            ui.ensureReady(task.targetPackage)
            try {
                ui.tapText(task.targetPackage, step.value)
                return
            } catch (failure: ExecutorFailure) {
                if (failure.code != "TAP_TEXT_NOT_FOUND") throw failure
                if (scrolls >= TAP_TEXT_MAX_SCROLLS || elapsedMs() >= deadline ||
                    !ui.canScrollTextList(task.targetPackage)
                ) {
                    throw failure
                }
                scrolls += 1
                ui.scrollTextListForward(task.targetPackage)
            }
        }
    }
    private fun requireNode(task: AutomationTask, locatorRef: String): LocalNodeState =
        ui.inspect(task.targetPackage, locatorRef)
            ?: throw ExecutorFailure("LOCATOR_NOT_FOUND", "Approved locator was not found")

    private fun matches(task: AutomationTask, locatorRef: String, condition: NodeCondition): Boolean {
        val node = ui.inspect(task.targetPackage, locatorRef)
        return when (condition) {
            NodeCondition.EXISTS -> node != null && node.visible
            NodeCondition.NOT_EXISTS -> node == null || !node.visible
            NodeCondition.ENABLED -> node?.visible == true && node.enabled
        }
    }

    private suspend fun waitFor(
        task: AutomationTask,
        locatorRef: String,
        condition: NodeCondition,
        pollMs: Long,
        runDeadline: Long,
        control: ExecutionControl? = null,
        lastCompleted: AutomationStep? = null,
        lastCompletedIndex: Int = -1,
    ) {
        while (true) {
            throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
            ensureWithinTaskDeadline(task, runDeadline)
            ui.ensureReady(task.targetPackage)
            if (locatorRef == "xianyu_home_sell" || locatorRef == "xianyu_publish_page" || locatorRef == "xianyu_publish_success") {
                if (ui.inspect(task.targetPackage, "xianyu_draft_discard")?.visible == true) {
                    ui.tap(task.targetPackage, "xianyu_draft_discard")
                }
                if (ui.inspect(task.targetPackage, "xianyu_draft_nosave")?.visible == true) {
                    ui.tap(task.targetPackage, "xianyu_draft_nosave")
                }
                if (ui.inspect(task.targetPackage, "xianyu_publish_blocked_ack")?.visible == true) {
                    ui.tap(task.targetPackage, "xianyu_publish_blocked_ack")
                }
            }
            if ((locatorRef == "xianyu_price" || locatorRef == "xianyu_shipping" || locatorRef == "xianyu_location") &&
                !matches(task, locatorRef, condition)
            ) {
                ui.swipeUp()
            }
            if (matches(task, locatorRef, condition)) return
            sleep(pollMs)
        }
    }

    private suspend fun waitForText(
        task: AutomationTask,
        locatorRef: String,
        expected: String,
        pollMs: Long,
        runDeadline: Long,
    ) {
        while (true) {
            ensureWithinTaskDeadline(task, runDeadline)
            ui.ensureReady(task.targetPackage)
            if (ui.visibleTextContains(expected)) return
            if (locatorRef == "xianyu_price") {
                val typed = PriceKeypad.keys(expected)
                if (typed.isNotEmpty() && ui.visibleTextContains(typed)) return
            }
            val node = ui.inspect(task.targetPackage, locatorRef)
            val actual = node?.text.orEmpty()
            if (FlutterTextCommit.accepted(actual, expected)) return
            if (locatorRef == "xianyu_price" && PriceKeypad.acceptedOnForm(actual, expected)) return
            // Flutter replaces the "描述一下" hint after focus. Missing locator is not success.
            sleep(pollMs)
        }
    }

    private fun ensureWithinTaskDeadline(task: AutomationTask, runDeadline: Long) {
        if (!task.expiresAt.isAfter(now())) throw ExecutorFailure("TASK_EXPIRED", "Task expired during execution")
        if (elapsedMs() >= runDeadline) throw ExecutorFailure("TASK_TIMEOUT", "Task exceeded its local runtime limit")
    }

    private fun throwIfControlRequested(
        control: ExecutionControl?,
        lastCompleted: AutomationStep? = null,
        lastCompletedIndex: Int = -1,
    ) {
        when {
            control == null -> return
            control.cancelRequested -> throw ExecutorFailure("CANCELLED", control.reason ?: "Task was cancelled")
            control.pauseRequested -> throw TaskPausedException(
                lastCompleted?.stepId,
                lastCompletedIndex,
                control.reason,
            )
        }
    }

    private fun AutomationStep.pollInterval() = minOf(200L, timeoutMs)

    private companion object {
        val SHA256 = Regex("^[a-f0-9]{64}$")
        const val TAP_TEXT_MAX_SCROLLS = 10
        const val CARD_SEARCH_POLL_MS = 700L
    }
}
