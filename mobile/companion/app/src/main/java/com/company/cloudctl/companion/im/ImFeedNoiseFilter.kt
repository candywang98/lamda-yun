package com.company.cloudctl.companion.im

/**
 * Layered defense against xianyu feed/marketing/system pushes being captured as
 * IM buyer sessions. Device evidence 2026-09-14 (production db): two ad pushes
 * created fake peer threads —「全场支持验货保真 买手机更便宜 验货0.1元起」(text「19:23」,
 * a feed-card timestamp) and「附近上新notion商业版」(text「本地急出，点击捡漏。」).
 *
 * Layer 1 — channel: once the DM vs feed NotificationChannel ids are calibrated
 * from the IM_NOTIF logcat lines (see CloudCtlAccessibilityService), fill the
 * deny/allow sets in [NoiseProfile] (via [calibrate]). Both empty = uncalibrated:
 * the channel layer stays neutral and only the source/form layers decide, so a
 * wrong guess can never drop a real DM before calibration.
 *
 * Layer 2 — source identity (always on, I10 20260917): system notices and
 * marketing broadcasts title the notification with the SENDER identity, not a
 * buyer conversation identity (「系统通知」「官方公告」…). Exact-match titles in
 * [BUILTIN_SYSTEM_SOURCE_TITLES] plus the calibrated [NoiseProfile.systemSources]
 * are dropped; exact match keeps a real buyer with a similar name untouched.
 *
 * Layer 3 — form (always on): feed card titles are long ad copy; real peer
 * names are short usernames ("lucas"). Long titles, titles with line breaks,
 * or titles carrying marketing keywords are dropped.
 */
internal object ImFeedNoiseFilter {
    /** Logcat event code emitted for every dropped feed-shaped notification. */
    const val DROP_EVENT = "IM_FEED_DROPPED"

    /**
     * Xianyu channel calibration targets for com.taobao.idlefish (lowercase;
     * substring match, same convention as ImMonitorConfig.isChannelAllowed).
     * Kept as the (empty) pre-calibration defaults inside [NoiseProfile.DEFAULT];
     * runtime calibration goes through [calibrate] so the whole filter basis is
     * one replaceable, test-visible value.
     */
    val XIANYU_FEED_CHANNELS: Set<String> = emptySet()
    val XIANYU_DM_CHANNELS: Set<String> = emptySet()

    /**
     * System-sender titles that are never a buyer conversation, harvested from
     * on-device notification captures. Exact (trimmed) match only.
     */
    val BUILTIN_SYSTEM_SOURCE_TITLES: Set<String> = setOf(
        "系统通知",
        "系统消息",
        "官方公告",
        "系统提示",
        "闲鱼通知",
    )

    /**
     * Marketing keywords for the form layer, harvested from the two production
     * feed samples (2026-09-14). Extend via [NoiseProfile.marketingPeerKeywords]
     * as new feed shapes appear — no other change is needed. 「起」 is the
     * weakest signal (it only appears in the sample as the「…元起」pricing
     * suffix); duty-mode list scanning backstops any real peer wrongly dropped
     * here.
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

    /**
     * I10: the whole filter basis as one replaceable value (channel calibration
     * + system sources + marketing keywords + name length bar). Defaults keep
     * the pre-I10 behaviour: channel layer neutral (uncalibrated), builtin
     * system titles only, production-sample keywords.
     */
    data class NoiseProfile(
        val feedChannels: Set<String> = XIANYU_FEED_CHANNELS,
        val dmChannels: Set<String> = XIANYU_DM_CHANNELS,
        val systemSources: Set<String> = emptySet(),
        val marketingPeerKeywords: List<String> = FEED_PEER_KEYWORDS,
        val peerNameMaxLength: Int = FEED_PEER_NAME_MAX_LENGTH,
    )

    @Volatile
    private var active: NoiseProfile = NoiseProfile()

    /** Current filter basis (snapshot; safe to read from any thread). */
    fun profile(): NoiseProfile = active

    /** Replace the filter basis after an on-device IM_NOTIF calibration capture. */
    fun calibrate(next: NoiseProfile) {
        active = next
    }

    /** Test/ops hook: back to the uncalibrated builtin defaults. */
    fun resetCalibration() {
        active = NoiseProfile()
    }

    enum class Layer { CHANNEL, SOURCE, FORM }

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
        feedChannels: Set<String> = profile().feedChannels,
        dmChannels: Set<String> = profile().dmChannels,
    ): Drop? {
        if (platform != ImMonitorConfig.PLATFORM_XIANYU) return null

        // Layer 1: calibrated channel deny/allow lists.
        val channel = channelId?.trim()?.lowercase().orEmpty()
        val feed = feedChannels.map { it.trim().lowercase() }.filter { it.isNotEmpty() }
        val dm = dmChannels.map { it.trim().lowercase() }.filter { it.isNotEmpty() }
        if (channel.isNotEmpty() && feed.any { it in channel }) {
            return Drop(Layer.CHANNEL, "channel=$channel is in the feed denylist")
        }

        // Layer 2: sender identity — system notices / official broadcasts are
        // not buyer conversations, calibrated or not.
        val name = peerName.trim()
        val systemSources = BUILTIN_SYSTEM_SOURCE_TITLES +
            profile().systemSources.map { it.trim() }.filter { it.isNotEmpty() }
        if (systemSources.any { it.equals(name, ignoreCase = true) }) {
            return Drop(Layer.SOURCE, "peer「$name」is a system/official sender")
        }

        if (dm.isNotEmpty() && dm.none { it in channel }) {
            return Drop(Layer.CHANNEL, "channel=${channel.ifEmpty { "null" }} is not in the DM allowlist")
        }

        // Layer 3: shape of the peer name (notification title).
        if (name.length > profile().peerNameMaxLength) {
            return Drop(Layer.FORM, "peer length ${name.length} > ${profile().peerNameMaxLength}")
        }
        if (name.contains('\n') || name.contains('\r')) {
            return Drop(Layer.FORM, "peer contains a line break")
        }
        val keyword = profile().marketingPeerKeywords.firstOrNull { it in name }
        if (keyword != null) return Drop(Layer.FORM, "peer keyword「$keyword」")
        return null
    }
}
