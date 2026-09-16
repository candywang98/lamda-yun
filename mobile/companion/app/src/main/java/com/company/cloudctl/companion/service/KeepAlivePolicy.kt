package com.company.cloudctl.companion.service

import android.content.Intent

internal object ServiceLaunchPolicy {
    const val ACTION_RESTART_SYNC = "com.company.cloudctl.companion.RESTART_SYNC"
    const val ACTION_QUICKBOOT_POWERON = "android.intent.action.QUICKBOOT_POWERON"

    private val supportedActions = setOf(
        Intent.ACTION_BOOT_COMPLETED,
        Intent.ACTION_MY_PACKAGE_REPLACED,
        Intent.ACTION_USER_UNLOCKED,
        ACTION_QUICKBOOT_POWERON,
        ACTION_RESTART_SYNC,
    )

    fun shouldStart(action: String?, hasBinding: Boolean): Boolean =
        hasBinding && action in supportedActions
}

internal object BatteryOptimizationPolicy {
    fun shouldPrompt(bound: Boolean, ignoring: Boolean): Boolean = bound && !ignoring
}

internal object ForegroundRestartPolicy {
    const val DELAY_MILLIS = 15_000L

    fun shouldSchedule(hasBinding: Boolean): Boolean = hasBinding
}

// ---------------------------------------------------------------------------
// B11 slice: honest startup-outcome classification, user-recovery boundaries,
// and the specialUse foreground-service declaration check. A normal app can
// NOT self-start unconditionally — each trigger maps to an explicit outcome
// (BOOT_OK / LOCKED / KILLED / NEEDS_USER) that stays queryable instead of
// silently retrying.
// ---------------------------------------------------------------------------

/** What woke the startup path. Mirrors ServiceLaunchPolicy.supportedActions. */
enum class StartTrigger { BOOT_COMPLETED, QUICKBOOT_POWERON, USER_UNLOCKED, PACKAGE_REPLACED, RESTART_ALARM }

internal object StartTriggerMapper {
    fun fromAction(action: String?): StartTrigger? = when (action) {
        Intent.ACTION_BOOT_COMPLETED -> StartTrigger.BOOT_COMPLETED
        ServiceLaunchPolicy.ACTION_QUICKBOOT_POWERON -> StartTrigger.QUICKBOOT_POWERON
        Intent.ACTION_USER_UNLOCKED -> StartTrigger.USER_UNLOCKED
        Intent.ACTION_MY_PACKAGE_REPLACED -> StartTrigger.PACKAGE_REPLACED
        ServiceLaunchPolicy.ACTION_RESTART_SYNC -> StartTrigger.RESTART_ALARM
        else -> null
    }
}

/**
 * As-is classification (B11 acceptance): boot / lock / system kill / user
 * force-stop each produce their own outcome. No outcome claims an ordinary
 * app can start itself unconditionally:
 *  - BOOT_OK — a supported broadcast arrived while bound and unlocked.
 *  - LOCKED — service start proceeds, but task execution is withheld until
 *    the user unlocks (USER_UNLOCKED re-triggers and lands in BOOT_OK).
 *  - KILLED — best-effort restart after a system kill / FGS timeout
 *    (START_STICKY or the restart alarm); delivery may be deferred by
 *    Doze/battery restrictions, it is NOT guaranteed.
 *  - NEEDS_USER — no binding, user force-stop (all broadcasts and alarms are
 *    cancelled by the system; only the user can relaunch), permission turned
 *    off, or the platform refused the foreground start. Never auto-recovered.
 */
enum class ServiceStartOutcome { BOOT_OK, LOCKED, KILLED, NEEDS_USER }

object StartupClassifier {
    fun classify(
        trigger: StartTrigger,
        hasBinding: Boolean,
        keyguardLocked: Boolean,
        userStoppedPackage: Boolean = false,
    ): ServiceStartOutcome = when {
        // A force-stopped package never even receives the broadcast; the
        // classification documents why nothing will arrive on its own.
        userStoppedPackage -> ServiceStartOutcome.NEEDS_USER
        !hasBinding -> ServiceStartOutcome.NEEDS_USER
        trigger == StartTrigger.RESTART_ALARM -> ServiceStartOutcome.KILLED
        keyguardLocked -> ServiceStartOutcome.LOCKED
        else -> ServiceStartOutcome.BOOT_OK
    }

    fun explain(outcome: ServiceStartOutcome): String = when (outcome) {
        ServiceStartOutcome.BOOT_OK -> "开机自举成功，服务已按绑定启动"
        ServiceStartOutcome.LOCKED -> "服务已启动但设备处于锁屏，任务执行被挂起，解锁后自动恢复"
        ServiceStartOutcome.KILLED -> "系统杀进程/前台服务超时后的尽力重启，可能被系统延迟，不保证立即送达"
        ServiceStartOutcome.NEEDS_USER -> "需要用户介入（未绑定 / 被 force-stop / 权限被关 / 平台拒绝后台启动），应用不会也无法自动恢复"
    }
}

/**
 * force-stop 或权限被关闭进入 NEEDS_USER 而非自动恢复（B11 任务 3）：
 * 普通应用 force-stop 后广播与闹钟均被系统取消，唯一出路是用户手动
 * 打开；无障碍开关被关同样只能由用户重新打开。策略层禁止对这两类
 * 场景安排任何自动重启。
 */
object UserRecoveryPolicy {
    fun shouldEnterNeedsUser(
        userForceStopped: Boolean,
        accessibilityPermissionOff: Boolean,
        bound: Boolean = true,
    ): Boolean = userForceStopped || accessibilityPermissionOff || !bound

    fun allowsAutoRestart(outcome: ServiceStartOutcome): Boolean =
        outcome != ServiceStartOutcome.NEEDS_USER

    fun recoveryHint(userForceStopped: Boolean, accessibilityPermissionOff: Boolean): String = buildString {
        if (userForceStopped) append("用户 force-stop 后系统取消一切广播与闹钟，请手动打开 App 恢复；")
        if (accessibilityPermissionOff) append("无障碍权限已被关闭，请用户在系统设置中重新启用；")
    }.ifBlank { "无需用户介入" }
}

/**
 * specialUse 前台服务声明核对（B11 任务 2）。现有声明为 specialUse 且带
 * 真实用途子类型——用户授权的 Control API 任务监听与本地执行协调器；
 * 六小时 dataSync 限时与该类型无关，绝不能套用到重启策略上。
 */
object ForegroundServiceDeclarationPolicy {
    const val DECLARED_FGS_TYPE = "specialUse"
    const val DECLARED_SUBTYPE =
        "User-authorized Control API task listener and local execution coordinator"

    /** Only the dataSync FGS type carries the 6h cap; specialUse does not. */
    const val DATA_SYNC_SIX_HOUR_MILLIS = 6 * 3_600_000L

    data class DeclarationCheck(
        val typeMatches: Boolean,
        val subtypeDeclared: Boolean,
        /** Always false for specialUse: the 6h dataSync timeout must not be applied. */
        val appliesDataSyncTimeout: Boolean,
    ) {
        val valid: Boolean get() = typeMatches && subtypeDeclared
    }

    fun verify(declaredType: String?, declaredSubtype: String?): DeclarationCheck = DeclarationCheck(
        typeMatches = declaredType == DECLARED_FGS_TYPE,
        subtypeDeclared = !declaredSubtype.isNullOrBlank(),
        appliesDataSyncTimeout = false,
    )
}
