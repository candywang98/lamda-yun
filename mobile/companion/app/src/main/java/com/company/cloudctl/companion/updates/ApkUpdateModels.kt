package com.company.cloudctl.companion.updates

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.OutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest

/**
 * U11 (fleet-first-20260916.1): device-side models, persistence ledger and the
 * unified artifact download pipeline for apk-release/v1@20260917.1 install
 * candidates. This file deliberately has ZERO Android framework imports so the
 * whole state machine is unit-testable on the plain JVM (the thin Android
 * PackageInstaller bridge lives in [ApkInstallReceiver.kt]).
 *
 * Field alignment: `ApkInstallCandidate.fromJson` mirrors the server's
 * `_candidate_view` (services/control-api/src/cloudctl_api/apk_releases.py),
 * which is the payload of `GET /companion/v2/apk/candidates` items.
 */

// ---------------------------------------------------------------------------
// Candidate model (apk-release/v1 installCandidate)
// ---------------------------------------------------------------------------

data class ApkDataSchemaWindow(val minCompatible: Int, val current: Int) {
    init {
        require(minCompatible in 1..current) { "Invalid data schema window" }
    }
}

data class ApkInstallCandidate(
    val candidateId: String,
    val releaseId: String,
    val releaseStatus: String, // ACTIVE | RETIRED
    val status: String, // OFFERED | DOWNLOADED (INSTALLED rows are not listed anymore)
    val packageName: String,
    val versionCode: Int,
    val versionName: String,
    val sha256: String,
    val signatureDigest: String,
    val sourceRef: String,
    val ring: String,
    val dataSchema: ApkDataSchemaWindow,
    val requiresUserConfirmation: Boolean,
    val assignedAt: String,
) {
    init {
        require(Regex("^[0-9a-f]{64}$").matches(sha256)) { "Invalid candidate sha256" }
        require(Regex("^[0-9a-f]{64}$").matches(signatureDigest)) { "Invalid candidate signatureDigest" }
        require(releaseStatus in RELEASE_STATUSES) { "Invalid releaseStatus" }
        require(status in CANDIDATE_STATUSES) { "Invalid candidate status" }
        require(ring in RINGS) { "Invalid ring" }
        require(versionCode >= 0 && packageName.isNotBlank() && sourceRef.isNotBlank())
    }

    fun toJson(): JSONObject = JSONObject()
        .put("candidateId", candidateId)
        .put("releaseId", releaseId)
        .put("releaseStatus", releaseStatus)
        .put("status", status)
        .put("packageName", packageName)
        .put("versionCode", versionCode)
        .put("versionName", versionName)
        .put("sha256", sha256)
        .put("signatureDigest", signatureDigest)
        .put("sourceRef", sourceRef)
        .put("ring", ring)
        .put("dataSchema", JSONObject().put("minCompatible", dataSchema.minCompatible).put("current", dataSchema.current))
        .put("requiresUserConfirmation", requiresUserConfirmation)
        .put("assignedAt", assignedAt)

    companion object {
        val RELEASE_STATUSES = setOf("ACTIVE", "RETIRED")
        val CANDIDATE_STATUSES = setOf("OFFERED", "DOWNLOADED")
        val RINGS = setOf("canary", "early", "all")

        /** Fail-closed parsing: unknown or malformed candidates are rejected, never defaulted. */
        fun fromJson(root: JSONObject): ApkInstallCandidate = ApkInstallCandidate(
            candidateId = root.getString("candidateId"),
            releaseId = root.getString("releaseId"),
            releaseStatus = root.getString("releaseStatus"),
            status = root.getString("status"),
            packageName = root.getString("packageName"),
            versionCode = root.getInt("versionCode"),
            versionName = root.getString("versionName"),
            sha256 = root.getString("sha256").lowercase(),
            signatureDigest = root.getString("signatureDigest").lowercase(),
            sourceRef = root.getString("sourceRef"),
            ring = root.getString("ring"),
            dataSchema = ApkDataSchemaWindow(
                minCompatible = root.getJSONObject("dataSchema").getInt("minCompatible"),
                current = root.getJSONObject("dataSchema").getInt("current"),
            ),
            requiresUserConfirmation = root.getBoolean("requiresUserConfirmation"),
            assignedAt = root.getString("assignedAt"),
        )

        /** `GET /companion/v2/apk/candidates` returns `{"items": [...]}`. */
        fun listFrom(responseBody: String): List<ApkInstallCandidate> {
            val root = JSONObject(responseBody)
            val items = root.getJSONArray("items")
            return (0 until items.length()).map { fromJson(items.getJSONObject(it)) }
        }
    }
}

