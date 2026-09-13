package com.company.cloudctl.companion.automation

internal sealed interface ApprovedLocator {
    data class ResourceId(val value: String) : ApprovedLocator
    data class ContentDescription(val value: String) : ApprovedLocator
    data class ContentDescriptionPrefix(val prefix: String) : ApprovedLocator
    data class IndexedContentDescription(val value: String, val index: Int) : ApprovedLocator
    data class Text(val value: String) : ApprovedLocator
    data class TextPrefix(val prefix: String) : ApprovedLocator
    data class IndexedResourceId(val value: String, val index: Int) : ApprovedLocator
    data class IndexedContentDescriptionPrefix(val prefix: String, val index: Int) : ApprovedLocator
    data class IndexedContentDescriptionPrefixParent(val prefix: String, val index: Int) : ApprovedLocator
}

/**
 * Stable, reviewed locators for applications that do not expose view resource IDs for key controls.
 * XHS locators are verified against com.xingin.xhs 8.50.1, Douyin against 39.6.0 (OnePlus 9R) on 2026-09-13.
 */
internal object TargetLocatorRegistry {
    const val COMPANION_PACKAGE = "com.company.cloudctl.companion"
    const val XIANYU_PACKAGE = "com.taobao.idlefish"
    const val XHS_PACKAGE = "com.xingin.xhs"
    const val DOUYIN_PACKAGE = "com.ss.android.ugc.aweme"

    private val companionLocators = mapOf(
        "companion_home_root" to ApprovedLocator.ContentDescription("companion_home_root"),
        "companion_refresh" to ApprovedLocator.ContentDescription("Refresh status"),
        "companion_stop" to ApprovedLocator.ContentDescription("Stop automation"),
        "companion_bind" to ApprovedLocator.ContentDescription("Bind device"),
    )

    private val xianyuLocators = mapOf(
        "xianyu_home_sell" to ApprovedLocator.ContentDescription("卖闲置"),
        "xianyu_publish_entry" to ApprovedLocator.ContentDescription("发闲置\n自己拍图卖·啥都能换钱"),
        "xianyu_publish_page" to ApprovedLocator.ContentDescription("发闲置"),
        "xianyu_draft_discard" to ApprovedLocator.ContentDescription("放弃"),
        "xianyu_draft_nosave" to ApprovedLocator.ContentDescription("不保存"),
        "xianyu_add_image" to ApprovedLocator.ContentDescription("添加图片"),
        "xianyu_gallery_next" to ApprovedLocator.ContentDescriptionPrefix("下一步"),
        "xianyu_crop_done" to ApprovedLocator.ContentDescription("完成"),
        "xianyu_description" to ApprovedLocator.ContentDescriptionPrefix("描述一下"),
        "xianyu_price" to ApprovedLocator.ContentDescriptionPrefix("价格"),
        "xianyu_price_sheet" to ApprovedLocator.ContentDescription("定价"),
        "xianyu_price_amount" to ApprovedLocator.ContentDescription("¥"),
        "xianyu_price_confirm" to ApprovedLocator.ContentDescription("确定"),
        "xianyu_composer_done" to ApprovedLocator.ContentDescription("完成"),
        "xianyu_publish_success" to ApprovedLocator.ContentDescriptionPrefix("发布成功"),
        "xianyu_paste" to ApprovedLocator.ContentDescription("粘贴"),
        "xianyu_select_all" to ApprovedLocator.ContentDescription("全选"),
        "xianyu_shipping" to ApprovedLocator.ContentDescription("发货方式\n包邮"),
        "xianyu_location" to ApprovedLocator.ContentDescription("选择位置"),
        "xianyu_location_page" to ApprovedLocator.ContentDescription("宝贝所在地"),
        "xianyu_location_saved_0" to ApprovedLocator.ContentDescriptionPrefix("北营新村丰景佳园"),
        "xianyu_publish_blocked_ack" to ApprovedLocator.ContentDescription("我知道了"),
        "xianyu_publish_button" to ApprovedLocator.ContentDescription("发布"),
    )

    private val xhsLocators = mapOf(
        "xhs_home_publish" to ApprovedLocator.ContentDescription("发布"),
        "xhs_publish_sheet" to ApprovedLocator.Text("相册"),
        "xhs_pick_next" to ApprovedLocator.Text("下一步"),
        "xhs_edit_next" to ApprovedLocator.Text("下一步"),
        "xhs_edit_page" to ApprovedLocator.Text("贴纸"),
        "xhs_note_title" to ApprovedLocator.Text("添加标题"),
        "xhs_note_body" to ApprovedLocator.Text("添加正文"),
        "xhs_publish_button" to ApprovedLocator.Text("发布笔记"),
        "xhs_publish_success" to ApprovedLocator.TextPrefix("发布成功"),
        "xhs_draft_stay" to ApprovedLocator.Text("留在本页"),
    )

    // Verified against com.ss.android.ugc.aweme 39.6.0 (OnePlus 9R) on 2026-09-13.
    private val douyinLocators = mapOf(
        "dy_home_publish" to ApprovedLocator.ContentDescription("拍摄，按钮"),
        "dy_camera_album" to ApprovedLocator.Text("相册"),
        "dy_media_images_tab" to ApprovedLocator.Text("图片"),
        "dy_pick_next" to ApprovedLocator.Text("下一步"),
        "dy_edit_page" to ApprovedLocator.Text("贴纸"),
        "dy_edit_next" to ApprovedLocator.Text("下一步"),
        "dy_note_title" to ApprovedLocator.Text("添加标题"),
        "dy_note_body" to ApprovedLocator.TextPrefix("添加作品描述"),
        "dy_publish_button" to ApprovedLocator.Text("发作品"),
        "dy_publish_success" to ApprovedLocator.TextPrefix("发布成功"),
        "dy_cellmark_probe" to ApprovedLocator.TextPrefix(", 未选中"),
    )

    fun resolve(targetPackage: String, locatorRef: String): ApprovedLocator {
        val locators = when (targetPackage) {
            COMPANION_PACKAGE -> companionLocators
            XIANYU_PACKAGE -> xianyuLocators
            XHS_PACKAGE -> xhsLocators
            DOUYIN_PACKAGE -> douyinLocators
            else -> throw IllegalArgumentException("Target package is not allowlisted")
        }
        locators[locatorRef]?.let { return it }
        if (targetPackage == XIANYU_PACKAGE) {
            val match = Regex("^xianyu_gallery_select_([0-9]|[1-4][0-9])$").matchEntire(locatorRef)
            if (match != null) return ApprovedLocator.IndexedContentDescription("选择", match.groupValues[1].toInt())
        }
        if (targetPackage == XHS_PACKAGE) {
            val match = Regex("^xhs_gallery_cell_([0-9]|[1-4][0-9])$").matchEntire(locatorRef)
            if (match != null) {
                return ApprovedLocator.IndexedResourceId("com.xingin.xhs:id/ixd", match.groupValues[1].toInt())
            }
        }
        if (targetPackage == DOUYIN_PACKAGE) {
            val match = Regex("^dy_gallery_cell_([0-9]|[1-4][0-9])$").matchEntire(locatorRef)
            if (match != null) {
                // Douyin grid cells expose no stable resource-id lookup through the
                // accessibility view-id search; their selection mark ("<name>, 未选中")
                // is unique per cell and verified on 39.6.0.
                return ApprovedLocator.IndexedContentDescriptionPrefixParent(", 未选中", match.groupValues[1].toInt())
            }
        }
        throw IllegalArgumentException("Unknown Companion locator")
    }
}
