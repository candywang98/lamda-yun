package com.company.cloudctl.companion.media

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * im-live slice 2, gap 4: repeated exports of the same asset must reuse or
 * overwrite the newest same-name MediaStore row instead of accumulating
 * "(26)(25)..." copies, while "gallery cell 0 = newest export" stays intact.
 */
class GalleryUpsertTest {
    private val sha = "a".repeat(64)
    private val otherSha = "b".repeat(64)

    private fun row(id: Long, size: Long = 1_024L, added: Long = 1_000L, hash: String? = sha) =
        GalleryUpsert.ExistingRow(id = id, sizeBytes = size, dateAddedSec = added, sha256 = hash)

    @Test
    fun noExistingRowInserts() {
        assertEquals(GalleryUpsert.Decision.Insert, GalleryUpsert.decide(emptyList(), sha, 1_024L))
    }

    @Test
    fun identicalContentIsReused() {
        val newest = row(id = 7L, added = 2_000L)

        val decision = GalleryUpsert.decide(listOf(row(id = 3L, added = 1_000L), newest), sha, 1_024L)

        val reuse = assertIs<GalleryUpsert.Decision.Reuse>(decision)
        assertEquals(7L, reuse.row.id)
    }

    @Test
    fun differentBytesOverwriteTheNewestRowInPlace() {
        val newest = row(id = 9L, added = 2_000L)

        val bySize = GalleryUpsert.decide(listOf(row(id = 3L), newest), sha, 2_048L)
        val byHash = GalleryUpsert.decide(listOf(row(id = 3L), newest), otherSha, 1_024L)

        assertEquals(9L, assertIs<GalleryUpsert.Decision.Overwrite>(bySize).row.id)
        assertEquals(9L, assertIs<GalleryUpsert.Decision.Overwrite>(byHash).row.id)
    }

    @Test
    fun unknownStoredHashOverwritesConservatively() {
        val unknown = row(id = 5L, hash = null)

        val decision = GalleryUpsert.decide(listOf(unknown), sha, 1_024L)

        assertEquals(5L, assertIs<GalleryUpsert.Decision.Overwrite>(decision).row.id)
    }
}
