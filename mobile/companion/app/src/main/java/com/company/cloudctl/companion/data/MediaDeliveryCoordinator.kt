package com.company.cloudctl.companion.data

import android.content.Context
import com.company.cloudctl.companion.media.MediaDeliveryStore
import com.company.cloudctl.companion.media.MediaGalleryExporter
import com.company.cloudctl.companion.model.ArtifactDeliveryState
import com.company.cloudctl.companion.model.ArtifactDeliveryStatus
import com.company.cloudctl.companion.model.ArtifactKind
import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.CloudTaskClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import android.net.Uri
import java.io.FileInputStream

class MediaDeliveryCoordinator(
    context: Context,
    private val deliveryStore: ArtifactDeliveryStore = ArtifactDeliveryStore(context),
    private val privateRoot: File = File(context.filesDir, "media-deliveries"),
    private val mediaStore: MediaDeliveryStore = MediaDeliveryStore(privateRoot),
    private val galleryExporter: MediaGalleryExporter = MediaGalleryExporter(context.contentResolver),
) {
    suspend fun deliver(connection: CloudConnection, deliveryId: String, assetIds: List<String>) {
        val client = CloudTaskClient(connection)
        val manifest = withContext(Dispatchers.IO) { client.requestMediaManifest(deliveryId, assetIds) }
        val exportedUris = mutableListOf<Uri>()
        val downloadedFiles = mutableListOf<File>()
        try {
            manifest.items.forEach { item ->
            deliveryStore.upsert(ArtifactDeliveryStatus(item.assetId, deliveryId, ArtifactKind.Media, ArtifactDeliveryState.Downloading, 0, item.sizeBytes, 0))
                val path = item.downloadPath ?: error("Missing media download path")
                val downloaded = File.createTempFile(".${item.assetId}-", ".download", File(privateRoot, manifest.deliveryId).also { it.mkdirs() })
                downloadedFiles += downloaded
                val headers = withContext(Dispatchers.IO) { client.downloadMediaToFile(path, item.sizeBytes, downloaded) }
                val expectedHash = headers["x-content-sha256"]
                require(expectedHash == null || expectedHash.equals(item.sha256, ignoreCase = true)) {
                    "Media response hash header mismatch"
                }
                val privateFile = withContext(Dispatchers.IO) { FileInputStream(downloaded).use { mediaStore.install(manifest, item, it) } }
                downloaded.delete()
                val galleryUri = withContext(Dispatchers.IO) { galleryExporter.export(privateFile, item) }
                exportedUris += galleryUri
                deliveryStore.upsert(ArtifactDeliveryStatus(item.assetId, deliveryId, ArtifactKind.Media, ArtifactDeliveryState.Delivered, item.sizeBytes, item.sizeBytes, 100, null, galleryUri.toString()))
            }
        } catch (error: Exception) {
            manifest.items.forEach { item ->
                deliveryStore.upsert(ArtifactDeliveryStatus(item.assetId, deliveryId, ArtifactKind.Media, ArtifactDeliveryState.Failed, 0, item.sizeBytes, 0, error.javaClass.simpleName))
            }
            exportedUris.forEach { uri -> runCatching { galleryExporter.delete(uri) } }
            downloadedFiles.forEach { it.delete() }
            mediaStore.clear(deliveryId)
            throw error
        }
    }

}
