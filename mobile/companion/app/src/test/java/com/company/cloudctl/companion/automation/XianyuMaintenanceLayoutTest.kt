package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * JVM coverage for the frozen xianyu maintenance coordinate layer
 * (contracts/phase1/xianyu-maintenance-anchors-20260915.md, OnePlus 9R
 * 1080x2400): every mapped pairing reproduces the surveyed coordinate, and
 * every unmapped pairing — other resolution, unknown tab/action, or a card row
 * off the guarded screen — fails closed with null.
 */
class XianyuMaintenanceLayoutTest {

    private val width = XianyuMaintenanceLayout.GUARD_WIDTH
    private val height = XianyuMaintenanceLayout.GUARD_HEIGHT

    private fun resolve(
        tab: XianyuMaintenanceLayout.Tab,
        action: XianyuMaintenanceLayout.LayoutAction,
        cardIndex: Int,
    ) = XianyuMaintenanceLayout.resolve(width, height, tab, action, cardIndex)

    @Test
    fun delistedCardsStepByTheFrozen460RowPitch() {
        // 已下架卡片：删除(657,y)/重新上架(904,y)；y = 1207/1667/2127（步进 460）。
        assertEquals(
            listOf(1207, 1667, 2127),
            (0..2).map { index ->
                resolve(XianyuMaintenanceLayout.Tab.DELISTED, XianyuMaintenanceLayout.LayoutAction.DELETE_CARD, index)!!.y
            },
        )
        assertEquals(
            listOf(657, 657, 657),
            (0..2).map { index ->
                resolve(XianyuMaintenanceLayout.Tab.DELISTED, XianyuMaintenanceLayout.LayoutAction.DELETE_CARD, index)!!.x
            },
        )
        assertEquals(
            XianyuMaintenanceLayout.Point(904, 1207),
            resolve(XianyuMaintenanceLayout.Tab.DELISTED, XianyuMaintenanceLayout.LayoutAction.RELIST_CARD, 0),
        )
        assertEquals(
            XianyuMaintenanceLayout.Point(904, 2127),
            resolve(XianyuMaintenanceLayout.Tab.DELISTED, XianyuMaintenanceLayout.LayoutAction.RELIST_CARD, 2),
        )
    }

    @Test
    fun draftCardsStepByTheFrozen393RowPitch() {
        // 草稿卡片：删除(695,y)/编辑(920,y)；y = 1138/1531（步进 393）。
        assertEquals(
            XianyuMaintenanceLayout.Point(695, 1138),
            resolve(XianyuMaintenanceLayout.Tab.DRAFT, XianyuMaintenanceLayout.LayoutAction.DELETE_CARD, 0),
        )
        assertEquals(
            XianyuMaintenanceLayout.Point(695, 1531),
            resolve(XianyuMaintenanceLayout.Tab.DRAFT, XianyuMaintenanceLayout.LayoutAction.DELETE_CARD, 1),
        )
        assertEquals(
            XianyuMaintenanceLayout.Point(920, 1138),
            resolve(XianyuMaintenanceLayout.Tab.DRAFT, XianyuMaintenanceLayout.LayoutAction.EDIT_CARD, 0),
        )
        assertEquals(
            XianyuMaintenanceLayout.Point(920, 1531),
            resolve(XianyuMaintenanceLayout.Tab.DRAFT, XianyuMaintenanceLayout.LayoutAction.EDIT_CARD, 1),
        )
    }

    @Test
    fun onsaleFirstCardAndPageEntriesUseTheSurveyedPoints() {
        // 在卖首卡：···(85,1270)/编辑(927,1270)；后续行无已验证步进。
        assertEquals(
            XianyuMaintenanceLayout.Point(85, 1270),
            resolve(XianyuMaintenanceLayout.Tab.ONSALE, XianyuMaintenanceLayout.LayoutAction.MORE, 0),
        )
        assertEquals(
            XianyuMaintenanceLayout.Point(927, 1270),
            resolve(XianyuMaintenanceLayout.Tab.ONSALE, XianyuMaintenanceLayout.LayoutAction.EDIT_CARD, 0),
        )
        // 页顶「一键擦亮」(210,620) 与 ActionSheet「下架」第 5 项 (540,1763)。
        assertEquals(
            XianyuMaintenanceLayout.Point(210, 620),
            resolve(XianyuMaintenanceLayout.Tab.ONSALE, XianyuMaintenanceLayout.LayoutAction.POLISH_ALL, 0),
        )
        assertEquals(
            XianyuMaintenanceLayout.Point(540, 1763),
            resolve(XianyuMaintenanceLayout.Tab.ONSALE, XianyuMaintenanceLayout.LayoutAction.DELIST_MENU_ITEM, 0),
        )
    }

