package com.company.cloudctl.companion.ime

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.os.Build
import android.text.Editable
import android.text.InputType
import android.text.Selection
import android.view.View
import android.view.ViewGroup
import android.view.KeyEvent
import android.view.inputmethod.BaseInputConnection
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.ExtractedText
import android.view.inputmethod.ExtractedTextRequest
import android.view.inputmethod.InputConnection
import android.widget.Button
import androidx.test.core.app.ApplicationProvider
import java.io.File
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

internal class ManualTestConnection(context: Context) : BaseInputConnection(View(context), true) {
    val buffer = Editable.Factory.getInstance().newEditable("")
    var fail = false
    var throws = false
    var secret = false
    var writes = 0
    var reads = 0
    var actions = 0
    var events = 0

    init { Selection.setSelection(buffer, 0) }

    override fun getEditable(): Editable = buffer

    override fun commitText(text: CharSequence?, newCursorPosition: Int): Boolean {
        writes++
        if (throws) error("disconnected")
        return !fail && super.commitText(text, newCursorPosition)
    }

    override fun deleteSurroundingTextInCodePoints(beforeLength: Int, afterLength: Int): Boolean {
        writes++
        if (throws) error("disconnected")
        return !fail && super.deleteSurroundingTextInCodePoints(beforeLength, afterLength)
    }

    override fun getSelectedText(flags: Int): CharSequence? {
        reads++
        check(!secret)
        return super.getSelectedText(flags)
    }

    override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence? {
        reads++
        check(!secret)
        return super.getTextBeforeCursor(length, flags)
    }

    override fun getTextAfterCursor(length: Int, flags: Int): CharSequence? {
        reads++
        check(!secret)
        return super.getTextAfterCursor(length, flags)
    }

    override fun getExtractedText(request: ExtractedTextRequest?, flags: Int): ExtractedText {
        reads++
        check(!secret)
        return ExtractedText().apply {
            text = buffer.toString()
            startOffset = 0
            selectionStart = Selection.getSelectionStart(buffer)
            selectionEnd = Selection.getSelectionEnd(buffer)
        }
    }

