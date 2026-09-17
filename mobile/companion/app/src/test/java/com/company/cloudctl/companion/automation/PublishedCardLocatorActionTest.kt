package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * B13 — action-button-first card interaction (contract evolution of
 * xianyu-anchors-20260915 §1/§2): the button is the preferred tap target,
 * but ONLY with a same-card proof. Same-name buttons, adjacent-button blobs,
 * cross-card parents and full-list wrappers all fail closed with readable
 * reasons; nothing is ever tapped on a guess.
 */
class PublishedCardLocatorActionTest {
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

    private fun card(top: Int, bottom: Int, vararg children: PublishedCardLocator.UiNode) =
        node(left = 24, top = top, right = 1056, bottom = bottom, children = children.toList())

    /** 在卖卡：标题 + 数据行 + 价格 + 动作区（真实结构里动作区是单条多行 blob）。 */
    private val onsaleCard = card(
        909, 1497,
        node(desc = "托管\n降价\n编辑\n诊断", left = 66, top = 909, right = 546, bottom = 969),
        node(text = "《黄同学漫画二战史2》个人闲置", left = 80, top = 990, right = 760, bottom = 1050),
        node(desc = "曝光12\n浏览34\n想要5", left = 80, top = 1060, right = 546, bottom = 1120),
        node(text = "¥45.00", left = 80, top = 1130, right = 300, bottom = 1190),
    )

    private fun scrollableOf(vararg children: PublishedCardLocator.UiNode) =
        node(top = 885, bottom = 2400, children = children.toList())

    @Test
    fun actionButtonIsPreferredAndProvenInsideTheUniqueCard() {
        // 单行「编辑」节点真身在卡内（托管/降价/编辑/诊断 blob 不是按钮目标）。
        val withButtons = card(
            909, 1497,
            node(desc = "托管\n降价\n编辑\n诊断", left = 66, top = 909, right = 546, bottom = 969),
            node(text = "《黄同学漫画二战史2》个人闲置", left = 80, top = 990, right = 760, bottom = 1050),
            node(text = "编辑", left = 66, top = 1380, right = 226, bottom = 1470),
        )
        val outcome = PublishedCardLocator.locateActionButton(
            listOf(scrollableOf(withButtons)), tabBottom, "黄同学漫画二战史2", "编辑",
        )
        val button = outcome as PublishedCardLocator.ActionOutcome.Button
        assertEquals(PublishedCardLocator.Bounds(66, 1380, 226, 1470), button.buttonBounds)
        // 同卡证明：按钮矩形完全在标题钉住的卡矩形内。
        val b = button.buttonBounds
        val c = button.cardBounds
        assertTrue(c.left <= b.left && c.top <= b.top && c.right >= b.right && c.bottom >= b.bottom)
        assertEquals(24, button.cardBounds.left)
        assertEquals(909, button.cardBounds.top)
        assertEquals("《黄同学漫画二战史2》个人闲置", button.matchedTitleLine)
        assertEquals("编辑", button.actionLabel)
    }

    @Test
    fun multiLabelBlobIsNeverTheButtonTarget() {
        // 相邻按钮陷阱：blob「托管\n降价\n编辑\n诊断」中心落在按钮之间，
        // 不是「编辑」——只有它存在时必须 fail-closed，绝不猜中心点。
        val outcome = PublishedCardLocator.locateActionButton(
            listOf(scrollableOf(onsaleCard)), tabBottom, "黄同学漫画二战史2", "编辑",
        )
        val miss = outcome as PublishedCardLocator.ActionOutcome.NoActionButton
        assertEquals(909, miss.cardBounds.top)
        assertTrue("multi-label" in miss.reason)
    }

    @Test
    fun sameNameButtonsAcrossCardsFailClosedThroughTitleAmbiguity() {
        // 同名按钮：两张卡的标题都含片段 → 先在卡层 fail-closed。
        val otherCard = card(
            1521, 2109,
            node(text = "黄同学漫画二战史2 绝版复印本", left = 80, top = 1600, right = 760, bottom = 1660),
            node(text = "编辑", left = 66, top = 2000, right = 226, bottom = 2090),
        )
        val twoButtonsCard = card(
            909, 1497,
            node(text = "《黄同学漫画二战史2》个人闲置", left = 80, top = 990, right = 760, bottom = 1050),
            node(text = "编辑", left = 66, top = 1380, right = 226, bottom = 1470),
        )
        val outcome = PublishedCardLocator.locateActionButton(
            listOf(scrollableOf(twoButtonsCard, otherCard)), tabBottom, "黄同学漫画二战史2", "编辑",
        )
        val ambiguous = outcome as PublishedCardLocator.ActionOutcome.AmbiguousCard
        assertEquals(2, ambiguous.count)
    }