// ---------------------------------------------------------------------------
// Persisted install state (the device-side pending ledger)
// ---------------------------------------------------------------------------

/**
 * Local install stages. The server only knows OFFERED -> DOWNLOADED -> INSTALLED;
 * everything between REPORTED_DOWNLOADED and a terminal outcome is device-local
 * and MUST survive a reboot so an in-flight install intent is never mistaken
 * for a success (or silently lost).
 */
enum class ApkStage {
    DOWNLOADING,
    DOWNLOADED,
    REPORTED_DOWNLOADED,
    SESSION_STAGED,
    SESSION_COMMITTED,
    AWAITING_USER_ACTION,
    SUCCESS_OBSERVED,
    TERMINAL,
}

/** Terminal receipt outcomes reported upstream. */
enum class ApkReceiptOutcome { INSTALLED, FAILED, USER_DECLINED, INTERRUPTED }

/** Mirrors android.content.pm.PackageInstaller status constants without the framework. */
enum class ApkInstallerOutcome {
    PENDING_USER_ACTION,
    SUCCESS,
    FAILURE,
    FAILURE_BLOCKED,
    FAILURE_ABORTED,
    FAILURE_INVALID,
    FAILURE_CONFLICT,
    FAILURE_STORAGE,
    FAILURE_INCOMPATIBLE,
}

data class ApkPendingInstall(
    val candidate: ApkInstallCandidate,
    val stage: ApkStage,
    val sessionId: Int? = null,
    val bytesWritten: Long = 0,
    val attempts: Int = 0,
    val updatedAt: String,
    val terminalOutcome: ApkReceiptOutcome? = null,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("candidate", candidate.toJson())
        .put("stage", stage.name)
        .put("sessionId", sessionId ?: JSONObject.NULL)
        .put("bytesWritten", bytesWritten)
        .put("attempts", attempts)
        .put("updatedAt", updatedAt)
        .put("terminalOutcome", terminalOutcome?.name ?: JSONObject.NULL)

    companion object {
        fun fromJson(root: JSONObject): ApkPendingInstall = ApkPendingInstall(
            candidate = ApkInstallCandidate.fromJson(root.getJSONObject("candidate")),
            stage = runCatching { ApkStage.valueOf(root.getString("stage")) }
                .getOrElse { throw IllegalArgumentException("Unknown install stage $it") },
            sessionId = if (root.isNull("sessionId")) null else root.getInt("sessionId"),
            bytesWritten = root.optLong("bytesWritten", 0),
            attempts = root.optInt("attempts", 0),
            updatedAt = root.getString("updatedAt"),
            terminalOutcome = if (root.isNull("terminalOutcome")) null
            else runCatching { ApkReceiptOutcome.valueOf(root.getString("terminalOutcome")) }
                .getOrElse { throw IllegalArgumentException("Unknown terminal outcome $it") },
        )
    }
}

/**
 * Install receipt handed to the (seam) `:report-installed` companion endpoint.
 * Aligned with the candidate/target identity fields U10 already persists, so
 * the server can join on (candidateId, releaseId, packageName, versionCode).
 */
