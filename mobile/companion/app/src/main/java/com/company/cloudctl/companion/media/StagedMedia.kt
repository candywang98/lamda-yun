package com.company.cloudctl.companion.media

/**
 * B15 (fleet-first-20260916.1): task-dedicated media identity. Staging pins
 * every asset to (assetId, sha256, orderIndex) before anything reaches the
 * gallery, so downstream selection can match by verifiable business markers
 * instead of grid position. Pure model — the real MediaStore rows are device
 * side; this layer only records what was reported back.
 */

/** One requested asset pinned to its position in the caller's assetIds order. */
data class StagedMediaAsset(
    val assetId: String,
    val orderIndex: Int,
    val fileName: String,
    val sha256: String,
    val sizeBytes: Long,
    val contentType: String,
) {
    init {
        require(orderIndex >= 0) { "Order index must not be negative" }
    }

    /** The display name MediaStore will show (and the selection marker). */
    val businessDisplayName: String
        get() = GalleryNaming.displayNameFor(fileName, contentType)
}

/** How the gallery row we ended up addressing came to exist. */
enum class GalleryOrigin {
    /** This delivery inserted a fresh MediaStore row. */
    Inserted,

    /** A same-name row with identical bytes was reused; owner may be another delivery. */
    ReusedExisting,

    /** A same-name row was overwritten in place; the previous owner is unknown. */
    OverwrittenExisting;

    companion object {
        fun from(decision: GalleryUpsert.Decision): GalleryOrigin = when (decision) {
            GalleryUpsert.Decision.Insert -> Inserted
            is GalleryUpsert.Decision.Reuse -> ReusedExisting
            is GalleryUpsert.Decision.Overwrite -> OverwrittenExisting
        }
    }
}

/** Device-side identity of one staged asset after the gallery upsert. */
data class StagedMediaRecord(
    val asset: StagedMediaAsset,
    val mediaStoreUri: String,
    val mimeType: String,
    val canonicalPath: String?,
    val origin: GalleryOrigin,
    val exportedAtMs: Long,
)

/**
 * Single source of truth for the stored display name so the exporter and the
 * selection matcher cannot drift apart.
 */
object GalleryNaming {
    fun displayNameFor(fileName: String, contentType: String): String {
        if (fileName.contains('.')) return fileName
        val extension = when (contentType) {
            "image/jpeg" -> ".jpg"
            "image/png" -> ".png"
            "image/webp" -> ".webp"
            "image/gif" -> ".gif"
            "video/mp4" -> ".mp4"
            "video/webm" -> ".webm"
            else -> ""
        }
        return fileName + extension
    }
}

/**
 * Pins manifest items to the caller-requested assetIds order. The final album
 * selection order must equal the passed assetIds exactly, so the staging order
 * is fixed here and any drift (missing id, extra id, duplicate request) is a
 * fail-closed error instead of a silent reorder.
 */
object StagedMediaPlan {
    fun pinOrder(manifest: MediaManifest, requestedAssetIds: List<String>): List<StagedMediaAsset> {
        require(requestedAssetIds.isNotEmpty()) { "Requested asset ID list is empty" }
        require(requestedAssetIds.toSet().size == requestedAssetIds.size) {
            "Requested asset IDs must be unique"
        }
        val byId = manifest.items.associateBy { it.assetId }
        val missing = requestedAssetIds.filterNot { byId.containsKey(it) }
        require(missing.isEmpty()) { "Manifest is missing requested assets: $missing" }
        val extra = manifest.items.map { it.assetId } - requestedAssetIds.toSet()
        require(extra.isEmpty()) { "Manifest carries assets that were not requested: $extra" }
        return requestedAssetIds.mapIndexed { index, assetId ->
            val item = byId.getValue(assetId)
            StagedMediaAsset(
                assetId = item.assetId,
                orderIndex = index,
                fileName = item.fileName,
                sha256 = item.sha256,
                sizeBytes = item.sizeBytes,
                contentType = item.contentType,
            )
        }
    }
}
