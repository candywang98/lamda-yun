package com.company.cloudctl.companion.service

import android.app.KeyguardManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import java.util.UUID

/**
 * B11 slice (fleet-identity/v1@20260916.1 §2 bootId): every supported startup
 * trigger is classified into an honest outcome (BOOT_OK / LOCKED / KILLED /
 * NEEDS_USER), recorded to a queryable store, and a detected OS reboot
 * invalidates any write grant minted before it — the business cursor
 * (checkpoints) survives, the old session does not.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val trigger = StartTriggerMapper.fromAction(intent.action) ?: return
        StartupCoordinator(BootSessionStore(context), BootOutcomeStore(context)).onStartup(
            trigger = trigger,
            hasBinding = CompanionServiceStarter.hasBinding(context),
            keyguardLocked = {
                context.getSystemService(KeyguardManager::class.java)?.isKeyguardLocked == true
            },
            start = { CompanionServiceStarter.tryStartIfBound(context) },
        )
    }
}

/** One OS boot session: stable bootId plus a monotonic epoch per reboot. */
data class BootSession(
    val bootId: String,
    val startEpoch: Long,
    val rebooted: Boolean,
    val previousBootId: String?,
)

/**
 * Persists the boot session marker. Reboot detection uses the elapsed-realtime
 * clock, which is monotonic within one boot and resets to a small value on the
 * next: observing a value SMALLER than the last persisted one means the
 * device rebooted since our previous observation.
 */
internal class BootSessionStore(
    context: Context,
    private val elapsedRealtime: () -> Long = { android.os.SystemClock.elapsedRealtime() },
    private val newBootId: () -> String = { UUID.randomUUID().toString() },
) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    fun observeBoot(): BootSession {
        val storedBootId = preferences.getString(KEY_BOOT_ID, null)
        val storedEpoch = preferences.getLong(KEY_START_EPOCH, 0L)
        val storedElapsed = preferences.getLong(KEY_LAST_ELAPSED, Long.MIN_VALUE)
        val currentElapsed = elapsedRealtime()
        val rebooted = storedBootId != null && storedElapsed != Long.MIN_VALUE && currentElapsed < storedElapsed
        val bootId = if (storedBootId == null || rebooted) newBootId() else storedBootId!!
        val epoch = if (rebooted) storedEpoch + 1L else storedEpoch
        preferences.edit()
            .putString(KEY_BOOT_ID, bootId)
            .putLong(KEY_START_EPOCH, epoch)
            .putLong(KEY_LAST_ELAPSED, currentElapsed)
            .apply()
        return BootSession(
            bootId = bootId,
            startEpoch = epoch,
            rebooted = rebooted,
            previousBootId = storedBootId?.takeIf { rebooted },
        )
    }

    /** Read-only view of the last observed session, without mutating state. */
    fun peek(): BootSession? {
        val bootId = preferences.getString(KEY_BOOT_ID, null) ?: return null
        return BootSession(
            bootId = bootId,
            startEpoch = preferences.getLong(KEY_START_EPOCH, 0L),
            rebooted = false,
            previousBootId = null,
        )
    }

    private companion object {
        const val PREFERENCES = "cloudctl_boot_session"
        const val KEY_BOOT_ID = "boot_id"
        const val KEY_START_EPOCH = "start_epoch"
        const val KEY_LAST_ELAPSED = "last_elapsed"
    }
}

/** Last startup outcome, queryable so the UI can explain why we are (not) running. */
data class BootOutcomeSnapshot(
    val outcome: ServiceStartOutcome,
    val detailCode: String,
    val explanation: String,
    val trigger: StartTrigger,
    val bootId: String,
    val startEpoch: Long,
    val recordedAtEpochMillis: Long,
)

