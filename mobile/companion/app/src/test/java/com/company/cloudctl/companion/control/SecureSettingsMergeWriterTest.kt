package com.company.cloudctl.companion.control

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class SecureSettingsMergeWriterTest {
    private var granted = false
    private var stored: String? = null
    private var writes = 0
    private var writeSucceeds = true

    private fun writer() = SecureSettingsMergeWriter(
        checkPermission = { granted },
        readEnabledServices = { stored },
        writeEnabledServices = {
            writes++
            if (writeSucceeds) {
                stored = it
                true
            } else {
                false
            }
        },
    )

    @Test
    fun `merge preserves every existing service`() {
        granted = true
        stored = "com.a/.Svc:com.b/.Other"
        val result = writer().mergeAppendOwnService("com.cloudctl/.automation.CloudCtlAccessibilityService")
        assertTrue(result.changed)
        assertEquals("com.a/.Svc:com.b/.Other:com.cloudctl/.automation.CloudCtlAccessibilityService", result.mergedValue)
        assertEquals(1, writes)
    }

    @Test
    fun `already present is a no-op without writing`() {
        granted = true
        stored = "com.a/.Svc:com.cloudctl/.Own"
        val result = writer().mergeAppendOwnService("com.cloudctl/.Own")
        assertFalse(result.changed)
        assertEquals(0, writes)
    }

    @Test
    fun `empty and null settings still merge cleanly`() {
        granted = true
        stored = null
        assertEquals(
            "com.cloudctl/.Own",
            writer().mergeAppendOwnService("com.cloudctl/.Own").mergedValue,
        )
        stored = ""
        assertTrue(writer().mergeAppendOwnService("com.cloudctl/.Own").changed)
    }

    @Test
    fun `missing permission throws before any read or write`() {
        granted = false
        stored = "com.a/.Svc"
        assertFailsWith<SecureSettingsMergeWriter.MissingWriteSecureSettingsPermission> {
            writer().mergeAppendOwnService("com.cloudctl/.Own")
        }
        assertEquals(0, writes)
        assertEquals("com.a/.Svc", stored, "nothing may be overwritten without the grant")
    }

    @Test
    fun `failed settings write surfaces an error`() {
        granted = true
        stored = "com.a/.Svc"
        writeSucceeds = false
        assertFailsWith<IllegalStateException> {
            writer().mergeAppendOwnService("com.cloudctl/.Own")
        }
    }

    @Test
    fun `the writer stays unwired by default`() {
        assertFalse(SecureSettingsMergeWriter.ENABLED_BY_DEFAULT, "B17 ships the tool disabled")
    }
}
