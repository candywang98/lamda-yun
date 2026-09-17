package com.company.cloudctl.companion.updates

import org.json.JSONObject
import java.io.IOException
import java.time.Instant

/** Result of a candidate poll/download cycle. Never claims install success. */
sealed interface ApkVerdict {
    data object Idle : ApkVerdict

    /** Progressed locally; [stage] is the persisted stage after this poll. */
    data class Advanced(val stage: ApkStage) : ApkVerdict

    /** Fail-closed rejection — always requires manual intervention, nothing was downloaded. */
    data class Rejected(val reason: ApkRejectionReason, val candidateId: String) : ApkVerdict

    /** Download/report failed before any install attempt; retryable unless [deterministic]. */
    data class Failed(
        val reason: ApkFailureReason,
        val retryable: Boolean,
        val attempts: Int,
        val detail: String? = null,
    ) : ApkVerdict
}

enum class ApkRejectionReason {
    /** Rollback policy: only a HIGHER versionCode may restore old logic; a true downgrade needs a human. */
    VERSION_DOWNGRADE,

    /** Device data schema provably older than the release's minCompatible window. */
    SCHEMA_INCOMPATIBLE,

    /** Installed app signature does not match the release's signatureDigest (update would be rejected by Android). */
    SIGNATURE_MISMATCH,

    /** Ledger candidate drifted from the server's frozen release fields — contract-impossible, treated as tampering. */
    CANDIDATE_DRIFT,
}

enum class ApkFailureReason {
    DOWNLOAD_INTERRUPTED,
    DOWNLOAD_STORAGE,
    /** Device-side digest mismatch — same semantics as apk-release/v1 APK_DOWNLOAD_HASH_MISMATCH. */
    HASH_MISMATCH,
    /** Server rejected our verified digest with 422 APK_DOWNLOAD_HASH_MISMATCH. */
    SERVER_HASH_MISMATCH,
    /** The artifact exceeded the local transfer cap; deterministic, parked for manual action. */
    ARTIFACT_TOO_LARGE,
    REPORT_ERROR,
}

data class ApkPollResult(val verdict: ApkVerdict, val pending: ApkPendingInstall?)

/** Outcome of the install-time gate + session opening (U11 task requirement 3). */
sealed interface ApkInstallDecision {
    data class ReadyToCommit(val sessionId: Int, val candidate: ApkInstallCandidate) : ApkInstallDecision
    data object BlockedDeviceBusy : ApkInstallDecision
    data object BlockedCriticalReports : ApkInstallDecision
    data class HeldAwaitingUserAction(val pending: ApkPendingInstall) : ApkInstallDecision

    /** Retired releases still serve pinned downloads (contract §1.3) but installing them needs a human decision. */
    data class HeldRetiredRelease(val pending: ApkPendingInstall) : ApkInstallDecision
    data object PendingDownloadIncomplete : ApkInstallDecision
    data object NothingToInstall : ApkInstallDecision
}

data class ApkRecoveryResult(
    val receipts: List<ApkInstallReceipt>,
    val pending: ApkPendingInstall?,
    val replayedStatusEvents: Int,
)

/**
 * U11 device-side coordinator for apk-release/v1@20260917.1 install candidates.
 *
 * State discipline:
 * - A candidate is only ever elected after local fail-closed eligibility
 *   (versionCode rollback policy, data-schema window, signature digest).
 * - Downloads flow through the shared [ArtifactTransfer] pipeline
 *   (temp -> SHA-256 -> atomic ready) — identical discipline for APKs and
 *   recipe packages ([RecipeArtifactPipeline]).
 * - `POST .../report-downloaded` happens ONLY after the local digest matched;
 *   a 422 APK_DOWNLOAD_HASH_MISMATCH from the server deletes the local file
 *   and parks the candidate in the failure ledger (deterministic, manual clear).
 * - Installs open a PackageInstaller session ONLY when the device is idle,
 *   critical report queues are drained and claim intake is suspended. The
 *   coordinator never stops, kills or force-stops its own (or any) service.
 * - PENDING_USER_ACTION is a persisted waiting state, not success; a user
 *   decline is a terminal USER_DECLINED receipt. Ordinary install failures
 *   NEVER trigger an uninstall or data clear — there is no such code path.
 * - Success is confirmed by re-reading the installed versionCode/signature
 *   from the device, including across reboots ([recoverAfterRestart]): an
 *   interrupted session is reported INTERRUPTED, never INSTALLED.
 */
