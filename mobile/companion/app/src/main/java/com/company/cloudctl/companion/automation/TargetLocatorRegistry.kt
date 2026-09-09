package com.company.cloudctl.companion.automation

internal sealed interface ApprovedLocator {
    data class ResourceId(val value: String) : ApprovedLocator
    data class ContentDescription(val value: String) : ApprovedLocator
    data class ContentDescriptionPrefix(val prefix: String) : ApprovedLocator
    data class IndexedContentDescription(val value: String, val index: Int) : ApprovedLocator
}

/**
 * Stable, reviewed locators for applications that do not expose view resource IDs for key controls.
 */
internal object TargetLocatorRegistry {
    const val COMPANION_PACKAGE = "com.company.cloudctl.companion"
    const val XIANYU_PACKAGE = "com.taobao.idlefish"
    const val XHS_PACKAGE = "com.xingin.xhs"

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

    fun resolve(targetPackage: String, locatorRef: String): ApprovedLocator {
        val locators = when (targetPackage) {
            COMPANION_PACKAGE -> companionLocators
            XIANYU_PACKAGE -> xianyuLocators
            else -> throw IllegalArgumentException("Target package is not allowlisted")
        }
        locators[locatorRef]?.let { return it }
        if (targetPackage == XIANYU_PACKAGE) {
            val match = Regex("^xianyu_gallery_select_([0-9]|[1-4][0-9])$").matchEntire(locatorRef)
            if (match != null) return ApprovedLocator.IndexedContentDescription("选择", match.groupValues[1].toInt())
        }
        throw IllegalArgumentException("Unknown Companion locator")
    }
}
