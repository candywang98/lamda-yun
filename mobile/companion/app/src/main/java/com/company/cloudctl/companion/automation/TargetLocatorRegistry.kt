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
    /** Full-match regular expression over a single content description / text value. */
    data class DescRegex(val pattern: Regex) : ApprovedLocator
    data class IndexedContentDescriptionPrefixParent(val prefix: String, val index: Int) : ApprovedLocator
    data class GuardedDialogAction(
        val actionText: String,
        val dialogText: String,
        val cancelText: String,
    ) : ApprovedLocator

    /**
     * Any alternative can satisfy the locator. Used for controls the target app
     * exposes in several accessibility forms (e.g. a tab with and without an
     * unread badge); alternatives are tried against the same node tree and the
     * results are merged, so a node matching any form resolves exactly as before.
     */
    data class AnyOf(val alternatives: List<ApprovedLocator>) : ApprovedLocator
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

    // Verified 消息 tab accessibility forms (uiautomator dump 2026-09-14):
    // unread "消息，未读消息数1", plain "消息，未选中状态" / "消息，选中状态".
    // The home tab is "闲鱼，未读消息数0，选中状态" and never matches these.
    const val MESSAGES_TAB_UNREAD_PREFIX = "消息，未读消息数"
    const val MESSAGES_TAB_UNSELECTED_FORM = "消息，未选中状态"
    const val MESSAGES_TAB_SELECTED_FORM = "消息，选中状态"

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
        // Verified on-device 2026-09-13 + 2026-09-14 (pa-im): the 消息 tab exposes
        // three accessibility forms — unread "消息，未读消息数N，…状态", plain
        // "消息，未选中状态" (no unread) and "消息，选中状态". The home tab reads
        // "闲鱼，未读消息数N，…状态", so every alternative is anchored on the
        // leading "消息，" and can never match it. The unread prefix stays the
        // first alternative so existing unread-scenario matching is unchanged.
        "xianyu_messages_tab" to ApprovedLocator.AnyOf(
            listOf(
                ApprovedLocator.ContentDescriptionPrefix(MESSAGES_TAB_UNREAD_PREFIX),
                ApprovedLocator.ContentDescription(MESSAGES_TAB_UNSELECTED_FORM),
                ApprovedLocator.ContentDescription(MESSAGES_TAB_SELECTED_FORM),
            ),
        ),
        "xianyu_chat_input" to ApprovedLocator.ContentDescriptionPrefix("想跟TA说点什么"),
        "xianyu_chat_send" to ApprovedLocator.ContentDescription("发送"),
        // Verified on-device 2026-09-15 (contract
        // contracts/phase1/xianyu-maintenance-anchors-20260915.md, OnePlus 9R):
        // the profile tab reads 「我的，未选中状态」/「我的，选中状态」/「我的」;
        // the 我发布的 entry reads 「我发布的」; the published-goods tabs carry an
        // optional leading badge line (「1\n在卖」/「在卖」, 「N\n草稿」, 「N\n已下架」).
        // Full-match regexes keep the 「闲鱼，…」 home tab and unrelated nodes out.
        "xianyu_profile_tab" to ApprovedLocator.AnyOf(
            listOf(
                // On the 我的 page the bare prefix ambiguously matched
                // 我的收藏/我的关注/我的交易/我发布的/我的空间 (device-verified
                // 2026-09-15: the stray match opened 收藏的宝贝 mid-task). Only
                // the bottom-bar tab forms qualify.
                ApprovedLocator.ContentDescriptionPrefix("我的，未读消息数"),
                ApprovedLocator.ContentDescription("我的，未选中状态"),
                ApprovedLocator.ContentDescription("我的，选中状态"),
            ),
        ),
        "xianyu_my_published" to ApprovedLocator.ContentDescription("我发布的"),
        "xianyu_pub_tab_onsale" to ApprovedLocator.DescRegex(Regex("^(\\d{1,4}\\n)?在卖$")),
        "xianyu_pub_tab_draft" to ApprovedLocator.DescRegex(Regex("^(\\d{1,4}\\n)?草稿$")),
        "xianyu_pub_tab_delisted" to ApprovedLocator.DescRegex(Regex("^(\\d{1,4}\\n)?已下架$")),
        // Order-sync slice 1, device-verified on OnePlus 9R (b0644fb5) 2026-09-15
        // (controller survey recon-20260915-2 dumps 03/08/09 + anchor contract
        // xianyu-anchors-20260915 §3): the 我的-page entries are plain TextViews
        // (text field, content-desc empty); the orders container is the shared
        // parent of the 「订单信息」-prefixed rows (rows are not clickable).
        "xianyu_order_list_sold" to ApprovedLocator.Text("我卖出的"),
        "xianyu_order_list_bought" to ApprovedLocator.Text("我买到的"),
        "xianyu_orders_container" to ApprovedLocator.IndexedContentDescriptionPrefixParent(
            OrderRowParser.ROW_MARKER_PREFIX, 0,
        ),
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
        "dy_picker_cancel" to ApprovedLocator.ContentDescription("取消"),
        "dy_camera_ready" to ApprovedLocator.Text("开直播"),
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
            // W4 pre-registered definitions (see pendingXianyuLocators): resolvable
            // so the acceptance flip only edits the unverified set, still gated.
            pendingXianyuLocators[locatorRef]?.let { return it }
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

    // W4 maintenance v2 (contract xianyu-anchors-20260915 §2): detail-page
    // manage button + manage-menu text anchors, pre-registered pending the
    // on-device acceptance sweep. Their definitions live in
    // pendingXianyuLocators so the controller flip is a set edit only; until
    // then resolveVerified() returns null and every ui.tap navigation onto
    // them terminates with LOCATOR_UNVERIFIED, zero side effects.
    private val pendingXianyuLocators = mapOf(
        "xianyu_detail_manage" to ApprovedLocator.ContentDescription("管理按钮"),
        "xianyu_manage_delist" to ApprovedLocator.Text("下架"),
        "xianyu_manage_delete" to ApprovedLocator.Text("删除"),
        "xianyu_manage_cancel" to ApprovedLocator.Text("取消"),
        // Device-verified 2026-09-16 on OnePlus 9R: the destructive delete
        // dialog exposes one title plus separate 取消/确定 Text nodes.
        "xianyu_delete_confirm" to ApprovedLocator.GuardedDialogAction(
            actionText = "确定",
            dialogText = "确定删除该宝贝吗",
            cancelText = "取消",
        ),
    )

    // §7 fail-closed registry (contract order-sync/20260915.1 §7): refs listed
    // here are registered ahead of their on-device survey and stay unverified —
    // resolveVerified() returns null and every consumer (ui.tap navigation,
    // ui.readOrders container) terminates the step with LOCATOR_UNVERIFIED,
    // zero side effects. The slice-1 order locators were flipped 2026-09-15
    // (OnePlus 9R, controller acceptance); the W4 detail-page manage refs were
    // flipped after the controller's no-intent dry run on 2026-09-15; the
    // slice-2 order-detail container is pre-registered here until surveyed.
    val UNVERIFIED_XIANYU_LOCATOR_REFS: Set<String> = setOf(
        "xianyu_order_detail_container",
    )

    /** True when [locatorRef] is registered for [targetPackage] but still unverified (§7). */
    fun isUnverifiedLocator(targetPackage: String, locatorRef: String): Boolean =
        targetPackage == XIANYU_PACKAGE && locatorRef in UNVERIFIED_XIANYU_LOCATOR_REFS

    /**
     * Verified-only resolution gate (fail-closed, §7): null means the ref is
     * registered but not device-verified — callers must fail the step with
     * LOCATOR_UNVERIFIED and terminate the task safely. Anything else defers
     * to [resolve], which still rejects unknown refs.
     */
    fun resolveVerified(targetPackage: String, locatorRef: String): ApprovedLocator? {
        if (isUnverifiedLocator(targetPackage, locatorRef)) return null
        return resolve(targetPackage, locatorRef)
    }

    /**
     * True when a node content description / text string is one of the verified
     * xianyu 消息 tab forms (used both by the xianyu_messages_tab locator and by
     * duty-mode list detection). The 闲鱼 home tab form never matches.
     */
    fun isXianyuMessagesTabDescription(description: String): Boolean =
        description.startsWith(MESSAGES_TAB_UNREAD_PREFIX) ||
            description == MESSAGES_TAB_UNSELECTED_FORM ||
            description == MESSAGES_TAB_SELECTED_FORM

    /**
     * Canonical string test for description/text-based locators: does a single
     * content description (or text) value satisfy this locator? View-id and
     * indexed locators decide over node lists (the index is applied by the
     * caller), so only their string test is reflected here. AnyOf recurses into
     * its alternatives. Shared by node matching and unit tests so semantics
     * cannot drift between them.
     */
    fun acceptsDescription(locator: ApprovedLocator, value: String): Boolean = when (locator) {
        is ApprovedLocator.ContentDescription -> value == locator.value
        is ApprovedLocator.ContentDescriptionPrefix -> value.startsWith(locator.prefix)
        is ApprovedLocator.IndexedContentDescription -> value == locator.value
        is ApprovedLocator.Text -> value == locator.value
        is ApprovedLocator.TextPrefix -> value.startsWith(locator.prefix)
        is ApprovedLocator.IndexedContentDescriptionPrefix -> value.startsWith(locator.prefix)
        is ApprovedLocator.IndexedContentDescriptionPrefixParent -> value.startsWith(locator.prefix)
        is ApprovedLocator.DescRegex -> locator.pattern.matches(value)
        is ApprovedLocator.AnyOf -> locator.alternatives.any { acceptsDescription(it, value) }
        is ApprovedLocator.GuardedDialogAction -> value == locator.actionText
        is ApprovedLocator.ResourceId, is ApprovedLocator.IndexedResourceId -> false
    }

    /**
     * Root-page anchors (im-live slice 2, gap 1): any of these visible means the
     * target sits on a root page with its bottom tab bar, so fresh task steps can
     * start. Empty means the target has no reset contract.
     */
    fun rootAnchorRefs(targetPackage: String): List<String> = when (targetPackage) {
        COMPANION_PACKAGE -> listOf("companion_home_root")
        XIANYU_PACKAGE -> listOf("xianyu_home_sell", "xianyu_messages_tab", "xianyu_my_published")
        XHS_PACKAGE -> listOf("xhs_home_publish")
        DOUYIN_PACKAGE -> listOf("dy_home_publish")
        else -> emptyList()
    }
}