    @Test
    fun centeredConfirmDialogRowIsTabIndependent() {
        // 确认弹窗行 y=1305：下架确定(755)/删除确定(745)/取消(345)。
        for (tab in XianyuMaintenanceLayout.Tab.entries) {
            assertEquals(
                XianyuMaintenanceLayout.Point(755, 1305),
                resolve(tab, XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELIST, 0),
            )
            assertEquals(
                XianyuMaintenanceLayout.Point(745, 1305),
                resolve(tab, XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELETE, 0),
            )
            assertEquals(
                XianyuMaintenanceLayout.Point(345, 1305),
                resolve(tab, XianyuMaintenanceLayout.LayoutAction.CONFIRM_CANCEL, 0),
            )
        }
    }

    @Test
    fun cardRowsPastTheGuardedScreenFailClosed() {
        // 已下架第 4 卡 y=2587、草稿第 5 卡 y=2710：越界 → null，不猜测。
        assertNull(resolve(XianyuMaintenanceLayout.Tab.DELISTED, XianyuMaintenanceLayout.LayoutAction.DELETE_CARD, 3))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.DELISTED, XianyuMaintenanceLayout.LayoutAction.RELIST_CARD, 3))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.DRAFT, XianyuMaintenanceLayout.LayoutAction.DELETE_CARD, 4))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.DRAFT, XianyuMaintenanceLayout.LayoutAction.EDIT_CARD, 4))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.ONSALE, XianyuMaintenanceLayout.LayoutAction.MORE, -1))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.ONSALE, XianyuMaintenanceLayout.LayoutAction.MORE, 1))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.ONSALE, XianyuMaintenanceLayout.LayoutAction.EDIT_CARD, 1))
        // 确认弹窗不依赖卡片序号，但非 0 拒绝。
        assertNull(resolve(XianyuMaintenanceLayout.Tab.ONSALE, XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELIST, 2))
    }

    @Test
    fun unverifiedTabActionPairingsFailClosed() {
        assertNull(resolve(XianyuMaintenanceLayout.Tab.ONSALE, XianyuMaintenanceLayout.LayoutAction.DELETE_CARD, 0))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.ONSALE, XianyuMaintenanceLayout.LayoutAction.RELIST_CARD, 0))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.ONSALE, XianyuMaintenanceLayout.LayoutAction.DELIST_MENU_ITEM, 1))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.DELISTED, XianyuMaintenanceLayout.LayoutAction.EDIT_CARD, 0))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.DRAFT, XianyuMaintenanceLayout.LayoutAction.POLISH_ALL, 0))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.DRAFT, XianyuMaintenanceLayout.LayoutAction.MORE, 0))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.DRAFT, XianyuMaintenanceLayout.LayoutAction.DELIST_MENU_ITEM, 0))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.DELISTED, XianyuMaintenanceLayout.LayoutAction.POLISH_ALL, 0))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.DELISTED, XianyuMaintenanceLayout.LayoutAction.MORE, 0))
        assertNull(resolve(XianyuMaintenanceLayout.Tab.DELISTED, XianyuMaintenanceLayout.LayoutAction.DELIST_MENU_ITEM, 0))
    }

    @Test
    fun resolutionGuardAcceptsOnlyTheFrozen1080x2400Geometry() {
        val action = XianyuMaintenanceLayout.LayoutAction.DELETE_CARD
        for ((w, h) in listOf(1080 to 2340, 1080 to 2401, 1440 to 3200, 720 to 1600, 0 to 0)) {
            assertNull(
                XianyuMaintenanceLayout.resolve(w, h, XianyuMaintenanceLayout.Tab.DELISTED, action, 0),
                "expected guard rejection for ${w}x$h",
            )
        }
        // The frozen geometry alone maps.
        assertEquals(
            XianyuMaintenanceLayout.Point(657, 1207),
            XianyuMaintenanceLayout.resolve(1080, 2400, XianyuMaintenanceLayout.Tab.DELISTED, action, 0),
        )
    }

    @Test
    fun badgeNumbersParseFromTabDescriptions() {
        // 「N\n在卖」的 N 是核验信号；纯文案按 0 处理。
        assertEquals(1, XianyuMaintenanceLayout.parseBadge("1\n在卖"))
        assertEquals(12, XianyuMaintenanceLayout.parseBadge("12\n在卖"))
        assertEquals(0, XianyuMaintenanceLayout.parseBadge("0\n在卖"))
        assertEquals(3, XianyuMaintenanceLayout.parseBadge("3\n草稿"))
        assertEquals(2, XianyuMaintenanceLayout.parseBadge("2\n已下架"))
        assertEquals(0, XianyuMaintenanceLayout.parseBadge("在卖"))
        assertEquals(0, XianyuMaintenanceLayout.parseBadge("草稿"))
        assertEquals(0, XianyuMaintenanceLayout.parseBadge("已下架"))
        // 未验证形态一律 null，绝不猜数。
        assertNull(XianyuMaintenanceLayout.parseBadge(null))
        assertNull(XianyuMaintenanceLayout.parseBadge(""))
        assertNull(XianyuMaintenanceLayout.parseBadge("闲鱼，闲不住"))
        assertNull(XianyuMaintenanceLayout.parseBadge("在卖 1"))
        assertNull(XianyuMaintenanceLayout.parseBadge("1 在卖"))
        assertNull(XianyuMaintenanceLayout.parseBadge("在卖\n1"))
        assertNull(XianyuMaintenanceLayout.parseBadge("12345\n在卖"))
    }

    @Test
    fun gatedActionsAreExactlyTheDestructiveConfirmStrikes() {
        assertEquals(
            setOf(
                XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELETE,
                XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELIST,
            ),
            XianyuMaintenanceLayout.GATED_DESTRUCTIVE_CONFIRM_ACTIONS,
        )
        // 下架成功⇒在卖 N-1；删除成功⇒已下架 N-1；擦亮无角标核验。
        assertEquals(
            "xianyu_pub_tab_onsale",
            XianyuMaintenanceLayout.badgeLocatorFor(XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELIST),
        )
        assertEquals(
            "xianyu_pub_tab_delisted",
            XianyuMaintenanceLayout.badgeLocatorFor(XianyuMaintenanceLayout.LayoutAction.CONFIRM_DELETE),
        )
        assertNull(XianyuMaintenanceLayout.badgeLocatorFor(XianyuMaintenanceLayout.LayoutAction.POLISH_ALL))
        assertNull(XianyuMaintenanceLayout.badgeLocatorFor(XianyuMaintenanceLayout.LayoutAction.CONFIRM_CANCEL))
    }

    @Test
    fun badgeTabLocatorsMatchOnlyPublishedTabDescriptions() {
        assertEquals(
            listOf(
                "xianyu_pub_tab_onsale",
                "xianyu_pub_tab_draft",
                "xianyu_pub_tab_delisted",
            ),
            AutomationTaskParser.BADGE_TAB_LOCATOR_REFS.toList(),
        )
        val onsale = TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_pub_tab_onsale")
        val delisted = TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_pub_tab_delisted")
        for (value in listOf("1\n在卖", "在卖", "9999\n在卖")) {
            assertTrue(TargetLocatorRegistry.acceptsDescription(onsale, value), "expected match for $value")
        }
        for (value in listOf("2\n已下架", "已下架")) {
            assertTrue(TargetLocatorRegistry.acceptsDescription(delisted, value), "expected match for $value")
        }
        // 首页 tab 与无关节点绝不匹配。
        for (value in listOf("闲鱼，闲不住的都在这里", "我的", "我发布的", "1 在卖")) {
            assertTrue(!TargetLocatorRegistry.acceptsDescription(onsale, value), "expected rejection for $value")
        }
    }
}
