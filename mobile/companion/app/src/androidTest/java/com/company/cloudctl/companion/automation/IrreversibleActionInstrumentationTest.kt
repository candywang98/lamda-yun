package com.company.cloudctl.companion.automation

import android.content.Context
import android.content.ContextWrapper
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.service.IrreversibleActionCoordinator
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.nio.file.Files

/** Device-local, isolated counter effects; never invokes a platform UI or network. */
@RunWith(AndroidJUnit4::class)
class IrreversibleActionInstrumentationTest {
    private lateinit var directory: File
    private lateinit var context: Context
    private lateinit var store: AutomationStore
    private lateinit var coordinator: IrreversibleActionCoordinator
    private val task = "p09-isolated-task"
    private val action = "p09-isolated-action"
    private val hash = "a".repeat(64)

    @Before fun setup() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        directory = Files.createTempDirectory(instrumentation.targetContext.cacheDir.toPath(), "p09-action-").toFile()
        context = object : ContextWrapper(instrumentation.context) {
            override fun getDatabasePath(name: String): File {
                require(name == AutomationStore.DATABASE_NAME)
                return File(directory, name)
            }
            override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?): SQLiteDatabase =
                SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name), factory)
            override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?, errorHandler: DatabaseErrorHandler?): SQLiteDatabase =
                SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name).path, factory, errorHandler)
        }
        reopen()
        store.enqueueTask(task, "{}", "isolated-lease", 0)
        assertNotNull(store.claimNext())
    }

    @After fun cleanup() {
        if (::store.isInitialized) store.close()
        if (::directory.isInitialized) directory.deleteRecursively()
    }

    private fun reopen() {
        if (::store.isInitialized) store.close()
        store = AutomationStore(context)
        assertEquals(directory.canonicalFile, File(store.writableDatabase.path).canonicalFile.parentFile)
        coordinator = IrreversibleActionCoordinator(store)
    }
    private fun count(): Int = File(directory, "counter").takeIf { it.exists() }?.readText()?.toInt() ?: 0
    private fun increment() { File(directory, "counter").writeText((count() + 1).toString()) }
    private fun state(): String = store.readableDatabase.rawQuery("SELECT state FROM task_inbox WHERE task_id=?", arrayOf(task)).use {
        check(it.moveToFirst()); it.getString(0)
    }

    @Test fun lostConfirmationStaysUnknownAcrossReopenAndDoesNotRepeat() = runBlocking {
        val first = coordinator.executeOnce(action, task, hash, confirmApplied = false) { increment() }
        assertEquals("UNKNOWN", first.journalStatus)
        assertEquals(1, count())
        assertEquals("RECONCILING", state())
        reopen()
        assertTrue(store.hasBlockingHead())
        assertNull(store.claimNext())
        val again = coordinator.executeOnce(action, task, hash, confirmApplied = true) { increment() }
        assertFalse(again.actionInvoked)
        assertEquals(1, count())
        assertEquals("UNKNOWN", store.actionJournal(action)?.status)
    }

    @Test fun appliedRepeatNeverInvokesEffectAgainAfterReopen() = runBlocking {
        val first = coordinator.executeOnce(action, task, hash, confirmApplied = true) {
            increment()
            check(count() == 1) // Independent readback of this isolated effect.
        }
        assertEquals("APPLIED", first.journalStatus)
        reopen()
        val again = coordinator.executeOnce(action, task, hash, confirmApplied = true) { increment() }
        assertFalse(again.actionInvoked)
        assertEquals(1, count())
        assertEquals("APPLIED", store.actionJournal(action)?.status)
    }

    @Test fun cancellationAfterEffectPersistsUnknownAndCannotReleaseHead() = runBlocking {
        val entered = CompletableDeferred<Unit>()
        val job = launch {
            coordinator.executeOnce(action, task, hash, confirmApplied = true) {
                increment()
                entered.complete(Unit)
                awaitCancellation()
            }
        }
        entered.await()
        job.cancelAndJoin()
        assertTrue(job.isCancelled)
        reopen()
        assertEquals("UNKNOWN", store.actionJournal(action)?.status)
        assertEquals("RECONCILING", state())
        assertTrue(store.hasBlockingHead())
        val again = coordinator.executeOnce(action, task, hash, confirmApplied = true) { increment() }
        assertFalse(again.actionInvoked)
        assertEquals(1, count())
    }
}
