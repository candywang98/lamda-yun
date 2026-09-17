package com.company.cloudctl.companion.data

import android.content.Context
import android.net.Uri
import com.company.cloudctl.companion.media.GalleryCleanupPolicy
import com.company.cloudctl.companion.media.GalleryExportOutcome
import com.company.cloudctl.companion.media.MediaDeliveryStore
import com.company.cloudctl.companion.media.MediaGalleryExporter
import com.company.cloudctl.companion.media.StagedMediaAsset
import com.company.cloudctl.companion.media.StagedMediaLedger
import com.company.cloudctl.companion.media.StagedMediaPlan
import com.company.cloudctl.companion.media.StagedMediaRecord
import com.company.cloudctl.companion.model.ArtifactDeliveryState
import com.company.cloudctl.companion.model.ArtifactDeliveryStatus
import com.company.cloudctl.companion.model.ArtifactKind
import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.CloudTaskClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileInputStream

class MediaDeliveryCoordinator(
    context: Context,
    private val deliveryStore: ArtifactDeliveryStore = ArtifactDeliveryStore(context),
    private val privateRoot: File = File(context.filesDir, "media-deliveries"),
    private val mediaStore: MediaDeliveryStore = MediaDeliveryStore(privateRoot),
    private val galleryExporter: MediaGalleryExporter = MediaGalleryExporter(context.contentResolver),
    private val ledger: StagedMediaLedger = StagedMediaLedger(File(privateRoot, "ledger")),
) {
    suspend fun deliver(connection: CloudConnection, deliveryId: String, assetIds: List<String>) {
        val client = CloudTaskClient(connection)
        val manifest = withContext(Dispatchers.IO) { client.requestMediaManifest(deliveryId, assetIds) }
        // B15: the staging order is pinned to the caller's assetIds order; any
        // drift between manifest and request is a fail-closed error because the
        // final album selection order must equal the passed assetIds exactly.
        val staged: List<StagedMediaAsset> = withContext(Dispatchers.Default) {
            StagedMediaPlan.pinOrder(manifest, assetIds)
        }
        val exported = mutableListOf<Pair<StagedMediaAsset, GalleryExportOutcome>>()
        val downloadedFiles = mutableListOf<File>()
        try {
            staged.forEach { asset ->
            deliveryStore.upsert(ArtifactDeliveryStatus(asset.assetId, deliveryId, ArtifactKind.Media, ArtifactDeliveryState.Downloading, 0, asset.sizeBytes, 0))
                val path = manifest.items.first { it.assetId == asset.assetId }.downloadPath
                    ?: error("Missing media download path")
                val downloaded = File.createTempFile(".${asset.assetId}-", ".download", File(privateRoot, manifest.deliveryId).also { it.mkdirs() })
                downloadedFiles += downloaded
                val headers = withContext(Dispatchers.IO) { client.downloadMediaToFile(path, asset.sizeBytes, downloaded) }
                val expectedHash = headers["x-content-sha256"]
                require(expectedHash == null || expectedHash.equals(asset.sha256, ignoreCase = true)) {
                    "Media response hash header mismatch"
                }
                val privateFile = withContext(Dispatchers.IO) { FileInputStream(downloaded).use { mediaStore.install(manifest, manifest.items.first { it.assetId == asset.assetId }, it) } }
                downloaded.delete()
                val outcome = withContext(Dispatchers.IO) { galleryExporter.export(privateFile, manifest.items.first { it.assetId == asset.assetId }) }
                exported += asset to outcome
                withContext(Dispatchers.Default) {
                    ledger.record(
                        deliveryId,
                        StagedMediaRecord(
                            asset = asset,
                            mediaStoreUri = outcome.uri.toString(),
                            mimeType = outcome.mimeType,
                            canonicalPath = outcome.canonicalPath,
                            origin = outcome.origin,
                            exportedAtMs = System.currentTimeMillis(),
                        ),
                    )
                }
                deliveryStore.upsert(ArtifactDeliveryStatus(asset.assetId, deliveryId, ArtifactKind.Media, ArtifactDeliveryState.Delivered, asset.sizeBytes, asset.sizeBytes, 100, null, outcome.uri.toString()))
            }
        } catch (error: Exception) {
            staged.forEach { asset ->
                deliveryStore.upsert(ArtifactDeliveryStatus(asset.assetId, deliveryId, ArtifactKind.Media, ArtifactDeliveryState.Failed, 0, asset.sizeBytes, 0, error.javaClass.simpleName))
            }
            cleanupFailedDelivery(deliveryId, exported)
            downloadedFiles.forEach { it.delete() }
            mediaStore.clear(deliveryId)
            throw error
        }
    }

    /** Ordered staged assets for selection planning (resume support). */
    fun stagedAssets(deliveryId: String): List<StagedMediaAsset> = ledger.stagedAssets(deliveryId)

    /** Business progress: how many ordered assets were already selected. */
    fun albumIndex(deliveryId: String): Int = ledger.albumIndex(deliveryId)

    /** Advances the selection progress after a verified pick. */
    fun advanceAlbumIndex(deliveryId: String, albumIndex: Int) = ledger.advanceAlbumIndex(deliveryId, albumIndex)

    /**
     * B15: cleanup respects reference counts and unknown-task evidence. Only
     * rows this delivery inserted and no other delivery references are deleted;
     * reused/overwritten pre-existing rows are kept as foreign/unknown evidence.
     */
    private fun cleanupFailedDelivery(
        deliveryId: String,
        exported: List<Pair<StagedMediaAsset, GalleryExportOutcome>>,
    ) {
        val candidates = exported.map { (_, outcome) ->
            GalleryCleanupPolicy.CleanupCandidate(
                uri = outcome.uri.toString(),
                origin = outcome.origin,
                sharedWithDeliveryIds = ledger.referencingDeliveryIds(outcome.uri.toString(), excluding = deliveryId),
            )
        }
        GalleryCleanupPolicy.plan(candidates).forEach { decision ->
            if (decision is GalleryCleanupPolicy.Decision.Delete) {
                runCatching { galleryExporter.delete(Uri.parse(decision.uri)) }
            }
        }
        ledger.clear(deliveryId)
    }
}
