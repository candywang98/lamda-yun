package com.company.cloudctl.companion.updates

import com.company.cloudctl.companion.automation.RecipeCatalog
import com.company.cloudctl.companion.automation.RecipeCatalogTest
import org.json.JSONObject
import org.junit.After
import org.junit.Before
import org.junit.Test
import java.io.File
import java.io.IOException
import java.nio.file.Files
import kotlin.test.*

/** Pure-JVM tests for the U11 ledger, unified artifact transfer and candidate parsing. */
class ApkUpdateModelsTest {
    private lateinit var root: File
    private lateinit var transfer: ArtifactTransfer
    private lateinit var ledger: FileApkUpdateLedger

    private val bytes = "artifact-bytes-0123456789".repeat(8).toByteArray()

    @Before
    fun setup() {
        root = Files.createTempDirectory("apk-u11-models").toFile()
        transfer = ArtifactTransfer(File(root, "artifacts"))
        ledger = FileApkUpdateLedger(root)
    }

    @After
    fun cleanup() {
        RecipeCatalog.clear()
        root.deleteRecursively()
    }

    private fun sha256(value: ByteArray): String =
        java.security.MessageDigest.getInstance("SHA-256").digest(value).joinToString("") { "%02x".format(it) }

    private fun candidateJson(candidateId: String = "cand-1", versionCode: Int = 21): JSONObject = JSONObject()
        .put("candidateId", candidateId)
        .put("releaseId", "rel-1")
        .put("releaseStatus", "ACTIVE")
        .put("status", "OFFERED")
        .put("packageName", "com.example.target")
        .put("versionCode", versionCode)
        .put("versionName", "1.2.1")
        .put("sha256", sha256("apk".toByteArray()))
        .put("signatureDigest", sha256("sig".toByteArray()))
        .put("sourceRef", "https://artifacts.example/target.apk")
        .put("ring", "all")
        .put("dataSchema", JSONObject().put("minCompatible", 1).put("current", 2))
        .put("requiresUserConfirmation", true)
        .put("assignedAt", "2026-09-17T00:00:00Z")

    @Test
    fun candidateParsingMirrorsServerCandidateViewAndFailsClosedOnMalformed() {
        val parsed = ApkInstallCandidate.fromJson(candidateJson())
        assertEquals("cand-1", parsed.candidateId)
        assertEquals(21, parsed.versionCode)
        assertEquals(ApkDataSchemaWindow(1, 2), parsed.dataSchema)
        assertTrue(parsed.requiresUserConfirmation)
        val listed = ApkInstallCandidate.listFrom("""{"items":[${candidateJson()}]}""")
        assertEquals(listOf(parsed), listed)
        // Missing releaseStatus or a bad sha fails closed instead of defaulting.
        val missing = candidateJson().apply { remove("releaseStatus") }
        assertFailsWith<Exception> { ApkInstallCandidate.fromJson(missing) }
        val badSha = candidateJson().put("sha256", "not-a-digest")
        assertFailsWith<IllegalArgumentException> { ApkInstallCandidate.fromJson(badSha) }
    }

    @Test
    fun ledgerRoundTripsPendingReceiptsFailuresAndStatusInboxAcrossRestart() {
        val candidate = ApkInstallCandidate.fromJson(candidateJson())
        ledger.record(ApkPendingInstall(candidate, ApkStage.DOWNLOADING, attempts = 1, updatedAt = "t0"))
        ledger.appendReceipt(
            ApkInstallReceipt(
                candidateId = "cand-1", releaseId = "rel-1", packageName = candidate.packageName,
                attemptedVersionCode = 21, outcome = ApkReceiptOutcome.INSTALLED, installedVersionCode = 21,
                signatureMatched = true, message = null, completedAt = "t1",
            ),
        )
        ledger.appendStatusEvent(
            ApkInstallerStatusEvent(11, ApkInstallerOutcome.PENDING_USER_ACTION, null, "t2"),
        )
        ledger.noteFailure(ApkCandidateFailure("cand-1", candidate.sha256, 21, "VERSION_DOWNGRADE", "t3"))

        val reopened = FileApkUpdateLedger(root) // restart: fresh instance, same disk
        assertEquals(ApkStage.DOWNLOADING, reopened.pending()!!.stage)
        assertEquals(candidate, reopened.pending()!!.candidate)
        assertEquals(1, reopened.undeliveredReceipts().size)
        assertEquals(1, reopened.failures().size)
        val drained = reopened.drainStatusEvents()
        assertEquals(1, drained.size)
        assertEquals(ApkInstallerOutcome.PENDING_USER_ACTION, drained[0].outcome)
        assertTrue(reopened.drainStatusEvents().isEmpty())
        assertFalse(File(root, ".ledger-tmp.json").exists()) // atomic writes never leave temps
    }

