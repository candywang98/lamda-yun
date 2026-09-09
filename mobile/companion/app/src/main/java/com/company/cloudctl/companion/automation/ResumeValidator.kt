package com.company.cloudctl.companion.automation

import org.json.JSONObject

object ResumeValidator {
    fun expectedLocator(task: AutomationTask, lastCompletedIndex: Int): String? {
        if (lastCompletedIndex < 0) return locatorOf(task.steps.firstOrNull())
        val completed = task.steps.getOrNull(lastCompletedIndex) ?: return locatorOf(task.steps.firstOrNull())
        return when (completed) {
            is AutomationStep.Tap -> completed.postconditionLocatorRef ?: completed.locatorRef
            is AutomationStep.Wait -> completed.locatorRef
            is AutomationStep.Find -> completed.locatorRef
            is AutomationStep.Input -> completed.locatorRef
            is AutomationStep.Assert -> completed.locatorRef
            else -> locatorOf(task.steps.getOrNull(lastCompletedIndex + 1))
        }
    }

    fun guard(
        ui: LocalAutomationUi,
        task: AutomationTask,
        checkpoint: JSONObject,
        payload: JSONObject,
        pageVerified: Boolean,
    ) {
        requirePageVerified(pageVerified)
        requireIdentity(checkpoint, payload)
        ui.ensureReady(task.targetPackage)
        if (task.steps.isEmpty()) return
        val lastCompletedIndex = checkpoint.optInt("loopCursor", -1)
        val locator = expectedLocator(task, lastCompletedIndex) ?: return
        inspectVisible(ui, task.targetPackage, locator)
    }

    fun guard(
        ui: LocalAutomationUi,
        task: AutomationTask,
        checkpoint: JSONObject,
        payload: JSONObject,
        pageVerified: Boolean,
        recipe: RecipePackage,
        resumeFromStateId: String,
    ) {
        requirePageVerified(pageVerified)
        requireIdentity(checkpoint, payload)
        requireRecipeIdentity(recipe, checkpoint, payload)
        if (task.targetPackage != recipe.app) {
            throw ExecutorFailure("RESUME_TARGET_MISMATCH", "command target does not match recipe app")
        }
        val state = recipe.states[resumeFromStateId]
            ?: throw ExecutorFailure("RESUME_UNKNOWN_STATE", "resumeFromStateId is not in the signed recipe")
        val locator = state.locatorRef?.takeIf { it.isNotBlank() }
            ?: throw ExecutorFailure("RESUME_LOCATOR_UNCHECKABLE", "resume state has no inspectable locator")
        ui.ensureReady(task.targetPackage)
        inspectVisible(ui, task.targetPackage, locator)
    }

    private fun requirePageVerified(pageVerified: Boolean) {
        if (!pageVerified) {
            throw ExecutorFailure("RESUME_PAGE_UNVERIFIED", "resumeGuard requires pageVerified=true")
        }
    }

    private fun requireIdentity(checkpoint: JSONObject, payload: JSONObject) {
        val expectedAccount = ClaimedTaskInterpreter.accountId(payload)
        val checkpointAccount = checkpoint.optString("accountId")
        if (expectedAccount.isNotBlank() && checkpointAccount.isNotBlank() && expectedAccount != checkpointAccount) {
            throw ExecutorFailure("RESUME_ACCOUNT_CHANGED", "account changed; original task cannot continue")
        }
        val expectedBinding = ClaimedTaskInterpreter.bindingVersion(payload)
        val checkpointBinding = checkpoint.optInt("bindingVersion", 0)
        if (expectedBinding > 0 && checkpointBinding > 0 && expectedBinding != checkpointBinding) {
            throw ExecutorFailure("RESUME_BINDING_CHANGED", "binding changed; original task cannot continue")
        }
        val expectedRecipe = ClaimedTaskInterpreter.recipeHash(payload)
        val checkpointRecipe = checkpoint.optString("recipeHash")
        if (expectedRecipe.isNotBlank() && checkpointRecipe.isNotBlank() && expectedRecipe != checkpointRecipe) {
            throw ExecutorFailure("RESUME_RECIPE_INCOMPATIBLE", "recipe is incompatible with the checkpoint")
        }
    }

    private fun requireRecipeIdentity(
        recipe: RecipePackage,
        checkpoint: JSONObject,
        payload: JSONObject,
    ) {
        val expectedRecipe = ClaimedTaskInterpreter.recipeHash(payload)
        val checkpointRecipe = checkpoint.optString("recipeHash")
        if (expectedRecipe.isNotBlank() && expectedRecipe != recipe.hash) {
            throw ExecutorFailure("RESUME_RECIPE_INCOMPATIBLE", "recipe is incompatible with the checkpoint")
        }
        if (checkpointRecipe.isNotBlank() && checkpointRecipe != recipe.hash) {
            throw ExecutorFailure("RESUME_RECIPE_INCOMPATIBLE", "recipe is incompatible with the checkpoint")
        }
    }

    private fun inspectVisible(ui: LocalAutomationUi, targetPackage: String, locator: String) {
        val node = ui.inspect(targetPackage, locator)
        if (node == null || !node.visible) {
            throw ExecutorFailure("RESUME_PAGE_MISMATCH", "current page does not match the checkpoint")
        }
    }

    private fun locatorOf(step: AutomationStep?): String? = when (step) {
        is AutomationStep.Find -> step.locatorRef
        is AutomationStep.Tap -> step.locatorRef
        is AutomationStep.Input -> step.locatorRef
        is AutomationStep.Wait -> step.locatorRef
        is AutomationStep.Assert -> step.locatorRef
        else -> null
    }
}