data class ApkInstallReceipt(
    val candidateId: String,
    val releaseId: String,
    val packageName: String,
    val attemptedVersionCode: Int,
    val outcome: ApkReceiptOutcome,
    val installedVersionCode: Int?,
    val signatureMatched: Boolean?,
    val message: String?,
    val completedAt: String,
    val delivered: Boolean = false,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("candidateId", candidateId)
        .put("releaseId", releaseId)
        .put("packageName", packageName)
        .put("attemptedVersionCode", attemptedVersionCode)
        .put("outcome", outcome.name)
        .put("installedVersionCode", installedVersionCode ?: JSONObject.NULL)
        .put("signatureMatched", signatureMatched ?: JSONObject.NULL)
        .put("message", message ?: JSONObject.NULL)
        .put("completedAt", completedAt)
        .put("delivered", delivered)

    /** Wire payload for the receipt endpoint seam (see ApkReleaseClient.reportInstallReceipt). */
    fun toWireJson(): JSONObject = toJson().apply { remove("delivered") }

    companion object {
        fun fromJson(root: JSONObject): ApkInstallReceipt = ApkInstallReceipt(
            candidateId = root.getString("candidateId"),
            releaseId = root.getString("releaseId"),
            packageName = root.getString("packageName"),
            attemptedVersionCode = root.getInt("attemptedVersionCode"),
            outcome = runCatching { ApkReceiptOutcome.valueOf(root.getString("outcome")) }
                .getOrElse { throw IllegalArgumentException("Unknown receipt outcome $it") },
            installedVersionCode = if (root.isNull("installedVersionCode")) null else root.getInt("installedVersionCode"),
            signatureMatched = if (root.isNull("signatureMatched")) null else root.getBoolean("signatureMatched"),
            message = if (root.isNull("message")) null else root.getString("message"),
            completedAt = root.getString("completedAt"),
            delivered = root.optBoolean("delivered", false),
        )
    }
}

/** A PackageInstaller status delivery that arrived before any coordinator attached. */
data class ApkInstallerStatusEvent(
    val sessionId: Int,
    val outcome: ApkInstallerOutcome,
    val message: String?,
    val occurredAt: String,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("sessionId", sessionId)
        .put("outcome", outcome.name)
        .put("message", message ?: JSONObject.NULL)
        .put("occurredAt", occurredAt)

    companion object {
        fun fromJson(root: JSONObject): ApkInstallerStatusEvent = ApkInstallerStatusEvent(
            sessionId = root.getInt("sessionId"),
            outcome = runCatching { ApkInstallerOutcome.valueOf(root.getString("outcome")) }
                .getOrElse { throw IllegalArgumentException("Unknown installer outcome $it") },
            message = if (root.isNull("message")) null else root.getString("message"),
            occurredAt = root.getString("occurredAt"),
        )
    }
}

/** A fail-closed candidate rejection remembered so poll() stops re-electing it. */
data class ApkCandidateFailure(
    val candidateId: String,
    val sha256: String,
    val versionCode: Int,
    val reason: String,
    val occurredAt: String,
)

// ---------------------------------------------------------------------------
// Ledger persistence
// ---------------------------------------------------------------------------

class LedgerCorruptException(message: String) : IllegalStateException(message)

/**
 * Durable device-side install ledger: ONE pending install at a time, undelivered
 * receipts and pre-attach installer status events. Written atomically
 * (temp file + fsync + rename) exactly like the P14 recipe staging pattern, so
 * a crash mid-write never destroys the previous consistent state.
 */
interface ApkUpdateLedger {
    fun pending(): ApkPendingInstall?
    fun record(state: ApkPendingInstall)
    fun clearPending()

    fun failures(): List<ApkCandidateFailure>
    fun noteFailure(failure: ApkCandidateFailure)
    fun clearFailure(candidateId: String)

    fun appendReceipt(receipt: ApkInstallReceipt)
    fun undeliveredReceipts(): List<ApkInstallReceipt>
    fun markReceiptDelivered(receipt: ApkInstallReceipt)

    fun appendStatusEvent(event: ApkInstallerStatusEvent)
    fun drainStatusEvents(): List<ApkInstallerStatusEvent>
}

