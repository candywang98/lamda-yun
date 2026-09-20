package com.company.cloudctl.companion.features.xhs.publish

/**
 * F14 任务卡 §1：小红书发布流程的草稿策略。
 *
 * 规则（可解释，不允许静默）：
 * - 弹出「保存草稿 / 放弃」对话框时，动作必须由显式策略决定；
 * - 默认策略 [WAITING_USER]：暂停等人，绝不自动选择；
 * - [DISCARD_DRAFT] 只允许丢弃「本次运行创建、身份匹配」的草稿；
 *   未知旧草稿（身份未知 / 不是本次创建）一律不自动删除 → 升级为 WAITING_USER。
 */
enum class XhsDraftPolicy(val wireName: String) {
    SAVE_DRAFT("SAVE_DRAFT"),
    DISCARD_DRAFT("DISCARD_DRAFT"),
    WAITING_USER("WAITING_USER"),
}

/** 草稿对话框的可执行动作。 */
enum class XhsDraftAction { TAP_SAVE_DRAFT, TAP_DISCARD, PAUSE_WAITING_USER }

/** 草稿决策：动作 + 可解释原因（事件对账用）。 */
data class XhsDraftDecision(
    val action: XhsDraftAction,
    val reason: String,
    val escalatedToWaitingUser: Boolean = false,
)

object XhsDraftPolicyEngine {

    /**
     * @param policy 用户显式策略（默认 WAITING_USER，由 planner 保证）。
     * @param dialogShown 是否出现草稿对话框。
     * @param draftIdentity 草稿身份（标题/首图摘要等）；null = 身份未知。
     * @param createdThisRun 该草稿是否由本次运行创建。
     */
    fun decide(
        policy: XhsDraftPolicy,
        dialogShown: Boolean,
        draftIdentity: String?,
        createdThisRun: Boolean,
    ): XhsDraftDecision {
        if (!dialogShown) {
            return XhsDraftDecision(XhsDraftAction.PAUSE_WAITING_USER, "no-draft-dialog")
        }
        return when (policy) {
            XhsDraftPolicy.WAITING_USER -> XhsDraftDecision(
                XhsDraftAction.PAUSE_WAITING_USER,
                "policy=WAITING_USER：草稿对话框交由用户处理",
            )
            XhsDraftPolicy.SAVE_DRAFT -> XhsDraftDecision(
                XhsDraftAction.TAP_SAVE_DRAFT,
                "policy=SAVE_DRAFT：保存草稿后继续",
            )
            XhsDraftPolicy.DISCARD_DRAFT -> {
                if (createdThisRun && draftIdentity != null) {
                    XhsDraftDecision(
                        XhsDraftAction.TAP_DISCARD,
                        "policy=DISCARD_DRAFT：草稿身份匹配本次运行（identity=$draftIdentity）",
                    )
                } else {
                    XhsDraftDecision(
                        XhsDraftAction.PAUSE_WAITING_USER,
                        "未知旧草稿不自动删除（identityKnown=${draftIdentity != null}, " +
                            "createdThisRun=$createdThisRun），已升级 WAITING_USER",
                        escalatedToWaitingUser = true,
                    )
                }
            }
        }
    }
}
