package com.company.cloudctl.companion.ime

import android.content.Context
import android.text.InputType
import android.text.Selection
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.Button
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.automation.CloudCtlAccessibilityService
import com.company.cloudctl.companion.automation.ChatInputReadback
import com.company.cloudctl.companion.automation.ExecutorFailure
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowLog
import org.robolectric.util.ReflectionHelpers
import kotlin.coroutines.Continuation
import kotlin.coroutines.intrinsics.COROUTINE_SUSPENDED
import kotlin.coroutines.suspendCoroutine
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29, 32, 34], qualifiers = "mdpi")
class ManualImeIntegrationTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private val serviceController = Robolectric.buildService(CloudCtlInputMethod::class.java).create()
    private val service = serviceController.get()
    private var connection = ManualTestConnection(context)
    private val editor = EditorInfo().apply {
        packageName = "fixture.editor"
        inputType = InputType.TYPE_CLASS_TEXT
        fieldId = 9
        initialSelStart = 0
        initialSelEnd = 0
    }

    private fun bind(restarting: Boolean = false) {
        ReflectionHelpers.setField(service, "mStartedInputConnection", connection)
        ReflectionHelpers.setField(service, "mInputEditorInfo", editor)
        service.onStartInput(editor, restarting)
    }

    private fun keys(view: View): List<Button> = when (view) {
        is Button -> listOf(view)
        is ViewGroup -> (0 until view.childCount).flatMap { keys(view.getChildAt(it)) }
        else -> emptyList()
    }

    private fun click(view: View, label: String) {
        keys(view).single { it.text.toString() == label }.performClick()
        selection()
    }

    private fun selection() {
        service.onUpdateSelection(-1, -1, Selection.getSelectionStart(connection.buffer),
            Selection.getSelectionEnd(connection.buffer), -1, -1)
    }

    @After fun close() {
        CloudCtlInputMethod.setTemporarySelection(false)
        serviceController.destroy()
    }

    @Test fun manualTypeDeleteAbaDuringPostCommitProveIsRejected() = runBlocking {
        bind()
        val view = service.onCreateInputView()
        val transport = CloudCtlImeTransport(editor.packageName)
        var pauses = 0
        val writer = VerifiedEditorInput(transport, { editor.packageName }) {
            pauses++
            if (pauses == 2) {
                selection()
                click(view, "x")
                click(view, "⌫")
                assertEquals("expected", connection.buffer.toString())
            }
        }
        assertFailsWith<ExecutorFailure> { writer.write("expected") }
        assertEquals(1, transport.commitCount())
        assertNull(transport.snapshot())
    }

    @Test fun heldProofExpiresEvenWithFreshTransportAndTextRestored() = runBlocking {
        bind()
        val view = service.onCreateInputView()
        val writer = VerifiedEditorInput(CloudCtlImeTransport(editor.packageName), { editor.packageName }, {})
        val proof = writer.write("expected")
        selection()
        click(view, "x")
        click(view, "⌫")
        assertEquals(proof.expected, connection.buffer.toString())
        val fresh = VerifiedEditorInput(CloudCtlImeTransport(editor.packageName), { editor.packageName }, {})
        assertFailsWith<ExecutorFailure> { fresh.verify(proof) }
        val current = fresh.write("expected")
        fresh.verify(current)
        assertEquals(CloudCtlInputMethod.manualActionEpoch, current.snapshot.manualActionEpoch)
        assertEquals(0, current.commitCount)
    }

    @Test fun normalConnectionRebuildStillProducesAndVerifiesProof() = runBlocking {
        bind()
        var pauses = 0
        val epoch = CloudCtlInputMethod.manualActionEpoch
        val writer = VerifiedEditorInput(CloudCtlImeTransport(editor.packageName), { editor.packageName }) {
            pauses++
            if (pauses == 2) {
                val replacement = ManualTestConnection(context)
                replacement.buffer.append(connection.buffer)
                Selection.setSelection(replacement.buffer, replacement.buffer.length)
                connection = replacement
                bind(true)
            }
        }
        val proof = writer.write("expected")
        writer.verify(proof)
        assertEquals(epoch, CloudCtlInputMethod.manualActionEpoch)
        assertEquals(1, proof.commitCount)
    }

    @Test fun lifecycleResetsLayoutAndRejectsDetachedKeysAndRebindsSameFieldAfterHide() {
        bind()
        val view = service.onCreateInputView()
        click(view, "⇧")
        val oldKey = keys(view).single { it.text == "A" }
        click(view, "123 #+")
        service.onFinishInputView(false)
        service.onStartInputView(editor, false)
        assertTrue(keys(view).any { it.text == "a" })
        oldKey.performClick()
        assertEquals(0, connection.writes)
        click(view, "a")
        assertEquals("a", connection.buffer.toString())
        service.onFinishInput()
        assertNull(CloudCtlInputMethod.chatSession(editor.packageName))
        assertFalse(keys(view).any { it.text == "a" })
        bind()
        assertTrue(keys(view).any { it.text == "a" })
    }

    @Test fun temporarySelectionImmediatelyHidesTypingButNeverSwitchEscape() {
        bind()
        val view = service.onCreateInputView()
        val oldKey = keys(view).single { it.text == "a" }
        CloudCtlInputMethod.setTemporarySelection(true)
        assertFalse(keys(view).any { it.text == "a" })
        assertTrue(keys(view).single { it.text == "切换键盘" }.isEnabled)
        oldKey.performClick()
        assertEquals(0, connection.writes)
        CloudCtlInputMethod.setTemporarySelection(false)
        oldKey.performClick()
        assertEquals(0, connection.writes)
        click(view, "a")
        assertEquals("a", connection.buffer.toString())
    }

    @Test fun hideShowAndTemporaryViewResetPreserveLatestSelectionInsteadOfInitialCaret() {
        bind()
        val view = service.onCreateInputView()
        connection.buffer.append("abc😀")
        Selection.setSelection(connection.buffer, 1, 3)
        service.onUpdateSelection(0, 0, 1, 3, -1, -1)
        service.onFinishInputView(false)
        service.onStartInputView(editor, false)
        CloudCtlInputMethod.setTemporarySelection(true)
        CloudCtlInputMethod.setTemporarySelection(false)
        keys(view).single { it.text == "⌫" }.performClick()
        assertEquals("a😀", connection.buffer.toString())
        keys(view).single { it.text == "⌫" }.performClick()
        assertEquals("😀", connection.buffer.toString())
        assertTrue(keys(view).any { it.text == "a" })
        assertEquals(0, connection.reads)
    }

    @Test fun burstSurrogateDeletesWithoutCallbacksKeepTypingAvailable() {
        bind()
        val view = service.onCreateInputView()
        connection.buffer.append("a😀😀")
        Selection.setSelection(connection.buffer, 5)
        service.onUpdateSelection(0, 0, 5, 5, -1, -1)
        repeat(3) { keys(view).single { it.text == "⌫" }.performClick() }
        assertEquals("", connection.buffer.toString())
        keys(view).single { it.text == "a" }.performClick()
        assertEquals("a", connection.buffer.toString())
        assertEquals(0, connection.reads)
    }

    @Test fun unknownSelectionRefusesDeleteWithoutLosingKeyboardOrQueuingIt() {
        editor.initialSelStart = -1
        editor.initialSelEnd = -1
        bind()
        val view = service.onCreateInputView()
        connection.buffer.append("ab")
        Selection.setSelection(connection.buffer, 2)
        repeat(2) { keys(view).single { it.text == "⌫" }.performClick() }
        assertEquals(0, connection.writes)
        assertTrue(keys(view).any { it.text == "a" })
        assertTrue(keys(view).single { it.text == "切换键盘" }.isEnabled)
        service.onUpdateSelection(-1, -1, 2, 2, -1, -1)
        assertEquals("ab", connection.buffer.toString())
        keys(view).single { it.text == "⌫" }.performClick()
        assertEquals("a", connection.buffer.toString())
        assertEquals(0, connection.reads)
    }

    @Test fun failedManualOperationInvalidatesCapturedSnapshotAndNeverLogsInput() = runBlocking {
        bind()
        val view = service.onCreateInputView()
        val transport = CloudCtlImeTransport(editor.packageName)
        val snapshot = assertNotNull(transport.snapshot())
        connection.fail = true
        click(view, "x")
        connection.fail = false
        assertFalse(transport.commit(snapshot, "private-fixture-phrase"))
        assertNull(transport.snapshot())
        assertFalse(ShadowLog.getLogs().any { it.msg.contains("private-fixture-phrase") })
        assertEquals("", connection.buffer.toString())
    }

    @Test fun temporaryReadbackAcceptsFreshNonzeroEpochButRejectsOldProofAndAbaDuringRead() = runBlocking {
        bind()
        val view = service.onCreateInputView()
        click(view, "x")
        click(view, "⌫")
        val identity = assertNotNull(CloudCtlInputMethod.currentEditorIdentity())
        val epoch = CloudCtlInputMethod.manualActionEpoch
        assertTrue(epoch > 0L)
        val proof = ChatInputProofFactory.fromReadback(
            editor.packageName, "xianyu_chat_input", "",
            FieldAnchor(editor.packageName, "xianyu_chat_input", "fixture"),
            ChatInputReadback("", assertNotNull(CloudCtlInputMethod.chatSession(editor.packageName)), identity.fingerprint),
            editor.packageName,
        )
        assertEquals(epoch, proof.snapshot.manualActionEpoch)
        val accessibility = Robolectric.buildService(CloudCtlAccessibilityService::class.java).get()
        assertTrue(readStable(accessibility, proof))
        val inFlight = async { readStable(accessibility, proof) }
        delay(20)
        click(view, "x")
        click(view, "⌫")
        assertFalse(inFlight.await())
        assertFalse(readStable(accessibility, proof))
        val fresh = proof.copy(snapshot = proof.snapshot.copy(manualActionEpoch = CloudCtlInputMethod.manualActionEpoch))
        assertTrue(readStable(accessibility, fresh))
    }

    private suspend fun readStable(service: CloudCtlAccessibilityService, proof: InputProof): Boolean =
        suspendCoroutine { continuation ->
            val method = CloudCtlAccessibilityService::class.java.getDeclaredMethod(
                "readStableFullText", String::class.java, InputProof::class.java, Continuation::class.java,
            )
            method.isAccessible = true
            val result = method.invoke(service, editor.packageName, proof, continuation)
            if (result !== COROUTINE_SUSPENDED) continuation.resumeWith(Result.success(result as Boolean))
        }
}
