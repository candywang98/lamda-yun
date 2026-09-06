package com.company.cloudctl.companion.media

import java.io.ByteArrayInputStream
import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class MediaDeliveryTest {
    @Test
    fun parsesBoundedManifestAndRejectsPathTraversal() {
        val digest = sha("image-bytes")
        val manifest = MediaManifestParser.parse(
            """{"protocolVersion":"cloudctl.media/v1","deliveryId":"delivery-1","items":[{"assetId":"asset-1","fileName":"cover.jpg","sha256":"$digest","sizeBytes":11,"contentType":"image/jpeg"}]}""",
        )
        assertEquals("delivery-1", manifest.deliveryId)
        assertEquals("cover.jpg", manifest.items.single().fileName)
        assertFailsWith<IllegalArgumentException> {
            MediaManifestParser.parse(
                """{"protocolVersion":"cloudctl.media/v1","deliveryId":"delivery-1","items":[{"assetId":"asset-1","fileName":"../cover.jpg","sha256":"$digest","sizeBytes":11,"contentType":"image/jpeg"}]}""",
            )
        }
    }

    @Test
    fun verifiesSizeAndHashBeforeAtomicCommit() {
        val root = Files.createTempDirectory("cloudctl-media").toFile()
        try {
            val payload = "image-bytes".toByteArray()
            val item = MediaManifestItem("asset-1", "cover.jpg", sha("image-bytes"), payload.size.toLong(), "image/jpeg")
            val store = MediaDeliveryStore(root)
            val target = store.install(MediaManifest("delivery-1", listOf(item)), item, ByteArrayInputStream(payload))
            assertTrue(target.isFile)
            assertEquals("image-bytes", target.readText())
            val bad = item.copy(sha256 = "0".repeat(64))
            assertFailsWith<IllegalArgumentException> {
                store.install(MediaManifest("delivery-2", listOf(bad)), bad, ByteArrayInputStream(payload))
            }
            assertFalse(File(root, "delivery-2/.cover.jpg.part").exists())
        } finally {
            root.deleteRecursively()
        }
    }

    private fun sha(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray())
        .joinToString("") { "%02x".format(it) }
}