    @Test
    fun corruptLedgerFailsClosedInsteadOfSilentlyResetting() {
        File(root, "ledger.json").writeText("{ this is not json")
        assertFailsWith<LedgerCorruptException> { ledger.pending() }
    }

    @Test
    fun transferStagesVerifiesAtomicallyAndReusesRetainedFile() {
        val digest = sha256(bytes)
        assertEquals(bytes.size.toLong(), transfer.stage("apk-cand-1", digest, 1024 * 1024) { it.write(bytes) })
        assertContentEquals(bytes, transfer.readyFile("apk-cand-1").readBytes())
        // A retained, verified ready file is reused without invoking the writer.
        assertEquals(bytes.size.toLong(), transfer.stage("apk-cand-1", digest, 1024 * 1024) { error("must reuse retained artifact") })
        // A corrupted retained file is discarded and re-staged from scratch.
        transfer.readyFile("apk-cand-1").writeBytes("junk".toByteArray())
        assertEquals(bytes.size.toLong(), transfer.stage("apk-cand-1", digest, 1024 * 1024) { it.write(bytes) })
        assertContentEquals(bytes, transfer.readyFile("apk-cand-1").readBytes())
    }

    @Test
    fun failingOrHashMismatchedTransferLeavesNoPartialFile() {
        assertFailsWith<IOException> {
            transfer.stage("apk-x", sha256(bytes), 1024 * 1024) {
                it.write(bytes)
                throw IOException("connection reset mid-stream")
            }
        }
        assertFailsWith<ArtifactHashMismatchException> {
            transfer.stage("apk-x", sha256("other".toByteArray()), 1024 * 1024) { it.write(bytes) }
        }
        assertTrue(transfer.readyFile("apk-x").let { !it.exists() })
        val leftovers = File(root, "artifacts").listFiles()?.filter { it.isFile } ?: emptyList()
        assertTrue(leftovers.isEmpty(), "interrupted transfers must not leave temp files: $leftovers")
    }

    @Test
    fun oversizedArtifactFailsClosed() {
        assertFailsWith<ArtifactTooLargeException> {
            transfer.stage("apk-big", sha256(bytes), 4) { it.write(bytes) }
        }
        assertFalse(transfer.readyFile("apk-big").exists())
    }

    @Test
    fun recipePipelineUnifiedStagingFeedsPackageManagerWithoutHalfFiles() {
        val keys = mapOf(
            "test-automation-1" to "A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg=",
            "phase1-recipe-1" to "LZxWUG0N3Ke3PiBS2nGPZm0PMVa2lIJfJQynfu/oR4M=",
        )
        val manager = RecipePackageManager(File(root, "recipes"), keys)
        val pipeline = RecipeArtifactPipeline(transfer, manager)
        val body = RecipeCatalogTest.SIGNED_PROBE
        val ref = RecipeReference("version-u11", JSONObject(body).getJSONObject("manifest").getString("hash"), 1)

        var fetches = 0
        val encoded = pipeline.ensure(ref) {
            fetches++
            RecipeDownload(body, ref.sha256)
        }
        assertEquals(1, fetches)
        assertEquals(body, encoded)
        assertEquals(body, manager.load(ref))
        // The retained package serves the next ensure without a re-download.
        assertEquals(body, pipeline.ensure(ref) { error("retained recipe package must be reused") })

        // An interrupted recipe download leaves neither a version directory nor staged bytes.
        val interrupted = RecipeReference("version-u11-missing", ref.sha256, 1)
        assertFailsWith<IOException> {
            pipeline.ensure(interrupted) { throw IOException("interrupted") }
        }
        assertFalse(File(File(root, "recipes"), "versions/version-u11-missing").exists())
        assertFalse(File(File(root, "artifacts"), "ready/recipe-version-u11-missing").exists())
        val leftovers = File(root, "artifacts").listFiles()?.filter { it.isFile } ?: emptyList()
        assertTrue(leftovers.isEmpty(), "no half recipe files: $leftovers")
    }
}
