package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * B14 acceptance: clipboard pollution can never trigger an automatic send —
 * send/publish-class actions are keyed off the verified readback only.
 */
class SendAuthorizationTest {
    @Test fun authorizationComesFromTheReadbackNotTheClipboard() {
        assertTrue(SendAuthorization.authorized("reply", "reply", null))
        assertTrue(SendAuthorization.authorized("reply", "reply", "立即购买"))
        // Clipboard holds exactly the expected text while the field disagrees.
        assertFalse(SendAuthorization.authorized("garbage", "reply", "reply"))
        assertFalse(SendAuthorization.authorized(null, "reply", "reply"))
    }

    @Test fun truncatedOrEmojiLostReadbacksNeverAuthorize() {
        val expected = "改价完成，请注意查收新的价格信息🙂如有疑问请随时联系客服处理\n谢谢支持与理解"
        assertTrue(expected.length > 16)
        assertFalse(SendAuthorization.authorized(expected.take(16), expected, null))
        assertFalse(SendAuthorization.authorized(expected.replace("🙂", "?"), expected, null))
        // Only an exact full-length round-trip authorizes.
        assertTrue(SendAuthorization.authorized(expected, expected, "polluted junk"))
    }
}
