package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class DouyinLocatorRegistryTest {
    private val pkg = TargetLocatorRegistry.DOUYIN_PACKAGE

    @Test
    fun resolvesVerifiedDouyinLocators() {
        assertEquals(
            ApprovedLocator.ContentDescription("拍摄，按钮"),
            TargetLocatorRegistry.resolve(pkg, "dy_home_publish"),
        )
        assertEquals(ApprovedLocator.Text("相册"), TargetLocatorRegistry.resolve(pkg, "dy_camera_album"))
        assertEquals(ApprovedLocator.Text("图片"), TargetLocatorRegistry.resolve(pkg, "dy_media_images_tab"))
        assertEquals(ApprovedLocator.Text("下一步"), TargetLocatorRegistry.resolve(pkg, "dy_pick_next"))
        assertEquals(ApprovedLocator.Text("贴纸"), TargetLocatorRegistry.resolve(pkg, "dy_edit_page"))
        assertEquals(ApprovedLocator.Text("添加标题"), TargetLocatorRegistry.resolve(pkg, "dy_note_title"))
        assertEquals(
            ApprovedLocator.TextPrefix("添加作品描述"),
            TargetLocatorRegistry.resolve(pkg, "dy_note_body"),
        )
        assertEquals(ApprovedLocator.Text("发作品"), TargetLocatorRegistry.resolve(pkg, "dy_publish_button"))
        assertEquals(
            ApprovedLocator.IndexedContentDescriptionPrefixParent(", 未选中", 0),
            TargetLocatorRegistry.resolve(pkg, "dy_gallery_cell_0"),
        )
    }

    @Test
    fun rejectsCrossPackageAndOutOfRangeCells() {
        assertFailsWith<IllegalArgumentException> { TargetLocatorRegistry.resolve(pkg, "xhs_home_publish") }
        assertFailsWith<IllegalArgumentException> { TargetLocatorRegistry.resolve(pkg, "dy_gallery_cell_50") }
        assertFailsWith<IllegalArgumentException> { TargetLocatorRegistry.resolve(pkg, "dy_unknown") }
    }
}
