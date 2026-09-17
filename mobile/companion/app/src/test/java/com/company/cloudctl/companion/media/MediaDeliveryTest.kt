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

    @Test
    fun interruptedDownloadLeavesNoHalfFileBehind() {
        val root = Files.createTempDirectory("cloudctl-media").toFile()
        try {
            val payload = "image-bytes".toByteArray()
            val item = MediaManifestItem("asset-1", "cover.jpg", sha("image-bytes"), payload.size.toLong(), "image/jpeg")
            val manifest = MediaManifest("delivery-1", listOf(item))
            val store = MediaDeliveryStore(root)

            // 断下载: the stream dies after a few bytes; nothing may commit.
            val broken = object : java.io.InputStream() {
                private var served = 0
                override fun read(): Int {
                    if (served >= 4) throw java.io.IOException("connection reset mid-download")
                    served += 1
                    return payload[served - 1].toInt()
                }
            }
            assertFailsWith<java.io.IOException> { store.install(manifest, item, broken) }

            // 截断 (early EOF): size mismatch; still nothing commits.
            assertFailsWith<IllegalArgumentException> {
                store.install(manifest, item, ByteArrayInputStream(payload.copyOf(4)))
            }

            assertFalse(File(root, "delivery-1/.cover.jpg.part").exists())
            assertFalse(File(root, "delivery-1/cover.jpg").exists())
            assertTrue(root.listFiles()?.flatMap { it.listFiles().orEmpty().toList() }.orEmpty().isEmpty())

            // The delivery is still usable afterwards: a clean retry commits.
            val target = store.install(manifest, item, ByteArrayInputStream(payload))
            assertEquals("image-bytes", target.readText())
        } finally {
            root.deleteRecursively()
        }
    }

    private fun sha(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray())
        .joinToString("") { "%02x".format(it) }
}
