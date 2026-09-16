package com.company.cloudctl.companion.service

import android.content.Context
import android.content.Intent
import androidx.test.core.app.ApplicationProvider
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/**
 * B11 验收：开机/锁屏/系统杀/force-stop 的启动结果被分类并持久可查；
 * 重启后业务游标保留但旧写授权（旧 session/bootId）无效化。
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class BootStartupTest {
    private lateinit var context: Context

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
    }

    @AfterTest
    fun clearBinding() {
        context.getSharedPreferences("cloudctl_binding", Context.MODE_PRIVATE).edit().clear().commit()
    }

    // ---- StartupCoordinator：四个场景各有结果且可查询 --------------------

    @Test
    fun `boot while bound records BOOT_OK and starts the service`() {
        writeBinding()
        val coordinator = StartupCoordinator(BootSessionStore(context), BootOutcomeStore(context))
        var started = 0

        val snapshot = coordinator.onStartup(
            trigger = StartTrigger.BOOT_COMPLETED,
            hasBinding = true,
            keyguardLocked = { false },
            start = { started++; ServiceStartAttempt.Started },
        )

        assertSame(ServiceStartOutcome.BOOT_OK, snapshot.outcome)
        assertEquals("STARTED", snapshot.detailCode)
        assertEquals(1, started)
        // 结果可查询（UI 可解释）
        val stored = BootOutcomeStore(context).snapshot()
        assertNotNull(stored)
        assertSame(ServiceStartOutcome.BOOT_OK, stored.outcome)
        assertTrue(stored.explanation.isNotBlank())
        assertTrue(stored.bootId.isNotBlank())
    }

    @Test
    fun `locked boot still starts the service but records LOCKED`() {
        val coordinator = StartupCoordinator(BootSessionStore(context), BootOutcomeStore(context))
        var started = 0

        val snapshot = coordinator.onStartup(
            trigger = StartTrigger.BOOT_COMPLETED,
            hasBinding = true,
            keyguardLocked = { true },
            start = { started++; ServiceStartAttempt.Started },
        )

        assertSame(ServiceStartOutcome.LOCKED, snapshot.outcome)
        assertEquals(1, started)
    }

    @Test
    fun `restart alarm after a system kill records KILLED`() {
        val coordinator = StartupCoordinator(BootSessionStore(context), BootOutcomeStore(context))

        val snapshot = coordinator.onStartup(
            trigger = StartTrigger.RESTART_ALARM,
            hasBinding = true,
            keyguardLocked = { false },
            start = { ServiceStartAttempt.Started },
        )

        assertSame(ServiceStartOutcome.KILLED, snapshot.outcome)
    }

    @Test
    fun `force-stop and unbound never start and record NEEDS_USER`() {
        val coordinator = StartupCoordinator(BootSessionStore(context), BootOutcomeStore(context))
        var started = 0
        val start: () -> ServiceStartAttempt = { started++; ServiceStartAttempt.Started }

        val forced = coordinator.onStartup(
            trigger = StartTrigger.BOOT_COMPLETED,
            hasBinding = true,
            keyguardLocked = { false },
            start = start,
            userStoppedPackage = true,
        )
        assertSame(ServiceStartOutcome.NEEDS_USER, forced.outcome)
        assertEquals("USER_FORCE_STOPPED", forced.detailCode)

        val unbound = coordinator.onStartup(
            trigger = StartTrigger.BOOT_COMPLETED,
            hasBinding = false,
            keyguardLocked = { false },
            start = start,
        )
        assertSame(ServiceStartOutcome.NEEDS_USER, unbound.outcome)
        assertEquals("NOT_BOUND", unbound.detailCode)
        assertEquals(0, started)
    }

    @Test
    fun `platform refusal degrades to NEEDS_USER with the reason recorded`() {
        val coordinator = StartupCoordinator(BootSessionStore(context), BootOutcomeStore(context))

        val snapshot = coordinator.onStartup(
            trigger = StartTrigger.BOOT_COMPLETED,
            hasBinding = true,
            keyguardLocked = { false },
            start = { ServiceStartAttempt.Refused("START_NOT_ALLOWED", null) },
        )

        assertSame(ServiceStartOutcome.NEEDS_USER, snapshot.outcome)
        assertEquals("START_NOT_ALLOWED", snapshot.detailCode)
    }

    // ---- BootReceiver 端到端 -------------------------------------------

    @Test
    fun `receiver end to end starts nothing when unbound and records the outcome`() {
        BootReceiver().onReceive(context, Intent(Intent.ACTION_BOOT_COMPLETED))

        assertNull(shadowOf(context as android.app.Application).nextStartedService)
        val stored = BootOutcomeStore(context).snapshot()
        assertNotNull(stored)
        assertSame(ServiceStartOutcome.NEEDS_USER, stored.outcome)
        assertEquals("NOT_BOUND", stored.detailCode)
        assertSame(StartTrigger.BOOT_COMPLETED, stored.trigger)
    }

    @Test
    fun `receiver end to end starts the sync service when bound`() {
        writeBinding()
        BootReceiver().onReceive(context, Intent(Intent.ACTION_BOOT_COMPLETED))

        val started = shadowOf(context as android.app.Application).nextStartedService
        assertNotNull(started)
        assertEquals(CompanionSyncService::class.java.name, started.component?.className)
        assertSame(ServiceStartOutcome.BOOT_OK, BootOutcomeStore(context).snapshot()?.outcome)
    }

    @Test
    fun `receiver ignores unsupported actions entirely`() {
        BootReceiver().onReceive(context, Intent("android.intent.action.USB_STATE"))
        assertNull(BootOutcomeStore(context).snapshot())
        assertNull(shadowOf(context as android.app.Application).nextStartedService)
    }

    // ---- BootSessionStore：重启检测与旧写授权无效化 ----------------------

    @Test
    fun `same boot keeps a stable bootId and epoch`() {
        val store = BootSessionStore(context, elapsedRealtime = { 500_000L })
        val first = store.observeBoot()
        val second = store.observeBoot()

        assertFalse(first.rebooted)
        assertEquals(first.bootId, second.bootId)
        assertEquals(first.startEpoch, second.startEpoch)
        assertFalse(second.rebooted)
        assertNull(second.previousBootId)
        assertEquals(first.bootId, store.peek()?.bootId)
    }

    @Test
    fun `elapsed clock going backwards means a reboot with a fresh bootId`() {
        var elapsed = 600_000L
        val store = BootSessionStore(context, elapsedRealtime = { elapsed })
        val before = store.observeBoot()

        elapsed = 2_000L // uptime reset → new OS boot
        val after = store.observeBoot()

        assertTrue(after.rebooted)
        assertNotEquals(before.bootId, after.bootId)
        assertEquals(before.startEpoch + 1L, after.startEpoch)
        assertEquals(before.bootId, after.previousBootId)
    }

    @Test
    fun `grant minted before the reboot is invalid but the business cursor survives`() {
        var elapsed = 900_000L
        val store = BootSessionStore(context, elapsedRealtime = { elapsed })
        val beforeReboot = store.observeBoot()
        val oldGrant = PersistedWriteGrant(bootId = beforeReboot.bootId, sessionEpoch = beforeReboot.startEpoch)
        assertEquals(WriteAuthorizationVerdict.Valid, WriteAuthorizationPolicy.evaluate(oldGrant, beforeReboot))

        elapsed = 1_000L
        val afterReboot = store.observeBoot()

        val verdict = WriteAuthorizationPolicy.evaluate(oldGrant, afterReboot) as WriteAuthorizationVerdict.Invalid
        assertEquals(InvalidReason.REBOOTED_SINCE_GRANT, verdict.reason)
        // 重启保留业务游标：只有写授权失效，检查点语义不受影响。
        assertTrue(verdict.businessCursorPreserved)
    }

    @Test
    fun `write authorization verdicts cover epoch supersede and missing grant`() {
        val session = BootSession(bootId = "boot-1", startEpoch = 3L, rebooted = false, previousBootId = null)
        assertEquals(
            WriteAuthorizationVerdict.Invalid(InvalidReason.NO_GRANT),
            WriteAuthorizationPolicy.evaluate(null, session),
        )
        assertEquals(
            InvalidReason.EPOCH_SUPERSEDED,
            (WriteAuthorizationPolicy.evaluate(
                PersistedWriteGrant(bootId = "boot-1", sessionEpoch = 2L),
                session,
            ) as WriteAuthorizationVerdict.Invalid).reason,
        )
    }

    private fun writeBinding() {
        context.getSharedPreferences("cloudctl_binding", Context.MODE_PRIVATE)
            .edit()
            .putString("binding", """{"cloudUrl":"https://cloud.example"}""")
            .commit()
    }
}
