package com.company.cloudctl.companion.updates

import org.junit.After
import org.junit.Before
import org.junit.Test
import java.io.File
import java.io.IOException
import java.io.OutputStream
import java.nio.file.Files
import java.time.Instant
import kotlin.test.*

/**
 * U11 acceptance suite: broken downloads / user refusal / storage exhaustion /
 * reboot never report success; same-signature upgrades keep the pending ledger
 * across restarts; rollback policy; SHA-256 mismatch discipline.
 */
class ApkUpdateCoordinatorTest {
    private lateinit var root: File
    private lateinit var harness: Harness

    private val apkBytes = "fake-apk-artifact-bytes-0123456789".repeat(4).toByteArray()
    private val apkSha = sha256(apkBytes)
    private val sigSha = sha256("sig".toByteArray())
    private val otherSigSha = sha256("other-signature".toByteArray())
    private val packageName = "com.example.target"

    @Before
    fun setup() {
        root = Files.createTempDirectory("apk-u11-coordinator").toFile()
        harness = Harness(root)
    }

    @After
    fun cleanup() {
        root.deleteRecursively()
    }

    // -- fakes ------------------------------------------------------------

    private class FakeClient : ApkReleaseClient {
        val candidates = mutableListOf<ApkInstallCandidate>()
        var downloadBytes: ByteArray = ByteArray(0)
        var downloadFailure: (() -> Exception)? = null
        var reportResult: ApkDownloadReportResult = ApkDownloadReportResult.Accepted
        var receiptDelivery: (ApkInstallReceipt) -> Boolean = { true }
        var downloadCount = 0
        val reported = mutableListOf<Pair<String, String>>()
        val receipts = mutableListOf<ApkInstallReceipt>()

        override fun listCandidates(): List<ApkInstallCandidate> = candidates.toList()

        override fun downloadApk(candidate: ApkInstallCandidate, sink: OutputStream, maxBytes: Long): Long {
            downloadFailure?.let { throw it() }
            downloadCount++
            sink.write(downloadBytes)
            return downloadBytes.size.toLong()
        }

        override fun reportDownloaded(candidateId: String, sha256: String): ApkDownloadReportResult {
            reported += candidateId to sha256
            return reportResult
        }

        override fun reportInstallReceipt(receipt: ApkInstallReceipt): Boolean {
            receipts += receipt
            return receiptDelivery(receipt)
        }
    }

    private class FakeSession(override val sessionId: Int) : ApkInstallSession {
        var stagedFile: File? = null
        var committed = false
        var abandoned = false
        var closed = false
        override fun stage(file: File) {
            stagedFile = file
        }

        override fun commit() {
            committed = true
        }

        override fun abandon() {
            abandoned = true
        }

        override fun close() {
            closed = true
        }
    }

    private class FakeInstaller : ApkInstallPort {
        val sessions = mutableListOf<FakeSession>()
        private var next = 11
        override fun createSession(): FakeSession = FakeSession(next++).also { sessions += it }
    }

    private class FakeGate : ApkInstallGate {
        var busy = false
        var pendingReports = false
        val opened = mutableListOf<String>()
        val closed = mutableListOf<String>()
        private var counter = 0

        override fun hasUnfinishedTaskRows() = busy
        override fun hasPendingCriticalReports() = pendingReports

        override fun suspendClaiming(): ApkClaimSuspension {
            val id = "suspension-${counter++}"
            opened += id
            return object : ApkClaimSuspension {
                override val id: String = id
                override fun close() {
                    closed += id
                }
            }
        }
    }

    private class FakeDevice : ApkDeviceStatePort {
        val installed = mutableMapOf<String, Int>()
        val signatures = mutableMapOf<String, String>()
        val schemas = mutableMapOf<String, Int>()
        override val sdkInt = 35
        override val abis = setOf("arm64-v8a")
        override fun canRequestInstalls() = true
        override fun installedVersionCode(packageName: String): Int? = installed[packageName]
        override fun installedSignatureDigest(packageName: String): String? = signatures[packageName]
        override fun dataSchemaVersion(packageName: String): Int? = schemas[packageName]
    }

