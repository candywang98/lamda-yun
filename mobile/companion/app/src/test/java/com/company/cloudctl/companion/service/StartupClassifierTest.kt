package com.company.cloudctl.companion.service

import android.content.Intent
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * B11 验收：开机/锁屏/系统杀进程/用户 force-stop 分别有结果
 * （BOOT_OK / LOCKED / KILLED / NEEDS_USER），不声称普通 App 能无条件自启。
 */
class StartupClassifierTest {
    @Test
    fun `trigger mapper mirrors the supported launch actions`() {
        assertEquals(StartTrigger.BOOT_COMPLETED, StartTriggerMapper.fromAction(Intent.ACTION_BOOT_COMPLETED))
        assertEquals(StartTrigger.QUICKBOOT_POWERON, StartTriggerMapper.fromAction(ServiceLaunchPolicy.ACTION_QUICKBOOT_POWERON))
        assertEquals(StartTrigger.USER_UNLOCKED, StartTriggerMapper.fromAction(Intent.ACTION_USER_UNLOCKED))
        assertEquals(StartTrigger.PACKAGE_REPLACED, StartTriggerMapper.fromAction(Intent.ACTION_MY_PACKAGE_REPLACED))
        assertEquals(StartTrigger.RESTART_ALARM, StartTriggerMapper.fromAction(ServiceLaunchPolicy.ACTION_RESTART_SYNC))
        assertNull(StartTriggerMapper.fromAction("android.intent.action.USB_STATE"))
        assertNull(StartTriggerMapper.fromAction(null))
    }

    @Test
    fun `boot while bound and unlocked is BOOT_OK`() {
        assertEquals(
            ServiceStartOutcome.BOOT_OK,
            StartupClassifier.classify(StartTrigger.BOOT_COMPLETED, hasBinding = true, keyguardLocked = false),
        )
        assertEquals(
            ServiceStartOutcome.BOOT_OK,
            StartupClassifier.classify(StartTrigger.USER_UNLOCKED, hasBinding = true, keyguardLocked = false),
        )
    }

    @Test
    fun `boot with keyguard locked is LOCKED not failed`() {
        assertEquals(
            ServiceStartOutcome.LOCKED,
            StartupClassifier.classify(StartTrigger.BOOT_COMPLETED, hasBinding = true, keyguardLocked = true),
        )
    }

    @Test
    fun `restart after a system kill is KILLED and honestly best-effort`() {
        assertEquals(
            ServiceStartOutcome.KILLED,
            StartupClassifier.classify(StartTrigger.RESTART_ALARM, hasBinding = true, keyguardLocked = false),
        )
        assertTrue(StartupClassifier.explain(ServiceStartOutcome.KILLED).contains("不保证"))
    }

    @Test
    fun `force-stop and missing binding are NEEDS_USER for every trigger`() {
        for (trigger in StartTrigger.entries) {
            assertEquals(
                ServiceStartOutcome.NEEDS_USER,
                StartupClassifier.classify(trigger, hasBinding = true, keyguardLocked = false, userStoppedPackage = true),
            )
        }
        assertEquals(
            ServiceStartOutcome.NEEDS_USER,
            StartupClassifier.classify(StartTrigger.BOOT_COMPLETED, hasBinding = false, keyguardLocked = false),
        )
    }

    @Test
    fun `needs user outcomes never auto-restart`() {
        for (outcome in ServiceStartOutcome.entries) {
            assertEquals(outcome != ServiceStartOutcome.NEEDS_USER, UserRecoveryPolicy.allowsAutoRestart(outcome))
        }
    }

    @Test
    fun `force-stop or permission off enters NEEDS_USER instead of auto recovery`() {
        assertTrue(UserRecoveryPolicy.shouldEnterNeedsUser(userForceStopped = true, accessibilityPermissionOff = false))
        assertTrue(UserRecoveryPolicy.shouldEnterNeedsUser(userForceStopped = false, accessibilityPermissionOff = true))
        assertFalse(UserRecoveryPolicy.shouldEnterNeedsUser(userForceStopped = false, accessibilityPermissionOff = false))
        assertTrue(UserRecoveryPolicy.shouldEnterNeedsUser(userForceStopped = false, accessibilityPermissionOff = false, bound = false))
        assertTrue(UserRecoveryPolicy.recoveryHint(true, true).contains("force-stop"))
        assertTrue(UserRecoveryPolicy.recoveryHint(true, true).contains("无障碍"))
        assertEquals("无需用户介入", UserRecoveryPolicy.recoveryHint(false, false))
    }

    @Test
    fun `specialUse declaration is kept and the dataSync six hour cap is not applied`() {
        val check = ForegroundServiceDeclarationPolicy.verify(
            ForegroundServiceDeclarationPolicy.DECLARED_FGS_TYPE,
            ForegroundServiceDeclarationPolicy.DECLARED_SUBTYPE,
        )
        assertTrue(check.valid)
        assertTrue(check.typeMatches)
        assertTrue(check.subtypeDeclared)
        // specialUse 不带 dataSync 的六小时限制，重启策略绝不套用该上限。
        assertFalse(check.appliesDataSyncTimeout)
        assertEquals(6 * 3_600_000L, ForegroundServiceDeclarationPolicy.DATA_SYNC_SIX_HOUR_MILLIS)

        assertFalse(ForegroundServiceDeclarationPolicy.verify("dataSync", "sync").valid)
        assertFalse(ForegroundServiceDeclarationPolicy.verify("specialUse", null).valid)
        assertFalse(ForegroundServiceDeclarationPolicy.verify("specialUse", "  ").valid)
        assertFalse(ForegroundServiceDeclarationPolicy.verify(null, null).valid)
    }
}
