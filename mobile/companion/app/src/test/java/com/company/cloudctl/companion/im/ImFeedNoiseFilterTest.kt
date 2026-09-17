package com.company.cloudctl.companion.im

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * im-feed-noise (device evidence 2026-09-14): two xianyu marketing pushes were
 * captured as IM sessions. The filter decides on the parsed capture fields —
 * platform, notification channel id, peer name (notification title) — the same
 * structure the notification callback hands over after extraction.
 */
class ImFeedNoiseFilterTest {
    private fun drop(
        peer: String,
        channel: String? = null,
        feed: Set<String>? = null,
        dm: Set<String>? = null,
        platform: String = ImMonitorConfig.PLATFORM_XIANYU,
    ) = ImFeedNoiseFilter.dropReason(
        platform, channel, peer,
        // Null = let the filter use its current (calibrated or default) profile.
        feedChannels = feed ?: ImFeedNoiseFilter.profile().feedChannels,
        dmChannels = dm ?: ImFeedNoiseFilter.profile().dmChannels,
    )

    // Layer 1 — channel.

    @Test
    fun realDmPeerPassesWithAnyUncalibratedChannel() {
        assertNull(drop("lucas", channel = "some_unknown_channel"))
        assertNull(drop("lucas", channel = null))
        assertNull(drop("小白", channel = "notification"))
    }

    @Test
    fun calibratedFeedChannelIsDroppedBeforeTheFormLayer() {
        val drop = drop(
            "lucas",
            channel = "Feed_Push ",
            feed = setOf("feed_push"),
        )
        assertEquals(ImFeedNoiseFilter.Layer.CHANNEL, drop?.layer)
        assertTrue(drop!!.reason.contains("feed_push"))
    }

    @Test
    fun calibratedDmAllowlistKeepsDmAndDropsOtherChannels() {
        val dm = setOf("dm")
        assertNull(drop("lucas", channel = "notification_dm", dm = dm))
        assertEquals(
            ImFeedNoiseFilter.Layer.CHANNEL,
            drop("lucas", channel = "promo_v2", dm = dm)?.layer,
        )
        assertEquals(
            ImFeedNoiseFilter.Layer.CHANNEL,
            drop("lucas", channel = null, dm = dm)?.layer,
        )
    }

    // Layer 2 — form of the peer name (notification title).

    @Test
    fun longAdCopyPeerNameIsDroppedByLength() {
        // Production sample 1 (2026-09-14): peer_name=「全场支持验货保真 买手机更便宜 验货0.1元起」
        val peer = "全场支持验货保真 买手机更便宜 验货0.1元起"
        assertTrue(peer.length > ImFeedNoiseFilter.FEED_PEER_NAME_MAX_LENGTH)
        val drop = drop(peer)
        assertEquals(ImFeedNoiseFilter.Layer.FORM, drop?.layer)
        assertTrue(drop!!.reason.contains("length"))
    }

    @Test
    fun shortFeedTitleIsDroppedByMarketingKeyword() {
        // Production sample 2 (2026-09-14): peer_name=「附近上新notion商业版」
        // (13 chars, under the length bar) text=「本地急出，点击捡漏。」
        val peer = "附近上新notion商业版"
        assertTrue(peer.length <= ImFeedNoiseFilter.FEED_PEER_NAME_MAX_LENGTH)
        val drop = drop(peer, channel = "whatever")
        assertEquals(ImFeedNoiseFilter.Layer.FORM, drop?.layer)
        assertTrue(drop!!.reason.contains("上新"))
    }

    @Test
    fun peerNameWithLineBreakIsDropped() {
        val drop = drop("lucas\n本地急出，点击捡漏。")
        assertEquals(ImFeedNoiseFilter.Layer.FORM, drop?.layer)
        assertTrue(drop!!.reason.contains("line break"))
    }

    @Test
    fun keywordListCoversBothProductionFeedSamples() {
        val samples = listOf(
            "全场支持验货保真 买手机更便宜 验货0.1元起",
            "附近上新notion商业版",
        )
        samples.forEach { sample ->
            val byKeyword = ImFeedNoiseFilter.FEED_PEER_KEYWORDS.any { it in sample }
            val byLength = sample.length > ImFeedNoiseFilter.FEED_PEER_NAME_MAX_LENGTH
            assertTrue(byKeyword || byLength, "no form signal covers $sample")
        }
    }