    /** A fresh Harness over the same root simulates a process restart: same disk, new fakes. */
    private class Harness(root: File) {
        val client = FakeClient()
        val transfer = ArtifactTransfer(File(root, "artifacts"))
        val ledger = FileApkUpdateLedger(root)
        val installer = FakeInstaller()
        val gate = FakeGate()
        val device = FakeDevice()

        fun coordinator(): ApkUpdateCoordinator =
            ApkUpdateCoordinator(client, transfer, ledger, installer, gate, device, clock = { Instant.parse("2026-09-17T00:00:00Z") })
    }

    // -- helpers -----------------------------------------------------------

    private fun sha256(value: ByteArray): String =
        java.security.MessageDigest.getInstance("SHA-256").digest(value).joinToString("") { "%02x".format(it) }

    private fun candidate(
        versionCode: Int = 21,
        releaseStatus: String = "ACTIVE",
        dataSchema: ApkDataSchemaWindow = ApkDataSchemaWindow(1, 2),
    ) = ApkInstallCandidate(
        candidateId = "cand-1",
        releaseId = "rel-1",
        releaseStatus = releaseStatus,
        status = "OFFERED",
        packageName = packageName,
        versionCode = versionCode,
        versionName = "1.2.1",
        sha256 = apkSha,
        signatureDigest = sigSha,
        sourceRef = "https://artifacts.example/target.apk",
        ring = "all",
        dataSchema = dataSchema,
        requiresUserConfirmation = true,
        assignedAt = "2026-09-17T00:00:00Z",
    )

    private fun readyFile(candidateId: String = "cand-1"): File =
        File(File(File(root, "artifacts"), "ready"), "apk-$candidateId")

    private fun tempLeftovers(): List<String> =
        File(root, "artifacts").listFiles()?.filter { it.isFile }?.map { it.name } ?: emptyList()

    /** Drives poll + gate + session commit up to (and including) the installer commit. */
    private class Committed(val coordinator: ApkUpdateCoordinator, val sessionId: Int)

    private fun commitSession(h: Harness = harness): Committed {
        h.client.candidates += candidate()
        h.client.downloadBytes = apkBytes
        h.device.installed[packageName] = 20
        h.device.signatures[packageName] = sigSha
        val coordinator = h.coordinator()
        assertEquals(ApkStage.REPORTED_DOWNLOADED, (coordinator.poll().verdict as ApkVerdict.Advanced).stage)
        val decision = coordinator.prepareInstall()
        assertTrue(decision is ApkInstallDecision.ReadyToCommit, "expected ReadyToCommit but got $decision")
        return Committed(coordinator, (decision as ApkInstallDecision.ReadyToCommit).sessionId)
    }

    // -- acceptance: same-signature upgrade end-to-end ----------------------

    @Test
    fun sameSignatureUpgradeInstallsWithPersistedLedgerAndResumesClaiming() {
        val committed = commitSession()
        val coordinator = committed.coordinator
        assertEquals(ApkStage.SESSION_COMMITTED, coordinator.pendingState()!!.stage)
        assertEquals(committed.sessionId, coordinator.pendingState()!!.sessionId)
        assertEquals(1, harness.gate.opened.size)

        // PENDING_USER_ACTION is a waiting state: neither success nor failure.
        assertNull(coordinator.onInstallerStatus(committed.sessionId, ApkInstallerOutcome.PENDING_USER_ACTION, null))
        assertEquals(ApkStage.AWAITING_USER_ACTION, coordinator.awaitingUserAction()!!.stage)
        assertTrue(coordinator.drainReceipts().isEmpty())

        harness.device.installed[packageName] = 21
        val receipt = coordinator.onInstallerStatus(committed.sessionId, ApkInstallerOutcome.SUCCESS, null)
        assertEquals(ApkReceiptOutcome.INSTALLED, receipt!!.outcome)
        assertEquals(21, receipt.installedVersionCode)
        assertEquals(true, receipt.signatureMatched)
        assertEquals(listOf(receipt), coordinator.drainReceipts())
        assertNull(coordinator.pendingState())
        // The claim window closed exactly once when the install attempt ended.
        assertEquals(harness.gate.opened, harness.gate.closed)
        assertEquals(1, harness.gate.closed.size)
    }

    // -- acceptance: interrupted download / storage exhaustion -------------

