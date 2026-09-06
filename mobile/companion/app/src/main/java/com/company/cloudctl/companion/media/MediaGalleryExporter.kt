package com.company.cloudctl.companion.media

import android.content.ContentResolver
import android.content.ContentValues
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import java.io.File

class MediaGalleryExporter(private val resolver: ContentResolver) {
    fun export(file: File, item: MediaManifestItem): Uri {
        val collection = when {
            item.contentType.startsWith("image/") -> MediaStore.Images.Media.EXTERNAL_CONTENT_URI
            item.contentType.startsWith("video/") -> MediaStore.Video.Media.EXTERNAL_CONTENT_URI
            else -> throw IllegalArgumentException("Unsupported gallery media type")
        }
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, item.fileName)
            put(MediaStore.MediaColumns.MIME_TYPE, item.contentType)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                put(MediaStore.MediaColumns.RELATIVE_PATH, "Pictures/CloudCtl")
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
        }
        val uri = resolver.insert(collection, values) ?: error("Cannot create gallery media entry")
        try {
            resolver.openOutputStream(uri, "w").use { output ->
                requireNotNull(output) { "Cannot open gallery media entry" }
                file.inputStream().use { input -> input.copyTo(output) }
            }
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

    fun delete(uri: Uri): Int = resolver.delete(uri, null, null)
}