    @Test
    fun nonXianyuPlatformsBypassTheFilterEntirely() {
        assertNull(drop("超长的营销标题超过十六个字啦", channel = "x", platform = "xhs"))
        assertNull(drop("点击捡漏", channel = "x", platform = "douyin"))
    }

    // I10 layer — source identity (system/official senders are not buyers).

    @Test
    fun builtinSystemSenderTitlesAreDroppedEvenOnUncalibratedChannels() {
        for (title in ImFeedNoiseFilter.BUILTIN_SYSTEM_SOURCE_TITLES) {
            val dropped = drop(title, channel = null)
            assertEquals(ImFeedNoiseFilter.Layer.SOURCE, dropped?.layer, "title=$title")
            assertTrue(dropped!!.reason.contains("system/official"))
        }
    }

    @Test
    fun realBuyerWithASimilarNameIsNotDroppedByTheSourceLayer() {
        // Exact-match only: a buyer actually named like a system sender prefix
        // or a longer variant stays a conversation.
        assertNull(drop("系统通知小助手是谁", channel = null))
        assertNull(drop("通知中心", channel = null))
    }

    @Test
    fun systemSourceDropSurvivesACalibratedDmAllowlist() {
        // Even a DM-channel notification titled by a system sender is not a
        // buyer message — the source layer runs before the DM allowlist.
        val dropped = drop("系统通知", channel = "notification_dm", dm = setOf("dm"))
        assertEquals(ImFeedNoiseFilter.Layer.SOURCE, dropped?.layer)
    }

    // I10 — configurable filter basis (NoiseProfile).

    @Test
    fun calibratedProfileDropsConfiguredSystemSourcesAndMarketingKeywords() {
        ImFeedNoiseFilter.calibrate(
            ImFeedNoiseFilter.NoiseProfile(
                systemSources = setOf("闲鱼小蜜"),
                marketingPeerKeywords = ImFeedNoiseFilter.FEED_PEER_KEYWORDS + "清仓",
            ),
        )
        try {
            // Calibrated system source (not in the builtin set).
            assertEquals(
                ImFeedNoiseFilter.Layer.SOURCE,
                drop("闲鱼小蜜", channel = "notification_dm")?.layer,
            )
            // Calibrated extra marketing keyword on a short title.
            val marketing = drop("周末清仓专场", channel = null)
            assertEquals(ImFeedNoiseFilter.Layer.FORM, marketing?.layer)
            assertTrue(marketing!!.reason.contains("清仓"))
            // A plain buyer still passes under the calibrated profile.
            assertNull(drop("lucas", channel = "notification_dm"))
            // Explicit channel overrides keep working alongside the profile.
            assertEquals(
                ImFeedNoiseFilter.Layer.CHANNEL,
                drop("lucas", channel = "feed_push", feed = setOf("feed_push"))?.layer,
            )
        } finally {
            ImFeedNoiseFilter.resetCalibration()
        }
    }

    @Test
    fun profileCalibratesChannelDenyAndAllowLists() {
        ImFeedNoiseFilter.calibrate(
            ImFeedNoiseFilter.NoiseProfile(
                feedChannels = setOf("feed_push"),
                dmChannels = setOf("dm"),
            ),
        )
        try {
            assertEquals(
                ImFeedNoiseFilter.Layer.CHANNEL,
                drop("lucas", channel = "Feed_Push")?.layer,
            )
            assertNull(drop("lucas", channel = "notification_dm"))
            assertEquals(
                ImFeedNoiseFilter.Layer.CHANNEL,
                drop("lucas", channel = "promo_v2")?.layer,
            )
        } finally {
            ImFeedNoiseFilter.resetCalibration()
        }
    }

    @Test
    fun resetCalibrationRestoresNeutralChannelLayer() {
        ImFeedNoiseFilter.calibrate(
            ImFeedNoiseFilter.NoiseProfile(dmChannels = setOf("dm")),
        )
        ImFeedNoiseFilter.resetCalibration()
        assertNull(drop("lucas", channel = "some_unknown_channel"))
    }
}