    @Test
    fun interruptedDownloadLeavesNoHalfFileAndStaysRetryable() {
        harness.client.candidates += candidate()
        harness.client.downloadBytes = apkBytes
        harness.client.downloadFailure = { IOException("connection reset mid-stream") }
        val coordinator = harness.coordinator()
        val first = coordinator.poll().verdict as ApkVerdict.Failed
        assertEquals(ApkFailureReason.DOWNLOAD_INTERRUPTED, first.reason)
        assertTrue(first.retryable)
        assertTrue(harness.client.reported.isEmpty())
        assertFalse(readyFile().exists())
        assertTrue(tempLeftovers().isEmpty())

        // The next poll resumes from a clean slate and completes.
        harness.client.downloadFailure = null
        val second = harness.coordinator().poll().verdict as ApkVerdict.Advanced
        assertEquals(ApkStage.REPORTED_DOWNLOADED, second.stage)
        assertEquals(listOf("cand-1" to apkSha), harness.client.reported)
    }

    @Test
    fun storageExhaustedDownloadFailsClosedWithoutPartialFiles() {
        harness.client.candidates += candidate()
        harness.client.downloadFailure = { IOException("write failed: No space left on device") }
        val verdict = harness.coordinator().poll().verdict as ApkVerdict.Failed
        assertEquals(ApkFailureReason.DOWNLOAD_STORAGE, verdict.reason)
        assertTrue(harness.client.reported.isEmpty())
        assertFalse(readyFile().exists())
        assertTrue(tempLeftovers().isEmpty())
        assertNull(harness.coordinator().awaitingUserAction())
    }

    // -- acceptance: SHA-256 mismatch discipline ---------------------------

    @Test
    fun deviceHashMismatchRefusesToReportAndQuarantinesThenRecovers() {
        harness.client.candidates += candidate()
        harness.client.downloadBytes = "tampered-bytes".toByteArray()
        val coordinator = harness.coordinator()
        val verdict = coordinator.poll().verdict as ApkVerdict.Failed
        assertEquals(ApkFailureReason.HASH_MISMATCH, verdict.reason)
        assertTrue(verdict.retryable)
        // APK_DOWNLOAD_HASH_MISMATCH semantics: no report-downloaded, candidate stays eligible.
        assertTrue(harness.client.reported.isEmpty())
        assertFalse(readyFile().exists())
        assertTrue(tempLeftovers().isEmpty())

        harness.client.downloadBytes = apkBytes
        assertEquals(ApkStage.REPORTED_DOWNLOADED, (coordinator.poll().verdict as ApkVerdict.Advanced).stage)
    }

    @Test
    fun serverHashMismatchDeletesArtifactAndParksCandidateForManualAction() {
        harness.client.candidates += candidate()
        harness.client.downloadBytes = apkBytes
        harness.client.reportResult = ApkDownloadReportResult.HashMismatch("server-side digest disagrees")
        val coordinator = harness.coordinator()
        val verdict = coordinator.poll().verdict as ApkVerdict.Failed
        assertEquals(ApkFailureReason.SERVER_HASH_MISMATCH, verdict.reason)
        assertFalse(verdict.retryable)
        assertFalse(readyFile().exists())
        // Parked: later polls skip the candidate instead of looping.
        assertEquals(ApkVerdict.Idle, coordinator.poll().verdict)
        assertEquals(1, harness.ledger.failures().size)
    }

    @Test
    fun reportFailureKeepsVerifiedFileAndRetriesOnlyTheReport() {
        harness.client.candidates += candidate()
        harness.client.downloadBytes = apkBytes
        harness.client.reportResult = ApkDownloadReportResult.Error(503, "try later")
        val coordinator = harness.coordinator()
        val verdict = coordinator.poll().verdict as ApkVerdict.Failed
        assertEquals(ApkFailureReason.REPORT_ERROR, verdict.reason)
        assertTrue(verdict.retryable)
        assertTrue(readyFile().exists()) // locally verified bytes are retained

        harness.client.reportResult = ApkDownloadReportResult.Accepted
        val second = coordinator.poll().verdict as ApkVerdict.Advanced
        assertEquals(ApkStage.REPORTED_DOWNLOADED, second.stage)
        assertEquals(1, harness.client.downloadCount) // no re-download, only the report was retried
    }

