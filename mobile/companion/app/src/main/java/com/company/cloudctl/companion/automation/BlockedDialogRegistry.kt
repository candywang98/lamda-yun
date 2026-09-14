package com.company.cloudctl.companion.automation

/** Navigation recovery policy, deliberately separate from task-action locators. */
internal object BlockedDialogRegistry {
    data class Rule(val title: String, val safeButton: String, val otherButton: String)
    data class Node(
        val text: String?,
        val description: String? = null,
        val visible: Boolean = true,
        val enabled: Boolean = true,
        val clickable: Boolean = false,
    ) {
        fun matches(label: String): Boolean = visible && (text == label || description == label)
    }
    data class Match(val nodeIndex: Int, val label: String)

    // XHS 8.50.1 cold-start recovery: retain the draft, never resume or discard it.
    private val xhs = listOf(Rule(
        title = "\u7ee7\u7eed\u7f16\u8f91\u56fe\u6587\u7b14\u8bb0\u5417\uff1f",
        safeButton = "\u5b58\u8349\u7a3f",
        otherButton = "\u53bb\u7f16\u8f91",
    ))

    // Xianyu publish-editor exit (contract xianyu-maintenance-anchors-20260915,
    // 2026-09-15): dialog title 「确定要退出发布吗？」 with 「我再想想」 and
    // 「确定退出」. Navigation reset only ever confirms the exit — leaving the
    // editor so a maintenance flow can start from a root page — and only under
    // the same triple co-occurrence rule as XHS.
    private val xianyu = listOf(Rule(
        title = "\u786e\u5b9a\u8981\u9000\u51fa\u53d1\u5e03\u5417\uff1f",
        safeButton = "\u786e\u5b9a\u9000\u51fa",
        otherButton = "\u6211\u518d\u60f3\u60f3",
    ))

    fun rules(targetPackage: String): List<Rule> = when (targetPackage) {
        TargetLocatorRegistry.XHS_PACKAGE -> xhs
        TargetLocatorRegistry.XIANYU_PACKAGE -> xianyu
        // No verified Douyin camera/draft dialog policy yet. Unknown apps fail closed.
        else -> emptyList()
    }

    /** Nodes must come from one active window belonging to targetPackage. */
    fun match(targetPackage: String, nodes: List<Node>): Match? = rules(targetPackage).mapNotNull { rule ->
        fun unique(label: String): Int? = nodes.indices.filter { nodes[it].matches(label) }.singleOrNull()
        val title = unique(rule.title) ?: return@mapNotNull null
        val safe = unique(rule.safeButton) ?: return@mapNotNull null
        val other = unique(rule.otherButton) ?: return@mapNotNull null
        if (setOf(title, safe, other).size != 3) return@mapNotNull null
        if (!nodes[safe].enabled || !nodes[safe].clickable || !nodes[other].clickable) return@mapNotNull null
        Match(safe, rule.safeButton)
    }.singleOrNull()
}
