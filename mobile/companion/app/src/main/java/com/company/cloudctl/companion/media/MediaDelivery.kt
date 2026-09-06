package com.company.cloudctl.companion.media

import org.json.JSONObject
import java.io.File
import java.io.InputStream
import java.security.MessageDigest

data class MediaManifestItem(
    val assetId: String,
    val fileName: String,
    val sha256: String,
    val sizeBytes: Long,
    val contentType: String,
    val downloadPath: String? = null,
)

data class MediaManifest(
    val deliveryId: String,
    val items: List<MediaManifestItem>,
)

object MediaManifestParser {
    private val idPattern = Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    private val shaPattern = Regex("^[a-f0-9]{64}$")
    private val fileNamePattern = Regex("^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    fun parse(encoded: String): MediaManifest {
        require(encoded.toByteArray().size <= 128 * 1024) { "Media manifest exceeds limit" }
        val root = JSONObject(encoded)
        require(root.optString("protocolVersion") == "cloudctl.media/v1") { "Unsupported media manifest protocol" }
        val deliveryId = root.getString("deliveryId").also { require(idPattern.matches(it)) { "Invalid delivery ID" } }
        val values = root.getJSONArray("items")
        require(values.length() in 1..50) { "Media manifest item count is invalid" }
        val items = List(values.length()) { index ->
            val value = values.getJSONObject(index)
            val item = MediaManifestItem(
                assetId = value.getString("assetId").also { require(idPattern.matches(it)) { "Invalid asset ID" } },
                fileName = value.getString("fileName").also { require(fileNamePattern.matches(it)) { "Invalid media file name" } },
                sha256 = value.getString("sha256").lowercase().also { require(shaPattern.matches(it)) { "Invalid media SHA-256" } },
                sizeBytes = value.getLong("sizeBytes").also { require(it in 1..5_000_000_000L) { "Invalid media size" } },
                contentType = value.getString("contentType").also { require(it.length in 1..160 && '\u0000' !in it) { "Invalid media content type" } },
                downloadPath = value.optString("downloadPath").takeIf(String::isNotBlank)?.also {
                    require(it.startsWith("/companion/v2/media/")) { "Invalid media download path" }
                },
            )
            item
        }
        require(items.map(MediaManifestItem::assetId).toSet().size == items.size) { "Media asset IDs must be unique" }
        return MediaManifest(deliveryId, items)
    }
}

class MediaDeliveryStore(private val root: File) {
    fun install(manifest: MediaManifest, item: MediaManifestItem, input: InputStream): File {
        require(manifest.items.any { it.assetId == item.assetId }) { "Item is not part of the manifest" }
        val deliveryRoot = File(root, manifest.deliveryId).canonicalFile
        require(deliveryRoot.path == root.canonicalFile.path || deliveryRoot.path.startsWith(root.canonicalFile.path + File.separator)) {
            "Delivery path escapes private root"
        }
        require(deliveryRoot.mkdirs() || deliveryRoot.isDirectory) { "Cannot create delivery directory" }
        val target = File(deliveryRoot, item.fileName).canonicalFile
        require(target.parentFile?.canonicalPath == deliveryRoot.path) { "Media file path escapes delivery directory" }
        val temporary = File(deliveryRoot, ".${item.fileName}.part")
        temporary.delete()
        var bytes = 0L
        val digest = MessageDigest.getInstance("SHA-256")
        try {
            temporary.outputStream().use { output ->
                val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    require(count > 0)
                    bytes += count
                    require(bytes <= item.sizeBytes) { "Media exceeds declared size" }
                    digest.update(buffer, 0, count)
                    output.write(buffer, 0, count)
                }
            }
            require(bytes == item.sizeBytes) { "Media size mismatch" }
            require(digest.digest().joinToString("") { "%02x".format(it) } == item.sha256) { "Media SHA-256 mismatch" }
            require(temporary.renameTo(target)) { "Cannot commit media file" }
            return target
        } catch (error: Exception) {
            temporary.delete()
            throw error
        }
    }

    fun clear(deliveryId: String) {
        File(root, deliveryId).deleteRecursively()
    }
}
