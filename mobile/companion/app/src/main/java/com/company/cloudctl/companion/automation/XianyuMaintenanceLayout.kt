package com.company.cloudctl.companion.automation

/**
 * Structured coordinate layer for the xianyu maintenance actions (擦亮/下架/删除已下架),
 * frozen from the device evidence in
 * contracts/phase1/xianyu-maintenance-anchors-20260915.md (OnePlus 9R, 1080x2400).
 *
 * Pure JVM logic in the ConversationListSwipe style: the caller supplies the
 * live screen size, the published-goods tab, the zero-based card index and the
 * action; the object answers with an absolute tap point or null. Every null
 * (unknown pairing, card index past the frozen step table, or any screen other
 * than 1080x2400) is a fail-safe rejection — the executor then aborts the
 * coordinate path instead of guessing. No coordinate is ever invented beyond
 * the frozen first-card y plus the frozen per-card step.
 */
object XianyuMaintenanceLayout {
    /** The only screen geometry the frozen evidence covers. */
    const val GUARD_WIDTH = 1080
    const val GUARD_HEIGHT = 2400

    /** Published-goods tabs inside 我发布的. */
    enum class Tab { ONSALE, DRAFT, DELISTED }

    enum class LayoutAction {
        /** 在卖 card ··· overflow button (first strike, opens the action sheet). */
        MORE,

        /** Page-top 一键擦亮 entry (light-risk write, no ledger). */
        POLISH_ALL,

        /** ··· action-sheet 下架 item (first strike, opens the confirm dialog). */
        DELIST_MENU_ITEM,

        /** Card 删除 button (first strike, opens the confirm dialog). */
        DELETE_CARD,

        /** Card 重新上架 button (opens the publish editor; not a one-shot action). */
        RELIST_CARD,

        /** Card 编辑 button. */
        EDIT_CARD,

        /** Confirm-dialog 确定 for a delete — destructive second strike (gated). */
        CONFIRM_DELETE,

        /** Confirm-dialog 确定 for a delist — destructive second strike (gated). */
        CONFIRM_DELIST,

        /** Confirm-dialog 取消 (always-safe exit of an unwanted dialog). */
        CONFIRM_CANCEL,
    }

    data class Point(val x: Int, val y: Int)

    /**
     * Destructive second strikes: the confirm-dialog 确定 taps that execute a
     * delist/delete. These must route through the controlled ledger
     * (intent -> one authorization -> one tap -> badge verification); the ···
     * menu first strike, the delete first strike and 一键擦亮 stay ungated but
     * are always screenshotted by the executor.
     */
    val GATED_DESTRUCTIVE_CONFIRM_ACTIONS: Set<LayoutAction> =
        setOf(LayoutAction.CONFIRM_DELETE, LayoutAction.CONFIRM_DELIST)

    /**
     * Verification badge per action: 下架成功 ⇒ 在卖 N-1, 删除成功 ⇒ 已下架 N-1
     * (contract 「tab 角标数字」core signal).
     */
    fun badgeLocatorFor(action: LayoutAction): String? = when (action) {
        LayoutAction.CONFIRM_DELIST -> "xianyu_pub_tab_onsale"
        LayoutAction.CONFIRM_DELETE -> "xianyu_pub_tab_delisted"
        LayoutAction.DELETE_CARD -> "xianyu_pub_tab_delisted"
        LayoutAction.MORE, LayoutAction.DELIST_MENU_ITEM -> "xianyu_pub_tab_onsale"
        else -> null
    }

