package com.company.cloudctl.companion.media

/**
 * Content-addressed gallery upsert decisions (im-live slice 2, gap 4): repeated
 * exports of the same asset must reuse or overwrite the single existing row
 * instead of accumulating "(26)(25)..." MediaStore copies that eventually break
 * inserts. Pure logic so the decision table is JVM-testable without MediaStore.
 */
object GalleryUpsert {

    /** A MediaStore row previously written under the same display name. */
    data class ExistingRow(
        val id: Long,
        val sizeBytes: Long,
        val dateAddedSec: Long,
        val sha256: String? = null,
    )

    sealed interface Decision {
        /** Same name and identical bytes: keep the row, only refresh its dates. */
        data class Reuse(val row: ExistingRow) : Decision

        /** Same name but different bytes: rewrite that row in place. */
        data class Overwrite(val row: ExistingRow) : Decision

        /** No row owns this display name yet. */
        object Insert : Decision
    }

    /**
     * Addresses the newest row with the same display name: identical content is
     * reused, anything else overwrites that row, and no row at all inserts.
     * An unknown stored hash ([ExistingRow.sha256] == null) cannot prove
     * identity, so it conservatively overwrites in place.
     */
    fun decide(existing: List<ExistingRow>, contentSha256: String, contentSize: Long): Decision {
        val newest = existing.maxByOrNull { it.dateAddedSec } ?: return Decision.Insert
        val identical = newest.sizeBytes == contentSize && newest.sha256 == contentSha256
        return if (identical) Decision.Reuse(newest) else Decision.Overwrite(newest)
    }
}
