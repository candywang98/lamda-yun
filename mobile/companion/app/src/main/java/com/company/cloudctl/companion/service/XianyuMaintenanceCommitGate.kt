package com.company.cloudctl.companion.service

import com.company.cloudctl.companion.automation.AutomationStep
import com.company.cloudctl.companion.automation.AutomationTask
import com.company.cloudctl.companion.automation.ControlledActionIdentity
import com.company.cloudctl.companion.automation.DestructiveClickGate
import com.company.cloudctl.companion.automation.ExecutorFailure
import com.company.cloudctl.companion.automation.LocalAutomationUi
import com.company.cloudctl.companion.automation.MaintenanceBadgeSnapshots
import com.company.cloudctl.companion.automation.LogLevel
import com.company.cloudctl.companion.automation.TargetLocatorRegistry
import com.company.cloudctl.companion.automation.XianyuMaintenanceLayout
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import org.json.JSONObject

/**
 * One gated destructive confirm for the xianyu maintenance steps task
 * (contract xianyu-maintenance-anchors-20260915). Covers only the destructive
 * second strike — the delist/delete confirm-dialog 确定 tap:
 *
 * intent -> one server authorization -> one coordinate tapOnce (dispatchGesture
 * only) -> badge verification (在卖/已下架 N-1) + screenshot evidence -> outcome.
 *
 * Never interprets tap completion as platform success: an unconfirmed badge
 * verification is reported UNKNOWN and never retried; a prior recorded intent
 * only ever reconciles. First strikes (··· menu, 删除 button, 一键擦亮) stay
 * outside this ledger — the executor screenshots them instead.
 */