class ApkUpdateCoordinator(
    private val client: ApkReleaseClient,
    private val transfer: ArtifactTransfer,
    private val ledger: ApkUpdateLedger,
    private val installer: ApkInstallPort,
    private val gate: ApkInstallGate,
    private val device: ApkDeviceStatePort,
    private val maxArtifactBytes: Long = 256L * 1024 * 1024,
    private val clock: () -> Instant = { Instant.now() },
) {
    private var claimSuspension: ApkClaimSuspension? = null

    fun pendingState(): ApkPendingInstall? = ledger.pending()

    /** The install awaiting a user yes/no, for the UI layer to surface. */
    fun awaitingUserAction(): ApkPendingInstall? =
        ledger.pending()?.takeIf { it.stage == ApkStage.AWAITING_USER_ACTION && it.terminalOutcome == null }

    // -- poll: candidates -> eligibility -> unified download -> report-downloaded --

    fun poll(): ApkPollResult {
        val candidates = client.listCandidates()
        var pending = ledger.pending()

        if (pending != null && pending.terminalOutcome != null) {
            // Terminal installs are receipts' business; never re-elect on top of them.
            val listed = candidates.firstOrNull { it.candidateId == pending!!.candidate.candidateId }
            if (listed == null) {
                ledger.clearPending()
                pending = null
            } else {
                return ApkPollResult(ApkVerdict.Advanced(pending.stage), pending)
            }
        }

        if (pending != null) {
            // Install phases are driven by installer statuses and recovery, not by poll().
            if (pending.stage >= ApkStage.REPORTED_DOWNLOADED) {
                return ApkPollResult(ApkVerdict.Advanced(pending.stage), pending)
            }
            val listed = candidates.firstOrNull { it.candidateId == pending!!.candidate.candidateId }
                ?: return ApkPollResult(
                    // Server stopped offering before we reported a download: drop the local intent.
                    ApkVerdict.Failed(ApkFailureReason.REPORT_ERROR, retryable = false, attempts = pending.attempts, detail = "candidate no longer offered"),
                    pending,
                )
            if (candidateDrifted(pending.candidate, listed)) {
                ledger.clearPending()
                transfer.discard(artifactKey(listed.candidateId))
                ledger.noteFailure(
                    ApkCandidateFailure(listed.candidateId, listed.sha256, listed.versionCode, ApkRejectionReason.CANDIDATE_DRIFT.name, now()),
                )
                return ApkPollResult(ApkVerdict.Rejected(ApkRejectionReason.CANDIDATE_DRIFT, listed.candidateId), null)
            }
            // A resumed download is a new attempt.
            val resumed = pending.copy(attempts = pending.attempts + 1, updatedAt = now())
            ledger.record(resumed)
            return ApkPollResult(advanceDownload(listed, resumed), ledger.pending())
        }

        val failures = ledger.failures()
        val candidate = candidates.firstOrNull { candidate ->
            failures.none { it.candidateId == candidate.candidateId && it.sha256 == candidate.sha256 && it.versionCode == candidate.versionCode }
        } ?: return ApkPollResult(ApkVerdict.Idle, null)

        val rejection = eligibility(candidate)
        if (rejection != null) {
            ledger.noteFailure(ApkCandidateFailure(candidate.candidateId, candidate.sha256, candidate.versionCode, rejection.name, now()))
            return ApkPollResult(ApkVerdict.Rejected(rejection, candidate.candidateId), null)
        }
        val fresh = ApkPendingInstall(candidate = candidate, stage = ApkStage.DOWNLOADING, attempts = 1, updatedAt = now())
        ledger.record(fresh)
        return ApkPollResult(advanceDownload(candidate, fresh), ledger.pending())
    }

    /**
     * Local fail-closed eligibility. Mirrors the server's assign-time gates
     * where the device can prove a violation itself, plus the rollback policy:
     * a HIGHER versionCode restoring older logic is the supported rollback;
     * a lower-or-equal versionCode downgrade is explicitly NOT promised and
     * requires manual intervention (server would 422 APK_VERSION_DOWNGRADE).
     */
    private fun eligibility(candidate: ApkInstallCandidate): ApkRejectionReason? {
        val installedVersion = device.installedVersionCode(candidate.packageName)
        if (installedVersion != null && candidate.versionCode <= installedVersion) {
            return ApkRejectionReason.VERSION_DOWNGRADE
        }
        val schema = device.dataSchemaVersion(candidate.packageName)
        if (schema != null && schema < candidate.dataSchema.minCompatible) {
            return ApkRejectionReason.SCHEMA_INCOMPATIBLE
        }
        val installedSignature = device.installedSignatureDigest(candidate.packageName)
        if (installedSignature != null && installedSignature.lowercase() != candidate.signatureDigest) {
            return ApkRejectionReason.SIGNATURE_MISMATCH
        }
        return null
    }

    private fun candidateDrifted(pinned: ApkInstallCandidate, listed: ApkInstallCandidate): Boolean =
        pinned.sha256 != listed.sha256 ||
            pinned.versionCode != listed.versionCode ||
            pinned.packageName != listed.packageName ||
            pinned.signatureDigest != listed.signatureDigest ||
            pinned.releaseId != listed.releaseId

    /** Download (or resume) -> verify -> atomic ready -> report-downloaded. */
    private fun advanceDownload(candidate: ApkInstallCandidate, current: ApkPendingInstall): ApkVerdict {
        val key = artifactKey(candidate.candidateId)
        val staged: Long
        try {
            staged = transfer.stage(key, candidate.sha256, maxArtifactBytes) { sink ->
                client.downloadApk(candidate, sink, maxArtifactBytes)
            }
        } catch (mismatch: ArtifactHashMismatchException) {
            // Device-side digest check failed: refuse to report the download and
            // quarantine the bytes; semantics aligned with apk-release/v1
            // APK_DOWNLOAD_HASH_MISMATCH (the candidate stays eligible).
            transfer.discard(key)
            val state = ledger.pending() ?: current
            ledger.record(state.copy(stage = ApkStage.DOWNLOADING, bytesWritten = 0, attempts = state.attempts, updatedAt = now()))
            return ApkVerdict.Failed(ApkFailureReason.HASH_MISMATCH, retryable = true, attempts = state.attempts, detail = "computed ${mismatch.actual}")
        } catch (error: IOException) {
            val state = ledger.pending() ?: current
            ledger.record(state.copy(stage = ApkStage.DOWNLOADING, bytesWritten = 0, updatedAt = now()))
            return if (isStorageExhaustion(error)) {
                ApkVerdict.Failed(ApkFailureReason.DOWNLOAD_STORAGE, retryable = true, attempts = state.attempts, detail = error.message)
            } else {
                ApkVerdict.Failed(ApkFailureReason.DOWNLOAD_INTERRUPTED, retryable = true, attempts = state.attempts, detail = error.message)
            }
        } catch (tooLarge: ArtifactTooLargeException) {
            transfer.discard(key)
            val state = ledger.pending() ?: current
            ledger.record(state.copy(stage = ApkStage.DOWNLOADING, bytesWritten = 0, updatedAt = now()))
            ledger.noteFailure(ApkCandidateFailure(candidate.candidateId, candidate.sha256, candidate.versionCode, ApkFailureReason.ARTIFACT_TOO_LARGE.name, now()))
            return ApkVerdict.Failed(ApkFailureReason.ARTIFACT_TOO_LARGE, retryable = false, attempts = state.attempts, detail = tooLarge.message)
        }
        val downloaded = (ledger.pending() ?: current).copy(stage = ApkStage.DOWNLOADED, bytesWritten = staged, updatedAt = now())
        ledger.record(downloaded)
        return when (val report = client.reportDownloaded(candidate.candidateId, candidate.sha256)) {
            is ApkDownloadReportResult.Accepted -> {
                ledger.record(downloaded.copy(stage = ApkStage.REPORTED_DOWNLOADED, updatedAt = now()))
                ApkVerdict.Advanced(ApkStage.REPORTED_DOWNLOADED)
            }
            is ApkDownloadReportResult.HashMismatch -> {
                // The server disagrees with our verified bytes: fail closed,
                // delete the artifact and park the candidate for manual action.
                transfer.discard(key)
                ledger.clearPending()
                ledger.noteFailure(
                    ApkCandidateFailure(candidate.candidateId, candidate.sha256, candidate.versionCode, ApkFailureReason.SERVER_HASH_MISMATCH.name, now()),
                )
                ApkVerdict.Failed(ApkFailureReason.SERVER_HASH_MISMATCH, retryable = false, attempts = downloaded.attempts, detail = report.detail)
            }
            is ApkDownloadReportResult.Error -> {
                // The file is locally verified; keep it and retry only the report.
                ApkVerdict.Failed(ApkFailureReason.REPORT_ERROR, retryable = true, attempts = downloaded.attempts, detail = "HTTP ${report.status}: ${report.detail}")
            }
        }
    }

    // -- install window: gate -> session -> commit (U11 task requirement 3) --

    fun prepareInstall(): ApkInstallDecision {
        val pending = ledger.pending() ?: return ApkInstallDecision.NothingToInstall
        if (pending.terminalOutcome != null) return ApkInstallDecision.NothingToInstall
        return when {
            pending.stage == ApkStage.AWAITING_USER_ACTION ->
                ApkInstallDecision.HeldAwaitingUserAction(pending)
            pending.candidate.releaseStatus == "RETIRED" ->
                ApkInstallDecision.HeldRetiredRelease(pending)
            pending.stage != ApkStage.REPORTED_DOWNLOADED ->
                ApkInstallDecision.PendingDownloadIncomplete
            gate.hasUnfinishedTaskRows() -> ApkInstallDecision.BlockedDeviceBusy
            gate.hasPendingCriticalReports() -> ApkInstallDecision.BlockedCriticalReports
            else -> {
                if (claimSuspension == null) claimSuspension = gate.suspendClaiming()
                installer.createSession().use { session ->
                    // Persist the session identity BEFORE staging/committing so a
                    // crash anywhere after this line leaves a resolvable intent.
                    ledger.record(pending.copy(stage = ApkStage.SESSION_STAGED, sessionId = session.sessionId, updatedAt = now()))
                    session.stage(transfer.readyFile(artifactKey(pending.candidate.candidateId)))
                    session.commit()
                    ledger.record(pending.copy(stage = ApkStage.SESSION_COMMITTED, sessionId = session.sessionId, updatedAt = now()))
                    ApkInstallDecision.ReadyToCommit(session.sessionId, pending.candidate)
                }
            }
        }
    }

    // -- installer statuses (PENDING_USER_ACTION / failure / success) --

    /**
     * Feeds a PackageInstaller status delivery into the state machine.
     * Returns a terminal receipt when the install attempt ended, else null
     * (PENDING_USER_ACTION is a persisted waiting state — never success).
     */
    fun onInstallerStatus(sessionId: Int, outcome: ApkInstallerOutcome, message: String?): ApkInstallReceipt? {
        val pending = ledger.pending() ?: return null
        if (pending.sessionId != null && pending.sessionId != sessionId) return null
        return when (outcome) {
            ApkInstallerOutcome.PENDING_USER_ACTION -> {
                ledger.record(pending.copy(stage = ApkStage.AWAITING_USER_ACTION, updatedAt = now()))
                null
            }
            ApkInstallerOutcome.SUCCESS -> finishWithVerification(pending, message)
            ApkInstallerOutcome.FAILURE_ABORTED ->
                terminal(pending, ApkReceiptOutcome.USER_DECLINED, message, installedVersionCode = device.installedVersionCode(pending.candidate.packageName))
            else -> terminal(pending, ApkReceiptOutcome.FAILED, message, installedVersionCode = device.installedVersionCode(pending.candidate.packageName))
        }
    }

    /** Success is only believed after the installed package fact confirms it. */
    private fun finishWithVerification(pending: ApkPendingInstall, message: String?): ApkInstallReceipt {
        val installed = device.installedVersionCode(pending.candidate.packageName)
        return if (installed == pending.candidate.versionCode) {
            terminal(pending, ApkReceiptOutcome.INSTALLED, message, installedVersionCode = installed)
        } else {
            // Fail closed: the session claimed success but the device still runs
            // something else — report interrupted, never success.
            terminal(pending, ApkReceiptOutcome.INTERRUPTED, "success status but installed versionCode is $installed", installedVersionCode = installed)
        }
    }

    private fun terminal(
        pending: ApkPendingInstall,
        outcome: ApkReceiptOutcome,
        message: String?,
        installedVersionCode: Int?,
    ): ApkInstallReceipt {
        val signatureMatched = device.installedSignatureDigest(pending.candidate.packageName)
            ?.let { it.lowercase() == pending.candidate.signatureDigest }
        ledger.record(pending.copy(stage = ApkStage.SUCCESS_OBSERVED, terminalOutcome = outcome, updatedAt = now()))
        val receipt = ApkInstallReceipt(
            candidateId = pending.candidate.candidateId,
            releaseId = pending.candidate.releaseId,
            packageName = pending.candidate.packageName,
            attemptedVersionCode = pending.candidate.versionCode,
            outcome = outcome,
            installedVersionCode = installedVersionCode,
            signatureMatched = signatureMatched,
            message = message,
            completedAt = now(),
        )
        ledger.appendReceipt(receipt)
        // The install window is over either way; resume claiming.
        claimSuspension?.close()
        claimSuspension = null
        // The verified artifact has been consumed by the installer session.
        if (outcome != ApkReceiptOutcome.INSTALLED) transfer.discard(artifactKey(pending.candidate.candidateId))
        ledger.clearPending()
        return receipt
    }

    // -- reboot / process-death recovery (U11 task requirement 2 and 4) --

    /**
     * Reconciles the persisted ledger against reality after a restart:
     * 1. replays installer statuses journaled by the receiver before attach;
     * 2. verifies a committed session against the actually-installed package —
     *    an install that died with the process/reboot is reported INTERRUPTED,
     *    a completed one is reported INSTALLED (correct continuation);
     * 3. keeps AWAITING_USER_ACTION pending (reboot never auto-confirms);
     * 4. pre-install stages simply resume via [poll].
     */
    fun recoverAfterRestart(): ApkRecoveryResult {
        val replayed = ledger.drainStatusEvents()
        val receipts = mutableListOf<ApkInstallReceipt>()
        replayed.forEach { event ->
            onInstallerStatus(event.sessionId, event.outcome, event.message)?.let { receipts += it }
        }
        val pending = ledger.pending()
        if (pending == null || pending.terminalOutcome != null) {
            return ApkRecoveryResult(receipts, ledger.pending(), replayed.size)
        }
        return when (pending.stage) {
            ApkStage.SESSION_STAGED, ApkStage.SESSION_COMMITTED, ApkStage.SUCCESS_OBSERVED -> {
                val installed = device.installedVersionCode(pending.candidate.packageName)
                val signatureMatched = device.installedSignatureDigest(pending.candidate.packageName)
                    ?.let { it.lowercase() == pending.candidate.signatureDigest }
                if (installed == pending.candidate.versionCode && signatureMatched != false) {
                    receipts += terminal(pending, ApkReceiptOutcome.INSTALLED, "reconciled after restart", installedVersionCode = installed)
                } else {
                    // The session died with the process/reboot: a committed
                    // intent is NOT an installed app. Fail closed.
                    receipts += terminal(
                        pending,
                        ApkReceiptOutcome.INTERRUPTED,
                        "install session did not complete before restart (installed=$installed)",
                        installedVersionCode = installed,
                    )
                }
                ApkRecoveryResult(receipts, ledger.pending(), replayed.size)
            }
            ApkStage.AWAITING_USER_ACTION ->
                // Deliberately kept pending: the pending user intent stays
                // distinguishable and is re-surfaced, never auto-confirmed.
                ApkRecoveryResult(receipts, pending, replayed.size)
            ApkStage.DOWNLOADING, ApkStage.DOWNLOADED, ApkStage.REPORTED_DOWNLOADED -> {
                // Nothing was handed to the installer yet; resume via poll().
                ApkRecoveryResult(receipts, pending, replayed.size)
            }
            ApkStage.TERMINAL -> ApkRecoveryResult(receipts, pending, replayed.size)
        }
    }

    // -- receipt drain + reconnect re-report (U11 task requirement 4) --

    /** Attempts delivery of every undelivered receipt; persisted across restarts until accepted. */
    fun drainReceipts(): List<ApkInstallReceipt> {
        val delivered = mutableListOf<ApkInstallReceipt>()
        ledger.undeliveredReceipts().forEach { receipt ->
            if (client.reportInstallReceipt(receipt)) {
                ledger.markReceiptDelivered(receipt)
                delivered += receipt
            }
        }
        return delivered
    }

    /**
     * Reconnect re-report payload (merged by the caller into the device
     * heartbeat / capabilities re-upload): current installed versions of the
     * tracked packages, install-permission readiness and any pending install
     * stage. After MY_PACKAGE_REPLACED this is what makes the server's
     * `target_app_versions` and permission view converge again.
     */
    fun statusReport(): JSONObject {
        val pending = ledger.pending()
        val tracked = mutableSetOf<String>()
        pending?.let { tracked += it.candidate.packageName }
        ledger.undeliveredReceipts().forEach { tracked += it.packageName }
        val packages = JSONObject()
        tracked.forEach { name ->
            packages.put(
                name,
                JSONObject()
                    .put("versionCode", device.installedVersionCode(name) ?: JSONObject.NULL)
                    .put("signatureDigest", device.installedSignatureDigest(name) ?: JSONObject.NULL),
            )
        }
        return JSONObject()
            .put("reportedAt", now())
            .put("canRequestPackageInstalls", device.canRequestInstalls())
            .put("sdkInt", device.sdkInt)
            .put("abis", org.json.JSONArray(device.abis.sorted()))
            .put("packages", packages)
            .put(
                "pendingInstall",
                if (pending == null) JSONObject.NULL else JSONObject()
                    .put("candidateId", pending.candidate.candidateId)
                    .put("packageName", pending.candidate.packageName)
                    .put("stage", pending.stage.name),
            )
    }

    private fun artifactKey(candidateId: String): String = "apk-$candidateId"

    private fun now(): String = clock().toString()
}
