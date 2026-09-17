package com.company.cloudctl.companion.media

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * B15: staging order is pinned to the caller's assetIds order. The final
 * selection order must equal the passed assetIds exactly, so a manifest that
 * drifts from the request (missing, extra, duplicated) is rejected up front
 * instead of being silently reordered.
 */
class StagedMediaPlanTest {

    private fun manifest(vararg ids: String): MediaManifest {
        val items = ids.map { id ->
            MediaManifestItem(
                assetId = id,
                fileName = "$id.jpg",
                sha256 = sha(id),
                sizeBytes = 100L,
                contentType = "image/jpeg",
            )
        }
        return MediaManifest("delivery-1", items)
    }

    @Test
    fun pinsRequestedOrderEvenWhenManifestAnswersInAnotherOrder() {
        val plan = StagedMediaPlan.pinOrder(manifest("b", "a", "c"), listOf("c", "a", "b"))
        assertEquals(listOf("c", "a", "b"), plan.map { it.assetId })
        assertEquals(List(3) { it }, plan.map { it.orderIndex })
    }

    @Test
    fun missingRequestedAssetFailsClosed() {
        assertFailsWith<IllegalArgumentException> {
            StagedMediaPlan.pinOrder(manifest("a", "b"), listOf("a", "b", "c"))
        }
    }

    @Test
    fun extraManifestAssetFailsClosed() {
        assertFailsWith<IllegalArgumentException> {
            StagedMediaPlan.pinOrder(manifest("a", "b", "x"), listOf("a", "b"))
        }
    }

    @Test
    fun duplicateRequestedAssetIdsFailClosed() {
        assertFailsWith<IllegalArgumentException> {
            StagedMediaPlan.pinOrder(manifest("a", "b"), listOf("a", "a"))
        }
    }

    @Test
    fun emptyRequestFailsClosed() {
        assertFailsWith<IllegalArgumentException> {
            StagedMediaPlan.pinOrder(manifest("a"), emptyList())
        }
    }

    @Test
    fun businessDisplayNameCarriesTheStoredExtension() {
        // MediaStore appends the canonical extension when the display name has
        // none; the marker must be the stored name or matching never fires.
        assertEquals("cover.jpg", GalleryNaming.displayNameFor("cover", "image/jpeg"))
        assertEquals("shot.png", GalleryNaming.displayNameFor("shot.png", "image/png"))
        assertEquals("clip", GalleryNaming.displayNameFor("clip", "application/octet-stream"))
        val asset = StagedMediaAsset("asset-1", 0, "cover", "a".repeat(64), 1L, "image/jpeg")
        assertEquals("cover.jpg", asset.businessDisplayName)
        assertTrue(asset.businessDisplayName == planFrom(asset))
    }

    private fun planFrom(asset: StagedMediaAsset): String =
        StagedMediaPlan.pinOrder(
            MediaManifest("delivery-1", listOf(MediaManifestItem(asset.assetId, asset.fileName, asset.sha256, asset.sizeBytes, asset.contentType))),
            listOf(asset.assetId),
        ).single().businessDisplayName

    private fun sha(value: String): String = java.security.MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray())
        .joinToString("") { "%02x".format(it) }
}
