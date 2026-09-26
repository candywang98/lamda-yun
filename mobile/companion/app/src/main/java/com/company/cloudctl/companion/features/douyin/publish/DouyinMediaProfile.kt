package com.company.cloudctl.companion.features.douyin.publish

import java.util.Locale

/**
 * F15 media sampling contract for the currently verified Douyin device/app pair.
 *
 * The values are an input-validation profile, not a claim that the platform has
 * accepted a file. Re-sampling a device may update the profile without changing
 * the planner's fail-closed behavior.
 */

data class DouyinVideoAsset(
    val fileId: String,
    val durationSeconds: Int,
    val format: String,
    /** Gallery cell selected by the device-side media picker sample. */
    val galleryCellIndex: Int = 0,
)

/**
 * Conservative media limits sampled from Douyin 39.6.0 on the OnePlus 9R.
 *
 * The planner preserves the supplied asset identity and never silently transcodes,
 * selects another asset, or truncates text.
 */
data class DouyinMediaProfile(
    val minDurationSeconds: Int = 3,
    val maxDurationSeconds: Int = 600,
    val allowedFormats: Set<String> = setOf("mp4", "mov"),
    val titleMaxLength: Int = 55,
    val descriptionMaxLength: Int = 1_000,
    val galleryCellCount: Int = 50,
) {
    init {
        require(minDurationSeconds in 1..maxDurationSeconds) {
            "minDurationSeconds must be within 1..maxDurationSeconds"
        }
        require(allowedFormats.isNotEmpty() && allowedFormats.all { it.isNotBlank() }) {
            "allowedFormats must contain at least one non-blank format"
        }
        require(titleMaxLength in 1..512) { "titleMaxLength out of sampled range" }
        require(descriptionMaxLength in 0..4_000) { "descriptionMaxLength out of sampled range" }
        require(galleryCellCount in 1..50) { "galleryCellCount must be within 1..50" }
    }

    val normalizedFormats: Set<String>
        get() = allowedFormats.map { it.trim().lowercase(Locale.ROOT) }.toSet()
}
