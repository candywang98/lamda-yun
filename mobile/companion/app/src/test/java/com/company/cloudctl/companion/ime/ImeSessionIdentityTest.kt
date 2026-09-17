package com.company.cloudctl.companion.ime

import android.view.inputmethod.EditorInfo
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * B14: after an editor restart the re-captured connection must be proven to target
 * the SAME field before typing continues; node identity, not just generation.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ImeSessionIdentityTest {
    private fun editor(
        packageName: String = "com.taobao.idlefish",
        inputType: Int = 1,
        imeOptions: Int = 6,
        fieldId: Int = -1,
        fieldName: String? = null,
    ) = EditorInfo().apply {
        this.packageName = packageName
        this.inputType = inputType
        this.imeOptions = imeOptions
        this.fieldId = fieldId
        this.fieldName = fieldName
    }

    @Test
    fun sameFieldSurvivesEditorRestartWithStableFingerprint() {
        // Flutter restarts the editor every second: same field, new generation.
        val before = ImeSessionIdentity.of(editor())
        val after = ImeSessionIdentity.of(editor())
        assertTrue(ImeSessionIdentity.sameField(before, after))
        assertEquals(before!!.fingerprint, after!!.fingerprint)
    }

    @Test
    fun differentInputTypeIsADifferentField() {
        val chat = ImeSessionIdentity.of(editor(inputType = 1))
        val price = ImeSessionIdentity.of(editor(inputType = 8194)) // number variation
        assertFalse(ImeSessionIdentity.sameField(chat, price))
    }

    @Test
    fun differentPackageIsADifferentField() {
        val idlefish = ImeSessionIdentity.of(editor(packageName = "com.taobao.idlefish"))
        val browser = ImeSessionIdentity.of(editor(packageName = "com.android.browser"))
        assertFalse(ImeSessionIdentity.sameField(idlefish, browser))
    }

    @Test
    fun unknownIdentityIsNeverSameField() {
        val known = ImeSessionIdentity.of(editor())
        assertFalse(ImeSessionIdentity.sameField(known, null))
        assertFalse(ImeSessionIdentity.sameField(null, known))
        assertFalse(ImeSessionIdentity.sameField(null, null))
    }

    @Test
    fun missingEditorOrPackageYieldsNull() {
        assertNull(ImeSessionIdentity.of(null))
        assertNull(ImeSessionIdentity.of(EditorInfo()))
    }

    @Test
    fun hintAndVolatileTextDoNotParticipate() {
        // hintText/initialText change per frame; they are not part of identity.
        val withHint = editor().apply { hintText = "描述一下宝贝" }
        val withoutHint = editor()
        assertEquals(
            ImeSessionIdentity.of(withHint)!!.fingerprint,
            ImeSessionIdentity.of(withoutHint)!!.fingerprint,
        )
    }
}