    /**
     * @return the guarded tap point, or null when the screen size is not the
     *   frozen 1080x2400, the tab/action pairing is unverified, or the card
     *   index steps past the bottom of the screen.
     */
    fun resolve(width: Int, height: Int, tab: Tab, action: LayoutAction, cardIndex: Int): Point? {
        // Resolution guard first: any other geometry rejects the whole path.
        if (width != GUARD_WIDTH || height != GUARD_HEIGHT) return null
        if (cardIndex < 0) return null
        return when (action) {
            LayoutAction.POLISH_ALL ->
                if (tab == Tab.ONSALE && cardIndex == 0) Point(POLISH_ALL_X, POLISH_ALL_Y) else null
            LayoutAction.DELIST_MENU_ITEM ->
                if (tab == Tab.ONSALE && cardIndex == 0) Point(DELIST_MENU_ITEM_X, DELIST_MENU_ITEM_Y) else null
            // The frozen evidence covers the first on-sale card row only; later
            // rows have no verified step, so they fail closed instead of extrapolating.
            LayoutAction.MORE ->
                if (tab == Tab.ONSALE && cardIndex == 0) Point(ONSALE_MORE_X, ONSALE_FIRST_CARD_Y) else null
            LayoutAction.EDIT_CARD -> when (tab) {
                Tab.ONSALE ->
                    if (cardIndex == 0) Point(ONSALE_EDIT_X, ONSALE_FIRST_CARD_Y) else null
                Tab.DRAFT -> cardPoint(DRAFT_EDIT_X, DRAFT_FIRST_CARD_Y, DRAFT_CARD_STEP, cardIndex, height)
                Tab.DELISTED -> null
            }
            LayoutAction.DELETE_CARD -> when (tab) {
                Tab.DELISTED -> cardPoint(DELISTED_DELETE_X, DELISTED_FIRST_CARD_Y, DELISTED_CARD_STEP, cardIndex, height)
                Tab.DRAFT -> cardPoint(DRAFT_DELETE_X, DRAFT_FIRST_CARD_Y, DRAFT_CARD_STEP, cardIndex, height)
                Tab.ONSALE -> null
            }
            LayoutAction.RELIST_CARD -> when (tab) {
                Tab.DELISTED -> cardPoint(DELISTED_RELIST_X, DELISTED_FIRST_CARD_Y, DELISTED_CARD_STEP, cardIndex, height)
                else -> null
            }
            // Centered fixed dialogs are page-independent; card index is unused.
            LayoutAction.CONFIRM_DELETE ->
                if (cardIndex == 0) Point(CONFIRM_DELETE_X, CONFIRM_ROW_Y) else null
            LayoutAction.CONFIRM_DELIST ->
                if (cardIndex == 0) Point(CONFIRM_DELIST_X, CONFIRM_ROW_Y) else null
            LayoutAction.CONFIRM_CANCEL ->
                if (cardIndex == 0) Point(CONFIRM_CANCEL_X, CONFIRM_ROW_Y) else null
        }
    }

    /** Verified desc forms: 「N\n在卖」→N, 「在卖」→0, 「已下架」→0; anything else → null. */
    fun parseBadge(description: String?): Int? {
        if (description == null) return null
        BADGE_WITH_NUMBER.find(description)?.let { return it.groupValues[1].toInt() }
        if (description in PLAIN_TAB_DESCRIPTIONS) return 0
        return null
    }

    private fun cardPoint(x: Int, firstCardY: Int, step: Int, cardIndex: Int, height: Int): Point? {
        val y = firstCardY + step * cardIndex
        // A card row that leaves the guarded screen (or overflows the Int range) is unmapped.
        if (y < 0 || y >= height) return null
        return Point(x, y)
    }

    // Frozen coordinates (contracts/phase1/xianyu-maintenance-anchors-20260915.md).
    /** 已下架卡片：删除(657,y)/重新上架(904,y)；y=1207/1667/2127（步进 460）。 */
    private const val DELISTED_DELETE_X = 657
    private const val DELISTED_RELIST_X = 904
    private const val DELISTED_FIRST_CARD_Y = 1207
    private const val DELISTED_CARD_STEP = 460

    /** 草稿卡片：删除(695,y)/编辑(920,y)；y=1138/1531（步进 393）。 */
    private const val DRAFT_DELETE_X = 695
    private const val DRAFT_EDIT_X = 920
    private const val DRAFT_FIRST_CARD_Y = 1138
    private const val DRAFT_CARD_STEP = 393

    /** 在卖卡片：···(85,1270)/编辑(927,1270)（首卡，无已验证步进）。 */
    private const val ONSALE_MORE_X = 85
    private const val ONSALE_EDIT_X = 927
    private const val ONSALE_FIRST_CARD_Y = 1270

    /** 页顶「一键擦亮」(210,620)。 */
    private const val POLISH_ALL_X = 210
    private const val POLISH_ALL_Y = 620

    /** ··· ActionSheet「下架」= 第 5 项 (540,1763)（菜单项数会漂移，点击前必须截图）。 */
    private const val DELIST_MENU_ITEM_X = 540
    private const val DELIST_MENU_ITEM_Y = 1763

    /** 居中确认弹窗行 y=1305：下架确定(755)、删除确定(745)、取消(345)。 */
    private const val CONFIRM_DELIST_X = 755
    private const val CONFIRM_DELETE_X = 745
    private const val CONFIRM_CANCEL_X = 345
    private const val CONFIRM_ROW_Y = 1305

    private val BADGE_WITH_NUMBER = Regex("^(\\d{1,4})\\n(在卖|草稿|已下架)$")
    private val PLAIN_TAB_DESCRIPTIONS = setOf("在卖", "草稿", "已下架")
}
