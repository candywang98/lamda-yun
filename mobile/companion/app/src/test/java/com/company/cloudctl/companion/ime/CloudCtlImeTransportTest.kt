package com.company.cloudctl.companion.ime

import android.view.inputmethod.InputConnection
import com.company.cloudctl.companion.automation.ExecutorFailure
import java.lang.reflect.Proxy
import kotlinx.coroutines.runBlocking
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [32])
class CloudCtlImeTransportTest {
    private class Connection(var text: String) {
        val calls = mutableListOf<String>()
        val connection: InputConnection = Proxy.newProxyInstance(
            InputConnection::class.java.classLoader,
            arrayOf(InputConnection::class.java),
        ) { _, method, args ->
            calls += method.name
            when (method.name) {
                "getExtractedText" -> null
                "getTextBeforeCursor" -> text
                "getTextAfterCursor" -> ""
                "finishComposingText" -> true
                "commitText" -> {
                    text = args[0] as String
                    true
                }
                "setSelection" -> error("selection must not be invented")
                else -> false
            }
        } as InputConnection
    }

    private fun identity() = ImeSessionIdentity.FieldIdentity(
        packageName = "com.taobao.idlefish",
        inputType = 1,
        imeOptions = 0,
        fieldId = 7,
        fieldName = "chat",
    )

    private fun transport(connection: Connection) = CloudCtlImeTransport(
        targetPackage = "com.taobao.idlefish",
        sessionOf = { 4L },
        readOf = { ImeTextReplacement.read(connection.connection) },
        connectionOf = { connection.connection },
        identityOf = { identity() },
        onMain = false,
    )

    @Test fun snapshotDoesNotClaimASelectionAtTheEnd() = runBlocking {
        val connection = Connection("")
        val snapshot = transport(connection).snapshot()!!
        assertFalse(snapshot.selectionKnown)
        assertEquals(0, snapshot.selectionStart)
        assertEquals(0, snapshot.selectionEnd)
        assertEquals("", snapshot.text)
    }

    @Test fun emptyFieldCommitsOnceWithoutSelecting() = runBlocking {
        val connection = Connection("")
        val live = transport(connection)
        val proof = VerifiedEditorInput(live, target = { "com.taobao.idlefish" }, pause = {}).write("在的")
        assertEquals("在的", connection.text)
        assertFalse("setSelection" in connection.calls)
        assertEquals(false, proof.selectionKnown)
        assertEquals(1, proof.commitCount)
        assertEquals(1, live.commitCount())
        live.let { VerifiedEditorInput(it, target = { "com.taobao.idlefish" }, pause = {}).verify(proof) }
    }

    @Test fun nonEmptyDifferentDraftIsNotOverwritten() = runBlocking {
        val connection = Connection("用户草稿")
        val live = transport(connection)
        val error = assertFailsWith<ExecutorFailure> {
            VerifiedEditorInput(live, target = { "com.taobao.idlefish" }, pause = {}).write("在的")
        }
        assertEquals("FIELD_DIRTY_BY_USER", error.code)
        assertEquals("用户草稿", connection.text)
        assertFalse("commitText" in connection.calls)
        assertFalse("setSelection" in connection.calls)
    }

    @Test fun fieldAlreadyEqualDoesNotCommit() = runBlocking {
        val connection = Connection("在的")
        val live = transport(connection)
        val proof = VerifiedEditorInput(live, target = { "com.taobao.idlefish" }, pause = {}).write("在的")
        assertEquals("在的", proof.expected)
        assertFalse("commitText" in connection.calls)
        assertTrue(connection.calls.count { it == "getTextBeforeCursor" } >= 2)
    }
}
