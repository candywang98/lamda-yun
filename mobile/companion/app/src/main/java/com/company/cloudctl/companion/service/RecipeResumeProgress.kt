package com.company.cloudctl.companion.service

import com.company.cloudctl.companion.automation.CommandV1
import com.company.cloudctl.companion.automation.ExecutorFailure
import com.company.cloudctl.companion.automation.RecipePackage
import org.json.JSONObject

internal data class RecipeCheckpointSnapshot(
    val nextStateId: String,
    val lastSuccessfulStateId: String?,
    val lastSuccessfulStateIndex: Int,
)

internal class RecipeResumeProgress private constructor(
    nextStateId: String,
    lastSuccessfulStateId: String?,
) {
    var nextStateId: String? = nextStateId
        private set
    var lastSuccessfulStateId: String? = lastSuccessfulStateId
        private set

    fun record(recipe: RecipePackage, stateId: String, state: String): String {
        val recipeState = recipe.states[stateId]
            ?: throw ExecutorFailure("UNKNOWN_STATE", stateId)
        return when (state) {
            "STARTED" -> {
                nextStateId = stateId
                "STEP_STARTED"
            }
            "SUCCEEDED" -> {
                lastSuccessfulStateId = stateId
                nextStateId = recipeState.onSuccess.takeUnless { recipeState.terminal || it in TERMINAL_STATES }
                "STEP_SUCCEEDED"
            }
            "FAILED" -> {
                nextStateId = recipeState.onFailure?.takeUnless { it in TERMINAL_STATES }
                "STEP_FAILED"
            }
            "WAITING_USER" -> {
                nextStateId = stateId
                "PAUSED_WAITING_USER"
            }
            else -> throw ExecutorFailure("UNKNOWN_STEP_STATE", state)
        }
    }

    fun checkpoint(recipe: RecipePackage): RecipeCheckpointSnapshot {
        val next = nextStateId
            ?: throw ExecutorFailure("RESUME_NO_PENDING_STATE", "recipe has no unexecuted state")
        return RecipeCheckpointSnapshot(
            nextStateId = next,
            lastSuccessfulStateId = lastSuccessfulStateId,
            lastSuccessfulStateIndex = lastSuccessfulStateId?.let { recipe.states.keys.indexOf(it) } ?: -1,
        )
    }

    companion object {
        private val TERMINAL_STATES = setOf("SUCCEEDED", "FAILED", "WAITING_USER")

        fun fresh(recipe: RecipePackage): RecipeResumeProgress =
            RecipeResumeProgress(recipe.startStateId, null)

        fun resume(
            recipe: RecipePackage,
            command: CommandV1,
            checkpoint: JSONObject,
        ): RecipeResumeProgress {
            val checkpointAccount = checkpoint.optString("accountId")
            val checkpointBinding = checkpoint.optInt("bindingVersion", 0)
            val checkpointRecipe = checkpoint.optString("recipeHash")
            val resumeFromStateId = checkpoint.optString("stateId")
            if (
                command.accountId.isBlank() || command.bindingVersion <= 0 || command.recipeSha256.isBlank() ||
                checkpointAccount.isBlank() || checkpointBinding <= 0 || checkpointRecipe.isBlank() ||
                resumeFromStateId.isBlank()
            ) {
                throw ExecutorFailure("RESUME_IDENTITY_MISSING", "resume checkpoint identity is incomplete")
            }
            if (checkpointAccount != command.accountId) {
                throw ExecutorFailure("RESUME_ACCOUNT_CHANGED", "account changed; original task cannot continue")
            }
            if (checkpointBinding != command.bindingVersion) {
                throw ExecutorFailure("RESUME_BINDING_CHANGED", "binding changed; original task cannot continue")
            }
            if (checkpointRecipe != command.recipeSha256 || checkpointRecipe != recipe.hash) {
                throw ExecutorFailure("RESUME_RECIPE_INCOMPATIBLE", "recipe is incompatible with the checkpoint")
            }
            if (resumeFromStateId !in recipe.states) {
                throw ExecutorFailure("RESUME_UNKNOWN_STATE", "resumeFromStateId is not in the signed recipe")
            }
            val lastSuccessful = checkpoint.optString("itemId").takeIf { it.isNotBlank() }
            if (lastSuccessful != null && lastSuccessful !in recipe.states) {
                throw ExecutorFailure("RESUME_LAST_SUCCESS_UNKNOWN", "last successful state is not in the signed recipe")
            }
            return RecipeResumeProgress(resumeFromStateId, lastSuccessful)
        }
    }
}
