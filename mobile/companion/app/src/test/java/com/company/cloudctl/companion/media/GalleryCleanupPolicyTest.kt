package com.company.cloudctl.companion.media

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * B15: cleanup respects reference counts and unknown-task evidence
 * retention — rows we inserted and nobody else references are deleted;
 * pre-existing rows (reused or overwritten) are kept as evidence we do not own.
 */
class GalleryCleanupPolicyTest {

    @Test
    fun insertedUnsharedRowsAreDeleted() {
        val plan = GalleryCleanupPolicy.plan(
            listOf(GalleryCleanupPolicy.CleanupCandidate("content://media/1", GalleryOrigin.Inserted)),
        )
        val decision = assertIs<GalleryCleanupPolicy.Decision.Delete>(plan.single())
        assertEquals("content://media/1", decision.uri)
    }

    @Test
    fun reusedPreexistingRowIsKeptAsForeignEvidence() {
        val plan = GalleryCleanupPolicy.plan(
            listOf(GalleryCleanupPolicy.CleanupCandidate("content://media/2", GalleryOrigin.ReusedExisting)),
        )
        val decision = assertIs<GalleryCleanupPolicy.Decision.Keep>(plan.single())
        assertEquals(GalleryCleanupPolicy.KeepReason.REUSED_PREEXISTING_ROW, decision.reason)
    }

    @Test
    fun overwrittenPreexistingRowIsKept() {
        val plan = GalleryCleanupPolicy.plan(
            listOf(GalleryCleanupPolicy.CleanupCandidate("content://media/3", GalleryOrigin.OverwrittenExisting)),
        )
        val decision = assertIs<GalleryCleanupPolicy.Decision.Keep>(plan.single())
        assertEquals(GalleryCleanupPolicy.KeepReason.OVERWROTE_PREEXISTING_ROW, decision.reason)
    }

    @Test
    fun insertedRowReferencedByAnotherDeliveryIsKept() {
        val plan = GalleryCleanupPolicy.plan(
            listOf(
                GalleryCleanupPolicy.CleanupCandidate(
                    "content://media/4",
                    GalleryOrigin.Inserted,
                    sharedWithDeliveryIds = setOf("delivery-b"),
                ),
            ),
        )
        val decision = assertIs<GalleryCleanupPolicy.Decision.Keep>(plan.single())
        assertEquals(GalleryCleanupPolicy.KeepReason.REFERENCED_BY_OTHER_DELIVERY, decision.reason)
    }

    @Test
    fun referenceCountBeatsOriginInTheMixedCase() {
        val plan = GalleryCleanupPolicy.plan(
            listOf(
                GalleryCleanupPolicy.CleanupCandidate("content://media/5", GalleryOrigin.ReusedExisting, sharedWithDeliveryIds = setOf("delivery-b")),
            ),
        )
        val decision = assertIs<GalleryCleanupPolicy.Decision.Keep>(plan.single())
        // Shared rows report the sharing reason first: the count is why we keep it.
        assertEquals(GalleryCleanupPolicy.KeepReason.REFERENCED_BY_OTHER_DELIVERY, decision.reason)
    }
}
