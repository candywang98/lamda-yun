package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * order-sync/20260915.1 §5/§7 + addendum 20260915.2：订单行解析规则。
 * 样本直接取自真机 dump /tmp/recon-ref/08-sold-orders-ui.xml、09-bought-orders-ui.xml
 * （U+200B 在 dump 里是真实字符，源码中显式转义为 \u200B）。
 */
class OrderRowParserTest {

    // 08 dump 第 1 行（SOLD）：买家 RUSHANG / 交易成功 / 二战史2 / ¥10.80（含问卷与操作按钮噪音）。
    private val soldRow = listOf(
        "订单信息, 退货运费险\n好评\n中评\n差评",
        "RUSHANG, RUSHANG",
        "交易成功, 交易成功",
        "《黄同学漫画二战史2》个人闲置, 《黄同学漫画二战史2》个人闲置",
        "¥​",
        "1​0​",
        ".​8​0​",
        "更多，按钮, 更多",
        "求小红花，按钮, 求小红花",
        "联系买家，按钮, 联系买家",
        "去评价，按钮, 去评价",
        "您​对​交​易​的​满​意​度​如​何​？​",
    )

    // 09 dump 第 3 行（BOUGHT）：卖家 大大章鱼 / 等待见面交易 / ¥17.88（无问卷按钮）。
    private val boughtRow = listOf(
        "订单信息",
        "大大章鱼, 大大章鱼",
        "等待见面交易, 等待见面交易",
        "【德克士咔滋脆皮手枪腿一个免配送】自取和配送免配送费！, 【德克士咔滋脆皮手枪腿一个免配送】自取和配送免配送费！",
        "¥​",
        "1​7​",
        ".​8​8​",
        "更多，按钮, 更多",
        "送小红花，按钮, 送小红花",
        "联系卖家，按钮, 联系卖家",
        "去评价，按钮, 去评价",
    )

    @Test
    fun parsesSurveyedSoldRowIntoCompositeKeyAndSnapshots() {
        val parsed = assertIs<OrderRowParseOutcome.Parsed>(OrderRowParser.parse(OrderDirection.SOLD, soldRow))
        assertEquals("SOLD|RUSHANG|《黄同学漫画二战史2》个人闲置|1080", parsed.orderKey)
        assertEquals("RUSHANG", parsed.buyerName)
        assertEquals("《黄同学漫画二战史2》个人闲置", parsed.itemTitle)
        assertEquals(1_080L, parsed.amountCents)
        assertEquals("交易成功", parsed.statusText)
        assertNull(parsed.occurredAt)
        // 问卷与操作按钮噪音绝不进入快照。
        assertEquals(15, parsed.itemTitle!!.length)
        assertEquals("RUSHANG", parsed.buyerName)
    }

    @Test
    fun parsesSurveyedBoughtRowWithSellerAndWaitingStatus() {
        val parsed = assertIs<OrderRowParseOutcome.Parsed>(OrderRowParser.parse(OrderDirection.BOUGHT, boughtRow))
        assertEquals("BOUGHT|大大章鱼|【德克士咔滋脆皮手枪腿一个免配送】自取和配送免配送费！|1788", parsed.orderKey)
        assertEquals("大大章鱼", parsed.buyerName)
        assertEquals(1_788L, parsed.amountCents)
        assertEquals("等待见面交易", parsed.statusText)
    }

    @Test
    fun collapsesMirroredNodeValuesAndRefundStatus() {
        assertEquals("RUSHANG", OrderRowParser.collapseMirrored("RUSHANG, RUSHANG"))
        assertEquals("交易关闭，有退款", OrderRowParser.collapseMirrored("交易关闭，有退款, 交易关闭，有退款"))
        // 非镜像（两半不等）保持原样。
        assertEquals("更多，按钮, 更多", OrderRowParser.collapseMirrored("更多，按钮, 更多"))
        // 08 dump 第 3 行：cll嘎哈 / 交易关闭，有退款 / ¥8.88。
        val parsed = assertIs<OrderRowParseOutcome.Parsed>(
            OrderRowParser.parse(
                OrderDirection.SOLD,
                listOf(
                    "订单信息, 退货运费险",
                    "cll嘎哈, cll嘎哈",
                    "交易关闭，有退款, 交易关闭，有退款",
                    "【天才少年维克多】 正版二手",
                    "¥​", "8​", ".​8​8​",
                    "查看钱款，按钮, 查看钱款",
                ),
            ),
        )
        assertEquals("cll嘎哈", parsed.buyerName)
        assertEquals("交易关闭，有退款", parsed.statusText)
        assertEquals(888L, parsed.amountCents)
        assertEquals("SOLD|cll嘎哈|【天才少年维克多】 正版二手|888", parsed.orderKey)
    }