internal class BootOutcomeStore(
    context: Context,
    private val nowMillis: () -> Long = { System.currentTimeMillis() },
) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    fun record(
        outcome: ServiceStartOutcome,
        detailCode: String,
        trigger: StartTrigger,
        session: BootSession,
    ): BootOutcomeSnapshot = BootOutcomeSnapshot(
        outcome = outcome,
        detailCode = detailCode,
        explanation = StartupClassifier.explain(outcome),
        trigger = trigger,
        bootId = session.bootId,
        startEpoch = session.startEpoch,
        recordedAtEpochMillis = nowMillis(),
    ).also { snapshot ->
        preferences.edit()
            .putString(KEY_OUTCOME, snapshot.outcome.name)
            .putString(KEY_DETAIL, snapshot.detailCode)
            .putString(KEY_TRIGGER, snapshot.trigger.name)
            .putString(KEY_BOOT_ID, snapshot.bootId)
            .putLong(KEY_START_EPOCH, snapshot.startEpoch)
            .putLong(KEY_RECORDED_AT, snapshot.recordedAtEpochMillis)
            .apply()
    }

    fun snapshot(): BootOutcomeSnapshot? {
        val outcomeName = preferences.getString(KEY_OUTCOME, null) ?: return null
        val outcome = runCatching { ServiceStartOutcome.valueOf(outcomeName) }
            .getOrElse { return null }
        val triggerName = preferences.getString(KEY_TRIGGER, null) ?: return null
        val trigger = runCatching { StartTrigger.valueOf(triggerName) }.getOrElse { return null }
        return BootOutcomeSnapshot(
            outcome = outcome,
            detailCode = preferences.getString(KEY_DETAIL, "").orEmpty(),
            explanation = StartupClassifier.explain(outcome),
            trigger = trigger,
            bootId = preferences.getString(KEY_BOOT_ID, "").orEmpty(),
            startEpoch = preferences.getLong(KEY_START_EPOCH, 0L),
            recordedAtEpochMillis = preferences.getLong(KEY_RECORDED_AT, 0L),
        )
    }

    private companion object {
        const val PREFERENCES = "cloudctl_boot_outcome"
        const val KEY_OUTCOME = "outcome"
        const val KEY_DETAIL = "detail"
        const val KEY_TRIGGER = "trigger"
        const val KEY_BOOT_ID = "boot_id"
        const val KEY_START_EPOCH = "start_epoch"
        const val KEY_RECORDED_AT = "recorded_at"
    }
}

/** A write grant as persisted before a potential reboot (B10 fencing minted it in-process). */
data class PersistedWriteGrant(
    val bootId: String,
    val sessionEpoch: Long,
    val taskId: String? = null,
)

sealed interface WriteAuthorizationVerdict {
    data object Valid : WriteAuthorizationVerdict
    data class Invalid(
        val reason: InvalidReason,
        /** Reboots never drop the business cursor — checkpoints survive; only the grant dies. */
        val businessCursorPreserved: Boolean = true,
    ) : WriteAuthorizationVerdict
}

enum class InvalidReason { NO_GRANT, REBOOTED_SINCE_GRANT, EPOCH_SUPERSEDED }

/**
 * 重启后保留业务游标但旧写授权无效（B11 任务 3）：任何在旧 boot 会话内
 * 持久化的写授权（bootId / startEpoch 不再匹配）一律判 Invalid，必须走
 * 新的领取与心跳边界重铸（B10 DeviceArbiter 的 fencing token 本就随进程
 * 消亡；本策略覆盖跨重启的持久化授权判断）。force-stop / 权限关闭类
 * NEEDS_USER 场景同样不会在这里被"自动恢复"。
 */
object WriteAuthorizationPolicy {
    fun evaluate(grant: PersistedWriteGrant?, current: BootSession): WriteAuthorizationVerdict = when {
        grant == null -> WriteAuthorizationVerdict.Invalid(InvalidReason.NO_GRANT)
        grant.bootId != current.bootId ->
            WriteAuthorizationVerdict.Invalid(InvalidReason.REBOOTED_SINCE_GRANT)
        grant.sessionEpoch != current.startEpoch ->
            WriteAuthorizationVerdict.Invalid(InvalidReason.EPOCH_SUPERSEDED)
        else -> WriteAuthorizationVerdict.Valid
    }
}

internal class StartupCoordinator(
    private val sessionStore: BootSessionStore,
    private val outcomeStore: BootOutcomeStore,
) {
    /**
     * Classify, start (unless NEEDS_USER), and record. A platform refusal
     * (start restrictions) degrades the outcome to NEEDS_USER instead of
     * crashing or silently retrying.
     */
    fun onStartup(
        trigger: StartTrigger,
        hasBinding: Boolean,
        keyguardLocked: () -> Boolean,
        start: () -> ServiceStartAttempt,
        userStoppedPackage: Boolean = false,
    ): BootOutcomeSnapshot {
        val session = sessionStore.observeBoot()
        val outcome = StartupClassifier.classify(
            trigger = trigger,
            hasBinding = hasBinding,
            keyguardLocked = keyguardLocked(),
            userStoppedPackage = userStoppedPackage,
        )
        if (!UserRecoveryPolicy.allowsAutoRestart(outcome)) {
            return outcomeStore.record(
                ServiceStartOutcome.NEEDS_USER,
                if (userStoppedPackage) "USER_FORCE_STOPPED" else if (!hasBinding) "NOT_BOUND" else outcome.name,
                trigger,
                session,
            )
        }
        return when (val attempt = start()) {
            ServiceStartAttempt.Started ->
                outcomeStore.record(outcome, "STARTED", trigger, session)
            ServiceStartAttempt.NotBound ->
                outcomeStore.record(ServiceStartOutcome.NEEDS_USER, "NOT_BOUND", trigger, session)
            is ServiceStartAttempt.Refused ->
                outcomeStore.record(ServiceStartOutcome.NEEDS_USER, attempt.reasonCode, trigger, session)
        }
    }
}
