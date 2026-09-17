package com.company.cloudctl.companion.media

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * B15: per-delivery staging ledger. Survives process restarts so an
 * interrupted album selection can resume from [albumIndex] instead of
 * restarting the whole order. Writes are atomic (temp file + rename); a crash
 * mid-write never leaves a parseable-but-truncated ledger behind.
 *
 * album_index keeps its business-progress meaning: it counts how many assets
 * of the ordered sequence were already selected in the album. It is NOT a
 * gallery cell position.
 */
class StagedMediaLedger(private val root: File) {

    init {
        root.mkdirs() || root.isDirectory || error("Cannot create media ledger directory")
    }

    data class DeliveryLedger(
        val deliveryId: String,
        val records: List<StagedMediaRecord>,
        val albumIndex: Int,
    )

    /** Records (or replaces, on repeated export) one staged asset. */
    @Synchronized
    fun record(deliveryId: String, entry: StagedMediaRecord) {
        val current = read(deliveryId)
        val records = (current.records.filterNot { it.asset.assetId == entry.asset.assetId } + entry)
            .sortedBy { it.asset.orderIndex }
        write(deliveryId, records, current.albumIndex)
    }

    /** Ordered staged assets for a delivery, empty when nothing was staged. */
    @Synchronized
    fun stagedAssets(deliveryId: String): List<StagedMediaAsset> =
        read(deliveryId).records.map { it.asset }.sortedBy { it.orderIndex }

    /** Business progress: how many ordered assets were already selected. */
    @Synchronized
    fun albumIndex(deliveryId: String): Int = read(deliveryId).albumIndex

    /**
     * Advances business progress. Only forward moves are accepted; a rewind
     * would silently re-publish assets and is rejected.
     */
    @Synchronized
    fun advanceAlbumIndex(deliveryId: String, albumIndex: Int) {
        val current = read(deliveryId)
        require(albumIndex in current.albumIndex..current.records.size) {
            "album_index must move forward within [${current.albumIndex}, ${current.records.size}]"
        }
        write(deliveryId, current.records, albumIndex)
    }

    /** Other deliveries whose ledger references the same MediaStore row. */
    fun referencingDeliveryIds(mediaStoreUri: String, excluding: String): Set<String> =
        root.listFiles { file -> file.isFile && file.extension == "json" }
            .orEmpty()
            .mapNotNull { file ->
                val deliveryId = file.nameWithoutExtension
                if (deliveryId == excluding) return@mapNotNull null
                val ledger = runCatching { read(deliveryId) }.getOrNull() ?: return@mapNotNull null
                if (ledger.records.any { it.mediaStoreUri == mediaStoreUri }) deliveryId else null
            }
            .toSet()

    /** Drops only this delivery's ledger file; other deliveries stay intact. */
    @Synchronized
    fun clear(deliveryId: String) {
        ledgerFile(deliveryId).delete()
    }

    private fun read(deliveryId: String): DeliveryLedger {
        val file = ledgerFile(deliveryId)
        if (!file.isFile) return DeliveryLedger(deliveryId, emptyList(), albumIndex = 0)
        val parsed = runCatching {
            val root = JSONObject(file.readText())
            require(root.optString(FIELD_PROTOCOL) == PROTOCOL) { "Unsupported media ledger protocol" }
            val encodedRecords = root.optJSONArray(FIELD_RECORDS) ?: JSONArray()
            val records = List(encodedRecords.length()) { index ->
                val record = encodedRecords.getJSONObject(index)
                val asset = record.getJSONObject(FIELD_ASSET)
                StagedMediaRecord(
                    asset = StagedMediaAsset(
                        assetId = asset.getString(FIELD_ASSET_ID),
                        orderIndex = asset.getInt(FIELD_ORDER),
                        fileName = asset.getString(FIELD_FILE_NAME),
                        sha256 = asset.getString(FIELD_SHA),
                        sizeBytes = asset.getLong(FIELD_SIZE),
                        contentType = asset.getString(FIELD_CONTENT_TYPE),
                    ),
                    mediaStoreUri = record.getString(FIELD_URI),
                    mimeType = record.getString(FIELD_MIME),
                    canonicalPath = record.optString(FIELD_CANONICAL_PATH).takeIf(String::isNotBlank),
                    origin = enumValueOf<GalleryOrigin>(record.optString(FIELD_ORIGIN, GalleryOrigin.Inserted.name)),
                    exportedAtMs = record.getLong(FIELD_EXPORTED_AT),
                )
            }
            DeliveryLedger(
                deliveryId = deliveryId,
                records = records.sortedBy { it.asset.orderIndex },
                albumIndex = root.optInt(FIELD_ALBUM_INDEX, 0),
            )
        }
        return parsed.getOrElse { DeliveryLedger(deliveryId, emptyList(), albumIndex = 0) }
    }

