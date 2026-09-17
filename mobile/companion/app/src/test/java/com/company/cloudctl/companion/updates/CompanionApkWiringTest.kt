package com.company.cloudctl.companion.updates

import org.junit.After
import org.junit.Before
import org.junit.Test
import java.io.File
import java.io.OutputStream
import java.nio.file.Files
import java.time.Instant
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * WIRE2 acceptance: the CompanionSyncService-side glue around the U11
 * coordinator — gate mapping (unfinished task rows block the install; claim
 * suspension flips exactly once per window), status-bus delivery into the
 * coordinator, and the driver's once-only reboot recovery.
 */
class CompanionApkWiringTest {
    private lateinit var root: File
    private lateinit var harness: Harness

    private val apkBytes = "wired-fake-apk-artifact-bytes-0123456789".repeat(4).toByteArray()

    @Before
    fun setup() {
        root = Files.createTempDirectory("apk-wire2").toFile()
        harness = Harness(root)
    }

    @After
    fun cleanup() {
        ApkInstallStatusBus.detach()
        root.deleteRecursively()
    }

    // -- fakes (same discipline as ApkUpdateCoordinatorTest) ----------------

    private class FakeClient : ApkReleaseClient {
        val candidates = mutableListOf<ApkInstallCandidate>()
        var downloadBytes: ByteArray = ByteArray(0)
        val reported = mutableListOf<Pair<String, String>>()
        val receipts = mutableListOf<ApkInstallReceipt>()

        override fun listCandidates(): List<ApkInstallCandidate> = candidates.toList()

        override fun downloadApk(candidate: ApkInstallCandidate, sink: OutputStream, maxBytes: Long): Long {
            sink.write(downloadBytes)
            return downloadBytes.size.toLong()
        }

        override fun reportDownloaded(candidateId: String, sha256: String): ApkDownloadReportResult {
            reported += candidateId to sha256
            return ApkDownloadReportResult.Accepted
        }

        override fun reportInstallReceipt(receipt: ApkInstallReceipt): Boolean {
            receipts += receipt
            return true
        }
    }

    private class FakeInstaller : ApkInstallPort {
        val sessions = mutableListOf<ApkInstallSession>()
        private var next = 21

        override fun createSession(): ApkInstallSession = object : ApkInstallSession {
            override val sessionId: Int = next++
            var committed = false
            override fun stage(file: File) = Unit
            override fun commit() {
                committed = true
            }
            override fun abandon() = Unit
            override fun close() = Unit
        }.also { sessions += it }
    }

    private class FakeDevice(val installed: MutableMap<String, Int> = mutableMapOf()) : ApkDeviceStatePort {
        override val sdkInt = 35
        override val abis = setOf("arm64-v8a")
        override fun canRequestInstalls() = true
        override fun installedVersionCode(packageName: String): Int? = installed[packageName]
        override fun installedSignatureDigest(packageName: String): String? = null
        override fun dataSchemaVersion(packageName: String): Int? = null
    }

    private class Harness(root: File) {
        val client = FakeClient()
        val transfer = ArtifactTransfer(root)
        val ledger = FileApkUpdateLedger(root)
        val installer = FakeInstaller()
        val device = FakeDevice()
        val claimLever = mutableListOf<String>()
        var unfinishedTaskRows = false
        var pendingCriticalReports = false
        val gate = CompanionApkInstallGate(
            unfinishedTaskRows = { unfinishedTaskRows },
            pendingCriticalReports = { pendingCriticalReports },
            suspendClaim = { claimLever += "suspend" },
            resumeClaim = { claimLever += "resume" },
        )

        fun coordinator(): ApkUpdateCoordinator = ApkUpdateCoordinator(
            client, transfer, ledger, installer, gate, device,
            clock = { Instant.parse("2026-09-17T00:00:00Z") },
        )
    }

    private fun sha256(value: ByteArray): String =
        java.security.MessageDigest.getInstance("SHA-256").digest(value)
            .joinToString("") { "%02x".format(it) }

    private fun candidate(): ApkInstallCandidate = ApkInstallCandidate(
        candidateId = "cand-wire2",
        releaseId = "rel-wire2",
        releaseStatus = "ACTIVE",
        status = "OFFERED",
        packageName = "com.example.target",
        versionCode = 83201,
        versionName = "0.83201",
        sha256 = sha256(apkBytes),
        signatureDigest = "d".repeat(64),
        sourceRef = "https://artifacts.example/target.apk",
        ring = "all",
        dataSchema = ApkDataSchemaWindow(minCompatible = 1, current = 2),
        requiresUserConfirmation = true,
        assignedAt = "2026-09-17T00:00:00Z",
    )

    // -- gate mapping -------------------------------------------------------

    @Test
    fun gateMapsStoreSignalsAndFlipsTheClaimLeverExactlyOncePerWindow() {
        val gate = harness.gate
        assertFalse(gate.hasUnfinishedTaskRows())
        assertFalse(gate.hasPendingCriticalReports())
        harness.unfinishedTaskRows = true
        harness.pendingCriticalReports = true
        assertTrue(gate.hasUnfinishedTaskRows())
        assertTrue(gate.hasPendingCriticalReports())

        val suspension = gate.suspendClaiming()
        assertEquals(listOf("suspend"), harness.claimLever)
        suspension.close()
        assertEquals(listOf("suspend", "resume"), harness.claimLever)

        // A second window flips the lever open and closed exactly once again.
        val second = gate.suspendClaiming()
        assertEquals(listOf("suspend", "resume", "suspend"), harness.claimLever)
        second.close()
        assertEquals(listOf("suspend", "resume", "suspend", "resume"), harness.claimLever)
    }