    @Test
    fun duplicateSameLabelNodesInsideOneCardFailClosed() {
        // 同一张卡里出现两个不同矩形的「编辑」（同名按钮）→ AmbiguousAction。
        val dupCard = card(
            909, 1497,
            node(text = "《黄同学漫画二战史2》个人闲置", left = 80, top = 990, right = 760, bottom = 1050),
            node(text = "编辑", left = 66, top = 1380, right = 226, bottom = 1470),
            node(text = "编辑", left = 300, top = 1380, right = 460, bottom = 1470),
        )
        val outcome = PublishedCardLocator.locateActionButton(
            listOf(scrollableOf(dupCard)), tabBottom, "黄同学漫画二战史2", "编辑",
        )
        val ambiguous = outcome as PublishedCardLocator.ActionOutcome.AmbiguousAction
        assertEquals(2, ambiguous.count)
        assertEquals(2, ambiguous.locations.size)
        assertTrue("same-name buttons fail closed" in ambiguous.reason)
    }

    @Test
    fun fullListWrapperCarryingTheLabelIsACrossCardTarget() {
        // 全列表包裹节点自带「编辑」描述（聚合文本）：与卡重叠但不在卡内。
        val title = node(text = "《黄同学漫画二战史2》个人闲置", left = 80, top = 990, right = 760, bottom = 1050)
        val blob1 = node(desc = "托管\n降价\n编辑\n诊断\n《小升初新思维作文》\n¥18.88", top = 885, bottom = 1434)
        val blob2 = node(desc = "托管\n降价\n编辑\n诊断\n《黄同学漫画二战史2》个人闲置\n¥45.00", top = 1434, bottom = 2022)
        val wrapper = node(desc = "编辑", top = 885, bottom = 2400, children = listOf(blob1, blob2, title))
        val outcome = PublishedCardLocator.locateActionButton(
            listOf(scrollableOf(wrapper)), tabBottom, "黄同学漫画二战史2", "编辑",
        )
        val cross = outcome as PublishedCardLocator.ActionOutcome.CrossCardTarget
        assertTrue("overlapping" in cross.reason)
        assertTrue("0,885,1080,2400" in cross.reason)
    }

    @Test
    fun parentOfTwoAdjacentCardsCarryingTheLabelIsRejected() {
        // 跨卡 parent：同时包住两张相邻卡、自带「编辑」——绝不能当按钮点。
        val targetCard = card(
            1434, 2022,
            node(text = "《黄同学漫画二战史2》个人闲置", left = 80, top = 1500, right = 760, bottom = 1560),
        )
        val otherCard = card(885, 1434)
        val crossParent = node(text = "编辑", top = 885, bottom = 2022, children = listOf(otherCard, targetCard))
        val outcome = PublishedCardLocator.locateActionButton(
            listOf(scrollableOf(crossParent)), tabBottom, "黄同学漫画二战史2", "编辑",
        )
        val cross = outcome as PublishedCardLocator.ActionOutcome.CrossCardTarget
        assertTrue("0,885,1080,2022" in cross.reason)
    }

    @Test
    fun invisibleSameLabelNodesNeverBecomeButtons() {
        val hiddenButtonCard = card(
            909, 1497,
            node(text = "《黄同学漫画二战史2》个人闲置", left = 80, top = 990, right = 760, bottom = 1050),
            node(text = "编辑", visible = false, left = 66, top = 1380, right = 226, bottom = 1470),
        )
        val outcome = PublishedCardLocator.locateActionButton(
            listOf(scrollableOf(hiddenButtonCard)), tabBottom, "黄同学漫画二战史2", "编辑",
        )
        assertTrue(outcome is PublishedCardLocator.ActionOutcome.NoActionButton)
    }

