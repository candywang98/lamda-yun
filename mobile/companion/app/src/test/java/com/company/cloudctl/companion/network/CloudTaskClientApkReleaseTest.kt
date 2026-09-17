package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.updates.ApkDownloadReportResult
import com.company.cloudctl.companion.updates.ApkInstallReceipt
import com.company.cloudctl.companion.updates.ApkReceiptOutcome
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * WIRE2 golden shapes: the apk-release/v1 companion calls this client builds
 * must stay byte-compatible with the server models in
 * services/control-api/src/cloudctl_api/apk_releases.py (strict, extra=forbid):
 * ApkDownloadedReport and ApkInstallReceiptReport. Any field added or renamed
 * on either side fails here first.
 */
class CloudTaskClientApkReleaseTest {
    @Test
    fun candidateListCallIsAGetOnTheFrozenPath() {
        val call = buildApkCandidateListCall()
        assertEquals("GET", call.method)
        assertEquals("/companion/v2/apk/candidates", call.path)
        assertEquals(null, call.body)
    }

    @Test
    fun reportDownloadedCallCarriesExactlyTheSha256Field() {
        val sha = "c".repeat(64)
        val call = buildApkReportDownloadedCall("cand-1", sha)
        assertEquals("POST", call.method)
        assertEquals("/companion/v2/apk/candidates/cand-1:report-downloaded", call.path)
        assertEquals(setOf("sha256"), call.body!!.keySet())
        assertEquals(sha, call.body!!.getString("sha256"))
    }

    @Test
    fun reportDownloadedCallRejectsMalformedDigests() {
        assertFailsWith<IllegalArgumentException> {
            buildApkReportDownloadedCall("cand-1", "not-a-digest")
        }
        assertFailsWith<IllegalArgumentException> {
            buildApkReportDownloadedCall(" ", "c".repeat(64))
        }
    }

    @Test
    fun reportInstalledCallMirrorsTheServerReceiptModelFieldSet() {
        val receipt = ApkInstallReceipt(
            candidateId = "cand-1",
            releaseId = "rel-1",
            packageName = "com.example.target",
            attemptedVersionCode = 83201,
            outcome = ApkReceiptOutcome.INSTALLED,
            installedVersionCode = 83201,
            signatureMatched = true,
            message = "ok",
            completedAt = "2026-09-17T00:00:00Z",
        )
        val call = buildApkReportInstalledCall(receipt)
        assertEquals("POST", call.method)
        assertEquals("/companion/v2/apk/candidates/cand-1:report-installed", call.path)
        // ApkInstallReceiptReport (extra=forbid) accepts exactly these fields.
        assertEquals(
            setOf(
                "candidateId",
                "releaseId",
                "packageName",
                "attemptedVersionCode",
                "outcome",
                "installedVersionCode",
                "signatureMatched",
                "message",
                "completedAt",
            ),
            call.body!!.keySet(),
        )
        assertEquals("INSTALLED", call.body!!.getString("outcome"))
        assertEquals(83201, call.body!!.getInt("attemptedVersionCode"))
        // The local-only delivery flag never reaches the wire.
        assertFalse(call.body!!.has("delivered"))
    }

    @Test
    fun reportInstalledCallSerializesNullOptionalsAsJsonNull() {
        val receipt = ApkInstallReceipt(
            candidateId = "cand-1",
            releaseId = "rel-1",
            packageName = "com.example.target",
            attemptedVersionCode = 83201,
            outcome = ApkReceiptOutcome.FAILED,
            installedVersionCode = null,
            signatureMatched = null,
            message = null,
            completedAt = "2026-09-17T00:00:00Z",
        )
        val body = buildApkReportInstalledCall(receipt).body!!
        assertTrue(body.isNull("installedVersionCode"))
        assertTrue(body.isNull("signatureMatched"))
        assertTrue(body.isNull("message"))
        assertEquals("FAILED", body.getString("outcome"))
    }

    @Test
    fun parsesDownloadReportVerdictsFromProblemJson() {
        assertEquals(
            ApkDownloadReportResult.Accepted,
            parseApkDownloadReport(200, """{"candidateId":"cand-1","status":"DOWNLOADED"}"""),
        )
        val mismatch = parseApkDownloadReport(
            422,
            """{"code":"APK_DOWNLOAD_HASH_MISMATCH","detail":"digest differs"}""",
        )
        assertTrue(mismatch is ApkDownloadReportResult.HashMismatch)
        assertEquals("digest differs", (mismatch as ApkDownloadReportResult.HashMismatch).detail)
        val error = parseApkDownloadReport(500, "boom")
        assertTrue(error is ApkDownloadReportResult.Error)
        assertEquals(500, (error as ApkDownloadReportResult.Error).status)
        // A 422 with a different code is a generic error, not a hash mismatch.
        assertTrue(
            parseApkDownloadReport(422, """{"code":"APK_RECEIPT_MISMATCH"}""") is
                ApkDownloadReportResult.Error,
        )
    }

    @Test
    fun receiptDeliveryStopsRetryingExactlyOnSuccessOrProven404() {
        assertTrue(parseApkInstallReceiptDelivery(200))
        assertTrue(parseApkInstallReceiptDelivery(204))
        assertTrue(parseApkInstallReceiptDelivery(404))
        assertFalse(parseApkInstallReceiptDelivery(409))
        assertFalse(parseApkInstallReceiptDelivery(422))
        assertFalse(parseApkInstallReceiptDelivery(500))
    }

    @Test
    fun splitsHttpsSourceRefIntoTransportBaseAndPath() {
        assertEquals(
            "https://artifacts.example" to "/tenant/apk/target.apk",
            splitApkSourceRef("https://artifacts.example/tenant/apk/target.apk"),
        )
        assertEquals(
            "https://artifacts.example:8443" to "/a/b.apk?token=1",
            splitApkSourceRef("https://artifacts.example:8443/a/b.apk?token=1"),
        )
        assertEquals(
            "https://artifacts.example" to "/",
            splitApkSourceRef("https://artifacts.example"),
        )
    }

    @Test
    fun rejectsNonHttpsSourceRefsFailClosed() {
        assertFailsWith<IllegalArgumentException> {
            splitApkSourceRef("s3://tenant/apk/target.apk")
        }
        assertFailsWith<IllegalArgumentException> {
            splitApkSourceRef("http://artifacts.example/target.apk")
        }
        assertFailsWith<IllegalArgumentException> {
            splitApkSourceRef("/relative/path.apk")
        }
    }
}
