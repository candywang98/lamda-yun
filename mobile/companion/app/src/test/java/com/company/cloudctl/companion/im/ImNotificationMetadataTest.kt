package com.company.cloudctl.companion.im

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull

class ImNotificationMetadataTest {
    @Test
    fun nullableFieldsAndUnknownFieldsAreNotUploaded() {
        val metadata = ImNotificationMetadata.fromJson(
            JSONObject("""{"packageName":null,"channelId":null,"category":null,"secret":"ignored"}"""),
        )
        assertEquals(ImNotificationMetadata(), metadata)
        assertEquals(0, metadata.toJson().length())
    }

    @Test
    fun boundsPreserveUnicodeCodePointsAndAreIdempotent() {
        val emoji = "\uD83D\uDE00"
        val metadata = ImNotificationMetadata(
            ImNotificationMetadata.XIANYU_PACKAGE,
            "c".repeat(255) + emoji + "tail",
            "k".repeat(63) + emoji + "tail",
        ).bounded()
        assertEquals("c".repeat(255) + emoji, metadata.channelId)
        assertEquals("k".repeat(63) + emoji, metadata.category)
        assertEquals(metadata, metadata.bounded())
        assertEquals(metadata, ImNotificationMetadata.fromJson(metadata.toJson()))
    }

    @Test
    fun invalidPackageIsOmittedWithoutLosingOtherContext() {
        for (pkg in listOf("com.xingin.xhs", "p".repeat(129))) {
            val metadata = ImNotificationMetadata(pkg, "feed", "msg").bounded()
            assertNull(metadata.packageName)
            assertFalse(metadata.toJson().has("packageName"))
            assertEquals("feed", metadata.channelId)
            assertEquals("msg", metadata.category)
        }
    }

    @Test
    fun exactBoundsAndEmptyOptionalValuesRemainUnchanged() {
        val metadata = ImNotificationMetadata(ImNotificationMetadata.XIANYU_PACKAGE, "c".repeat(256), "k".repeat(64))
        assertEquals(metadata, metadata.bounded())
        assertEquals(ImNotificationMetadata(channelId = "", category = ""),
            ImNotificationMetadata.fromJson(JSONObject("""{"channelId":"","category":""}""")))
    }
}
