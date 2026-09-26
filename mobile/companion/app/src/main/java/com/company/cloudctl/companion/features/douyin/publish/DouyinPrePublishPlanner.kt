package com.company.cloudctl.companion.features.douyin.publish

/**
 * F15's 14-step declarative pre-publish chain.
 *
 * Validation is deliberately complete before any plan is returned. This class
 * does not connect to Douyin or execute a step; it only freezes an auditable
 * plan that ends at the manual publish checkpoint.
 */
object DouyinPrePublishPlanner {
    const val PRE_PUBLISH_STEP_COUNT = 14

    sealed interface PlanResult {
        data class Plan(
            val steps: List<DouyinPublishStep>,
            val videoAsset: DouyinVideoAsset,
            val coverAssetId: String,
            val title: String,
        ) : PlanResult {
            val prePublishChain: List<DouyinPublishStep>
                get() = steps.take(PRE_PUBLISH_STEP_COUNT)
        }

        data class Rejected(val reason: String) : PlanResult
    }

    fun plan(
        videoAssets: List<DouyinVideoAsset>,
        coverAssetId: String,
        title: String,
        description: String = "",
        profile: DouyinMediaProfile = DouyinMediaProfile(),
    ): PlanResult {
        if (videoAssets.isEmpty()) {
            return PlanResult.Rejected("视频发布至少需要 1 个视频资产（videoAssets 为空）")
        }
        if (videoAssets.size > 1) {
            val ids = videoAssets.joinToString(",") { it.fileId.ifBlank { "<空>" } }
            return PlanResult.Rejected(
                "V1 单视频：收到 ${videoAssets.size} 个视频资产（$ids），" +
                    "多视频拼接不在 F15 范围，显式拒绝而非静默取首个",
            )
        }

        val video = videoAssets.single()
        if (video.fileId.isBlank()) {
            return PlanResult.Rejected("视频 fileId 为空，身份不可证")
        }
        if (video.durationSeconds !in profile.minDurationSeconds..profile.maxDurationSeconds) {
            return PlanResult.Rejected(
                "视频时长 ${video.durationSeconds}s 超出采样区间 " +
                    "[${profile.minDurationSeconds}s, ${profile.maxDurationSeconds}s]（fileId=${video.fileId}）",
            )
        }
        val format = video.format.trim().lowercase(java.util.Locale.ROOT)
        if (format !in profile.normalizedFormats) {
            return PlanResult.Rejected(
                "视频格式 '$format' 不在白名单 ${profile.normalizedFormats.sorted()}（fileId=${video.fileId}），" +
                    "显式拒绝而非静默转码",
            )
        }
        if (video.galleryCellIndex !in 0 until profile.galleryCellCount) {
            return PlanResult.Rejected(
                "图库 cell 索引 ${video.galleryCellIndex} 超出采样范围 " +
                    "[0, ${profile.galleryCellCount - 1}]（fileId=${video.fileId}）",
            )
        }
        if (coverAssetId.isBlank()) {
            return PlanResult.Rejected("封面必填（coverAssetId 为空）")
        }
        if (title.isBlank()) {
            return PlanResult.Rejected("title 不能为空")
        }
        if (title.length > profile.titleMaxLength) {
            return PlanResult.Rejected("title 长度 ${title.length} 超过上限 ${profile.titleMaxLength}")
        }
        if (description.length > profile.descriptionMaxLength) {
            return PlanResult.Rejected(
                "description 长度 ${description.length} 超过上限 ${profile.descriptionMaxLength}",
            )
        }

        val steps = listOf(
            DouyinPublishStep.LaunchApp(),
            DouyinPublishStep.AwaitHomeSettle(),
            DouyinPublishStep.OpenPublishEntry(),
            DouyinPublishStep.AwaitCameraReady(),
            DouyinPublishStep.OpenAlbum(),
            DouyinPublishStep.OpenMediaTab(),
            DouyinPublishStep.SelectVideoByCellMark(
                cellLocator = "dy_gallery_cell_${video.galleryCellIndex}",
                expectedFileId = video.fileId,
            ),
            DouyinPublishStep.ConfirmMediaPick(),
            DouyinPublishStep.AwaitTrimCropReturn(),
            DouyinPublishStep.AdvanceToPublishPage(),
            DouyinPublishStep.SelectCover(coverAssetId),
            DouyinPublishStep.ProveTitleInput(expected = title),
            DouyinPublishStep.ProveDescriptionInput(expected = description),
            DouyinPublishStep.VerifyBeforePublish(expectedCoverAssetId = coverAssetId),
            DouyinPublishStep.HumanCheckpoint(),
            DouyinPublishStep.AwaitPublishSuccess(),
        )
        return PlanResult.Plan(steps, video, coverAssetId, title)
    }
}