class FileApkUpdateLedger(private val root: File) : ApkUpdateLedger {
    private val file = File(root, "ledger.json")
    private val temp = File(root, ".ledger-tmp.json")

    private data class State(
        val pending: JSONObject?,
        val failures: JSONArray,
        val receipts: JSONArray,
        val statusInbox: JSONArray,
    )

    @Synchronized
    fun existsOnDisk(): Boolean = file.isFile

    @Synchronized
    override fun pending(): ApkPendingInstall? = read().pending?.let { ApkPendingInstall.fromJson(it) }

    @Synchronized
    override fun record(state: ApkPendingInstall) = mutate { it.put("pending", state.toJson()) }

    @Synchronized
    override fun clearPending() = mutate { it.put("pending", JSONObject.NULL) }

    @Synchronized
    override fun failures(): List<ApkCandidateFailure> {
        val array = read().failures
        return (0 until array.length()).map {
            val row = array.getJSONObject(it)
            ApkCandidateFailure(
                candidateId = row.getString("candidateId"),
                sha256 = row.getString("sha256"),
                versionCode = row.getInt("versionCode"),
                reason = row.getString("reason"),
                occurredAt = row.getString("occurredAt"),
            )
        }
    }

    @Synchronized
    override fun noteFailure(failure: ApkCandidateFailure) = mutate { root ->
        val array = root.getJSONArray("failures")
        for (index in 0 until array.length()) {
            if (array.getJSONObject(index).getString("candidateId") == failure.candidateId) {
                array.put(index, failureJson(failure))
                return@mutate
            }
        }
        array.put(failureJson(failure))
    }

    @Synchronized
    override fun clearFailure(candidateId: String) = mutate { root ->
        val array = root.getJSONArray("failures")
        var index = 0
        while (index < array.length()) {
            if (array.getJSONObject(index).getString("candidateId") == candidateId) array.remove(index) else index++
        }
    }

    @Synchronized
    override fun appendReceipt(receipt: ApkInstallReceipt) = mutate { it.getJSONArray("receipts").put(receipt.toJson()) }

    @Synchronized
    override fun undeliveredReceipts(): List<ApkInstallReceipt> {
        val array = read().receipts
        return (0 until array.length())
            .map { ApkInstallReceipt.fromJson(array.getJSONObject(it)) }
            .filterNot { it.delivered }
    }

    @Synchronized
    override fun markReceiptDelivered(receipt: ApkInstallReceipt) = mutate { root ->
        val array = root.getJSONArray("receipts")
        for (index in 0 until array.length()) {
            val row = array.getJSONObject(index)
            if (row.getString("candidateId") == receipt.candidateId &&
                row.getString("outcome") == receipt.outcome.name &&
                row.getString("completedAt") == receipt.completedAt
            ) {
                row.put("delivered", true)
            }
        }
    }

    @Synchronized
    override fun appendStatusEvent(event: ApkInstallerStatusEvent) = mutate { it.getJSONArray("statusInbox").put(event.toJson()) }

    @Synchronized
    override fun drainStatusEvents(): List<ApkInstallerStatusEvent> {
        val state = read()
        val events = (0 until state.statusInbox.length())
            .map { ApkInstallerStatusEvent.fromJson(state.statusInbox.getJSONObject(it)) }
        if (events.isNotEmpty()) mutate { it.put("statusInbox", JSONArray()) }
        return events
    }

    private fun failureJson(failure: ApkCandidateFailure): JSONObject = JSONObject()
        .put("candidateId", failure.candidateId)
        .put("sha256", failure.sha256)
        .put("versionCode", failure.versionCode)
        .put("reason", failure.reason)
        .put("occurredAt", failure.occurredAt)

