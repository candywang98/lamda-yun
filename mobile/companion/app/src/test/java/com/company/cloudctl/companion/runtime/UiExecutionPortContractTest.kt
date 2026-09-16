package com.company.cloudctl.companion.runtime

import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * B10 port contract: the narrow [UiExecutionPort] is the single application
 * point for every writer channel — allowed writes reach the raw device ops
 * exactly once; rejected writes never reach them and are recorded.
 */
class UiExecutionPortContractTest {
    private class RecordingOps : RawUiOps {
        val launches = mutableListOf<String>()
        val backs = mutableListOf<String>()
        val texts = mutableListOf<Triple<String, String, String>>()
        val taps = mutableListOf<Pair<Double, Double>>()
        val swipes = mutableListOf<Pair<Double, Double>>()

        override suspend fun launchTargetApp(targetPackage: String) {
            launches += targetPackage
        }

        override fun globalBack() {
            backs += "back"
        }

        override fun submitGestureTap(x: Double, y: Double) {
            taps += x to y
        }

        override fun submitGestureSwipe(x1: Double, y1: Double, x2: Double, y2: Double) {
            swipes += x1 to x2
        }

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) {
            texts += Triple(targetPackage, locatorRef, value)
        }
    }

    @Test
    fun taskWritesDelegateToTheRawOps() = runBlocking {
        val arbiter = DeviceArbiter()
        val ops = RecordingOps()
        val port = ArbiterGuardedUiExecutionPort(arbiter, ops)
        val session = arbiter.beginTaskSession("task-1")

        port.launchTarget(UiWriter.TASK, "com.taobao.idlefish", session.fencingToken)
        port.back(UiWriter.TASK, session.fencingToken)
        port.replaceText(UiWriter.TASK, "com.taobao.idlefish", "xianyu_chat_input", "你好", session.fencingToken)
        assertTrue(port.submitGestureTap(UiWriter.TASK, 1.0, 2.0, epoch = session.fencingToken))

        assertEquals(listOf("com.taobao.idlefish"), ops.launches)
        assertEquals(listOf("back"), ops.backs)
        assertEquals(listOf(Triple("com.taobao.idlefish", "xianyu_chat_input", "你好")), ops.texts)
        assertEquals(listOf(1.0 to 2.0), ops.taps)
    }

    @Test
    fun deniedSuspendWriteThrowsAndNeverReachesOps() = runBlocking {
        val arbiter = DeviceArbiter()
        val ops = RecordingOps()
        val port = ArbiterGuardedUiExecutionPort(arbiter, ops)
        arbiter.beginTaskSession("task-1")

        // Duty launch while a task is RUNNING: rejected, recorded, and the
        // raw op is untouched; the suspending surface fails closed.
        val error = assertFailsWith<ArbiterDenialException> {
            port.launchTarget(UiWriter.IM_DUTY, "com.taobao.idlefish")
        }
        assertEquals(ArbiterDenialReason.DEVICE_BUSY, error.denial.reason)
        assertEquals(UiWriter.IM_DUTY, error.denial.writer)

        val inputError = assertFailsWith<ArbiterDenialException> {
            port.replaceText(UiWriter.IM_DUTY, "com.taobao.idlefish", "xianyu_chat_input", "hi")
        }
        assertEquals(UiWriteKind.TEXT_INPUT, inputError.denial.kind)

        assertTrue(ops.launches.isEmpty())
        assertTrue(ops.texts.isEmpty())
        assertEquals(2, arbiter.denials().size)
    }

    @Test
    fun deniedFireAndForgetWriteReturnsFalseWithoutDispatch() {
        val arbiter = DeviceArbiter()
        val ops = RecordingOps()
        val port = ArbiterGuardedUiExecutionPort(arbiter, ops)
        arbiter.beginTaskSession("task-1")

        assertFalse(port.submitGestureTap(UiWriter.REMOTE_LIVE, 9.0, 9.0, epoch = null))
        assertFalse(port.submitGestureSwipe(UiWriter.EDGE, 1.0, 1.0, 2.0, 2.0, epoch = null))
        assertTrue(ops.taps.isEmpty())
        assertTrue(ops.swipes.isEmpty())
        assertEquals(
            listOf(UiWriter.REMOTE_LIVE, UiWriter.EDGE),
            arbiter.denials().map { it.writer },
        )
    }

    @Test
    fun portExposesTheHeldArbiter() {
        val arbiter = DeviceArbiter()
        val port = ArbiterGuardedUiExecutionPort(arbiter, RecordingOps())
        assertEquals(arbiter, port.arbiter)
    }
}
