package com.company.cloudctl.companion.features.xhs.publish

/**
 * F14 任务卡：小红书图文笔记发布的步骤原语（图文 V1）。
 *
 * 复用既有定位（TargetLocatorRegistry，com.xingin.xhs 8.50.1 实测）与
 * B14/B15 证明语义：文本输入必须回读一致（B14），选图必须顺序回读一致（B15）。
 * 视频不在本版范围：[XhsMediaSupport] 给出显式待定状态，不是漏项。
 */
sealed interface XhsNoteStep {
    val id: String

    /** 首页 settle：发布入口可见且稳定后继续。 */
    data class AwaitHomeSettle(val entryLocator: String = "xhs_home_publish") : XhsNoteStep {
        override val id: String get() = "xhs-home-settle"
    }

    /** 打开发布面板并进入相册选图。 */
    data class OpenPublishSheet(val sheetLocator: String = "xhs_publish_sheet") : XhsNoteStep {
        override val id: String get() = "xhs-open-publish-sheet"
    }

    /** B15 选图证明：按 mediaAssetIds 顺序选择且回读顺序一致。 */
    data class SelectImagesInOrder(val expectedOrder: List<String>) : XhsNoteStep {
        override val id: String get() = "xhs-select-images-in-order"
    }

    /** 相册→编辑→编辑页返回续行（B13 语义：页面回来才继续）。 */
    data class AwaitEditorPage(val pageLocator: String = "xhs_edit_page", val timeoutMs: Long = 8_000) : XhsNoteStep {
        override val id: String get() = "xhs-await-editor-page"
    }

    /** B14 输入证明：标题/正文回读一致。 */
    data class ProveNoteInput(val noteField: NoteField, val expected: String) : XhsNoteStep {
        override val id: String get() = "xhs-prove-input-${noteField.wireName}"

        enum class NoteField(val wireName: String) { TITLE("title"), BODY("body") }
    }

    /** 草稿对话框检查点：按 [XhsDraftPolicyEngine] 的决策执行。 */
    data class DraftDialogCheckpoint(val policy: XhsDraftPolicy) : XhsNoteStep {
        override val id: String get() = "xhs-draft-dialog-checkpoint"
    }

    /** 发布前必填检查：标题在场 + 至少一张图。 */
    class VerifyBeforePublish : XhsNoteStep {
        override val id: String get() = "xhs-verify-before-publish"
    }

    /** 最终发布人工检查点（副作用台账门，open-only 语义同闲鱼线）。 */
    class HumanCheckpoint : XhsNoteStep {
        override val id: String get() = "xhs-final-commit-checkpoint"
    }

    /** 发布成功观察（成功页/笔记页回读）。 */
    data class AwaitNotePublishSuccess(val successLocator: String = "xhs_publish_success") : XhsNoteStep {
        override val id: String get() = "xhs-await-publish-success"
    }
}

/** 图文 V1 的媒体口径：视频显式待定（R00 裁决前不实现、不静默丢弃请求）。 */
object XhsMediaSupport {
    const val VIDEO_STATUS = "VIDEO_PENDING_R00"
    const val VIDEO_REASON = "小红书视频笔记未获批范围（R00 裁决待定），本版仅图文"

    /** 图文上限与 F10 预检口径一致（xiaohongshu = 18）。 */
    const val MAX_IMAGES = 18
}
