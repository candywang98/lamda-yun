package com.company.cloudctl.companion.features.xhs.publish

import com.company.cloudctl.companion.features.xhs.publish.XhsNotePublishPlanner.PlanResult
import com.company.cloudctl.companion.features.xhs.publish.XhsNoteStep.ProveNoteInput
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * F14 验收：图文完整输入/图片顺序冻结；未批准视频显式待定而非漏项。
 */
class XhsNotePublishPlannerTest {

    private val images = listOf("img-a", "img-b", "img-c")

    @Test
    fun planFreezesImageOrderAndProducesFullStepChain() {
        val plan = assertIs<PlanResult.Plan>(
            XhsNotePublishPlanner.plan(
                title = "闲置好物",
                body = "九成新，见图。",
                mediaAssetIds = images,
                draftPolicy = XhsDraftPolicy.SAVE_DRAFT,
            ),
        )
        assertEquals(images, plan.imageOrder)
        assertEquals(XhsDraftPolicy.SAVE_DRAFT, plan.draftPolicy)
        val ids = plan.steps.map { it.id }
        assertTrue(ids.contains("xhs-select-images-in-order"))
        assertTrue(ids.indexOf("xhs-select-images-in-order") < ids.indexOf("xhs-prove-input-title"))
        // 草稿检查点在最终发布人工检查点之前。
        assertTrue(ids.indexOf("xhs-draft-dialog-checkpoint") < ids.indexOf("xhs-final-commit-checkpoint"))
        val select = plan.steps.filterIsInstance<XhsNoteStep.SelectImagesInOrder>().single()
        assertEquals(images, select.expectedOrder)
        val titleStep = plan.steps.filterIsInstance<ProveNoteInput>().first { it.noteField == ProveNoteInput.NoteField.TITLE }
        assertEquals("闲置好物", titleStep.expected)
    }

    @Test
    fun videoRequestIsExplicitlyRejectedNotSilentlyDropped() {
        val rejected = assertIs<PlanResult.Rejected>(
            XhsNotePublishPlanner.plan(
                title = "t",
                body = "b",
                mediaAssetIds = images,
                videoAssetIds = listOf("video-x"),
            ),
        )
        assertTrue(rejected.reason.contains(XhsMediaSupport.VIDEO_STATUS))
        assertTrue(rejected.reason.contains("显式拒绝"))
    }

    @Test
    fun invalidInputsAreRejectedWithExplainableReasons() {
        assertIs<PlanResult.Rejected>(XhsNotePublishPlanner.plan(" ", "b", images))
        assertIs<PlanResult.Rejected>(XhsNotePublishPlanner.plan("t", "", images))
        assertIs<PlanResult.Rejected>(XhsNotePublishPlanner.plan("t", "b", emptyList()))
        val tooMany = assertIs<PlanResult.Rejected>(
            XhsNotePublishPlanner.plan("t", "b", (1..19).map { "img-$it" }),
        )
        assertTrue(tooMany.reason.contains("19"))
        val duplicated = assertIs<PlanResult.Rejected>(
            XhsNotePublishPlanner.plan("t", "b", listOf("img-a", "img-a")),
        )
        assertTrue(duplicated.reason.contains("重复"))
    }
}