    // -- acceptance: rollback semantics ------------------------------------

    @Test
    fun higherVersionCodeRollbackPackageIsAccepted() {
        // The device runs a broken vc20 build; a vc21 release restoring the old
        // logic (with compatible data window) is the supported rollback path.
        harness.device.installed[packageName] = 20
        harness.device.signatures[packageName] = sigSha
        harness.device.schemas[packageName] = 1
        harness.client.candidates += candidate(versionCode = 21, dataSchema = ApkDataSchemaWindow(1, 2))
        harness.client.downloadBytes = apkBytes
        val verdict = harness.coordinator().poll().verdict as ApkVerdict.Advanced
        assertEquals(ApkStage.REPORTED_DOWNLOADED, verdict.stage)
    }

    @Test
    fun downgradeCandidateIsRejectedWithManualInterventionSemantics() {
        harness.device.installed[packageName] = 25
        harness.device.signatures[packageName] = sigSha
        harness.client.candidates += candidate(versionCode = 20)
        harness.client.downloadBytes = apkBytes
        val coordinator = harness.coordinator()
        val verdict = coordinator.poll().verdict as ApkVerdict.Rejected
        assertEquals(ApkRejectionReason.VERSION_DOWNGRADE, verdict.reason)
        assertEquals(0, harness.client.downloadCount) // nothing downloaded
        assertEquals(ApkVerdict.Idle, coordinator.poll().verdict) // parked for a human
        assertEquals("VERSION_DOWNGRADE", harness.ledger.failures()[0].reason)
    }

    @Test
    fun schemaIncompatibleCandidateIsRejectedFailClosed() {
        harness.device.installed[packageName] = 20
        harness.device.signatures[packageName] = sigSha
        harness.device.schemas[packageName] = 1
        harness.client.candidates += candidate(dataSchema = ApkDataSchemaWindow(2, 3))
        val verdict = harness.coordinator().poll().verdict as ApkVerdict.Rejected
        assertEquals(ApkRejectionReason.SCHEMA_INCOMPATIBLE, verdict.reason)
        assertEquals(0, harness.client.downloadCount)
    }

    @Test
    fun signatureMismatchCandidateIsRejectedBeforeAnySession() {
        harness.device.installed[packageName] = 20
        harness.device.signatures[packageName] = otherSigSha
        harness.client.candidates += candidate()
        val verdict = harness.coordinator().poll().verdict as ApkVerdict.Rejected
        assertEquals(ApkRejectionReason.SIGNATURE_MISMATCH, verdict.reason)
        assertEquals(0, harness.client.downloadCount)
        assertTrue(harness.installer.sessions.isEmpty())
    }

    // -- contract §1.3: retired releases still serve pinned candidates -----

    @Test
    fun retiredReleaseServesPinnedDownloadButHoldsInstallForHumanDecision() {
        harness.client.candidates += candidate(releaseStatus = "RETIRED")
        harness.client.downloadBytes = apkBytes
        val coordinator = harness.coordinator()
        assertEquals(ApkStage.REPORTED_DOWNLOADED, (coordinator.poll().verdict as ApkVerdict.Advanced).stage)
        assertEquals(1, harness.client.reported.size) // pinned candidate still downloads + reports
        val decision = coordinator.prepareInstall()
        assertTrue(decision is ApkInstallDecision.HeldRetiredRelease)
        assertTrue(harness.installer.sessions.isEmpty())
    }

    // -- acceptance: install-time gate -------------------------------------

    @Test
    fun installGateBlocksOnUnfinishedTasksAndUndrainedReports() {
        harness.client.candidates += candidate()
        harness.client.downloadBytes = apkBytes
        harness.device.installed[packageName] = 20
        harness.device.signatures[packageName] = sigSha
        val coordinator = harness.coordinator()
        assertEquals(ApkStage.REPORTED_DOWNLOADED, (coordinator.poll().verdict as ApkVerdict.Advanced).stage)

        harness.gate.busy = true // AutomationStore.hasUnfinishedTaskRows() semantics
        assertTrue(coordinator.prepareInstall() is ApkInstallDecision.BlockedDeviceBusy)
        harness.gate.busy = false
        harness.gate.pendingReports = true // critical report queue not drained
        assertTrue(coordinator.prepareInstall() is ApkInstallDecision.BlockedCriticalReports)
        // No session and no claim suspension happened while blocked.
        assertTrue(harness.installer.sessions.isEmpty())
        assertTrue(harness.gate.opened.isEmpty())
        harness.gate.pendingReports = false
        assertTrue(coordinator.prepareInstall() is ApkInstallDecision.ReadyToCommit)
        assertEquals(1, harness.gate.opened.size) // claiming suspended exactly once for the window
    }