    private fun read(): State {
        if (!file.isFile) {
            return State(null, JSONArray(), JSONArray(), JSONArray())
        }
        val root = try {
            JSONObject(file.readText(Charsets.UTF_8))
        } catch (error: Exception) {
            throw LedgerCorruptException("apk update ledger is unreadable: ${error.message}")
        }
        if (root.optInt("version") != 1) throw LedgerCorruptException("unsupported apk update ledger version")
        return State(
            pending = if (root.isNull("pending")) null else root.getJSONObject("pending"),
            failures = root.optJSONArray("failures") ?: JSONArray(),
            receipts = root.optJSONArray("receipts") ?: JSONArray(),
            statusInbox = root.optJSONArray("statusInbox") ?: JSONArray(),
        )
    }

    private fun mutate(change: (JSONObject) -> Unit) {
        val root = if (file.isFile) {
            try {
                JSONObject(file.readText(Charsets.UTF_8))
            } catch (error: Exception) {
                throw LedgerCorruptException("apk update ledger is unreadable: ${error.message}")
            }
        } else {
            JSONObject().put("version", 1).put("pending", JSONObject.NULL)
                .put("failures", JSONArray()).put("receipts", JSONArray()).put("statusInbox", JSONArray())
        }
        change(root)
        check(file.parentFile!!.mkdirs() || file.parentFile!!.isDirectory) { "apk update ledger directory unavailable" }
        FileOutputStream(temp).use { output ->
            output.write(root.toString().toByteArray(Charsets.UTF_8))
            output.fd.sync()
        }
        // Publish the complete ledger at once; a crash before this line keeps
        // the previous consistent state and at most an orphan temp file.
        Files.move(temp.toPath(), file.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
    }
}

// ---------------------------------------------------------------------------
// Unified artifact download pipeline (APK + Recipe share this)
// ---------------------------------------------------------------------------

class ArtifactHashMismatchException(val expected: String, val actual: String) :
    IllegalStateException("artifact sha-256 mismatch: expected $expected but downloaded $actual")

class ArtifactTooLargeException(val maxBytes: Long) :
    IllegalStateException("artifact exceeds the transfer limit of $maxBytes bytes")

/** OutputStream wrapper that digests and size-caps every byte written. */
class CountingDigestSink(private val delegate: OutputStream, private val maxBytes: Long) : OutputStream() {
    private val digest = MessageDigest.getInstance("SHA-256")
    var bytesWritten: Long = 0
        private set

    override fun write(byte: Int) = write(byteArrayOf(byte.toByte()), 0, 1)

    override fun write(buffer: ByteArray, offset: Int, length: Int) {
        if (bytesWritten + length > maxBytes) throw ArtifactTooLargeException(maxBytes)
        digest.update(buffer, offset, length)
        delegate.write(buffer, offset, length)
        bytesWritten += length
    }

    fun sha256Hex(): String = digest.digest().joinToString("") { "%02x".format(it) }
}

/**
 * Unified two-artifact download orchestration (U11 task requirement 1):
 * temp file -> SHA-256 verification -> atomic ready-file. Recipe packages
 * (text bodies consumed by [RecipePackageManager]) and APK files both flow
 * through this class. Two variants:
 *  - [stage] enforces a raw-byte digest match — used for APKs where
 *    `candidate.sha256` is the file hash (apk-release/v1).
 *  - [stageRaw] stages bytes and reports their digest — used for recipes,
 *    whose transport checksum is the CANONICAL recipe hash (not a raw-byte
 *    digest); semantic verification (canonical hash + Ed25519 signature +
 *    atomic visibility) stays in the read-only P14 [RecipePackageManager].
 *
 * Interrupted or failed transfers never leave a half file behind: the fixed
 * `.tmp-<key>` name is removed before staging and in a finally block, and the
 * ready name only ever appears via an atomic rename.
 */
class ArtifactTransfer(private val root: File) {
    init {
        check(root.isDirectory || root.mkdirs()) { "artifact transfer directory unavailable" }
        val readyDir = File(root, "ready")
        check(readyDir.isDirectory || readyDir.mkdirs()) { "artifact ready directory unavailable" }
    }

    /** Staged artifact facts: byte count and raw-byte SHA-256 digest. */
    data class Staged(val bytes: Long, val sha256Hex: String)

