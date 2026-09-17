package com.company.cloudctl.companion.automation.recipes

import org.json.JSONObject

/**
 * B16 restricted declarative page/action template (cloudctl.recipe-template/v1).
 *
 * A template describes WHAT should happen (pages, actions, budgets) — never
 * HOW to execute code: there is no eval, shell, JS or expression anywhere in
 * the DSL, and the compiler rejects unknown fields outright. Business submit
 * steps are not expressible at all (open-only red line): a template may walk
 * up to the WAITING_USER checkpoint; the irreversible submit stays a signed,
 * ledger-guarded recipe concern.
 */
data class RecipeTemplate(
    val templateId: String,
    val recipeId: String,
    val version: String,
    val platform: String,
    val app: String,
    val commandTypes: List<String>,
    val minEngineVersion: Int,
    val pages: List<TemplatePage>,
    val steps: List<TemplateStep>,
) {
    data class TemplatePage(val pageId: String, val anchors: List<String>)

    data class TemplateStep(
        val stepId: String,
        val action: String,
        val page: String?,
        val locatorRef: String?,
        val postcondition: String?,
        val valueRef: String?,
        val bounds: Bounds,
    ) {
        data class Bounds(
            val maxAttempts: Int? = null,
            val noProgressBudget: Int? = null,
            val deadlineMs: Long? = null,
            val onExhausted: String? = null,
        )
    }

    companion object {
        fun parse(encoded: String): RecipeTemplate {
            val root = JSONObject(encoded)
            require(root.getString("protocol") == RecipeContract.TEMPLATE_PROTOCOL) {
                "template protocol must be ${RecipeContract.TEMPLATE_PROTOCOL}"
            }
            require(root.getString("templateId").matches(RecipeContract.STATE_ID_PATTERN)) { "templateId is invalid" }
            val forbidden = RecipeStaticValidator.validate(
                encoded,
                strictSignature = false,
            ).filter { it.code == "FORBIDDEN_FIELD" }
            require(forbidden.isEmpty()) { forbidden.joinToString("; ") }
            val knownRoot = setOf(
                "protocol", "templateId", "recipeId", "version", "platform", "app",
                "commandTypes", "minEngineVersion", "pages", "steps",
            )
            require(root.keys().asSequence().toSet() == knownRoot) { "unknown template field" }
            val pagesJson = root.getJSONArray("pages")
            require(pagesJson.length() in 1..RecipeContract.MAX_STATES) { "pages count is invalid" }
            val pages = (0 until pagesJson.length()).map { index ->
                val page = pagesJson.getJSONObject(index)
                require(page.keys().asSequence().toSet() == setOf("pageId", "anchors")) { "unknown page field" }
                val pageId = page.getString("pageId")
                require(pageId.matches(RecipeContract.STATE_ID_PATTERN)) { "pageId is invalid" }
                val anchors = page.getJSONArray("anchors")
                require(anchors.length() in 1..8) { "anchors count is invalid" }
                RecipeTemplate.TemplatePage(
                    pageId = pageId,
                    anchors = (0 until anchors.length()).map { anchors.getString(it) },
                )
            }
            require(pages.map { it.pageId }.toSet().size == pages.size) { "pageId must be unique" }
            val stepsJson = root.getJSONArray("steps")
            require(stepsJson.length() in 1..RecipeContract.MAX_STATES) { "steps count is invalid" }
            val steps = (0 until stepsJson.length()).map { index -> parseStep(stepsJson.getJSONObject(index)) }
            require(steps.map { it.stepId }.toSet().size == steps.size) { "stepId must be unique" }
            val pageIds = pages.map { it.pageId }.toSet()
            steps.forEach { step ->
                require(step.page == null || step.page in pageIds) { "step '${step.stepId}' references unknown page" }
            }
            val types = root.getJSONArray("commandTypes")
            require(types.length() in 1..4) { "commandTypes count is invalid" }
            return RecipeTemplate(
                templateId = root.getString("templateId"),
                recipeId = root.getString("recipeId").also { require(it.matches(RecipeContract.STATE_ID_PATTERN)) },
                version = root.getString("version"),
                platform = root.getString("platform"),
                app = root.getString("app"),
                commandTypes = (0 until types.length()).map { types.getString(it) },
                minEngineVersion = root.getInt("minEngineVersion").also { require(it >= 1) },
                pages = pages,
                steps = steps,
            )
        }

        private fun parseStep(item: JSONObject): TemplateStep {
            val common = setOf("stepId", "action")
            val action = item.getString("action")
            require(action in RecipeContract.TEMPLATE_ACTIONS) {
                "template action '$action' is not in the declarative whitelist"
            }
            require(action !in RecipeContract.TEMPLATE_FORBIDDEN_ACTIONS) {
                "template action '$action' is forbidden (submit is a signed-recipe concern)"
            }
            val keys = item.keys().asSequence().toSet()
            val allowed = common + setOf("page", "locatorRef", "postcondition", "valueRef", "bounds")
            require(keys.containsAll(common) && keys.all { it in allowed }) { "unknown step field" }
            val boundsItem = item.optJSONObject("bounds")
            val bounds = if (boundsItem == null) {
                TemplateStep.Bounds()
            } else {
                require(boundsItem.keys().asSequence().all { it in setOf("maxAttempts", "noProgressBudget", "deadlineMs", "onExhausted") }) {
                    "unknown bounds field"
                }
                TemplateStep.Bounds(
                    maxAttempts = boundsItem.optInt("maxAttempts").takeIf { boundsItem.has("maxAttempts") && !boundsItem.isNull("maxAttempts") },
                    noProgressBudget = boundsItem.optInt("noProgressBudget").takeIf { boundsItem.has("noProgressBudget") && !boundsItem.isNull("noProgressBudget") },
                    deadlineMs = boundsItem.optLong("deadlineMs").takeIf { boundsItem.has("deadlineMs") && !boundsItem.isNull("deadlineMs") },
                    onExhausted = boundsItem.optString("onExhausted").takeIf { boundsItem.has("onExhausted") && !boundsItem.isNull("onExhausted") && it.isNotBlank() },
                )
            }
            bounds.maxAttempts?.let { require(it in 1..RecipeContract.MAX_WAIT_ATTEMPTS) { "maxAttempts exceeds cap" } }
            bounds.noProgressBudget?.let {
                require(it in 1..RecipeContract.MAX_NO_PROGRESS_POLLS) { "noProgressBudget exceeds cap" }
                require(bounds.maxAttempts == null || it <= bounds.maxAttempts) { "noProgressBudget must fit inside maxAttempts" }
            }
            bounds.onExhausted?.let { require(it in RecipeContract.ON_EXHAUSTED_VALUES) { "onExhausted is invalid" } }
            val valueRef = item.optString("valueRef").takeIf { item.has("valueRef") && !item.isNull("valueRef") && it.isNotBlank() }
            if (action == "input") {
                require(valueRef != null) { "input step requires valueRef" }
            }
            valueRef?.let { require(RecipeContract.VALUE_REF_PATTERN.matches(it)) { "valueRef is invalid" } }
            if (action in setOf("navigate", "wait", "media")) {
                require(item.optString("locatorRef").isNotBlank()) { "$action step requires locatorRef" }
            }
            return TemplateStep(
                stepId = item.getString("stepId").also { require(it.matches(RecipeContract.STATE_ID_PATTERN)) },
                action = action,
                page = item.optString("page").takeIf { item.has("page") && !item.isNull("page") && it.isNotBlank() },
                locatorRef = item.optString("locatorRef").takeIf { item.has("locatorRef") && !item.isNull("locatorRef") && it.isNotBlank() },
                postcondition = item.optString("postcondition").takeIf { item.has("postcondition") && !item.isNull("postcondition") && it.isNotBlank() },
                valueRef = valueRef,
                bounds = bounds,
            )
        }
    }
}
