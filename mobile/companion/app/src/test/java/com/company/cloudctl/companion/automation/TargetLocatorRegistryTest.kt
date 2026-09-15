package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertIs
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

    // order-sync/20260915.1 §7：三个订单定位器未真机验证，一律 fail-closed，
    // resolveVerified() 必须返回 null（→ 步失败 LOCATOR_UNVERIFIED）。

    @Test
    fun orderSyncLocatorsStayFailClosedUntilDeviceVerified() {
        val refs = setOf(
            "xianyu_order_list_sold",
            "xianyu_order_list_bought",
            "xianyu_orders_container",
        )
        assertEquals(refs, TargetLocatorRegistry.UNVERIFIED_XIANYU_LOCATOR_REFS)
        refs.forEach { ref ->
            assertTrue(TargetLocatorRegistry.isUnverifiedLocator(TargetLocatorRegistry.XIANYU_PACKAGE, ref), ref)
            assertEquals(null, TargetLocatorRegistry.resolveVerified(TargetLocatorRegistry.XIANYU_PACKAGE, ref), ref)
            // 既未验证也绝不混入已验证注册表（resolve() 不认它）。
            assertFailsWith<IllegalArgumentException> {
                TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, ref)
            }
        }
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
