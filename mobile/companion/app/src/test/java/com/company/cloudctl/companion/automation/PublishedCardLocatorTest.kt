package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * W4 维护动作 v2（契约 xianyu-anchors-20260915 §1/§2）：标题定位选卡纯逻辑。
 * 样本取自真机 recon-20260915-2 的卡片文本结构（在卖卡：托管/降价/编辑/诊断 +
 * 标题 + 曝光/浏览/想要 + ¥价格；已下架卡：下架原因 + 删除/重新上架 + 标题 +
 * 浏览N + ¥价格），tabs 底边 = 885，今日数据卡与推广位在 tabs 之上（§0 守卫）。
 */
class PublishedCardLocatorTest {
    private val tabBottom = 885

    private fun node(
        text: String? = null,
        desc: String? = null,
        visible: Boolean = true,
        left: Int = 0,
        top: Int = 0,
        right: Int = 1080,
        bottom: Int = 0,
        children: List<PublishedCardLocator.UiNode> = emptyList(),
    ) = PublishedCardLocator.UiNode(
        text = text,
        description = desc,
        visible = visible,
        bounds = PublishedCardLocator.Bounds(left, top, right, bottom),
        children = children,
    )

    /** 在卖列表：今日数据卡 + 推广位在 tabs 之上，两张真实卡片在 tabs 之下。 */
    private fun onsaleScrollable(vararg cards: PublishedCardLocator.UiNode) = node(
        top = 225, bottom = 2339, children = cards.toList(),
    )

    private val promoBlock = node(
        // 推广位（tabs 之上）自带推荐商品标题，绝不能被标题匹配命中。
        desc = "为你推荐",
        left = 666, top = 225, right = 1080, bottom = 729,
        children = listOf(node(desc = "黄同学漫画二战史2 推广精选")),
    )

    private val onsaleCard = node(
        left = 24, top = 909, right = 1056, bottom = 1497,
        children = listOf(
            node(desc = "托管\n降价\n编辑\n诊断"),
            node(text = "《黄同学漫画二战史2》个人闲置"),
            node(desc = "曝光12\n浏览34\n想要5"),
            node(text = "¥45.00"),
        ),
    )

    @Test
    fun findsTheUniqueCardBelowTheTabsAndIgnoresThePromoBlockAbove() {
        val scrollable = onsaleScrollable(promoBlock, onsaleCard)
        val outcome = PublishedCardLocator.locate(listOf(scrollable), tabBottom, "黄同学漫画二战史")
        val card = outcome as PublishedCardLocator.Outcome.Card
        assertEquals(24, card.bounds.left)
        assertEquals(909, card.bounds.top)
        assertEquals(1056, card.bounds.right)
        assertEquals(1497, card.bounds.bottom)
        assertEquals(540f, card.bounds.centerX)
        assertEquals(1203f, card.bounds.centerY)
    }

    @Test
    fun matchesTitlesExposedAsEitherTextOrContentDescription() {
        // Flutter 列表的文本有时只走 content-desc（订单行同款）。
        val descOnly = onsaleScrollable(
            node(
                left = 24, top = 909, right = 1056, bottom = 1287,
                children = listOf(node(desc = "《黄同学漫画二战史2》个人闲置")),
            ),
        )
        val outcome = PublishedCardLocator.locate(listOf(descOnly), tabBottom, "二战史2")
        assertTrue(outcome is PublishedCardLocator.Outcome.Card)
    }

    @Test
    fun reportsNotFoundWhenNoCardCarriesTheFragment() {
        val scrollable = onsaleScrollable(onsaleCard)
        val outcome = PublishedCardLocator.locate(listOf(scrollable), tabBottom, "不存在的标题")
        assertEquals(PublishedCardLocator.Outcome.NotFound, outcome)
    }

    @Test
    fun reportsAmbiguousWhenSeveralDistinctCardsMatch() {
        val otherCard = node(
            left = 24, top = 1521, right = 1056, bottom = 2109,
            children = listOf(
                node(text = "黄同学漫画二战史2 绝版复印本"),
                node(desc = "曝光1\n浏览2\n想要0"),
                node(text = "¥88.00"),
            ),
        )
        val scrollable = onsaleScrollable(onsaleCard, otherCard)
        val outcome = PublishedCardLocator.locate(listOf(scrollable), tabBottom, "黄同学漫画二战史")
        val ambiguous = outcome as PublishedCardLocator.Outcome.Ambiguous
        assertEquals(2, ambiguous.count)
    }