    override fun performEditorAction(editorAction: Int): Boolean { actions++; return false }
    override fun sendKeyEvent(event: KeyEvent?): Boolean { events++; return false }
}

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29, 32, 34], qualifiers = "mdpi")
class ManualKeyboardViewTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private val connection = ManualTestConnection(context)
    private var live: InputConnection? = connection
    private var temporary = false
    private var epoch = 0
    private var picker = 0
    private var settings = 0
    private var hidden = 0
    private var pickerSucceeds = true
    private var settingsSucceeds = true
    private val controller = ManualInputController(
        connectionOf = { live }, blocked = { temporary }, onAction = { epoch++ },
        switchKeyboard = {
            ImeAvailability.recoveryRequest(
                requestsSystemPicker = { picker++; pickerSucceeds },
                opensInputMethodSettings = { settings++; check(settingsSucceeds) },
            )
        },
        hideKeyboard = { hidden++ },
    )
    private val editor = EditorInfo().apply {
        packageName = "fixture.editor"
        inputType = InputType.TYPE_CLASS_TEXT
        initialSelStart = 0
        initialSelEnd = 0
    }
    private fun keyboard(): ManualKeyboardView {
        controller.bind(editor)
        return ManualKeyboardView(context, controller)
    }

    private fun buttons(view: View): List<Button> = when (view) {
        is Button -> listOf(view)
        is ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
        else -> emptyList()
    }

    private fun key(view: View, label: String): Button = buttons(view).single { it.text.toString() == label }

    private fun click(view: View, label: String) {
        assertTrue(key(view, label).performClick())
        controller.updateSelection(Selection.getSelectionStart(connection.buffer), Selection.getSelectionEnd(connection.buffer))
    }

    @Test fun actualClicksTypeAlphabetShiftNumbersEveryAsciiSymbolAndSpace() {
        val view = keyboard()
        "abcdefghijklmnopqrstuvwxyz".forEach { click(view, it.toString()) }
        click(view, "⇧")
        click(view, "A")
        click(view, "123 #+")
        "0123456789".forEach { click(view, it.toString()) }
        val typed = mutableSetOf<Char>()
        repeat(2) {
            buttons(view).map { it.text.toString() }.filter { it.length == 1 && it[0] in '!'..'~' && !it[0].isLetterOrDigit() }
                .forEach { click(view, it); typed += it[0] }
            click(view, "#+=")
        }
        assertEquals(('!'..'~').filter { !it.isLetterOrDigit() }.toSet(), typed)
        click(view, "空格")
        assertTrue(connection.buffer.toString().startsWith("abcdefghijklmnopqrstuvwxyzA0123456789"))
        assertTrue(connection.buffer.endsWith(" "))
        assertEquals(0, connection.actions)
        assertEquals(0, connection.events)
        assertEquals(0, connection.reads)
    }

    @Test fun selectionReplacementAndDeletionUseCurrentSelection() {
        val view = keyboard()
        connection.buffer.append("hello")
        Selection.setSelection(connection.buffer, 1, 4)
        controller.updateSelection(1, 4)
        click(view, "a")
        assertEquals("hao", connection.buffer.toString())
        Selection.setSelection(connection.buffer, 2, 0)
        controller.updateSelection(2, 0)
        click(view, "⌫")
        assertEquals("o", connection.buffer.toString())
    }

    @Test fun deleteRemovesOneUnicodeCodepointWithoutReadingText() {
        val view = keyboard()
        connection.buffer.append("A😀")
        Selection.setSelection(connection.buffer, connection.buffer.length)
        controller.updateSelection(3, 3)
        click(view, "⌫")
        assertEquals("A", connection.buffer.toString())
        assertEquals(0, connection.reads)
    }

    @Test fun secretTypingReplacementAndCodepointDeletionNeverReadSecrets() {
        editor.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        connection.secret = true
        val view = keyboard()
        click(view, "s")
        click(view, "e")
        click(view, "⌫")
        Selection.setSelection(connection.buffer, 0, 1)
        controller.updateSelection(0, 1)
        click(view, "x")
        click(view, "⌫")
        assertEquals("", connection.buffer.toString())
        assertEquals(0, connection.reads)
    }

    @Test fun singleLineAndActionSendNeverSendOrProduceNewline() {
        listOf(InputType.TYPE_CLASS_TEXT, InputType.TYPE_CLASS_NUMBER,
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_IME_MULTI_LINE,
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE).forEach { type ->
            editor.inputType = type
            editor.imeOptions = EditorInfo.IME_ACTION_SEND
            val view = keyboard()
            assertFalse(key(view, "换行").isEnabled)
            key(view, "换行").performClick()
        }
        editor.imeOptions = EditorInfo.IME_ACTION_DONE
        editor.inputType = InputType.TYPE_CLASS_TEXT
        val view = keyboard()
        assertFalse(key(view, "换行").isEnabled)
        key(view, "换行").performClick()
        assertEquals("", connection.buffer.toString())
        assertEquals(0, connection.actions)
        assertEquals(0, connection.events)
    }

    @Test fun multilineNewlineCommitsOnlyLiteralNewline() {
        editor.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        val view = keyboard()
        click(view, "a")
        click(view, "换行")
        assertEquals("a\n", connection.buffer.toString())
        assertEquals(0, connection.actions)
        assertEquals(0, connection.events)
    }

    @Test fun replacedConnectionAndOldEditorClicksFailClosed() {
        val view = keyboard()
        val oldKey = key(view, "a")
        val replacement = ManualTestConnection(context)
        live = replacement
        oldKey.performClick()
        assertEquals(0, replacement.writes)
        assertEquals(0, connection.writes)
        controller.bind(editor)
        view.reset()
        oldKey.performClick()
        assertEquals(0, replacement.writes)
        key(view, "a").performClick()
        assertEquals("a", replacement.buffer.toString())
    }

    @Test fun missingConnectionAndFalseOrThrowingWritesDoNotRetry() {
        listOf(false, true).forEach { throwing ->
            connection.fail = !throwing
            connection.throws = throwing
            val view = keyboard()
            val oldKey = key(view, "a")
            val before = connection.writes
            oldKey.performClick()
            oldKey.performClick()
            assertEquals(before + 1, connection.writes)
            assertFalse(buttons(view).any { it.text == "a" })
            assertTrue(key(view, "切换键盘").isEnabled)
        }
        live = null
        assertFalse(buttons(keyboard()).any { it.text == "a" })
        assertEquals("", connection.buffer.toString())
    }

    @Test fun switchCancelRetainsTypingAndInvalidatesOldFrame() {
        val view = keyboard()
        val oldKey = key(view, "a")
        click(view, "切换键盘")
        oldKey.performClick()
        assertEquals("", connection.buffer.toString())
        click(view, "b")
        assertEquals("b", connection.buffer.toString())
        assertEquals(1, picker)
        assertEquals(0, settings)
        assertEquals(2, epoch)
    }

    @Test fun switchFallbackAndTotalFailureBothKeepTypingAvailable() {
        pickerSucceeds = false
        listOf(true, false).forEach { fallbackWorks ->
            settingsSucceeds = fallbackWorks
            val view = keyboard()
            click(view, "切换键盘")
            click(view, "a")
        }
        assertEquals(2, picker)
        assertEquals(2, settings)
        assertEquals("aa", connection.buffer.toString())
    }

    @Test fun temporaryInterlockBlocksExistingClickAndKeepsSwitchEscape() {
        val view = keyboard()
        val oldKey = key(view, "a")
        temporary = true
        oldKey.performClick()
        assertEquals(0, connection.writes)
        view.reset()
        assertFalse(buttons(view).any { it.text == "a" })
        click(view, "切换键盘")
        assertEquals(1, picker)
        temporary = false
        controller.bind(editor)
        view.reset()
        oldKey.performClick()
        assertEquals(0, connection.writes)
        click(view, "a")
        assertEquals("a", connection.buffer.toString())
    }

    @Test fun hideAndRebindResetShiftAndSymbolsAndRejectStaleClicks() {
        val view = keyboard()
        click(view, "⇧")
        val oldUppercase = key(view, "A")
        click(view, "123 #+")
        click(view, "收起键盘")
        assertEquals(1, hidden)
        controller.reset()
        controller.bind(editor)
        view.reset()
        oldUppercase.performClick()
        assertEquals("", connection.buffer.toString())
        click(view, "a")
        assertTrue(buttons(view).any { it.text == "123 #+" })
        assertEquals("a", connection.buffer.toString())
    }

    @GraphicsMode(GraphicsMode.Mode.NATIVE)
    @Test fun portraitAndLandscapeKeysAndLabelsFitAndExportReviewBitmap() {
        val view = keyboard()
        listOf(360, 640).forEach { width ->
            listOf("letters", "shift", "symbols", "more-symbols").forEach { layout ->
                when (layout) {
                    "shift" -> click(view, "⇧")
                    "symbols" -> click(view, "123 #+")
                    "more-symbols" -> click(view, "#+=")
                }
                view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                view.layout(0, 0, view.measuredWidth, view.measuredHeight)
                assertTrue(view.height <= 330)
                buttons(view).forEach { button ->
                    val row = button.parent as ViewGroup
                    assertTrue(button.left >= 0 && button.right <= row.width, button.text.toString())
                    assertTrue(button.height >= 48)
                    assertTrue(button.width >= 34)
                    assertTrue(button.paint.measureText(button.text.toString()) <=
                        button.width - button.compoundPaddingLeft - button.compoundPaddingRight, button.text.toString())
                    assertEquals(1, button.layout.lineCount)
                    assertEquals(0, button.layout.getEllipsisCount(0))
                }
                System.getProperty("cloudctl.keyboardEvidence")?.let { directory ->
                    val file = File(directory, "keyboard-${Build.VERSION.SDK_INT}-$width-$layout.png")
                    file.parentFile?.mkdirs()
                    val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
                    view.draw(Canvas(bitmap))
                    file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
                }
            }
            view.reset()
        }
    }
}
