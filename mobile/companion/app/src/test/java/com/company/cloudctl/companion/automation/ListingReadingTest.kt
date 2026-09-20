package com.company.cloudctl.companion.automation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * P43/P44 listing parser tests — fixtures are the REAL card content-descs
 * captured 2026-09-20 on the OnePlus 9R 我发布的 list (186 在卖).
 */
class ListingReadingTest {

    private val realCard1 = "恭喜可托管无忧卖, 托管后预估将在1~3天内卖出\n托管\n降价\n编辑\n诊断\n《小升初新思维作文》个人闲置\n曝光2\n   \n浏览2\n   \n想要0\n¥\n18\n.88"
    private val realCard2 = "恭喜可托管无忧卖, 托管后预估将在1~3天内卖出\n托管\n降价\n编辑\n诊断\n《十万个为什么》个人闲置\n曝光13\n   \n浏览2\n   \n想要0\n¥\n8\n.88"

    @Test
    fun parses_real_card_with_all_user_fields() {
        val parsed = ListingReading.parseCard(realCard1) as ListingRowParseOutcome.Parsed
        assertEquals("《小升初新思维作文》个人闲置|1888", parsed.itemKey)
        assertEquals(1888L, parsed.priceCents)
        assertEquals("¥18.88", parsed.priceText)
        assertEquals(2, parsed.exposureCount)
        assertEquals(2, parsed.viewsCount)
        assertEquals(0, parsed.wantsCount)
        assertEquals("在卖", parsed.statusText)
    }

    @Test
    fun parses_second_real_card_metrics() {
        val parsed = ListingReading.parseCard(realCard2) as ListingRowParseOutcome.Parsed
        assertEquals("《十万个为什么》个人闲置|888", parsed.itemKey)
        assertEquals(13, parsed.exposureCount)
        assertEquals(2, parsed.viewsCount)
        assertEquals(0, parsed.wantsCount)
    }

    @Test
    fun refuses_priceless_or_titleless_cards() {
        assertEquals("NO_PRICE", (ListingReading.parse(listOf("只有标题的卡片", "浏览3")) as ListingRowParseOutcome.Skipped).reason)
        assertEquals("NO_TITLE", (ListingReading.parse(listOf("¥59")) as ListingRowParseOutcome.Skipped).reason)
        assertEquals("EMPTY_CARD", (ListingReading.parse(listOf(" ", "")) as ListingRowParseOutcome.Skipped).reason)
    }

    @Test
    fun key_cleans_and_caps_and_price_edges() {
        val key = ListingReading.compositeItemKey("​标题​".repeat(30), 100)
        assertTrue(key.length <= 128)
        assertNull(ListingReading.priceToCents("¥"))
        assertEquals(590L, ListingReading.priceToCents("5.90"))
        assertEquals(888L, ListingReading.priceToCents("8.88"))
    }

    @Test
    fun wan_suffix_multiplies_by_ten_thousand() {
        val parsed = ListingReading.parseCard(
            "托管\n降价\n编辑\n诊断\n《热门好书》\n曝光1.2万\n浏览8500\n想要3\n¥\n25\n.00",
        ) as ListingRowParseOutcome.Parsed
        assertEquals(12000, parsed.exposureCount)
        assertEquals(8500, parsed.viewsCount)
        assertEquals(3, parsed.wantsCount)
        assertEquals(2500L, parsed.priceCents)
    }

    @Test
    fun cdn_image_artifact_is_never_a_title() {
        val parsed = ListingReading.parseCard(
            "托管\n降价\n编辑\n诊断\nTB113y72xv1gK0jSZFFXXb0sXXa.png_110x10000.jpg_\n《真实标题》\n曝光5\n浏览6\n想要1\n¥\n9\n.90",
        ) as ListingRowParseOutcome.Parsed
        assertEquals("《真实标题》", parsed.title)
        assertEquals("《真实标题》|990", parsed.itemKey)
    }

    @Test
    fun missing_stats_default_to_zero() {
        val parsed = ListingReading.parseCard(
            "托管\n编辑\n《没有统计行的卡片》\n¥\n12\n.00",
        ) as ListingRowParseOutcome.Parsed
        assertEquals(0, parsed.exposureCount)
        assertEquals(0, parsed.viewsCount)
        assertEquals(0, parsed.wantsCount)
    }
}
