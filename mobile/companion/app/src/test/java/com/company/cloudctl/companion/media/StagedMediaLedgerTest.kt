package com.company.cloudctl.companion.media

import java.io.File
import java.nio.file.Files
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * B15: the staging ledger persists assetId/hash/order plus the MediaStore
 * identity (URI, MIME, canonical path) with atomic writes, so an interrupted
 * selection can resume from album_index and repeated exports stay idempotent.
 */
class StagedMediaLedgerTest {

    private lateinit var root: File

    @Test
    fun recordsAndReadsBackOrderedIdentity() {
        val ledger = ledger()
        ledger.record("delivery-1", record("asset-1", order = 1, uri = "content://media/11"))
        ledger.record("delivery-1", record("asset-0", order = 0, uri = "content://media/10"))
        val staged = ledger.stagedAssets("delivery-1")
        assertEquals(listOf("asset-0", "asset-1"), staged.map { it.assetId })
        assertEquals(List(2) { it }, staged.map { it.orderIndex })
        // album_index defaults to zero (nothing selected yet).
        assertEquals(0, ledger.albumIndex("delivery-1"))
    }

    @Test
    fun repeatedExportReplacesTheSameAssetInsteadOfAppending() {
        val ledger = ledger()
        ledger.record("delivery-1", record("asset-1", order = 0, uri = "content://media/10"))
        ledger.record("delivery-1", record("asset-0", order = 1, uri = "content://media/11"))
        ledger.record("delivery-1", record("asset-1", order = 0, uri = "content://media/99", origin = GalleryOrigin.ReusedExisting))
        val staged = ledger.stagedAssets("delivery-1")
        assertEquals(listOf("asset-1", "asset-0"), staged.map { it.assetId })
        val raw = File(root, "delivery-1.json").readText()
        assertTrue(raw.contains("content://media/99"))
        assertFalse(raw.contains("content://media/10"))
    }

    @Test
    fun albumIndexMovesOnlyForwardWithinRange() {
        val ledger = ledger()
        ledger.record("delivery-1", record("asset-0", order = 0))
        ledger.record("delivery-1", record("asset-1", order = 1))
        ledger.advanceAlbumIndex("delivery-1", 2)
        assertEquals(2, ledger.albumIndex("delivery-1"))
        // 断点后续传: a fresh ledger view over the same root keeps the progress.
        assertEquals(2, StagedMediaLedger(root).albumIndex("delivery-1"))
        assertFailsWith<IllegalArgumentException> { ledger.advanceAlbumIndex("delivery-1", 1) }
        assertFailsWith<IllegalArgumentException> { ledger.advanceAlbumIndex("delivery-1", 3) }
    }

    @Test
    fun writesAreAtomicAndLeaveNoPartialFiles() {
        val ledger = ledger()
        ledger.record("delivery-1", record("asset-0", order = 0))
        ledger.advanceAlbumIndex("delivery-1", 1)
        val parts = root.listFiles { file -> file.name.endsWith(".part") }.orEmpty()
        assertTrue(parts.isEmpty(), "ledger write left temporary files: ${parts.map { it.name }}")
        // A corrupted ledger is treated as empty, never crashes the reader.
        File(root, "broken.json").writeText("{ not json")
        assertEquals(0, StagedMediaLedger(root).albumIndex("broken"))
    }

    @Test
    fun invalidDeliveryIdIsRejected() {
        val ledger = ledger()
        assertFailsWith<IllegalArgumentException> { ledger.record("../escape", record("asset-0", order = 0)) }
        assertFailsWith<IllegalArgumentException> { ledger.stagedAssets("no ids allowed") }
    }

    @Test
    fun referencingDeliveryIdsSeesOnlyForeignLedgers() {
        val ledger = ledger()
        ledger.record("delivery-a", record("asset-0", order = 0, uri = "content://media/7"))
        ledger.record("delivery-b", record("asset-0", order = 0, uri = "content://media/7"))
        ledger.record("delivery-b", record("asset-1", order = 1, uri = "content://media/8"))
        ledger.record("delivery-a", record("asset-2", order = 2, uri = "content://media/9"))
        assertEquals(setOf("delivery-b"), ledger.referencingDeliveryIds("content://media/7", excluding = "delivery-a"))
        assertEquals(setOf("delivery-a"), ledger.referencingDeliveryIds("content://media/7", excluding = "delivery-b"))
        // A row only the excluded delivery references has no foreign referencer.
        assertEquals(emptySet(), ledger.referencingDeliveryIds("content://media/9", excluding = "delivery-a"))
        assertEquals(setOf("delivery-a"), ledger.referencingDeliveryIds("content://media/9", excluding = "delivery-b"))
    }

    @Test
    fun clearRemovesOnlyTheOwningDelivery() {
        val ledger = ledger()
        ledger.record("delivery-a", record("asset-0", order = 0))
        ledger.record("delivery-b", record("asset-0", order = 0))
        ledger.clear("delivery-a")
        assertTrue(ledger.stagedAssets("delivery-a").isEmpty())
        assertEquals(listOf("asset-0"), ledger.stagedAssets("delivery-b").map { it.assetId })
        assertEquals(0, ledger.albumIndex("delivery-a"))
    }

    // --- helpers -------------------------------------------------------------

    @AfterTest
    fun cleanUp() {
        if (::root.isInitialized) root.deleteRecursively()
    }

    private fun ledger(): StagedMediaLedger {
        root = Files.createTempDirectory("cloudctl-ledger").toFile()
        return StagedMediaLedger(root)
    }

    private fun record(
        assetId: String,
        order: Int,
        uri: String = "content://media/$order",
        origin: GalleryOrigin = GalleryOrigin.Inserted,
    ) = StagedMediaRecord(
        asset = StagedMediaAsset(
            assetId = assetId,
            orderIndex = order,
            fileName = "$assetId.jpg",
            sha256 = sha(assetId),
            sizeBytes = 100L + order,
            contentType = "image/jpeg",
        ),
        mediaStoreUri = uri,
        mimeType = "image/jpeg",
        canonicalPath = "/storage/emulated/0/Pictures/CloudCtl/$assetId.jpg",
        origin = origin,
        exportedAtMs = 1_000L + order,
    )

    private fun sha(value: String): String = java.security.MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray())
        .joinToString("") { "%02x".format(it) }
}
