package com.company.cloudctl.companion.features.douyin.publish

/**
 * F15 declarative step primitives for the Douyin video flow.
 *
 * These values describe a reviewed, pre-publish plan. They are not an executor
 * and do not send a publish action. The executable pre-publish portion ends at
 * HumanCheckpoint; any later observation descriptor is evidence classification only.
 */
sealed interface DouyinPublishStep {
    /** Stable primitive id used for evidence and replay comparison. */
    val id: String

    data class LaunchApp(
        val targetPackage: String = "com.ss.android.ugc.aweme",
    ) : DouyinPublishStep {
        override val id: String get() = "dy-launch-app"
    }

    data class AwaitHomeSettle(val entryLocator: String = "dy_home_publish") : DouyinPublishStep {
        override val id: String get() = "dy-home-settle"
    }

    data class OpenPublishEntry(val entryLocator: String = "dy_home_publish") : DouyinPublishStep {
        override val id: String get() = "dy-open-publish-entry"
    }

    data class AwaitCameraReady(val readyLocator: String = "dy_camera_ready") : DouyinPublishStep {
        override val id: String get() = "dy-await-camera-ready"
    }

    data class OpenAlbum(val albumLocator: String = "dy_camera_album") : DouyinPublishStep {
        override val id: String get() = "dy-open-album"
    }

    data class OpenMediaTab(val tabLocator: String = "dy_media_images_tab") : DouyinPublishStep {
        override val id: String get() = "dy-open-media-tab"
    }

    /** Select the cellmark container and verify its state; never tap image-center coordinates. */
    data class SelectVideoByCellMark(
        val cellLocator: String,
        val cellMarkProbeLocator: String = "dy_cellmark_probe",
        val expectedFileId: String,
    ) : DouyinPublishStep {
        override val id: String get() = "dy-select-video-cellmark"
    }

    data class ConfirmMediaPick(val nextLocator: String = "dy_pick_next") : DouyinPublishStep {
        override val id: String get() = "dy-confirm-media-pick"
    }

    data class AwaitTrimCropReturn(
        val pageLocator: String = "dy_edit_page",
        val timeoutMs: Long = 8_000,
    ) : DouyinPublishStep {
        override val id: String get() = "dy-await-trim-crop-return"
    }

    data class AdvanceToPublishPage(val nextLocator: String = "dy_edit_next") : DouyinPublishStep {
        override val id: String get() = "dy-advance-to-publish-page"
    }

    /** Cover identity is carried forward; the sampled cover locator is not yet verified. */
    data class SelectCover(val coverAssetId: String) : DouyinPublishStep {
        override val id: String get() = "dy-select-cover"
    }

    data class ProveTitleInput(
        val titleLocator: String = "dy_note_title",
        val expected: String,
    ) : DouyinPublishStep {
        override val id: String get() = "dy-prove-title-input"
    }

    data class ProveDescriptionInput(
        val bodyLocator: String = "dy_note_body",
        val expected: String,
    ) : DouyinPublishStep {
        override val id: String get() = "dy-prove-description-input"
    }

    data class VerifyBeforePublish(
        val publishButtonLocator: String = "dy_publish_button",
        val expectedCoverAssetId: String,
    ) : DouyinPublishStep {
        override val id: String get() = "dy-verify-before-publish"
    }

    /** Open-only boundary: no publish tap is represented by this plan. */
    data class HumanCheckpoint(
        val reasonCode: String = "WAITING_USER_BEFORE_PUBLISH",
    ) : DouyinPublishStep {
        override val id: String get() = "dy-final-commit-checkpoint"
    }

    /** Post-commit observation vocabulary; it never authorizes a second commit. */
    data class AwaitPublishSuccess(val successLocator: String = "dy_publish_success") : DouyinPublishStep {
        override val id: String get() = "dy-await-publish-success"
    }
}

/** Explicit observation states prevent upload/page readiness from being called success. */
enum class DouyinPublishObservation(val wireName: String) {
    UPLOAD_COMPLETE("upload_complete"),
    PUBLISH_PAGE_READY("publish_page_ready"),
    PLATFORM_REVIEW_IN_PROGRESS("platform_review_in_progress"),
    PUBLISHED("published"),
}

object DouyinPublishOutcomeJudge {
    fun successEligible(observation: DouyinPublishObservation?): Boolean =
        observation == DouyinPublishObservation.PUBLISHED
}
