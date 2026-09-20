package com.company.cloudctl.companion.features.xhs.publish

/**
 * F14：图文笔记发布计划器。
 *
 * 输入为后端 XiaohongshuPublishNoteParams 的对应面（title/body/tags/
 * mediaAssetIds/draftPolicy）。产出有序步骤；校验失败给出可解释拒绝，
 * 不产出半截计划。mediaAssetIds 的顺序即选图顺序契约：原样冻结、不重排。
 */
object XhsNotePublishPlanner {

    sealed interface PlanResult {
        data class Plan(
            val steps: List<XhsNoteStep>,
            val draftPolicy: XhsDraftPolicy,
            val imageOrder: List<String>,
        ) : PlanResult

        data class Rejected(val reason: String) : PlanResult
    }

    fun plan(
        title: String,
        body: String,
        mediaAssetIds: List<String>,
        draftPolicy: XhsDraftPolicy = XhsDraftPolicy.WAITING_USER,
        videoAssetIds: List<String> = emptyList(),
    ): PlanResult {
        if (videoAssetIds.isNotEmpty()) {
            return PlanResult.Rejected(
                "${XhsMediaSupport.VIDEO_STATUS}: ${XhsMediaSupport.VIDEO_REASON} " +
                    "（本次请求带 ${videoAssetIds.size} 个视频资产，显式拒绝而非静默丢弃）",
            )
        }
        if (title.isBlank()) return PlanResult.Rejected("title 不能为空")
        if (body.isBlank()) return PlanResult.Rejected("body 不能为空")
        if (title.length > 64) return PlanResult.Rejected("title 超过 64 字上限")
        if (mediaAssetIds.isEmpty()) {
            return PlanResult.Rejected("图文 V1 至少需要 1 张图（mediaAssetIds 为空）")
        }
        if (mediaAssetIds.size > XhsMediaSupport.MAX_IMAGES) {
            return PlanResult.Rejected("图片数 ${mediaAssetIds.size} 超过上限 ${XhsMediaSupport.MAX_IMAGES}")
        }
        if (mediaAssetIds.toSet().size != mediaAssetIds.size) {
            return PlanResult.Rejected("mediaAssetIds 存在重复，选图顺序契约要求唯一")
        }
        val steps = listOf(
            XhsNoteStep.AwaitHomeSettle(),
            XhsNoteStep.OpenPublishSheet(),
            XhsNoteStep.SelectImagesInOrder(mediaAssetIds.toList()),
            XhsNoteStep.AwaitEditorPage(),
            XhsNoteStep.ProveNoteInput(XhsNoteStep.ProveNoteInput.NoteField.TITLE, title),
            XhsNoteStep.ProveNoteInput(XhsNoteStep.ProveNoteInput.NoteField.BODY, body),
            XhsNoteStep.DraftDialogCheckpoint(draftPolicy),
            XhsNoteStep.VerifyBeforePublish(),
            XhsNoteStep.HumanCheckpoint(),
            XhsNoteStep.AwaitNotePublishSuccess(),
        )
        return PlanResult.Plan(steps, draftPolicy, mediaAssetIds.toList())
    }
}