class XianyuMaintenanceCommitGate(
    private val executor: ControlledActionExecutor,
    private val ui: LocalAutomationUi,
) : DestructiveClickGate {

    override suspend fun confirmOnce(task: AutomationTask, step: AutomationStep.TapLayout): Int? {
        if (task.targetPackage != TargetLocatorRegistry.XIANYU_PACKAGE) {
            throw ExecutorFailure("G3_NOT_ACCEPTED", "Maintenance confirms are approved for xianyu only")
        }
        val badgeRef: String
        val actionId: String
        when (step.layoutAction) {
            XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELIST -> {
                badgeRef = BADGE_ONSALE // 下架成功 ⇒ 在卖 N-1
                actionId = ACTION_CONFIRM_DELIST  // frozen server contract (mobile_actions XIANYU_MAINTENANCE_SHAPES action_id)
            }
            XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELETE -> {
                badgeRef = BADGE_DELISTED // 删除成功 ⇒ 已下架 N-1
                actionId = ACTION_CONFIRM_DELETE
            }
            else -> throw ExecutorFailure("G3_NOT_ACCEPTED", "Layout action is not a gated confirm")
        }
        TargetLocatorRegistry.resolve(task.targetPackage, badgeRef)
        val payload = JSONObject(
            requireNotNull(executor.persistedPayload(task.taskId)) { "Missing persisted steps task" },
        )
        val identity = ControlledActionIdentity.fromMaintenanceStepsPayload(payload, actionId)
        // Recover before touching UI: a recorded intent can never become a fresh strike.
        if (executor.hasRecordedAction(identity.actionKey)) {
            executor.reconcile(identity.actionKey)
            return null
        }
        currentCoroutineContext().ensureActive()
        ui.ensureReady(task.targetPackage)
        val size = ui.screenSize(task.targetPackage)
            ?: throw ExecutorFailure("LAYOUT_GUARD_REJECTED", "Screen size unavailable; coordinate path fails closed")
        val point = XianyuMaintenanceLayout.resolve(size.first, size.second, step.tab, step.layoutAction, step.cardIndex)
            ?: throw ExecutorFailure(
                "LAYOUT_ACTION_UNMAPPED",
                "Confirm ${step.layoutAction} has no guarded coordinate for ${size.first}x${size.second}",
            )
        // The centered confirm dialog covers the tab bar from the semantics tree
        // (device-verified: BADGE_UNREADABLE with the delete dialog open), so the
        // authoritative baseline is the first-strike snapshot; a live read only
        // applies when no dialog has covered the tabs yet. On the v2 title path
        // the confirm runs on the detail page where the tabs are structurally
        // gone — a missing baseline degrades to UNKNOWN (operator verifies with
        // platformItemId evidence, P09 delete precedent) instead of blocking.
        val v2TitlePath = payload.optString("commandType").endsWith(".steps.v2")
        val baseline = MaintenanceBadgeSnapshots.take(task.taskId, badgeRef)
            ?: XianyuMaintenanceLayout.parseBadge(ui.inspect(task.targetPackage, badgeRef)?.description)
            ?: if (v2TitlePath) {
                ui.log(LogLevel.WARN, "GATED_BADGE_UNKNOWN")
                null
            } else {
                throw ExecutorFailure("BADGE_UNREADABLE", "Verification badge '$badgeRef' is unreadable; confirm blocked")
            }
        // Device-verified: the delisted tab never carries a numeric badge, so the
        // precondition only guards badge-delta verifications (delist). Delete
        // verifies through the dialog-dismissal signal instead.
        if (baseline != null && step.layoutAction == XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELIST && baseline <= 0) {
            throw ExecutorFailure("BADGE_PRECONDITION_INVALID", "Badge '$badgeRef' has nothing to remove")
        }
        val before = evidence(task.taskId, identity.actionKey, "before")
        ui.log(LogLevel.INFO, "GATED_DESTRUCTIVE_INTENT")
        executor.executeStepsCommit(
            taskId = task.taskId,
            beforeEvidence = before,
            timeoutMs = 40_000,
            identity = identity,
            effect = {
                currentCoroutineContext().ensureActive()
                ui.ensureReady(task.targetPackage)
                // One dispatchGesture coordinate tap only; no fallback, no retry.
                ui.tapScreenAt(task.targetPackage, point.x, point.y)
            },
            postconditionEvidence = {
                if (baseline == null) {
                    // v2 degraded verification: capture operator evidence only —
                    // returning null keeps the commit UNKNOWN (no machine APPLIED).
                    evidence(task.taskId, identity.actionKey, "after")
                    null
                } else {
                    var reference: String? = null
                    for (attempt in 0 until BADGE_POLL_ATTEMPTS) {
                        currentCoroutineContext().ensureActive()
                        ui.ensureReady(task.targetPackage)
                        val value = XianyuMaintenanceLayout.parseBadge(
                            ui.inspect(task.targetPackage, badgeRef)?.description,
                        )
                        if (value == baseline - 1) {
                            reference = evidence(task.taskId, identity.actionKey, "after")
                            require(reference != before) { "Postcondition screenshot did not change" }
                            break
                        }
                        delay(BADGE_POLL_INTERVAL_MS)
                    }
                    reference
                }
            },
        )
        return baseline
    }

    override suspend fun confirmOnce(task: AutomationTask, locatorRef: String): Int? {
        if (task.targetPackage != TargetLocatorRegistry.XIANYU_PACKAGE ||
            locatorRef != DELETE_CONFIRM_LOCATOR
        ) {
            throw ExecutorFailure("G3_NOT_ACCEPTED", "Semantic maintenance confirm is not approved")
        }
        val payload = JSONObject(
            requireNotNull(executor.persistedPayload(task.taskId)) { "Missing persisted steps task" },
        )
        require(payload.optString("commandType") == "xianyu.delete_delisted.steps.v2") {
            "Semantic delete confirm is restricted to delete-delisted v2"
        }
        val identity = ControlledActionIdentity.fromMaintenanceStepsPayload(payload, ACTION_CONFIRM_DELETE)
        if (executor.hasRecordedAction(identity.actionKey)) {
            executor.reconcile(identity.actionKey)
            return null
        }
        currentCoroutineContext().ensureActive()
        ui.ensureReady(task.targetPackage)
        val confirm = ui.inspect(task.targetPackage, locatorRef)
            ?: throw ExecutorFailure("LOCATOR_NOT_FOUND", "Guarded delete confirmation is not present")
        if (!confirm.visible || !confirm.enabled) {
            throw ExecutorFailure("NODE_NOT_CLICKABLE", "Guarded delete confirmation is not safely clickable")
        }
        val before = evidence(task.taskId, identity.actionKey, "before")
        ui.log(LogLevel.INFO, "GATED_DESTRUCTIVE_INTENT")
        executor.executeStepsCommit(
            taskId = task.taskId,
            beforeEvidence = before,
            timeoutMs = 40_000,
            identity = identity,
            effect = {
                currentCoroutineContext().ensureActive()
                ui.ensureReady(task.targetPackage)
                // One semantic dispatchGesture only; no fallback and no retry.
                ui.tapOnce(task.targetPackage, locatorRef)
            },
            postconditionEvidence = {
                // The detail dialog has no trustworthy badge. Preserve UNKNOWN
                // until the operator reconciles against the delisted list.
                evidence(task.taskId, identity.actionKey, "after")
                null
            },
        )
        return null
    }

    private suspend fun evidence(taskId: String, actionKey: String, stage: String): String {
        val screenshot = ui.screenshot(taskId, "$actionKey-$stage")
        require(screenshot.size > 0 && screenshot.path.isNotBlank() &&
            Regex("[a-f0-9]{64}").matches(screenshot.sha256)) { "Invalid commit evidence" }
        return "sha256:${screenshot.sha256}"
    }

    companion object {
        const val BADGE_ONSALE = "xianyu_pub_tab_onsale"
        const val BADGE_DELISTED = "xianyu_pub_tab_delisted"
        const val ACTION_CONFIRM_DELIST = "confirm-delist"
        const val ACTION_CONFIRM_DELETE = "confirm-delete"
        const val DELETE_CONFIRM_LOCATOR = "xianyu_delete_confirm"
        private const val BADGE_POLL_ATTEMPTS = 24
        private const val BADGE_POLL_INTERVAL_MS = 250L
    }
}
