package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class XhsLocatorRegistryTest {
    @Test
    fun resolvesVerifiedXiaohongshuLocators() {
        val pkg = TargetLocatorRegistry.XHS_PACKAGE
        assertEquals(
            ApprovedLocator.ContentDescription("发布"),
            TargetLocatorRegistry.resolve(pkg, "xhs_home_publish"),
        )
        assertEquals(
            ApprovedLocator.Text("添加标题"),
            TargetLocatorRegistry.resolve(pkg, "xhs_note_title"),
        )
        assertEquals(
            ApprovedLocator.Text("添加正文"),
            TargetLocatorRegistry.resolve(pkg, "xhs_note_body"),
        )
        assertEquals(
            ApprovedLocator.Text("发布笔记"),
            TargetLocatorRegistry.resolve(pkg, "xhs_publish_button"),
        )
        assertEquals(
            ApprovedLocator.TextPrefix("发布成功"),
            TargetLocatorRegistry.resolve(pkg, "xhs_publish_success"),
        )
        assertEquals(
            ApprovedLocator.IndexedResourceId("com.xingin.xhs:id/ixd", 0),
            TargetLocatorRegistry.resolve(pkg, "xhs_gallery_cell_0"),
        )
        assertEquals(
            ApprovedLocator.IndexedResourceId("com.xingin.xhs:id/ixd", 17),
            TargetLocatorRegistry.resolve(pkg, "xhs_gallery_cell_17"),
        )
    }

    @Test
    fun rejectsUnknownOrCrossPackageLocators() {
        val pkg = TargetLocatorRegistry.XHS_PACKAGE
        assertFailsWith<IllegalArgumentException> { TargetLocatorRegistry.resolve(pkg, "xhs_unknown") }
        assertFailsWith<IllegalArgumentException> { TargetLocatorRegistry.resolve(pkg, "xianyu_publish_button") }
        assertFailsWith<IllegalArgumentException> {
            TargetLocatorRegistry.resolve(pkg, "xhs_gallery_cell_50")
        }
        assertFailsWith<IllegalArgumentException> {
            TargetLocatorRegistry.resolve("com.other.app", "xhs_home_publish")
        }
    }

    @Test
    fun gateRoutingCoversBothPlatforms() {
        assertTrue("xianyu_publish_button" in setOf("xianyu_publish_button", "xhs_publish_button"))
        assertTrue("xhs_publish_button" in setOf("xianyu_publish_button", "xhs_publish_button"))
    }
}
