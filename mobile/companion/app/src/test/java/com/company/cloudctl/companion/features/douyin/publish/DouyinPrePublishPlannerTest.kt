package com.company.cloudctl.companion.features.douyin.publish

import com.company.cloudctl.companion.features.douyin.publish.DouyinPrePublishPlanner.PlanResult
import com.company.cloudctl.companion.features.douyin.publish.DouyinPublishStep.SelectVideoByCellMark
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

class DouyinPrePublishPlannerTest {
    private val video = DouyinVideoAsset(
        fileId = "video-001",
        durationSeconds = 30,
        format = "mp4",
        galleryCellIndex = 3,
    )

    private fun planOk(
        title: String = "F15 采样视频",
        cover: String = "cover-001",
        description: String = "设备采样文案",
    ) = DouyinPrePublishPlanner.plan(
        videoAssets = listOf(video),
        coverAssetId = cover,
        title = title,
        description = description,
    )

    @Test
    fun planFreezesFourteenStepPrePublishChainAndStopsAtHumanCheckpoint() {
        val plan = assertIs<PlanResult.Plan>(planOk())
        assertEquals(
            listOf(
                "dy-launch-app",
                "dy-home-settle",
                "dy-open-publish-entry",
                "dy-await-camera-ready",
                "dy-open-album",
                "dy-open-media-tab",
                "dy-select-video-cellmark",
                "dy-confirm-media-pick",
                "dy-await-trim-crop-return",
                "dy-advance-to-publish-page",
                "dy-select-cover",
                "dy-prove-title-input",
                "dy-prove-description-input",
                "dy-verify-before-publish",
            ),
            plan.prePublishChain.map { it.id },
        )
        assertEquals("dy-final-commit-checkpoint", plan.steps[DouyinPrePublishPlanner.PRE_PUBLISH_STEP_COUNT].id)
        assertEquals("dy-await-publish-success", plan.steps.last().id)
        assertEquals(16, plan.steps.size)
    }

    @Test
    fun selectionUsesSampledCellAndVerifiedLocatorReferences() {
        val plan = assertIs<PlanResult.Plan>(planOk())
        val select = plan.steps.filterIsInstance<SelectVideoByCellMark>().single()
        assertEquals("dy_gallery_cell_3", select.cellLocator)
        assertEquals("dy_cellmark_probe", select.cellMarkProbeLocator)
        assertEquals("video-001", select.expectedFileId)
        assertEquals("cover-001", plan.steps.filterIsInstance<DouyinPublishStep.SelectCover>().single().coverAssetId)
        assertEquals(
            "cover-001",
            plan.steps.filterIsInstance<DouyinPublishStep.VerifyBeforePublish>().single().expectedCoverAssetId,
        )
    }

    @Test
    fun invalidVideoIdentityAndCellAreRejectedWithoutSelectingAnotherAsset() {
        val noVideo = assertIs<PlanResult.Rejected>(
            DouyinPrePublishPlanner.plan(emptyList(), "cover", "标题"),
        )
        assertTrue(noVideo.reason.contains("videoAssets 为空"))

        val multi = assertIs<PlanResult.Rejected>(
            DouyinPrePublishPlanner.plan(
                listOf(video, video.copy(fileId = "video-002")),
                "cover",
                "标题",
            ),
        )
        assertTrue(multi.reason.contains("V1 单视频"))
        assertTrue(multi.reason.contains("video-002"))
        assertTrue(multi.reason.contains("显式拒绝"))

        val blankId = assertIs<PlanResult.Rejected>(
            DouyinPrePublishPlanner.plan(listOf(video.copy(fileId = " ")), "cover", "标题"),
        )
        assertTrue(blankId.reason.contains("fileId"))

        val badCell = assertIs<PlanResult.Rejected>(
            DouyinPrePublishPlanner.plan(listOf(video.copy(galleryCellIndex = 50)), "cover", "标题"),
        )
        assertTrue(badCell.reason.contains("cell 索引"))
        assertTrue(badCell.reason.contains("50"))
    }

    @Test
    fun durationFormatCoverAndTextLimitsAreExplainable() {
        assertTrue(
            assertIs<PlanResult.Rejected>(
                DouyinPrePublishPlanner.plan(listOf(video.copy(durationSeconds = 2)), "cover", "标题"),
            ).reason.contains("区间"),
        )
        assertTrue(
            assertIs<PlanResult.Rejected>(
                DouyinPrePublishPlanner.plan(listOf(video.copy(format = "avi")), "cover", "标题"),
            ).reason.contains("白名单"),
        )
        assertIs<PlanResult.Plan>(
            DouyinPrePublishPlanner.plan(listOf(video.copy(format = "MOV")), "cover", "标题"),
        )

        assertTrue(
            assertIs<PlanResult.Rejected>(DouyinPrePublishPlanner.plan(listOf(video), " ", "标题"))
                .reason.contains("封面必填"),
        )
        assertTrue(
            assertIs<PlanResult.Rejected>(DouyinPrePublishPlanner.plan(listOf(video), "cover", " "))
                .reason.contains("title 不能为空"),
        )
        val profile = DouyinMediaProfile()
        assertTrue(
            assertIs<PlanResult.Rejected>(
                DouyinPrePublishPlanner.plan(
                    listOf(video),
                    "cover",
                    "长".repeat(profile.titleMaxLength + 1),
                ),
            ).reason.contains("${profile.titleMaxLength}"),
        )
        assertTrue(
            assertIs<PlanResult.Rejected>(
                DouyinPrePublishPlanner.plan(
                    listOf(video),
                    "cover",
                    "标题",
                    description = "文".repeat(profile.descriptionMaxLength + 1),
                ),
            ).reason.contains("description"),
        )
    }

    @Test
    fun uploadOrPublishPageReadinessIsNotPublishSuccess() {
        assertFalse(DouyinPublishOutcomeJudge.successEligible(null))
        assertFalse(
            DouyinPublishOutcomeJudge.successEligible(DouyinPublishObservation.UPLOAD_COMPLETE),
        )
        assertFalse(
            DouyinPublishOutcomeJudge.successEligible(DouyinPublishObservation.PUBLISH_PAGE_READY),
        )
        assertFalse(
            DouyinPublishOutcomeJudge.successEligible(DouyinPublishObservation.PLATFORM_REVIEW_IN_PROGRESS),
        )
        assertTrue(DouyinPublishOutcomeJudge.successEligible(DouyinPublishObservation.PUBLISHED))
        assertEquals(
            setOf("upload_complete", "publish_page_ready", "platform_review_in_progress", "published"),
            DouyinPublishObservation.entries.map { it.wireName }.toSet(),
        )
    }
}
