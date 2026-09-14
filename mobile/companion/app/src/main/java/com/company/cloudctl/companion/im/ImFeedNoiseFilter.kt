package com.company.cloudctl.companion.im

/**
 * Layered defense against xianyu feed/marketing pushes being captured as IM
 * sessions. Device evidence 2026-09-14 (production db): two ad pushes created
 * fake peer threads —「全场支持验货保真 买手机更便宜 验货0.1元起」(text「19:23」,
 * a feed-card timestamp) and「附近上新notion商业版」(text「本地急出，点击捡漏。」).
 *
 * Layer 1 — channel: once the DM vs feed NotificationChannel ids are calibrated
 * from the IM_NOTIF logcat lines (see CloudCtlAccessibilityService), fill the
 * deny/allow sets below. Both empty = uncalibrated: the channel layer stays
 * neutral and only the form layer decides, so a wrong guess can never drop a
 * real DM before calibration.
 *
 * Layer 2 — form (always on): feed card titles are long ad copy; real peer
 * names are short usernames ("lucas"). Long titles, titles with line breaks,
 * or titles carrying marketing keywords are dropped.
 */
internal object ImFeedNoiseFilter {
    /** Logcat event code emitted for every dropped feed-shaped notification. */
    const val DROP_EVENT = "IM_FEED_DROPPED"

    /**
     * Xianyu channel calibration targets for com.taobao.idlefish (lowercase;
     * substring match, same convention as ImMonitorConfig.isChannelAllowed).
     * The controller fills them from one on-device IM_NOTIF capture:
     * DM channel id -> XIANYU_DM_CHANNELS, feed/marketing channel id(s) ->
     * XIANYU_FEED_CHANNELS. Keep both empty until that capture exists.
     */
    val XIANYU_FEED_CHANNELS: Set<String> = emptySet()
    val XIANYU_DM_CHANNELS: Set<String> = emptySet()

    /**
     * Marketing keywords for the form layer, harvested from the two production
     * feed samples (2026-09-14). Extend this list as new feed shapes appear —
     * no other change is needed. 「起」 is the weakest signal (it only appears
     * in the sample as the「…元起」pricing suffix); duty-mode list scanning
     * backstops any real peer wrongly dropped here.
     */
    val FEED_PEER_KEYWORDS: List<String> = listOf(
        "点击",
        "捡漏",
        "上新",
        "验货",
        "更便宜",
        "起",
    )

    /** Real peer names are short usernames; feed card titles exceed this. */
    const val FEED_PEER_NAME_MAX_LENGTH = 16

    enum class Layer { CHANNEL, FORM }

    /** Which layer dropped the notification and why, for the audit log line. */
    data class Drop(val layer: Layer, val detail: String) {
        val reason: String get() = "${layer.name.lowercase()}:$detail"
    }

    /**
     * Non-null when the notification must not become an IM event. Pure decision
     * over the parsed capture fields (platform, notification channel id, peer
     * name / notification title) so the filter is unit-testable without
     * Android; the service only logs and drops.
     */
    fun dropReason(
        platform: String,
        channelId: String?,
        peerName: String,
        feedChannels: Set<String> = XIANYU_FEED_CHANNELS,
        dmChannels: Set<String> = XIANYU_DM_CHANNELS,
    ): Drop? {
        if (platform != ImMonitorConfig.PLATFORM_XIANYU) return null

        // Layer 1: calibrated channel deny/allow lists.
        val channel = channelId?.trim()?.lowercase().orEmpty()
        val feed = feedChannels.map { it.trim().lowercase() }.filter { it.isNotEmpty() }
        val dm = dmChannels.map { it.trim().lowercase() }.filter { it.isNotEmpty() }
        if (channel.isNotEmpty() && feed.any { it in channel }) {
            return Drop(Layer.CHANNEL, "channel=$channel is in the feed denylist")
        }
        if (dm.isNotEmpty() && dm.none { it in channel }) {
            return Drop(Layer.CHANNEL, "channel=${channel.ifEmpty { "null" }} is not in the DM allowlist")
        }

        // Layer 2: shape of the peer name (notification title).
        val name = peerName.trim()
        if (name.length > FEED_PEER_NAME_MAX_LENGTH) {
            return Drop(Layer.FORM, "peer length ${name.length} > $FEED_PEER_NAME_MAX_LENGTH")
        }
        if (name.contains('\n') || name.contains('\r')) {
            return Drop(Layer.FORM, "peer contains a line break")
        }
        val keyword = FEED_PEER_KEYWORDS.firstOrNull { it in name }
        if (keyword != null) return Drop(Layer.FORM, "peer keyword「$keyword」")
        return null
    }
}
