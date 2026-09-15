package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class TargetLocatorRegistryTest {
    @Test
    fun resolvesCompanionControlsToExactSelectors() {
        val root = assertIs<ApprovedLocator.ContentDescription>(
            TargetLocatorRegistry.resolve(
                TargetLocatorRegistry.COMPANION_PACKAGE,
                "companion_home_root",
            ),
        )
        val refresh = assertIs<ApprovedLocator.ContentDescription>(
            TargetLocatorRegistry.resolve(
                TargetLocatorRegistry.COMPANION_PACKAGE,
                "companion_refresh",
            ),
        )

        assertEquals("companion_home_root", root.value)
        assertEquals("Refresh status", refresh.value)
    }

    @Test
    fun refusesOtherPackagesAndUnknownNames() {
        assertFailsWith<IllegalArgumentException> {
            TargetLocatorRegistry.resolve("com.example.target", "companion_home_root")
        }
        assertFailsWith<IllegalArgumentException> {
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.COMPANION_PACKAGE, "unreviewed")
        }
    }

    @Test
    fun rejectsUnknownResourceIdLocators() {
        assertFailsWith<IllegalArgumentException> {
            TargetLocatorRegistry.resolve("com.example.target", "login_button")
        }
    }

    @Test
    fun resolvesIdlefishPublishFormControls() {
        val description = assertIs<ApprovedLocator.ContentDescriptionPrefix>(
            TargetLocatorRegistry.resolve(
                TargetLocatorRegistry.XIANYU_PACKAGE,
                "xianyu_description",
            ),
        )
        val price = assertIs<ApprovedLocator.ContentDescriptionPrefix>(
            TargetLocatorRegistry.resolve(
                TargetLocatorRegistry.XIANYU_PACKAGE,
                "xianyu_price",
            ),
        )

        assertEquals("描述一下", description.prefix)
        assertEquals("价格", price.prefix)
        listOf(
            "xianyu_home_sell",
            "xianyu_publish_entry",
            "xianyu_publish_page",
            "xianyu_draft_discard",
            "xianyu_paste",
            "xianyu_select_all",
            "xianyu_add_image",
            "xianyu_shipping",
            "xianyu_location",
            "xianyu_crop_done",
            "xianyu_price_amount",
            "xianyu_publish_success",
            "xianyu_publish_button",
        ).forEach { locatorRef ->
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, locatorRef)
        }
    }

    @Test
    fun refusesUnreviewedGalleryPicks() {
        assertFailsWith<IllegalArgumentException> {
            TargetLocatorRegistry.resolve(
                TargetLocatorRegistry.XIANYU_PACKAGE,
                "xianyu_gallery_item_0",
            )
        }
    }

    @Test
    fun resolvesOnlyBoundedIndexedGalleryPickLocators() {
        val locator = assertIs<ApprovedLocator.IndexedContentDescription>(
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_gallery_select_0"),
        )
        assertEquals("选择", locator.value)
        assertEquals(0, locator.index)
        TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_gallery_select_49")
        assertFailsWith<IllegalArgumentException> {
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_gallery_select_50")
        }
    }

    // im-feed-noise / duty-anchor (device evidence 2026-09-14): the 消息 tab
    // exposes three a11y forms; the 闲鱼 home tab must never match.

    @Test
    fun messagesTabLocatorKeepsTheVerifiedUnreadPrefixAsFirstAlternative() {
        val locator = assertIs<ApprovedLocator.AnyOf>(
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_messages_tab"),
        )
        val unread = assertIs<ApprovedLocator.ContentDescriptionPrefix>(locator.alternatives.first())
        assertEquals("消息，未读消息数", unread.prefix)
        assertEquals(3, locator.alternatives.size)
    }

    @Test
    fun messagesTabLocatorMatchesAllThreeTabFormsButNeverTheHomeTab() {
        val locator = TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_messages_tab")
        // 有未读 (verified 2026-09-13).
        assertTrue(TargetLocatorRegistry.acceptsDescription(locator, "消息，未读消息数1"))
        assertTrue(TargetLocatorRegistry.acceptsDescription(locator, "消息，未读消息数3，选中状态"))
        // 无未读 / 未选中 (verified 2026-09-14, bounds [663,2202][859,2352]).
        assertTrue(TargetLocatorRegistry.acceptsDescription(locator, "消息，未选中状态"))
        // 选中态.
        assertTrue(TargetLocatorRegistry.acceptsDescription(locator, "消息，选中状态"))
        // 首页 tab 以「闲鱼，」开头，绝不能误配.
        assertFalse(TargetLocatorRegistry.acceptsDescription(locator, "闲鱼，未读消息数0，选中状态"))
        assertFalse(TargetLocatorRegistry.acceptsDescription(locator, "闲鱼，未选中状态"))
        assertFalse(TargetLocatorRegistry.acceptsDescription(locator, "闲鱼，选中状态"))
        // Partial strings are not tab forms.
        assertFalse(TargetLocatorRegistry.acceptsDescription(locator, "消息"))
    }

    @Test
    fun xianyuMessagesTabFormDetectorMirrorsTheLocatorForms() {
        assertTrue(TargetLocatorRegistry.isXianyuMessagesTabDescription("消息，未读消息数1"))
        assertTrue(TargetLocatorRegistry.isXianyuMessagesTabDescription("消息，未选中状态"))
        assertTrue(TargetLocatorRegistry.isXianyuMessagesTabDescription("消息，选中状态"))
        assertFalse(TargetLocatorRegistry.isXianyuMessagesTabDescription("闲鱼，未读消息数0，选中状态"))
        assertFalse(TargetLocatorRegistry.isXianyuMessagesTabDescription("卖闲置"))
    }

    // order-sync slice 1：三个订单定位器已于 2026-09-15 真机验收翻转 verified
    // （总控 recon-20260915-2 + xianyu-anchors-20260915 §3）；§7 fail-closed 机制
    // 由预注册的 slice-2 详情容器定位器继续承载。
    @Test
    fun orderSyncSlice1LocatorsAreDeviceVerified() {
        val verified = setOf(
            "xianyu_order_list_sold",
            "xianyu_order_list_bought",
            "xianyu_orders_container",
        )
        verified.forEach { ref ->
            assertFalse(TargetLocatorRegistry.isUnverifiedLocator(TargetLocatorRegistry.XIANYU_PACKAGE, ref), ref)
            assertNotNull(TargetLocatorRegistry.resolveVerified(TargetLocatorRegistry.XIANYU_PACKAGE, ref), ref)
        }
        // 入口是 text 字段的 TextView（非 content-desc），容器是「订单信息」行的父节点。
        assertEquals(
            ApprovedLocator.Text("我卖出的"),
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_order_list_sold"),
        )
        assertEquals(
            ApprovedLocator.Text("我买到的"),
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_order_list_bought"),
        )
        assertEquals(
            ApprovedLocator.IndexedContentDescriptionPrefixParent(OrderRowParser.ROW_MARKER_PREFIX, 0),
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_orders_container"),
        )
    }

    @Test
    fun slice2OrderDetailLocatorStaysFailClosedUntilSurveyed() {
        val ref = "xianyu_order_detail_container"
        assertTrue(TargetLocatorRegistry.isUnverifiedLocator(TargetLocatorRegistry.XIANYU_PACKAGE, ref))
        assertEquals(null, TargetLocatorRegistry.resolveVerified(TargetLocatorRegistry.XIANYU_PACKAGE, ref), ref)
        // 既未验证也绝不混入已验证注册表（resolve() 不认它）。
        assertFailsWith<IllegalArgumentException> {
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, ref)
        }
    }

    // W4 维护动作 v2（契约 xianyu-anchors-20260915 §2）：详情页管理按钮 + 管理菜单
    // 文本锚点。定义已预挂在 pending 表，真机验收（总控）前 §7 集合成员保持
    // fail-closed：resolveVerified() 返回 null → ui.tap 以 LOCATOR_UNVERIFIED 安全
    // 终止，零副作用；翻转 = 仅从集合移除 ref。
    // 2026-09-15 总控完成无意图安全干跑后翻转：四个 ref 已 verified，集合仅剩
    // slice-2 详情容器。
    @Test
    fun w4ManageLocatorsFlippedAfterDeviceDryRun() {
        val refs = setOf(
            "xianyu_detail_manage",
            "xianyu_manage_delist",
            "xianyu_manage_delete",
            "xianyu_manage_cancel",
        )
        assertEquals(
            setOf("xianyu_order_detail_container"),
            TargetLocatorRegistry.UNVERIFIED_XIANYU_LOCATOR_REFS,
        )
        refs.forEach { ref ->
            assertFalse(TargetLocatorRegistry.isUnverifiedLocator(TargetLocatorRegistry.XIANYU_PACKAGE, ref), ref)
            // 翻转后消费方拿到冻结定义。
            assertNotNull(TargetLocatorRegistry.resolveVerified(TargetLocatorRegistry.XIANYU_PACKAGE, ref), ref)
        }
    }

    @Test
    fun w4ManageLocatorDefinitionsMatchTheFrozenAnchorContract() {
        // 契约 §2 冻结定义：管理按钮 content-desc=='管理按钮'；菜单项全文本标签。
        assertEquals(
            ApprovedLocator.ContentDescription("管理按钮"),
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_detail_manage"),
        )
        assertEquals(
            ApprovedLocator.Text("下架"),
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_manage_delist"),
        )
        assertEquals(
            ApprovedLocator.Text("删除"),
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_manage_delete"),
        )
        assertEquals(
            ApprovedLocator.Text("取消"),
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_manage_cancel"),
        )
        // 文本锚点是精确匹配：「一键擦亮」「推广宝贝」（G3 禁区）与带前缀的
        // 「重新上架」都不得命中下架/删除/取消锚点。
        val delist = TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_manage_delist")
        val delete = TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_manage_delete")
        val cancel = TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_manage_cancel")
        mapOf(
            delist to listOf("推广宝贝", "超级擦亮", "批量下架", "下架原因"),
            delete to listOf("删除成功", "不保存"),
            cancel to listOf("取消关注", "批量取消"),
        ).forEach { (locator, nonMatches) ->
            nonMatches.forEach { text ->
                assertFalse(TargetLocatorRegistry.acceptsDescription(locator, text), text)
            }
        }
        assertTrue(TargetLocatorRegistry.acceptsDescription(delist, "下架"))
        assertTrue(TargetLocatorRegistry.acceptsDescription(delete, "删除"))
        assertTrue(TargetLocatorRegistry.acceptsDescription(cancel, "取消"))
    }

    @Test
    fun verifiedLocatorsResolveAsBeforeThroughTheVerifiedGate() {
        val locator = TargetLocatorRegistry.resolveVerified(
            TargetLocatorRegistry.XIANYU_PACKAGE,
            "xianyu_home_sell",
        )
        assertEquals(
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_home_sell"),
            locator,
        )
        // 未验证集合只作用于闲鱼包：同名 ref 出现在别的包不受影响（仍走原 allowlist 拒绝）。
        assertFalse(TargetLocatorRegistry.isUnverifiedLocator(TargetLocatorRegistry.COMPANION_PACKAGE, "xianyu_orders_container"))
        assertFailsWith<IllegalArgumentException> {
            TargetLocatorRegistry.resolveVerified(TargetLocatorRegistry.COMPANION_PACKAGE, "xianyu_orders_container")
        }
    }
}