    // -- install window through the driver ----------------------------------

    @Test
    fun unfinishedTaskRowsBlockTheInstallAndNoSuspensionIsOpened() {
        val driver = CompanionApkUpdateDriver(harness.coordinator())
        harness.client.candidates += candidate()
        harness.client.downloadBytes = apkBytes
        harness.unfinishedTaskRows = true

        val report = driver.tick()
        // The download still progressed (poll is not gated), ...
        assertIs<ApkVerdict.Advanced>(report.verdict)
        assertEquals(ApkStage.REPORTED_DOWNLOADED, report.verdict.stage)
        // ... but the install window is blocked and claiming was never suspended.
        assertIs<ApkInstallDecision.BlockedDeviceBusy>(report.decision)
        assertTrue(harness.claimLever.isEmpty())
        assertTrue(harness.installer.sessions.isEmpty())
    }

    @Test
    fun pendingCriticalReportsBlockTheInstallWindow() {
        val driver = CompanionApkUpdateDriver(harness.coordinator())
        harness.client.candidates += candidate()
        harness.client.downloadBytes = apkBytes
        harness.unfinishedTaskRows = false
        harness.pendingCriticalReports = true

        val report = driver.tick()
        assertIs<ApkInstallDecision.BlockedCriticalReports>(report.decision)
        assertTrue(harness.claimLever.isEmpty())
    }

    @Test
    fun statusBusDeliversInstallerStatusesIntoTheCoordinator() {
        val driver = CompanionApkUpdateDriver(harness.coordinator())
        // Attach exactly like CompanionSyncService.apkRuntime() does.
        ApkInstallStatusBus.attach { sessionId, outcome, message ->
            driver.onInstallerStatus(sessionId, outcome, message)
        }
        harness.client.candidates += candidate()
        harness.client.downloadBytes = apkBytes

        val report = driver.tick()
        val ready = assertIs<ApkInstallDecision.ReadyToCommit>(report.decision)
        // The install window is open: exactly one suspend, no resume yet.
        assertEquals(listOf("suspend"), harness.claimLever)

        // The device now really runs the target version; the SUCCESS delivery
        // arrives through the bus (broadcast thread) just like in production.
        harness.device.installed[candidate().packageName] = 83201
        val sink = requireNotNull(ApkInstallStatusBus.current())
        sink(ready.sessionId, ApkInstallerOutcome.SUCCESS, null)

        val receipt = harness.ledger.undeliveredReceipts().single()
        assertEquals(ApkReceiptOutcome.INSTALLED, receipt.outcome)
        assertEquals("cand-wire2", receipt.candidateId)
        assertEquals(83201, receipt.installedVersionCode)
        // Terminal status closed the install window: lever flipped back once.
        assertEquals(listOf("suspend", "resume"), harness.claimLever)
        // The pending install is consumed; the artifact window is over.
        assertNull(harness.ledger.pending())

        // The next drain (reconnect / next tick) hands the receipt upstream.
        val delivered = driver.onReconnected()
        assertEquals(listOf(receipt.candidateId), delivered.map { it.candidateId })
        assertEquals(0, harness.ledger.undeliveredReceipts().size)
        assertEquals(1, harness.client.receipts.size)
    }

    @Test
    fun tickRunsRebootRecoveryExactlyOncePerProcess() {
        // First process: drive to a committed session, then "die".
        val first = CompanionApkUpdateDriver(harness.coordinator())
        harness.client.candidates += candidate()
        harness.client.downloadBytes = apkBytes
        assertIs<ApkInstallDecision.ReadyToCommit>(first.tick().decision)
        assertEquals(ApkStage.SESSION_COMMITTED, harness.ledger.pending()?.stage)

        // Reboot: the package actually landed while we were gone.
        harness.device.installed[candidate().packageName] = 83201
        val restarted = CompanionApkUpdateDriver(harness.coordinator())
        val firstTick = restarted.tick()
        assertEquals(1, firstTick.recoveryReceipts.size)
        assertEquals(ApkReceiptOutcome.INSTALLED, firstTick.recoveryReceipts.single().outcome)
        // The recovery receipt was drained upstream inside the same tick
        // (fake client accepts immediately).
        assertEquals(1, harness.client.receipts.size)
        assertEquals(0, harness.ledger.undeliveredReceipts().size)
        // The second tick never re-runs the reconciliation.
        val secondTick = restarted.tick()
        assertTrue(secondTick.recoveryReceipts.isEmpty())
    }

    @Test
    fun statusForAnotherSessionIsIgnoredByTheCoordinator() {
        val driver = CompanionApkUpdateDriver(harness.coordinator())
        harness.client.candidates += candidate()
        harness.client.downloadBytes = apkBytes
        assertIs<ApkInstallDecision.ReadyToCommit>(driver.tick().decision)
        val stray = driver.onInstallerStatus(9999, ApkInstallerOutcome.FAILURE, "stray session")
        assertNull(stray)
        // No terminal receipt, install window still open.
        assertEquals(listOf("suspend"), harness.claimLever)
        assertEquals(0, harness.ledger.undeliveredReceipts().size)
    }
}