    @Test
    fun assemblesU200bFragmentedPriceFromTheRulingSample() {
        // 裁决原始样本：'1'+'0'+'.8 0' → 1080（无独立 ¥ 节点也要拼得出）。
        val parsed = assertIs<OrderRowParseOutcome.Parsed>(
            OrderRowParser.parse(OrderDirection.SOLD, listOf("订单信息", "有人", "交易成功", "相机", "1", "0", ".8 0")),
        )
        assertEquals(1_080L, parsed.amountCents)
        assertEquals("SOLD|有人|相机|1080", parsed.orderKey)
    }

    @Test
    fun garbageFragmentConcatenationLeavesAmountNullInsteadOfGuessing() {
        // '1'+'2'+'.3'+'.4' → "12.3.4" 不是合法价格 → amount 为空，键里空段占位。
        val parsed = assertIs<OrderRowParseOutcome.Parsed>(
            OrderRowParser.parse(
                OrderDirection.SOLD,
                listOf("订单信息", "有人", "交易成功", "相机", "1", "2", ".3", ".4"),
            ),
        )
        assertNull(parsed.amountCents)
        assertEquals("SOLD|有人|相机|", parsed.orderKey)
    }

    @Test
    fun skipsRowOnlyWhenNicknameTitleAndAmountAreAllMissing() {
        // 只有结构行 + 状态 → 三段全缺 → NO_KEY（不算失败）。
        val statusOnly = OrderRowParser.parse(OrderDirection.SOLD, listOf("订单信息, 退货运费险", "交易成功, 交易成功"))
        assertEquals(OrderRowParser.REASON_NO_KEY, assertIs<OrderRowParseOutcome.Skipped>(statusOnly).reason)
        // 问卷按钮单独出现（行数据缺失）同样三段全缺 → NO_KEY。
        val promptOnly = OrderRowParser.parse(OrderDirection.BOUGHT, listOf("订单信息", "你​觉​得​该​宝​贝​价​格​值​不​值​？​去​表​态​"))
        assertEquals(OrderRowParser.REASON_NO_KEY, assertIs<OrderRowParseOutcome.Skipped>(promptOnly).reason)
        // 空行/零宽行 → NO_KEY。
        val blank = OrderRowParser.parse(OrderDirection.SOLD, listOf(" ", "​"))
        assertEquals(OrderRowParser.REASON_NO_KEY, assertIs<OrderRowParseOutcome.Skipped>(blank).reason)
        assertEquals(
            OrderRowParser.REASON_NO_KEY,
            assertIs<OrderRowParseOutcome.Skipped>(OrderRowParser.parse(OrderDirection.BOUGHT, emptyList())).reason,
        )
    }

    @Test
    fun keepsEmptyPlaceholderSegmentsForPartiallyMissingRows() {
        val amountOnly = assertIs<OrderRowParseOutcome.Parsed>(
            OrderRowParser.parse(OrderDirection.SOLD, listOf("订单信息", "交易成功", "¥​", "59", ".90")),
        )
        assertEquals("SOLD|||5990", amountOnly.orderKey)
        assertNull(amountOnly.buyerName)
        assertNull(amountOnly.itemTitle)

        val titleOnly = assertIs<OrderRowParseOutcome.Parsed>(
            OrderRowParser.parse(OrderDirection.BOUGHT, listOf("订单信息", "一本旧书")),
        )
        assertEquals("BOUGHT||一本旧书|", titleOnly.orderKey)
        assertEquals("一本旧书", titleOnly.itemTitle)
    }

    @Test
    fun capsTitleSegmentAt64AndWholeKeyAt128() {
        val longTitle = assertIs<OrderRowParseOutcome.Parsed>(
            OrderRowParser.parse(OrderDirection.SOLD, listOf("订单信息", "长".repeat(100))),
        )
        assertEquals("SOLD||" + "长".repeat(64) + "|", longTitle.orderKey)
        val both = assertIs<OrderRowParseOutcome.Parsed>(
            OrderRowParser.parse(OrderDirection.SOLD, listOf("订单信息", "甲".repeat(80), "乙".repeat(80), "¥​", "1")),
        )
        assertTrue(both.orderKey.length == 128)
    }

    @Test
    fun cleansZeroWidthAndOuterWhitespaceInsideSegments() {
        val parsed = assertIs<OrderRowParseOutcome.Parsed>(
            OrderRowParser.parse(
                OrderDirection.SOLD,
                listOf("订单信息", " ​昵称​ ", "交易成功", " 标题 ​x​ "),
            ),
        )
        assertEquals("SOLD|昵称|标题 x|", parsed.orderKey)
        assertEquals("昵称", parsed.buyerName)
        assertEquals("标题 x", parsed.itemTitle)
    }
}
