package com.company.cloudctl.companion.network

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class PreviewGrantTest {
    @Test
    fun readsActivePreviewGrantFromHeartbeat() {
        val grant = PreviewGrant.fromHeartbeat(
            JSONObject(
                """{"ok":true,"preview":{"sessionId":"00000000-0000-7000-8000-000000000001","expiresAt":"2026-09-05T04:00:00Z","captureIntervalMs":2000}}""",
            ),
        )
        assertEquals("00000000-0000-7000-8000-000000000001", grant?.sessionId)
        assertEquals(2000L, grant?.captureIntervalMs)
    }

    @Test
    fun ignoresMissingOrNullPreview() {
        assertNull(PreviewGrant.fromHeartbeat(JSONObject("""{"ok":true}""")))
        assertNull(PreviewGrant.fromHeartbeat(JSONObject("""{"ok":true,"preview":null}""")))
        assertNull(PreviewGrant.fromHeartbeat(JSONObject("""{"ok":true,"preview":{"sessionId":"short"}}""")))
    }
}
