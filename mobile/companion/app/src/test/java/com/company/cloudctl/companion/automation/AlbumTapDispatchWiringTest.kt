package com.company.cloudctl.companion.automation

import com.company.cloudctl.companion.locators.AlbumPickDispatcher
import com.company.cloudctl.companion.media.AlbumPick
import com.company.cloudctl.companion.media.MatchBasis
import com.company.cloudctl.companion.observation.Bounds
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * B15X wiring (fleet-first-20260916.1) — the dispatcher's last seam: an
 * APPROVED tap intent flows executor -> consumeAlbumPick -> ui.tapScreenAt
 * with the picker's package, and CoordinateTapPackageGate keeps the
 * coordinate path open for xianyu + the AOSP system galleries ONLY (every
 * other package, including Google Photos and OEM galleries, stays rejected
 * until surveyed on device).
 */
class AlbumTapDispatchWiringTest {
    private val fixedNow = Instant.parse("2026-09-16T08:00:00Z")

    @Test
    fun coordinateTapGateApprovesXianyuAndAospSystemGalleriesOnly() {
        assertTrue(CoordinateTapPackageGate.approves(TargetLocatorRegistry.XIANYU_PACKAGE))
        assertTrue(CoordinateTapPackageGate.approves("com.android.gallery3d"))
        assertTrue(CoordinateTapPackageGate.approves("com.android.gallery"))
        // Extension points, intentionally NOT approved yet (report seam): the
        // Google Photos picker and the OEM galleries need on-device survey.
        listOf(
            "com.google.android.apps.photos",
            "com.miui.gallery",
            "com.huawei.photos",
            "com.sec.android.gallery3d",
            "com.google.android.GoogleCamera",
            "com.company.cloudctl.companion",
            "",
        ).forEach { pkg ->
            assertTrue(!CoordinateTapPackageGate.approves(pkg), "unexpectedly approved: $pkg")
        }
    }

    @Test
    fun consumeAlbumPickForwardsTheApprovedIntentToTapScreenAt() = runBlocking {
        val ui = RecordingTapUi()
        val executor = LocalAutomationExecutor(
            ui = ui,
            now = { fixedNow },
            elapsedMs = { 1_000L },
            sleep = { delay(1) },
        )

        executor.consumeAlbumPick("com.android.gallery3d", approvedIntent())

        // The tap lands in the picker package at the FRESH admitted center.
        assertEquals(listOf(Triple("com.android.gallery3d", 270, 540)), ui.coordinateTaps)
        assertTrue(ui.logs.any { it.second.startsWith("ALBUM_PICK_TAP cell=3") })
    }

    @Test
    fun consumeAlbumPickKeepsWorkingForTheSecondaryAospGalleryPackage() = runBlocking {
        val ui = RecordingTapUi()
        val executor = LocalAutomationExecutor(
            ui = ui,
            now = { fixedNow },
            elapsedMs = { 1_000L },
            sleep = { delay(1) },
        )

        executor.consumeAlbumPick("com.android.gallery", approvedIntent())
        assertEquals(listOf(Triple("com.android.gallery", 270, 540)), ui.coordinateTaps)
    }

    @Test
    fun consumeAlbumPickPropagatesTheUiLayerRejection() = runBlocking {
        // The plain executor UI rejects every coordinate tap (the default
        // COORDINATE_TAP_UNAVAILABLE) — consumeAlbumPick must propagate the
        // fail-closed rejection, never swallow or retry it.
        val ui = RecordingTapUi().apply { rejectCoordinateTaps = true }
        val executor = LocalAutomationExecutor(
            ui = ui,
            now = { fixedNow },
            elapsedMs = { 1_000L },
            sleep = { delay(1) },
        )

        val failure = assertFailsWith<ExecutorFailure> {
            executor.consumeAlbumPick("com.android.gallery3d", approvedIntent())
        }
        assertEquals("COORDINATE_TAP_REJECTED_BY_FAKE", failure.code)
    }

    // ------------------------------------------------------------------
    // helpers
    // ------------------------------------------------------------------

    private fun approvedIntent(): AlbumPickDispatcher.ApprovedTapIntent =
        AlbumPickDispatcher.ApprovedTapIntent(
            pick = AlbumPick(
                assetId = "asset-7",
                orderIndex = 0,
                cellIndex = 3,
                mediaStoreId = 1234L,
                matchedDisplayName = "IMG_1234.jpg",
                basis = MatchBasis.NAME_AND_HASH,
            ),
            tapX = 270,
            tapY = 540,
            admittedBounds = Bounds(left = 180, top = 450, right = 360, bottom = 630),
            identityDigest = "digest-boilerplate",
            admissionReason = "BOUNDS_WITHIN_TOLERANCE",
        )

    private class RecordingTapUi : LocalAutomationUi {
        val coordinateTaps = mutableListOf<Triple<String, Int, Int>>()
        val logs = mutableListOf<Pair<LogLevel, String>>()
        var rejectCoordinateTaps = false

        override fun ensureReady(targetPackage: String) = Unit

        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? = null

        override suspend fun tapScreenAt(targetPackage: String, x: Int, y: Int) {
            if (rejectCoordinateTaps) {
                throw ExecutorFailure("COORDINATE_TAP_REJECTED_BY_FAKE", "fake rejection")
            }
            coordinateTaps += Triple(targetPackage, x, y)
        }

        override suspend fun tap(targetPackage: String, locatorRef: String) = Unit

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit

        override suspend fun screenshot(taskId: String, label: String) =
            ScreenshotEvidence("/private/proof.png", 32, "a".repeat(64))

        override fun log(level: LogLevel, messageCode: String) {
            logs += level to messageCode
        }
    }
}
