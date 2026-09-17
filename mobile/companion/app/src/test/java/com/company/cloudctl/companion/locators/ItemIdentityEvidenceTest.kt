package com.company.cloudctl.companion.locators

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * B13 — evidence levels when no reliable platformItemId exists: account
 * scope + composite visible attributes + human confirmation; attribute
 * ambiguity (zero or several matching cards) fails closed with a readable
 * reason string.
 */
class ItemIdentityEvidenceTest {
    private val attributes = CompositeItemAttributes(
        accountScope = "xianyu://account/seller-A",
        titleContains = "黄同学漫画二战史2",
        price = "¥45.00",
        actionLabel = "编辑",
        listingState = "在卖",
    )

    private val cardLines = listOf(
        "托管\n降价\n编辑\n诊断",
        "《黄同学漫画二战史2》个人闲置",
        "曝光12\n浏览34\n想要5",
        "¥45.00",
    )

    @Test
    fun genuinePlatformItemIdIsTheStrongestEvidence() {
        val evidence = ItemIdentityEvidencePolicy.evaluate(
            attributes, cardLines, distinctMatchingCards = 1, platformItemId = "7123456789",
        )
        val platform = evidence as ItemIdentityEvidence.PlatformItemId
        assertEquals(EvidenceLevel.PLATFORM_ITEM_ID, platform.level)
        assertEquals("7123456789", platform.itemId)
    }

    @Test
    fun blankPlatformItemIdIsTreatedAsAbsentAndNeverFabricated() {
        val evidence = ItemIdentityEvidencePolicy.evaluate(
            attributes, cardLines, distinctMatchingCards = 1, platformItemId = "  ",
        )
        // Falls through to the composite path instead of inventing an id.
        assertTrue(evidence is ItemIdentityEvidence.CompositeConfirmed)
    }

    @Test
    fun accountScopedCompositeIsConfirmedButRequiresHumanConfirmation() {
        val evidence = ItemIdentityEvidencePolicy.evaluate(
            attributes, cardLines, distinctMatchingCards = 1,
        )
        val composite = evidence as ItemIdentityEvidence.CompositeConfirmed
        assertEquals(EvidenceLevel.COMPOSITE_HUMAN_CONFIRMED, composite.level)
        assertTrue(composite.humanConfirmationRequired)
        assertEquals(1, composite.distinctMatchingCards)
        assertTrue(composite.confirmingLines.any { it.contains("黄同学漫画二战史2") })
        assertTrue(composite.confirmingLines.any { it.contains("¥45.00") })
    }

    @Test
    fun attributeAmbiguityFailsClosedWithAReadableReason() {
        // Two distinct cards carry the same composite (same-name relist).
        val evidence = ItemIdentityEvidencePolicy.evaluate(
            attributes, cardLines, distinctMatchingCards = 2,
        )
        val insufficient = evidence as ItemIdentityEvidence.Insufficient
        assertEquals(EvidenceLevel.INSUFFICIENT, insufficient.level)
        assertTrue("2 distinct cards" in insufficient.reason)
        assertTrue("forbidden" in insufficient.reason)
    }

    @Test
    fun zeroMatchingCardsFailsClosed() {
        val evidence = ItemIdentityEvidencePolicy.evaluate(
            attributes, cardLines, distinctMatchingCards = 0,
        )
        val insufficient = evidence as ItemIdentityEvidence.Insufficient
        assertTrue("ZERO" in insufficient.reason)
    }

    @Test
    fun missingAccountScopeFailsClosed() {
        val evidence = ItemIdentityEvidencePolicy.evaluate(
            attributes.copy(accountScope = null), cardLines, distinctMatchingCards = 1,
        )
        val insufficient = evidence as ItemIdentityEvidence.Insufficient
        assertTrue("account scope" in insufficient.reason)
    }

    @Test
    fun titleAloneIsNotACompositeIdentity() {
        val evidence = ItemIdentityEvidencePolicy.evaluate(
            attributes.copy(price = null, actionLabel = null, listingState = null),
            cardLines,
            distinctMatchingCards = 1,
        )
        val insufficient = evidence as ItemIdentityEvidence.Insufficient
        assertTrue("≥2 visible attributes" in insufficient.reason)
    }

    @Test
    fun blankTitleFragmentFailsClosed() {
        val evidence = ItemIdentityEvidencePolicy.evaluate(
            attributes.copy(titleContains = ""), cardLines, distinctMatchingCards = 1,
        )
        assertTrue(evidence is ItemIdentityEvidence.Insufficient)
    }

    @Test
    fun titlePlusOneAttributeIsEnoughForTheCompositeLevel() {
        // Title + action label = 2 visible attributes: admissible composite.
        val evidence = ItemIdentityEvidencePolicy.evaluate(
            attributes.copy(price = null, listingState = null), cardLines, distinctMatchingCards = 1,
        )
        assertTrue(evidence is ItemIdentityEvidence.CompositeConfirmed)
    }
}
