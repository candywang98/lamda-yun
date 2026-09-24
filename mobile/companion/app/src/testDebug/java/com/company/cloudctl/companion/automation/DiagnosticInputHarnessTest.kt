package com.company.cloudctl.companion.automation

import com.company.cloudctl.companion.ime.InputProof
import com.company.cloudctl.companion.ime.InputProofProjector
import com.company.cloudctl.companion.runtime.DeviceArbiter
import com.company.cloudctl.companion.runtime.UiWriteKind
import com.company.cloudctl.companion.runtime.UiWriter
import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Software gate for the debug-only isolated input runner.
 *
 * These tests compile against main + test, which sees the debug source set
 * the same way a debug unit-test variant does. They do not touch a device.
 */
class DiagnosticInputHarnessTest {
    private val now = Instant.parse("2026-09-22T12:00:00Z")

    @Test
    fun closedPolicyAdmitsNothing() {
        val policy = DiagnosticInputPolicy.Closed
        assertFalse(policy.admits(DebugDiagnosticInputPolicy.PACKAGE, DebugDiagnosticInputPolicy.FIELD))
        assertFalse(policy.admits(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_chat_input"))
        assertFalse(policy.admits(TargetLocatorRegistry.XIANYU_PACKAGE, "xianyu_price"))
        assertNull(policy.locator(DebugDiagnosticInputPolicy.PACKAGE, DebugDiagnosticInputPolicy.FIELD))
        assertFalse(policy.skipsRootNavigation(DebugDiagnosticInputPolicy.PACKAGE))
    }

    @Test
    fun debugPolicyAdmitsOnlyTheFixedField() {
        val policy = DebugDiagnosticInputPolicy
        assertTrue(policy.admits(DebugDiagnosticInputPolicy.PACKAGE, DebugDiagnosticInputPolicy.FIELD))
        assertFalse(policy.admits(DebugDiagnosticInputPolicy.PACKAGE, "xianyu_chat_input"))
        assertFalse(policy.admits(TargetLocatorRegistry.XIANYU_PACKAGE, DebugDiagnosticInputPolicy.FIELD))
        assertFalse(policy.admits(TargetLocatorRegistry.XHS_PACKAGE, DebugDiagnosticInputPolicy.FIELD))
        assertFalse(policy.admits(TargetLocatorRegistry.DOUYIN_PACKAGE, DebugDiagnosticInputPolicy.FIELD))
        assertFalse(policy.admits("com.taobao.idlefish", "xianyu_publish_button"))
        val locator = policy.locator(DebugDiagnosticInputPolicy.PACKAGE, DebugDiagnosticInputPolicy.FIELD)
        assertTrue(locator is ApprovedLocator.ResourceId)
        assertEquals(DebugDiagnosticInputPolicy.VIEW_ID, (locator as ApprovedLocator.ResourceId).value)
        assertTrue(policy.skipsRootNavigation(DebugDiagnosticInputPolicy.PACKAGE))
        assertFalse(policy.skipsRootNavigation(TargetLocatorRegistry.XIANYU_PACKAGE))
    }

    @Test
    fun productionRegistryStillRejectsTheHarnessPackage() {
        kotlin.test.assertFailsWith<IllegalArgumentException> {
            TargetLocatorRegistry.resolve(DebugDiagnosticInputPolicy.PACKAGE, DebugDiagnosticInputPolicy.FIELD)
        }
        kotlin.test.assertFailsWith<IllegalArgumentException> {
            TargetLocatorRegistry.resolve(TargetLocatorRegistry.XIANYU_PACKAGE, DebugDiagnosticInputPolicy.FIELD)
        }
    }

    @Test
    fun cloudParserStillRejectsTheHarnessPackage() {
        val payload = """
            {"protocolVersion":"cloudctl.mobile/v1","taskId":"t-1","deviceId":"d-1",
             "targetPackage":"${DebugDiagnosticInputPolicy.PACKAGE}",
             "issuedAt":"2026-09-22T00:00:00Z","expiresAt":"2026-09-22T01:00:00Z",
             "maxRunSeconds":30,"steps":[{"stepId":"s","action":"ui.input","timeoutMs":1000,
             "locatorRef":"${DebugDiagnosticInputPolicy.FIELD}","value":"x","replace":true}]}
        """.trimIndent()
        kotlin.test.assertFailsWith<IllegalArgumentException> {
            AutomationTaskParser.parse(payload)
        }
    }

    @Test
    fun runnerConstructsExactlyOneFixedInputStep() {
        val ui = RecordingUi()
        val runner = DiagnosticInputStepRunner(ui, DeviceArbiter(), sdkInt = 34, now = { now }, elapsedMs = { 0L })
        val task = runner.fixedTask("你好🙂\n第二行")
        assertEquals(DebugDiagnosticInputPolicy.PACKAGE, task.targetPackage)
        assertEquals(1, task.steps.size)
        val step = task.steps.single()
        assertTrue(step is AutomationStep.Input)
        val input = step as AutomationStep.Input
        assertEquals(DebugDiagnosticInputPolicy.FIELD, input.locatorRef)
        assertEquals("你好🙂\n第二行", input.value)
        assertTrue(runner.accepts(task))
        assertFalse(runner.accepts(task.copy(targetPackage = TargetLocatorRegistry.XIANYU_PACKAGE)))
        assertFalse(
            runner.accepts(
                task.copy(
                    steps = task.steps + AutomationStep.Tap("tap", 1000, "xianyu_chat_send", null),
                ),
            ),
        )
        assertFalse(
            runner.accepts(
                task.copy(steps = listOf(AutomationStep.Tap("tap", 1000, DebugDiagnosticInputPolicy.FIELD, null))),
            ),
        )
    }

    @Test
    fun runnerRejectsBusinessPackagesByConstruction() {
        val runner = DiagnosticInputStepRunner(RecordingUi(), DeviceArbiter(), sdkInt = 34, now = { now }, elapsedMs = { 0L })
        val business = listOf(
            TargetLocatorRegistry.XIANYU_PACKAGE,
            TargetLocatorRegistry.XHS_PACKAGE,
            TargetLocatorRegistry.DOUYIN_PACKAGE,
            TargetLocatorRegistry.COMPANION_PACKAGE,
        )
        business.forEach { pkg ->
            assertFalse(DebugDiagnosticInputPolicy.admits(pkg, "xianyu_chat_input"))
            assertFalse(DebugDiagnosticInputPolicy.admits(pkg, "xianyu_publish_button"))
            assertFalse(DebugDiagnosticInputPolicy.admits(pkg, "xianyu_price"))
            assertFalse(runner.accepts(runner.fixedTask("x").copy(targetPackage = pkg)))
        }
    }

    @Test
    fun emptyFieldCommitsOnceAndProjectsHashesOnly() = runBlocking {
        val fixture = "你好🙂\n第二行"
        val ui = RecordingUi(commitCount = 1)
        val arbiter = DeviceArbiter()
        val runner = DiagnosticInputStepRunner(ui, arbiter, sdkInt = 34, now = { now }, elapsedMs = { 1_000L })
        val projection = runner.runOnce(fixture)
        assertEquals("INPUT_VERIFIED", projection.resultCode)
        assertEquals(fixture.length, projection.utf16Length)
        assertEquals(InputProofProjector.sha256(fixture), projection.textSha256)
        assertEquals(7L, projection.generation)
        assertEquals(1, projection.commitCount)
        assertEquals("ACCESSIBILITY", projection.channel)
        assertEquals(InputProofProjector.sha256("field-fingerprint"), projection.fieldSha256)
        assertFalse(projection.textSha256.contains(fixture))
        assertFalse(projection.toString().contains(fixture))
        assertEquals(1, ui.writes)
        assertNull(arbiter.activeTaskSession())
        assertEquals(1, ui.demandWrites)
    }

    @Test
    fun alreadyEqualReportsZeroCommits() = runBlocking {
        val fixture = "已经相等"
        val ui = RecordingUi(initial = fixture, commitCount = 0)
        val projection = DiagnosticInputStepRunner(
            ui, DeviceArbiter(), sdkInt = 34, now = { now }, elapsedMs = { 1_000L },
        ).runOnce(fixture)
        assertEquals("INPUT_VERIFIED", projection.resultCode)
        assertEquals(0, projection.commitCount)
        assertEquals(0, ui.writes)
    }

    @Test
    fun dirtyDraftIsRefusedAndNotOverwritten() = runBlocking {
        val ui = RecordingUi(initial = "用户草稿", dirty = true)
        val projection = DiagnosticInputStepRunner(
            ui, DeviceArbiter(), sdkInt = 34, now = { now }, elapsedMs = { 1_000L },
        ).runOnce("新文本")
        assertEquals("FIELD_DIRTY_BY_USER", projection.resultCode)
        assertEquals("用户草稿", ui.field)
        assertEquals(0, ui.writes)
        assertEquals("", projection.textSha256)
    }

    @Test
    fun longTextPastTheWindowIsRejected() = runBlocking {
        val ui = RecordingUi()
        val projection = DiagnosticInputStepRunner(
            ui, DeviceArbiter(), sdkInt = 34, now = { now }, elapsedMs = { 1_000L },
        ).runOnce("字".repeat(10_001))
        assertEquals("INPUT_REJECTED", projection.resultCode)
        assertEquals(0, ui.writes)
    }

    @Test
    fun identityChangeFailsClosed() = runBlocking {
        val ui = RecordingUi(changeIdentity = true)
        val projection = DiagnosticInputStepRunner(
            ui, DeviceArbiter(), sdkInt = 34, now = { now }, elapsedMs = { 1_000L },
        ).runOnce("身份")
        assertEquals("INPUT_TARGET_CHANGED", projection.resultCode)
    }

    @Test
    fun api33UnboundDoesNotSwitchIme() = runBlocking {
        val ui = RecordingUi(unbound = true)
        val projection = DiagnosticInputStepRunner(
            ui, DeviceArbiter(), sdkInt = 34, now = { now }, elapsedMs = { 1_000L },
        ).runOnce("未绑定")
        assertEquals("INPUT_READBACK_UNAVAILABLE", projection.resultCode)
        assertEquals(0, ui.imeSwitches)
        assertEquals(0, ui.writes)
        assertEquals("ACCESSIBILITY", projection.channel)
    }

    @Test
    fun api30RunnerNamesTemporaryImeAndDoesNotLaunchXianyu() = runBlocking {
        val ui = RecordingUi(commitCount = 1)
        val projection = DiagnosticInputStepRunner(
            ui, DeviceArbiter(), sdkInt = 31, now = { now }, elapsedMs = { 1_000L },
        ).runOnce("临时")
        assertEquals("TEMPORARY_IME", projection.channel)
        assertEquals(0, ui.launches)
        assertTrue(ui.packages.none { it == TargetLocatorRegistry.XIANYU_PACKAGE })
    }

    @Test
    fun projectionNeverCarriesPlaintext() {
        val proof = sampleProof("机密🙂\n")
        val projection = InputProofProjector.project(proof, "ACCESSIBILITY", 1)
        val rendered = projection.toString()
        assertFalse(rendered.contains("机密"))
        assertFalse(rendered.contains(proof.expected))
        assertEquals(proof.expected.length, projection.utf16Length)
        assertEquals(64, projection.textSha256.length)
        assertEquals(64, projection.fieldSha256.length)
    }

    @Test
    fun staleProofFromAnotherNodeFailsClosed() = runBlocking {
        val ui = RecordingUi(commitCount = 1, staleNodeKey = "older-node")
        val projection = DiagnosticInputStepRunner(
            ui, DeviceArbiter(), sdkInt = 34, now = { now }, elapsedMs = { 1_000L },
        ).runOnce("旧证明")
        assertEquals("INPUT_TARGET_CHANGED", projection.resultCode)
        assertEquals("", projection.textSha256)
    }

    @Test
    fun moreThanOneCommitIsNotSuccess() = runBlocking {
        val ui = RecordingUi(commitCount = 2)
        val projection = DiagnosticInputStepRunner(
            ui, DeviceArbiter(), sdkInt = 34, now = { now }, elapsedMs = { 1_000L },
        ).runOnce("两次")
        assertEquals("INPUT_READBACK_UNAVAILABLE", projection.resultCode)
        assertNull(ui.lastInputProof())
    }

    @Test
    fun taskSessionIsHeldWhileTheStepRuns() = runBlocking {
        val arbiter = DeviceArbiter()
        val ui = RecordingUi(commitCount = 1, arbiter = arbiter)
        val projection = DiagnosticInputStepRunner(
            ui, arbiter, sdkInt = 34, now = { now }, elapsedMs = { 1_000L },
        ).runOnce("会话")
        assertEquals("INPUT_VERIFIED", projection.resultCode)
        assertTrue(ui.sawTaskSession)
        assertNull(arbiter.activeTaskSession())
    }

    private fun sampleProof(text: String) = InputProof(
        target = DebugDiagnosticInputPolicy.PACKAGE,
        field = "field-fingerprint",
        generation = 7L,
        expected = text,
        snapshot = com.company.cloudctl.companion.ime.EditorSnapshot(
            generation = 7L,
            field = "field-fingerprint",
            text = text,
            selectionStart = text.length,
            selectionEnd = text.length,
            composing = false,
            offsetKnown = true,
            offset = 0,
            truncated = false,
        ),
        targetPackage = DebugDiagnosticInputPolicy.PACKAGE,
        locatorRef = DebugDiagnosticInputPolicy.FIELD,
        nodeKey = "1|0,0,10,10|android.widget.EditText|id",
        selectionKnown = true,
        commitCount = 1,
    )

    /**
     * Stands in for the accessibility service's input path. It enforces the
     * same demand the service does, and it refuses to write a dirty field.
     * It does not launch, tap, or read a page substring.
     */
    private class RecordingUi(
        initial: String = "",
        private val commitCount: Int = 1,
        private val dirty: Boolean = false,
        private val unbound: Boolean = false,
        private val changeIdentity: Boolean = false,
        private val staleNodeKey: String? = null,
        private val arbiter: DeviceArbiter? = null,
    ) : LocalAutomationUi {
        var field: String = initial
        var writes = 0
        var imeSwitches = 0
        var launches = 0
        var demandWrites = 0
        var sawTaskSession = false
        val packages = mutableListOf<String>()
        private var proof: InputProof? = null

        override fun ensureReady(targetPackage: String) {
            packages += targetPackage
            check(targetPackage == DebugDiagnosticInputPolicy.PACKAGE)
        }

        override fun atRootPage(targetPackage: String): Boolean =
            DebugDiagnosticInputPolicy.skipsRootNavigation(targetPackage)

        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? {
            if (!DebugDiagnosticInputPolicy.admits(targetPackage, locatorRef)) return null
            return LocalNodeState(
                enabled = true,
                visible = true,
                clickable = true,
                editable = true,
                text = field,
                description = "field-fingerprint",
                nodeKey = if (changeIdentity) "other-node" else "node",
            )
        }

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) {
            replaceTextReturningProof(targetPackage, locatorRef, value)
        }

        override suspend fun replaceTextReturningProof(
            targetPackage: String,
            locatorRef: String,
            value: String,
        ): InputProof? {
            check(DebugDiagnosticInputPolicy.admits(targetPackage, locatorRef))
            demandWrites += 1
            // The runner must already hold the task session the service's
            // demandWrite would accept. A missing session is a failed test.
            val holder = arbiter
            if (holder != null) {
                val decision = holder.request(UiWriter.TASK, UiWriteKind.TEXT_INPUT, detail = "diagnostic")
                sawTaskSession = decision is com.company.cloudctl.companion.runtime.ArbiterDecision.Allowed
                check(sawTaskSession) { "diagnostic write ran without a task session" }
            }
            if (unbound) {
                throw ExecutorFailure(
                    "INPUT_READBACK_UNAVAILABLE",
                    "Accessibility editor is not bound; the user's keyboard was not switched",
                )
            }
            if (dirty && field.isNotEmpty() && field != value) {
                throw ExecutorFailure("FIELD_DIRTY_BY_USER", "The field contains an existing draft")
            }
            if (value.isBlank() || value.length > 10_000) {
                throw ExecutorFailure("INPUT_REJECTED", "Text is empty or longer than the verified window")
            }
            if (changeIdentity) {
                throw ExecutorFailure("INPUT_TARGET_CHANGED", "The target field changed after input")
            }
            if (field != value) {
                writes += 1
                field = value
            }
            val issued = if (writes == 0) 0 else commitCount
            // More than one commit is not a proof. The service clears its slot
            // before a failed write; this stand-in does the same.
            if (issued > 1) {
                proof = null
                return null
            }
            proof = InputProof(
                target = targetPackage,
                field = "field-fingerprint",
                generation = 7L,
                expected = value,
                snapshot = com.company.cloudctl.companion.ime.EditorSnapshot(
                    7L, "field-fingerprint", value, value.length, value.length, false, true, 0, false,
                ),
                targetPackage = targetPackage,
                locatorRef = locatorRef,
                nodeKey = staleNodeKey ?: "node",
                selectionKnown = true,
                commitCount = issued,
            )
            return proof
        }

        override fun lastInputProof(): InputProof? = proof

        override suspend fun tap(targetPackage: String, locatorRef: String) {
            error("diagnostic runner must not tap")
        }

        override suspend fun screenshot(taskId: String, label: String) =
            error("diagnostic runner must not capture a page")

        override fun log(level: LogLevel, messageCode: String) = Unit
    }
}
