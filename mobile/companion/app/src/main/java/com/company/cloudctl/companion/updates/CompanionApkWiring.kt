package com.company.cloudctl.companion.updates

import org.json.JSONObject
import java.util.concurrent.atomic.AtomicInteger

/**
 * WIRE2 (fleet-first-20260916.1): the service-side glue between the U11
 * coordinator and the companion's real infrastructure.
 *
 * Everything here is deliberately Android-free: every dependency is injected
 * as a function so the wiring stays unit-testable on the plain JVM.
 * [CompanionSyncService] supplies the AutomationStore-backed lambdas and the
 * claim-intake lever; the network port is [company.cloudctl.companion.network.
 * CloudTaskClient] (now an [ApkReleaseClient]) and the framework bridges live
 * in [ApkInstallReceiver.kt].
 */

/**
 * [ApkInstallGate] over AutomationStore-style signals (U11 task requirement 3):
 *
 * - `hasUnfinishedTaskRows` maps `AutomationStore.hasUnfinishedTaskRows()`
 *   directly (ANY un-finished inbox row, including the blocked rows that own
 *   nothing for the claim loop);
 * - `hasPendingCriticalReports` is true while the event outbox has due rows
 *   or the control-ack outbox is non-empty (U11's suggested mapping);
 * - `suspendClaiming` only ever SUSPENDS claim intake — it never stops, kills
 *   or force-stops any service. Nested suspensions are reference counted so
 *   the lever flips back exactly when the last one closes.
 */
class CompanionApkInstallGate(
    private val unfinishedTaskRows: () -> Boolean,
    private val pendingCriticalReports: () -> Boolean,
    private val suspendClaim: () -> Unit,
    private val resumeClaim: () -> Unit,
) : ApkInstallGate {
    private val openSuspensions = AtomicInteger(0)

    override fun hasUnfinishedTaskRows(): Boolean = unfinishedTaskRows()

    override fun hasPendingCriticalReports(): Boolean = pendingCriticalReports()

    override fun suspendClaiming(): ApkClaimSuspension {
        suspendClaim()
        val ticket = COUNTER.incrementAndGet()
        return object : ApkClaimSuspension {
            override val id: String = "apk-install-claim-$ticket"

            override fun close() {
                if (openSuspensions.decrementAndGet() <= 0) resumeClaim()
            }
        }.also { openSuspensions.incrementAndGet() }
    }

    private companion object {
        val COUNTER = AtomicInteger(0)
    }
}

/**
 * Serialized driver around [ApkUpdateCoordinator] for the sync service.
 *
 * The coordinator is not internally thread-safe: poll/prepareInstall run on
 * the IO dispatcher while PackageInstaller statuses arrive on the broadcast
 * (main) thread via [ApkInstallStatusBus]. Every entry point funnels through
 * one monitor so a status delivery can never interleave with a poll's
 * read-modify-write of the ledger.
 *
 * Receipt delivery (network) deliberately does NOT happen on the status path
 * — it stays on the caller's dispatcher (tick / [onReconnected], both invoked
 * on IO by the service).
 */
class CompanionApkUpdateDriver(private val coordinator: ApkUpdateCoordinator) {
    private val lock = Any()
    private var recoveredAfterRestart = false

    data class TickReport(
        /** Receipts minted by the once-per-process reboot reconciliation. */
        val recoveryReceipts: List<ApkInstallReceipt>,
        val verdict: ApkVerdict,
        val decision: ApkInstallDecision,
        /** Receipts successfully handed upstream during this tick. */
        val deliveredReceipts: List<ApkInstallReceipt>,
    )

    /** One sync-cycle tick: recovery (first only) -> poll -> install window -> receipt drain. */
    fun tick(): TickReport {
        synchronized(lock) {
            val recovery = if (!recoveredAfterRestart) {
                recoveredAfterRestart = true
                coordinator.recoverAfterRestart().receipts
            } else {
                emptyList()
            }
            val poll = coordinator.poll()
            val decision = coordinator.prepareInstall()
            val delivered = coordinator.drainReceipts()
            return TickReport(recovery, poll.verdict, decision, delivered)
        }
    }

    /**
     * Status-bus sink: a PackageInstaller delivery routed into the coordinator.
     * Returns the terminal receipt when this delivery ended the install.
     */
    fun onInstallerStatus(sessionId: Int, outcome: ApkInstallerOutcome, message: String?): ApkInstallReceipt? =
        synchronized(lock) { coordinator.onInstallerStatus(sessionId, outcome, message) }

    /**
     * Presence-loop reconnect hook (U11 task requirement 4): re-report every
     * undelivered receipt as soon as the control channel is back. The fuller
     * statusReport() block is exposed via [statusReport] for the heartbeat
     * merge once the server heartbeat model grows the field (see WIRE2 report).
     */
    fun onReconnected(): List<ApkInstallReceipt> = synchronized(lock) { coordinator.drainReceipts() }

    fun statusReport(): JSONObject = coordinator.statusReport()
}
