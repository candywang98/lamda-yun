package com.company.cloudctl.companion.media

/**
 * B15: gallery cleanup respects reference counts and unknown-task evidence
 * retention. Rows this delivery inserted and nobody else references are safe
 * to delete; rows that pre-existed this delivery (reused or overwritten in
 * place) belong to another or unknown task and are kept — their bytes are
 * evidence we do not own. Pure logic, JVM-testable.
 */
object GalleryCleanupPolicy {

    sealed interface Decision {
        val uri: String

        /** No other delivery references the row and this delivery created it. */
        data class Delete(override val uri: String) : Decision

        /** Row is shared, pre-existing, or evidence for an unknown task. */
        data class Keep(override val uri: String, val reason: KeepReason) : Decision
    }

    enum class KeepReason {
        /** Another known delivery still references the row (reference count > 0). */
        REFERENCED_BY_OTHER_DELIVERY,

        /** Row existed before this delivery and was reused untouched. */
        REUSED_PREEXISTING_ROW,

        /** Row existed before this delivery; we overwrote its bytes but do not own it. */
        OVERWROTE_PREEXISTING_ROW,
    }

    data class CleanupCandidate(
        val uri: String,
        val origin: GalleryOrigin,
        val sharedWithDeliveryIds: Set<String> = emptySet(),
    )

    fun plan(candidates: List<CleanupCandidate>): List<Decision> = candidates.map { candidate ->
        when {
            candidate.sharedWithDeliveryIds.isNotEmpty() -> Decision.Keep(
                candidate.uri,
                KeepReason.REFERENCED_BY_OTHER_DELIVERY,
            )
            candidate.origin == GalleryOrigin.ReusedExisting -> Decision.Keep(
                candidate.uri,
                KeepReason.REUSED_PREEXISTING_ROW,
            )
            candidate.origin == GalleryOrigin.OverwrittenExisting -> Decision.Keep(
                candidate.uri,
                KeepReason.OVERWROTE_PREEXISTING_ROW,
            )
            else -> Decision.Delete(candidate.uri)
        }
    }
}