    fun readyFile(key: String): File {
        require(KEY_PATTERN.matches(key)) { "Invalid artifact key" }
        val file = File(File(root, "ready"), key).canonicalFile
        require(file.parentFile == File(root, "ready").canonicalFile) { "Invalid artifact ready path" }
        return file
    }

    private fun tempFile(key: String): File {
        require(KEY_PATTERN.matches(key)) { "Invalid artifact key" }
        return File(root, ".tmp-$key").canonicalFile
    }

    /**
     * Idempotent: a retained ready file is re-verified and reused; anything
     * else streams through [write] into the temp file, fsyncs, compares the
     * digest and atomically renames. Returns the staged byte count.
     */
    fun stage(key: String, expectedSha256: String, maxBytes: Long, write: (CountingDigestSink) -> Unit): Long {
        require(Regex("^[0-9a-f]{64}$").matches(expectedSha256)) { "Invalid expected sha256" }
        val ready = readyFile(key)
        if (ready.isFile) {
            val retained = sha256File(ready)
            if (retained == expectedSha256) return ready.length()
            // A corrupted retained artifact is discarded and re-staged from scratch.
            ready.delete()
        }
        val temp = tempFile(key)
        temp.delete() // a leftover from an interrupted attempt is never appended to
        try {
            val (computed, bytes) = FileOutputStream(temp).use { output ->
                val sink = CountingDigestSink(output, maxBytes)
                write(sink)
                output.fd.sync()
                sink.sha256Hex() to sink.bytesWritten
            }
            if (computed != expectedSha256) throw ArtifactHashMismatchException(expectedSha256, computed)
            Files.move(temp.toPath(), ready.toPath(), StandardCopyOption.ATOMIC_MOVE)
            return bytes
        } finally {
            temp.delete()
        }
    }

    /** Temp-file staging without a digest expectation; digest returned for the caller's own verification. */
    fun stageRaw(key: String, maxBytes: Long, write: (CountingDigestSink) -> Unit): Staged {
        val ready = readyFile(key)
        ready.delete() // staged-raw artifacts are never retained across attempts
        val temp = tempFile(key)
        temp.delete() // a leftover from an interrupted attempt is never appended to
        try {
            val (computed, bytes) = FileOutputStream(temp).use { output ->
                val sink = CountingDigestSink(output, maxBytes)
                write(sink)
                output.fd.sync()
                sink.sha256Hex() to sink.bytesWritten
            }
            Files.move(temp.toPath(), ready.toPath(), StandardCopyOption.ATOMIC_MOVE)
            return Staged(bytes, computed)
        } finally {
            temp.delete()
        }
    }

    fun discard(key: String) {
        readyFile(key).delete()
        tempFile(key).delete()
    }