    // -- acceptance: user refusal ------------------------------------------

    @Test
    fun userDeclineAfterPendingActionIsTerminalAndNeverSuccess() {
        val committed = commitSession()
        val coordinator = committed.coordinator
        assertNull(coordinator.onInstallerStatus(committed.sessionId, ApkInstallerOutcome.PENDING_USER_ACTION, null))
        // The user taps "no" in the system installer UI.
        val receipt = coordinator.onInstallerStatus(committed.sessionId, ApkInstallerOutcome.FAILURE_ABORTED, "INSTALL_FAILED_ABORTED")
        assertEquals(ApkReceiptOutcome.USER_DECLINED, receipt!!.outcome)
        assertEquals(20, receipt.installedVersionCode) // evidence: the old build is still what runs
        assertEquals(20, harness.device.installed[packageName]) // nothing changed on the device
        assertEquals(listOf(receipt), coordinator.drainReceipts())
        assertNull(coordinator.pendingState())
        assertEquals(harness.gate.opened, harness.gate.closed)
        assertFalse(readyFile().exists()) // staged artifact consumed/discarded
    }

    @Test
    fun installerStorageFailureIsTerminalWithoutUninstallOrDataClear() {
        val committed = commitSession()
        val receipt = committed.coordinator
            .onInstallerStatus(committed.sessionId, ApkInstallerOutcome.FAILURE_STORAGE, "insufficient storage")
        assertEquals(ApkReceiptOutcome.FAILED, receipt!!.outcome)
        assertEquals(20, harness.device.installed[packageName]) // no uninstall, no data clear — device untouched
        assertEquals(listOf(receipt), committed.coordinator.drainReceipts())
        assertNull(committed.coordinator.pendingState())
        assertEquals(harness.gate.opened, harness.gate.closed)
    }

    @Test
    fun successWithoutDeviceEvidenceIsInterruptedNotInstalled() {
        val committed = commitSession()
        // SUCCESS status but the device still runs the old build: fail closed.
        val receipt = committed.coordinator.onInstallerStatus(committed.sessionId, ApkInstallerOutcome.SUCCESS, null)
        assertEquals(ApkReceiptOutcome.INTERRUPTED, receipt!!.outcome)
        assertEquals(20, receipt.installedVersionCode)
    }

    // -- acceptance: reboot recovery ---------------------------------------

    @Test
    fun rebootAfterCommitWithoutCompletionReportsInterrupted() {
        val committed = commitSession()
        assertEquals(ApkStage.SESSION_COMMITTED, committed.coordinator.pendingState()!!.stage)

        val restarted = Harness(root) // same disk, fresh process; install never completed
        val recovery = restarted.coordinator().recoverAfterRestart()
        assertEquals(1, recovery.receipts.size)
        assertEquals(ApkReceiptOutcome.INTERRUPTED, recovery.receipts[0].outcome)
        assertTrue(recovery.receipts.none { it.outcome == ApkReceiptOutcome.INSTALLED })
        assertNull(restarted.coordinator().pendingState())
        assertEquals(21, recovery.receipts[0].attemptedVersionCode)
    }

    @Test
    fun rebootAfterCompletedInstallReportsInstalledWithEvidence() {
        commitSession()
        val restarted = Harness(root)
        restarted.device.installed[packageName] = 21
        restarted.device.signatures[packageName] = sigSha

        val recovery = restarted.coordinator().recoverAfterRestart()
        assertEquals(listOf(ApkReceiptOutcome.INSTALLED), recovery.receipts.map { it.outcome })
        assertEquals(21, recovery.receipts[0].installedVersionCode)
        assertEquals(true, recovery.receipts[0].signatureMatched)
    }

