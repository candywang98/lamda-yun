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
        feed: Set<String> = emptySet(),
        dm: Set<String> = emptySet(),
        platform: String = ImMonitorConfig.PLATFORM_XIANYU,
    ) = ImFeedNoiseFilter.dropReason(platform, channel, peer, feed, dm)

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
}
