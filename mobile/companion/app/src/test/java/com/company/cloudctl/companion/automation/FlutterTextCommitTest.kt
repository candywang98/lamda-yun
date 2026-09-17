package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class FlutterTextCommitTest {
    @Test
    fun treatsWholeAndDecimalPricesAsKeypadInput() {
        assertTrue(FlutterTextCommit.isNumericPrice("199"))
        assertTrue(FlutterTextCommit.isNumericPrice("10.5"))
        assertFalse(FlutterTextCommit.isNumericPrice(""))
        assertFalse(FlutterTextCommit.isNumericPrice("."))
        assertFalse(FlutterTextCommit.isNumericPrice("199元"))
        assertFalse(FlutterTextCommit.isNumericPrice("Notion Business 兑换券，图示价值 $240。拍下后按说明发送兑换方式。支持当面交易。"))
    }

    @Test
    fun acceptsFlutterDescriptionEvenWhenWhitespaceDiffers() {
        val expected = "Notion Business 兑换券，图示价值 $240。拍下后按说明发送兑换方式。支持当面交易。"
        assertTrue(FlutterTextCommit.accepted("描述一下宝贝的品牌型号、货品来源…\n$expected", expected))
        assertTrue(FlutterTextCommit.accepted(expected.replace(" ", ""), expected))
        // Partial and stale-draft readbacks that share only the opening must fail.
        assertFalse(FlutterTextCommit.accepted("Notion Business 兑换券，图示价值 $240。拍下后按说明", expected))
        assertFalse(FlutterTextCommit.accepted("描述一下宝贝的品牌型号、货品来源…", expected))
    }

    @Test
    fun rejectsStaleDraftThatOnlySharesTheOpening() {
        val expected = "Notion Business 兑换券，图示价值 $240。拍下后按说明发送兑换方式。支持当面交易。"
        val staleDraft = "Notion Business 兑换券，图示价值$240。拍下后按说明发兑换方式。虚拟商品，直接发链接，不用等快递。"
        assertFalse(FlutterTextCommit.accepted(staleDraft, expected))
    }

    // ---- B14: full-length readback proof across redraw/blur ----

    @Test
    fun sixteenCharacterPrefixOfALongDescriptionIsNotAcceptance() {
        val expected = "虚拟商品交付说明，拍下后自动发货。".repeat(12) // 336 chars
        assertTrue(FlutterTextCommit.accepted(expected, expected))
        // Transient node / partial paint that agrees on the first 16 chars only.
        assertFalse(FlutterTextCommit.accepted(expected.take(16), expected))
        assertFalse(FlutterTextCommit.accepted(expected.take(16) + "…", expected))
    }

    @Test
    fun emojiMustRoundTripInFull() {
        val expected = "兑换码发货🙂截图确认\n售后说明"
        assertTrue(FlutterTextCommit.accepted(expected, expected))
        assertFalse(FlutterTextCommit.accepted(expected.replace("🙂", "?"), expected))
        assertFalse(FlutterTextCommit.accepted(expected.replace("🙂", ""), expected))
    }

    @Test
    fun missingLineIsContentLossNotFormatting() {
        val expected = "第一行说明交付方式\n第二行说明售后\n第三行提醒及时确认收货"
        assertTrue(FlutterTextCommit.accepted(expected, expected))
        val missingMiddleLine = "第一行说明交付方式\n第三行提醒及时确认收货"
        assertFalse(FlutterTextCommit.accepted(missingMiddleLine, expected))
    }

    @Test
    fun placeholderOnlyReadbackIsNotAcceptance() {
        val expected = "全新的虚拟商品说明，内容足够长用于回读校验。"
        // The field still shows its hint text: nothing was accepted.
        assertFalse(FlutterTextCommit.accepted("描述一下宝贝的品牌型号、货品来源…", expected))
        assertFalse(FlutterTextCommit.accepted("", expected))
    }
}