    @Test
    fun nestedSameLabelNodesCollapseToTheSmallestButton() {
        // 文本节点与其父块都恰好是「编辑」单行 → 同一按钮（按 bounds 去重取最小）。
        val nestedCard = card(
            909, 1497,
            node(text = "《黄同学漫画二战史2》个人闲置", left = 80, top = 990, right = 760, bottom = 1050),
            node(
                text = "编辑", left = 66, top = 1380, right = 226, bottom = 1470,
                children = listOf(node(desc = "编辑", left = 70, top = 1385, right = 222, bottom = 1465)),
            ),
        )
        val outcome = PublishedCardLocator.locateActionButton(
            listOf(scrollableOf(nestedCard)), tabBottom, "黄同学漫画二战史2", "编辑",
        )
        val button = outcome as PublishedCardLocator.ActionOutcome.Button
        assertEquals(PublishedCardLocator.Bounds(70, 1385, 222, 1465), button.buttonBounds)
    }

    @Test
    fun titleNotFoundPropagatesToTheActionPath() {
        val outcome = PublishedCardLocator.locateActionButton(
            listOf(scrollableOf(onsaleCard)), tabBottom, "不存在的标题", "编辑",
        )
        assertEquals(PublishedCardLocator.ActionOutcome.NotFound, outcome)
    }

    @Test
    fun unprovableCardRectangleFailsClosedBeforeAnyButtonSearch() {
        // 标题在，但唯一承载者是全列表包裹（无卡矩形可证）→ UnverifiedCardBounds。
        val title = node(text = "《黄同学漫画二战史2》个人闲置", left = 80, top = 990, right = 760, bottom = 1050)
        val wrapper = node(top = 885, bottom = 2400, children = listOf(title))
        val outcome = PublishedCardLocator.locateActionButton(
            listOf(scrollableOf(wrapper)), tabBottom, "黄同学漫画二战史2", "编辑",
        )
        assertTrue(outcome is PublishedCardLocator.ActionOutcome.UnverifiedCardBounds)
    }

    @Test
    fun buttonsOfOtherCardsAreIrrelevantToTheMatchedCard() {
        // 别的卡里也有「编辑」：与本卡无关，不构成歧义。
        val targetCard = card(
            909, 1497,
            node(text = "《黄同学漫画二战史2》个人闲置", left = 80, top = 990, right = 760, bottom = 1050),
            node(text = "编辑", left = 66, top = 1380, right = 226, bottom = 1470),
        )
        val otherCard = card(
            1521, 2109,
            node(text = "《海底两万里》个人闲置", left = 80, top = 1600, right = 760, bottom = 1660),
            node(text = "编辑", left = 66, top = 2000, right = 226, bottom = 2090),
        )
        val outcome = PublishedCardLocator.locateActionButton(
            listOf(scrollableOf(targetCard, otherCard)), tabBottom, "黄同学漫画二战史2", "编辑",
        )
        val button = outcome as PublishedCardLocator.ActionOutcome.Button
        assertEquals(PublishedCardLocator.Bounds(66, 1380, 226, 1470), button.buttonBounds)
        assertEquals(909, button.cardBounds.top)
    }

    @Test
    fun occludedShapeStaysFailClosedAtTheGateNotTheLocator() {
        // 遮挡类验收走 TapAdmissionGate（locators 包）——这里钉住职责边界：
        // 定位器只负责身份/结构证明，遮挡/漂移在 tap 前由门禁复查。
        val targetCard = card(
            909, 1497,
            node(text = "《黄同学漫画二战史2》个人闲置", left = 80, top = 990, right = 760, bottom = 1050),
            node(text = "编辑", left = 66, top = 1380, right = 226, bottom = 1470),
        )
        val outcome = PublishedCardLocator.locateActionButton(
            listOf(scrollableOf(targetCard)), tabBottom, "黄同学漫画二战史2", "编辑",
        )
        assertTrue(outcome is PublishedCardLocator.ActionOutcome.Button)
        assertEquals(
            com.company.cloudctl.companion.locators.TapAdmissionGate.DRIFT_TOLERANCE_PX,
            PublishedCardLocator.BOUNDS_FRESHNESS_TOLERANCE_PX,
        )
    }

    @Test
    fun blankActionLabelIsRejectedAtTheApiBoundary() {
        val failure = kotlin.test.assertFailsWith<IllegalArgumentException> {
            PublishedCardLocator.locateActionButton(
                listOf(scrollableOf(onsaleCard)), tabBottom, "黄同学漫画二战史2", " ",
            )
        }
        assertTrue("actionLabel" in failure.message.orEmpty())
    }
}
