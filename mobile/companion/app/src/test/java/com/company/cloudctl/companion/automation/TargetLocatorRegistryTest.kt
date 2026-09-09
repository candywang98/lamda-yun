package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs

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
}
