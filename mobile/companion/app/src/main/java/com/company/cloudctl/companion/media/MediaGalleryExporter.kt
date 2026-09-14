package com.company.cloudctl.companion.media

import android.content.ContentResolver
import android.content.ContentUris
import android.content.ContentValues
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import java.io.File
import java.security.MessageDigest

class MediaGalleryExporter(private val resolver: ContentResolver) {
    fun export(file: File, item: MediaManifestItem): Uri {
        val collection = when {
            item.contentType.startsWith("image/") -> MediaStore.Images.Media.EXTERNAL_CONTENT_URI
            item.contentType.startsWith("video/") -> MediaStore.Video.Media.EXTERNAL_CONTENT_URI
            else -> throw IllegalArgumentException("Unsupported gallery media type")
        }
        // Content-addressed upsert (im-live slice 2, gap 4): MediaStore renames
        // repeated same-name inserts into "(26)(25)..." copies until inserts
        // fail, so exports address the newest same-name row instead of inserting.
        // MediaStore appends the canonical extension for the MIME type when the
        // display name lacks one, so the query must address the stored name or it
        // never matches and every export inserts a fresh copy (verified on device).
        val displayName = displayNameFor(item)
        val contentSha256 = sha256Of(file)
        val existing = queryExisting(collection, displayName, file.length())
        android.util.Log.i(
            "CompanionSync",
            "gallery upsert name=$displayName existing=${existing.size} " +
                "decision=${GalleryUpsert.decide(existing, contentSha256, file.length())::class.simpleName}",
        )
        return when (val decision = GalleryUpsert.decide(existing, contentSha256, file.length())) {
            is GalleryUpsert.Decision.Reuse -> {
                touchDates(collection, decision.row.id)
                rowUri(collection, decision.row.id)
            }
            is GalleryUpsert.Decision.Overwrite -> {
                val uri = rowUri(collection, decision.row.id)
                rewrite(uri, file)
                touchDates(collection, decision.row.id)
                uri
            }
            GalleryUpsert.Decision.Insert -> insertNew(collection, file, item, displayName)
        }
    }

    private fun displayNameFor(item: MediaManifestItem): String {
        if (item.fileName.contains('.')) return item.fileName
        val extension = when (item.contentType) {
            "image/jpeg" -> ".jpg"
            "image/png" -> ".png"
            "image/webp" -> ".webp"
            "image/gif" -> ".gif"
            "video/mp4" -> ".mp4"
            "video/webm" -> ".webm"
            else -> ""
        }
        return item.fileName + extension
    }

    fun delete(uri: Uri): Int = resolver.delete(uri, null, null)

    private fun insertNew(collection: Uri, file: File, item: MediaManifestItem, displayName: String): Uri {
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, displayName)
            put(MediaStore.MediaColumns.MIME_TYPE, item.contentType)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                put(MediaStore.MediaColumns.RELATIVE_PATH, RELATIVE_DIR)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
        }
        val uri = resolver.insert(collection, values) ?: error("Cannot create gallery media entry")
        try {
            writeBytes(uri, file)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                resolver.update(uri, ContentValues().apply {
                    put(MediaStore.MediaColumns.IS_PENDING, 0)
                }, null, null)
            }
            return uri
        } catch (error: Exception) {
            resolver.delete(uri, null, null)
            throw error
        }
    }

    /** Rewrites an owned row in place; no new MediaStore entry is created. */
    private fun rewrite(uri: Uri, file: File) {
        writeBytes(uri, file)
    }

    private fun writeBytes(uri: Uri, file: File) {
        resolver.openOutputStream(uri, "w").use { output ->
            requireNotNull(output) { "Cannot open gallery media entry" }
            file.inputStream().use { input -> input.copyTo(output) }
        }
    }

    /**
     * Keeps the "gallery cell 0 = newest export" contract by re-dating the
     * reused/overwritten row. Best effort: a rejected date update must not
     * fail the delivery.
     */
    private fun touchDates(collection: Uri, id: Long) {
        val now = System.currentTimeMillis() / 1_000
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DATE_MODIFIED, now)
            put(MediaStore.MediaColumns.DATE_ADDED, now)
        }
        runCatching { resolver.update(rowUri(collection, id), values, null, null) }
    }

    private fun queryExisting(
        collection: Uri,
        displayName: String,
        contentSize: Long,
    ): List<GalleryUpsert.ExistingRow> {
        val projection = arrayOf(
            MediaStore.MediaColumns._ID,
            MediaStore.MediaColumns.SIZE,
            MediaStore.MediaColumns.DATE_ADDED,
        )
        val selection: String
        val args: Array<String>
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            selection = "${MediaStore.MediaColumns.DISPLAY_NAME}=? AND ${MediaStore.MediaColumns.RELATIVE_PATH}=?"
            args = arrayOf(displayName, RELATIVE_DIR)
        } else {
            selection = "${MediaStore.MediaColumns.DISPLAY_NAME}=?"
            args = arrayOf(displayName)
        }
        val rows = runCatching {
            resolver.query(collection, projection, selection, args, null)?.use { cursor ->
                buildList {
                    while (cursor.moveToNext()) {
                        add(
                            GalleryUpsert.ExistingRow(
                                id = cursor.getLong(0),
                                sizeBytes = cursor.getLong(1),
                                dateAddedSec = cursor.getLong(2),
                            ),
                        )
                    }
                }
            }
        }.onFailure { error ->
            android.util.Log.w(
                "CompanionSync",
                "gallery upsert query failed selection=$selection args=${args.joinToString()}",
                error,
            )
        }.getOrNull() ?: return emptyList()
        // Hash the stored bytes only when the size already matches, so the
        // reuse check costs one stream read at most.
        return rows.map { row ->
            if (row.sizeBytes == contentSize) {
                row.copy(sha256 = storedSha256(rowUri(collection, row.id)))
            } else {
                row
            }
        }
    }

    private fun storedSha256(uri: Uri): String? = runCatching {
        resolver.openInputStream(uri)?.use { input ->
            val digest = MessageDigest.getInstance("SHA-256")
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
            digest.digest().joinToString("") { "%02x".format(it) }
        }
    }.getOrNull()

    private fun sha256Of(file: File): String = file.inputStream().use { input ->
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(64 * 1024)
        while (true) {
            val read = input.read(buffer)
            if (read < 0) break
            digest.update(buffer, 0, read)
        }
        digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun rowUri(collection: Uri, id: Long): Uri = ContentUris.withAppendedId(collection, id)

    private companion object {
        // MediaStore canonicalizes RELATIVE_PATH with a trailing slash; querying
        // without it matched nothing and every export fell through to Insert,
        // duplicating the same asset as "(1)", "(2)"... copies (verified on device).
        const val RELATIVE_DIR = "Pictures/CloudCtl/"
    }
}