    private fun write(deliveryId: String, records: List<StagedMediaRecord>, albumIndex: Int) {
        require(albumIndex in 0..records.size) { "album_index out of range" }
        val encoded = JSONObject()
            .put(FIELD_PROTOCOL, PROTOCOL)
            .put(FIELD_DELIVERY_ID, deliveryId)
            .put(FIELD_ALBUM_INDEX, albumIndex)
            .put(
                FIELD_RECORDS,
                JSONArray().apply {
                    records.forEach { record ->
                        put(
                            JSONObject()
                                .put(
                                    FIELD_ASSET,
                                    JSONObject()
                                        .put(FIELD_ASSET_ID, record.asset.assetId)
                                        .put(FIELD_ORDER, record.asset.orderIndex)
                                        .put(FIELD_FILE_NAME, record.asset.fileName)
                                        .put(FIELD_SHA, record.asset.sha256)
                                        .put(FIELD_SIZE, record.asset.sizeBytes)
                                        .put(FIELD_CONTENT_TYPE, record.asset.contentType),
                                )
                                .put(FIELD_URI, record.mediaStoreUri)
                                .put(FIELD_MIME, record.mimeType)
                                .put(FIELD_CANONICAL_PATH, record.canonicalPath ?: "")
                                .put(FIELD_ORIGIN, record.origin.name)
                                .put(FIELD_EXPORTED_AT, record.exportedAtMs),
                        )
                    }
                },
            )
        val target = ledgerFile(deliveryId)
        val temporary = File(root, ".${target.name}.part")
        try {
            temporary.outputStream().use { it.write(encoded.toString().toByteArray()) }
            check(temporary.renameTo(target)) { "Cannot commit media ledger" }
        } catch (error: Exception) {
            temporary.delete()
            throw error
        }
    }

    private fun ledgerFile(deliveryId: String): File {
        require(ID_PATTERN.matches(deliveryId)) { "Invalid delivery ID for media ledger" }
        val file = File(root, "$deliveryId.json").canonicalFile
        require(file.parentFile?.canonicalPath == root.canonicalPath) { "Ledger path escapes root" }
        return file
    }

    private companion object {
        const val PROTOCOL = "cloudctl.media-ledger/v1"
        const val FIELD_PROTOCOL = "protocolVersion"
        const val FIELD_DELIVERY_ID = "deliveryId"
        const val FIELD_ALBUM_INDEX = "album_index"
        const val FIELD_RECORDS = "records"
        const val FIELD_ASSET = "asset"
        const val FIELD_ASSET_ID = "assetId"
        const val FIELD_ORDER = "orderIndex"
        const val FIELD_FILE_NAME = "fileName"
        const val FIELD_SHA = "sha256"
        const val FIELD_SIZE = "sizeBytes"
        const val FIELD_CONTENT_TYPE = "contentType"
        const val FIELD_URI = "mediaStoreUri"
        const val FIELD_MIME = "mimeType"
        const val FIELD_CANONICAL_PATH = "canonicalPath"
        const val FIELD_ORIGIN = "origin"
        const val FIELD_EXPORTED_AT = "exportedAtMs"
        val ID_PATTERN = Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    }
}