    fun sha256File(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    companion object {
        val KEY_PATTERN = Regex("^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    }
}

/**
 * Recipe-side adapter of the unified pipeline: same temp -> fsync -> atomic
 * ready discipline as the APK path. The recipe transport checksum is the
 * CANONICAL recipe hash (RecipeLifecycle semantics), not a raw-byte digest,
 * so raw staging is followed by the header equality check plus the P14
 * [RecipePackageManager]'s canonical-hash / Ed25519 verification and atomic
 * versions-directory move. A body that fails verification is discarded and
 * never becomes visible.
 */
class RecipeArtifactPipeline(
    private val transfer: ArtifactTransfer,
    private val packages: RecipePackageManager,
) {
    /** Same semantics as RecipeLifecycle.ensure: retained first, then header checksum, then install. */
    fun ensure(ref: RecipeReference, download: () -> RecipeDownload): String {
        packages.load(ref)?.let { return it }
        val response = download()
        transfer.stageRaw(recipeKey(ref.versionId), MAX_RECIPE_BYTES) { sink ->
            sink.write(response.body.toByteArray(Charsets.UTF_8))
        }
        if (response.sha256?.lowercase() != ref.sha256) {
            transfer.discard(recipeKey(ref.versionId))
            throw IllegalArgumentException("recipe download checksum mismatch")
        }
        val encoded = transfer.readyFile(recipeKey(ref.versionId)).readText(Charsets.UTF_8)
        try {
            packages.install(ref, encoded)
        } catch (error: RuntimeException) {
            // The cached body failed canonical/signature verification: drop it.
            transfer.discard(recipeKey(ref.versionId))
            throw error
        }
        return encoded
    }

    private fun recipeKey(versionId: String): String = "recipe-$versionId"

    companion object {
        const val MAX_RECIPE_BYTES: Long = 8L * 1024 * 1024
    }
}

// ---------------------------------------------------------------------------
// Injected ports (seams the main session wires to real infrastructure)
// ---------------------------------------------------------------------------

/** Companion-side apk-release/v1 client seam; main session adapts CloudTaskClient/PinnedHttpsTransport. */
interface ApkReleaseClient {
    /** GET /companion/v2/apk/candidates */
    fun listCandidates(): List<ApkInstallCandidate>

    /** Streams the APK bytes from the candidate's source into [sink]; transport failures throw IOException. */
    fun downloadApk(candidate: ApkInstallCandidate, sink: OutputStream, maxBytes: Long): Long

    /**
     * POST /companion/v2/apk/candidates/{candidateId}:report-downloaded with
     * `{"sha256": "<64 lowercase hex>"}` (ApkDownloadedReport). A 422
     * APK_DOWNLOAD_HASH_MISMATCH surfaces as [ApkDownloadReportResult.HashMismatch].
     */
    fun reportDownloaded(candidateId: String, sha256: String): ApkDownloadReportResult

    /**
     * Seam: U10's server currently exposes candidates + report-downloaded only.
     * This is the future `:report-installed` companion endpoint; receipts are
     * persisted locally until this returns true so late wiring loses nothing.
     */
    fun reportInstallReceipt(receipt: ApkInstallReceipt): Boolean
}

sealed interface ApkDownloadReportResult {
    data object Accepted : ApkDownloadReportResult

    /** Server-side APK_DOWNLOAD_HASH_MISMATCH (422): the candidate stays OFFERED. */
    data class HashMismatch(val detail: String) : ApkDownloadReportResult

    data class Error(val status: Int, val detail: String) : ApkDownloadReportResult
}

/**
 * Install-time gate (U11 task requirement 3). The implementor reads
 * AutomationStore-style state; it must only ever SUSPEND claim intake —
 * it never stops, kills or force-stops the companion's own services.
 */
interface ApkInstallGate {
    /** True when any un-finished task row exists (AutomationStore.hasUnfinishedTaskRows() semantics). */
    fun hasUnfinishedTaskRows(): Boolean

    /** True when critical report queues (event outbox / control acks) are not drained. */
    fun hasPendingCriticalReports(): Boolean

    /** Stops claiming NEW tasks for the install window; close() resumes. Never force-stops anything. */
    fun suspendClaiming(): ApkClaimSuspension
}

interface ApkClaimSuspension : AutoCloseable {
    val id: String
    override fun close()
}

/** PackageInstaller session abstraction (bridge: AndroidPackageInstallerPort in ApkInstallReceiver.kt). */
interface ApkInstallPort {
    fun createSession(): ApkInstallSession
}

interface ApkInstallSession : AutoCloseable {
    val sessionId: Int
    fun stage(file: File)
    fun commit()
    fun abandon()
}

/** Device facts used for eligibility, rollback and post-install verification. */
interface ApkDeviceStatePort {
    fun installedVersionCode(packageName: String): Int?
    fun installedSignatureDigest(packageName: String): String?
    fun dataSchemaVersion(packageName: String): Int?
    val sdkInt: Int
    val abis: Set<String>
    fun canRequestInstalls(): Boolean
}

/** Marks an IOException as local-storage exhaustion when the platform surfaces it that way. */
fun isStorageExhaustion(error: IOException): Boolean {
    val message = error.message ?: error.cause?.message ?: return false
    return message.contains("space", ignoreCase = true) || message.contains("ENOSPC")
}
