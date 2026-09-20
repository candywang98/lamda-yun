package com.company.cloudctl.companion.automation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** P43/P44 listing parser unit tests (listing-collect/20260920.1). */
class ListingReadingTest {

    @Test
    fun parses_title_price_status_and_builds_composite_key() {
        val outcome = ListingReading.parse(
            listOf("闲置机械键盘 98新", "¥\u200b1\u200b9\u200b9", "在卖"),
        )
        assertTrue(outcome is ListingRowParseOutcome.Parsed)
        val parsed = outcome as ListingRowParseOutcome.Parsed
        assertEquals("闲置机械键盘 98新|19900", parsed.itemKey)
        assertEquals(19900L, parsed.priceCents)
        assertEquals("¥199", parsed.priceText)
        assertEquals("在卖", parsed.statusText)
    }

    @Test
    fun refuses_priceless_cards_instead_of_fabricating_identity() {
        val outcome = ListingReading.parse(listOf("没有价格的卡片", "在卖"))
        assertTrue(outcome is ListingRowParseOutcome.Skipped)
        assertEquals("NO_PRICE", (outcome as ListingRowParseOutcome.Skipped).reason)
    }

    @Test
    fun refuses_empty_and_titleless_cards() {
        assertEquals("EMPTY_CARD", (ListingReading.parse(listOf(" ", "")) as ListingRowParseOutcome.Skipped).reason)
        assertEquals("NO_TITLE", (ListingReading.parse(listOf("¥59")) as ListingRowParseOutcome.Skipped).reason)
    }

    @Test
    fun key_cleans_u200b_and_caps_length() {
        val key = ListingReading.compositeItemKey("​标题​".repeat(30), 100)
        assertTrue(key.length <= 128)
        assertTrue(key.startsWith("标题"))
        assertNull(ListingReading.priceToCents("¥"))
        assertEquals(590L, ListingReading.priceToCents("¥5.90"))
    }
}
