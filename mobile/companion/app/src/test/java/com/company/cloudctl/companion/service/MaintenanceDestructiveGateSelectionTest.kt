package com.company.cloudctl.companion.service

import com.company.cloudctl.companion.automation.AutomationStep
import com.company.cloudctl.companion.automation.AutomationTask
import com.company.cloudctl.companion.automation.TargetLocatorRegistry
import com.company.cloudctl.companion.automation.XianyuMaintenanceLayout
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class MaintenanceDestructiveGateSelectionTest {
    @Test
    fun semanticDeleteV2BuildsTheProductionGate() {
        assertTrue(
            hasMaintenanceDestructiveConfirm(
                task(AutomationStep.Tap("confirm-delete", 1_000, XianyuMaintenanceCommitGate.DELETE_CONFIRM_LOCATOR, null)),
            ),
        )
    }

    @Test
    fun ordinaryTapDoesNotBuildTheMaintenanceGate() {
        assertFalse(
            hasMaintenanceDestructiveConfirm(
                task(AutomationStep.Tap("cancel", 1_000, "xianyu_manage_cancel", null)),
            ),
        )
    }

    @Test
    fun legacyLayoutConfirmStillBuildsTheMaintenanceGate() {
        assertTrue(
            hasMaintenanceDestructiveConfirm(
                task(
                    AutomationStep.TapLayout(
                        "confirm-delist",
                        1_000,
                        XianyuMaintenanceLayout.Tab.ONSALE,
                        XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELIST,
                        0,
                        null,
                    ),
                ),
            ),
        )
    }

    private fun task(step: AutomationStep) = AutomationTask(
        taskId = "task-maintenance-gate",
        deviceId = "device-1",
        targetPackage = TargetLocatorRegistry.XIANYU_PACKAGE,
        issuedAt = Instant.parse("2026-09-16T00:00:00Z"),
        expiresAt = Instant.parse("2099-01-01T00:00:00Z"),
        maxRunSeconds = 60,
        steps = listOf(step),
    )
}