    @Test
    fun sameTitleInsideOneCardIsOneMatchNotAmbiguity() {
        // 同一张卡里标题与其父块聚合文本都含关键词 → 仍是同一张卡（去重 by bounds）。
        val card = node(
            left = 24, top = 909, right = 1056, bottom = 1497,
            children = listOf(
                node(desc = "《黄同学漫画二战史2》个人闲置\n曝光12"),
                node(text = "《黄同学漫画二战史2》个人闲置"),
            ),
        )
        val outcome = PublishedCardLocator.locate(listOf(onsaleScrollable(card)), tabBottom, "黄同学漫画二战史")
        assertTrue(outcome is PublishedCardLocator.Outcome.Card)
    }

    @Test
    fun invisibleAndAboveTabsCardsNeverMatch() {
        val hiddenCard = node(
            visible = false,
            left = 24, top = 909, right = 1056, bottom = 1497,
            children = listOf(node(text = "黄同学漫画二战史2 隐藏卡")),
        )
        val scrollable = onsaleScrollable(promoBlock, hiddenCard)
        assertEquals(
            PublishedCardLocator.Outcome.NotFound,
            PublishedCardLocator.locate(listOf(scrollable), tabBottom, "黄同学漫画二战史"),
        )
        // 推广位关键词在 tabs 之上：即便唯一命中也必须被 cardAreaTop 排除。
        val promoOnly = PublishedCardLocator.locate(listOf(onsaleScrollable(promoBlock)), tabBottom, "推广精选")
        assertEquals(PublishedCardLocator.Outcome.NotFound, promoOnly)
    }

    // 2026-09-16 事故回归（错删爆笑漫画成语）：真机活树把全部卡片嵌在滚动容器的
    // 单个全列表包裹子节点下（uiautomator 展平为兄弟，活树不是），卡片文本节点
    // 自带卡片矩形。旧实现返回包裹节点中心 (540,1642) 落在上一张卡上。
    @Test
    fun liveNestedWrapperLayoutTapsTheMatchedCardNotTheWrapperCenter() {
        val blob1 = node(desc = "托管\n降价\n编辑\n诊断\n《小升初新思维作文》个人闲置\n¥18.88", top = 885, bottom = 1434)
        val blob2 = node(desc = "托管\n降价\n编辑\n诊断\n《爆笑漫画成语》个人闲置\n¥18.88", top = 1434, bottom = 2022)
        val blob3 = node(desc = "托管\n降价\n编辑\n诊断\n《海底两万里》个人闲置\n¥8.88", top = 2022, bottom = 2400)
        val wrapper = node(top = 885, bottom = 2400, children = listOf(blob1, blob2, blob3))
        val scrollable = node(top = 885, bottom = 2400, children = listOf(wrapper))

        val outcome = PublishedCardLocator.locate(listOf(scrollable), tabBottom, "海底两万里")
        val card = outcome as PublishedCardLocator.Outcome.Card

        // 必须命中第三张卡自身的矩形，绝不是包裹节点中心。
        assertEquals(2022, card.bounds.top)
        assertEquals(2400, card.bounds.bottom)
        assertEquals(2211f, card.bounds.centerY)
    }

    @Test
    fun aggregatedParentAndBlobBothMatchingCollapseToTheCard() {
        // 包裹层若聚合了子卡文本（同时含关键词），与卡片自身命中同属一张卡。
        val blob = node(desc = "《黄同学漫画二战史2》个人闲置", top = 885, bottom = 1434)
        val aggregate = node(desc = "黄同学漫画二战史2 推荐合集", top = 885, bottom = 1434, children = listOf(blob))
        val scrollable = node(top = 885, bottom = 2400, children = listOf(aggregate))
        val outcome = PublishedCardLocator.locate(listOf(scrollable), tabBottom, "黄同学漫画二战史")
        assertTrue(outcome is PublishedCardLocator.Outcome.Card)
    }

    @Test
    fun delistedCardsMatchThroughTheirOwnTextShape() {
        // 已下架卡片：下架原因 + 删除/重新上架 + 标题 + 浏览N + ¥价格。
        val delistedCard = node(
            left = 0, top = 885, right = 1080, bottom = 1465,
            children = listOf(
                node(desc = "售出下架"),
                node(desc = "删除\n重新上架"),
                node(text = "《黄同学漫画二战史2》个人闲置"),
                node(desc = "浏览7"),
                node(text = "¥45.00"),
            ),
        )
        val scrollable = node(top = 885, bottom = 2339, children = listOf(delistedCard))
        val outcome = PublishedCardLocator.locate(listOf(scrollable), tabBottom, "二战史2》个人")
        assertTrue(outcome is PublishedCardLocator.Outcome.Card)
        assertEquals(885, (outcome as PublishedCardLocator.Outcome.Card).bounds.top)
    }
}