    @Test
    fun rebootKeepsAwaitingUserActionPendingAndLaterDeclineResolves() {
        val committed = commitSession()
        committed.coordinator.onInstallerStatus(committed.sessionId, ApkInstallerOutcome.PENDING_USER_ACTION, null)

        val restarted = Harness(root)
        val coordinator = restarted.coordinator()
        val recovery = coordinator.recoverAfterRestart()
        assertTrue(recovery.receipts.isEmpty()) // a reboot neither confirms nor fails the install
        assertEquals(ApkStage.AWAITING_USER_ACTION, recovery.pending!!.stage)
        assertEquals(ApkStage.AWAITING_USER_ACTION, coordinator.awaitingUserAction()!!.stage)
        assertTrue(coordinator.prepareInstall() is ApkInstallDecision.HeldAwaitingUserAction)

        // The pending intent stays resolvable across the restart: the decline receipt resolves it.
        val receipt = coordinator.onInstallerStatus(committed.sessionId, ApkInstallerOutcome.FAILURE_ABORTED, null)
        assertEquals(ApkReceiptOutcome.USER_DECLINED, receipt!!.outcome)
        assertEquals(listOf(receipt), coordinator.drainReceipts())
    }

    @Test
    fun journaledStatusEventIsReplayedByRecovery() {
        val committed = commitSession()
        // The receiver fired before any coordinator attached: journaled to disk.
        harness.ledger.appendStatusEvent(
            ApkInstallerStatusEvent(committed.sessionId, ApkInstallerOutcome.PENDING_USER_ACTION, null, "t"),
        )
        val restarted = Harness(root)
        val recovery = restarted.coordinator().recoverAfterRestart()
        assertEquals(1, recovery.replayedStatusEvents)
        assertEquals(ApkStage.AWAITING_USER_ACTION, restarted.coordinator().awaitingUserAction()!!.stage)
        assertTrue(harness.ledger.drainStatusEvents().isEmpty())
    }

    @Test
    fun receiptsSurviveRestartUntilDelivered() {
        harness.client.receiptDelivery = { false }
        val committed = commitSession()
        harness.device.installed[packageName] = 21
        val receipt = committed.coordinator.onInstallerStatus(committed.sessionId, ApkInstallerOutcome.SUCCESS, null)
        assertEquals(ApkReceiptOutcome.INSTALLED, receipt!!.outcome)
        assertTrue(committed.coordinator.drainReceipts().isEmpty()) // endpoint unavailable

        val restarted = Harness(root)
        assertEquals(listOf(receipt), restarted.coordinator().drainReceipts())
        assertTrue(restarted.ledger.undeliveredReceipts().isEmpty())
    }

    @Test
    fun interruptedDownloadAcrossRestartResumesCleanly() {
        harness.client.candidates += candidate()
        harness.client.downloadBytes = apkBytes
        harness.client.downloadFailure = { IOException("process died mid-download") }
        assertTrue(harness.coordinator().poll().verdict is ApkVerdict.Failed)
        assertTrue(tempLeftovers().isEmpty())

        val restarted = Harness(root)
        restarted.client.candidates += candidate()
        restarted.client.downloadBytes = apkBytes
        val verdict = restarted.coordinator().poll().verdict as ApkVerdict.Advanced
        assertEquals(ApkStage.REPORTED_DOWNLOADED, verdict.stage)
        assertTrue(readyFile().exists())
    }

    // -- acceptance: reconnect re-report -----------------------------------

    @Test
    fun statusReportCarriesVersionsPermissionAndPendingStage() {
        harness.client.candidates += candidate()
        harness.client.downloadBytes = apkBytes
        harness.device.installed[packageName] = 20
        harness.device.signatures[packageName] = sigSha
        val coordinator = harness.coordinator()
        coordinator.poll()
        val report = coordinator.statusReport()
        assertEquals(20, report.getJSONObject("packages").getJSONObject(packageName).getInt("versionCode"))
        assertEquals(sigSha, report.getJSONObject("packages").getJSONObject(packageName).getString("signatureDigest"))
        assertTrue(report.getBoolean("canRequestPackageInstalls"))
        assertEquals(35, report.getInt("sdkInt"))
        assertTrue(report.getJSONArray("abis").length() > 0)
        assertEquals("REPORTED_DOWNLOADED", report.getJSONObject("pendingInstall").getString("stage"))
    }
}
