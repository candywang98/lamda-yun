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
        assertTrue(FlutterTextCommit.accepted("Notion Business 兑换券，图示价值 $240。拍下后按说明", expected))
        assertFalse(FlutterTextCommit.accepted("描述一下宝贝的品牌型号、货品来源…", expected))
    }
}
