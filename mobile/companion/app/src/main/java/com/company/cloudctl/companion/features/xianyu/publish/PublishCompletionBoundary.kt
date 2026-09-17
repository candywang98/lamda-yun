package com.company.cloudctl.companion.features.xianyu.publish

/**
 * P10 任务卡 §1：闲鱼普通商品发布的四种完成边界（completion boundary）。
 *
 * 边界由两个「人工动作位」唯一确定：价格是否人工填、最终发布点击是否人工点。
 * 低完成度（人工位更多）绝不允许记成高完成度（全自动）成功——这是单调降级规则，
 * 由 [envelope] 编码：两个边界的并集永远取更保守（人工位更多）的一侧。
 *
 * 语义对齐（fleet-first-20260916.1 P10）：
 * - [FULL_AUTO]                    全自动：价格机器填 + 发布机器点。
 * - [AUTO_FILL_HUMAN_PRICE]        自动填写 + 人工价格（现生产行为：表单/媒体机器填，
 *                                  价格在确认点人工填）。
 * - [AUTO_FILL_HUMAN_COMMIT]       自动填写 + 人工最终点击（价格机器填并回读验证，
 *                                  发布按钮人工点）。
 * - [HUMAN_PRICE_HUMAN_COMMIT]     人工价格 + 人工点击。
 */
enum class PublishCompletionBoundary(
    val wireName: String,
    /** 价格是否由人工填写。 */
    val humanPrice: Boolean,
    /** 最终发布点击是否由人工完成。 */
    val humanCommit: Boolean,
) {
    FULL_AUTO("FULL_AUTO", humanPrice = false, humanCommit = false),
    AUTO_FILL_HUMAN_PRICE("AUTO_FILL_HUMAN_PRICE", humanPrice = true, humanCommit = false),
    AUTO_FILL_HUMAN_COMMIT("AUTO_FILL_HUMAN_COMMIT", humanPrice = false, humanCommit = true),
    HUMAN_PRICE_HUMAN_COMMIT("HUMAN_PRICE_HUMAN_COMMIT", humanPrice = true, humanCommit = true),
    ;

    companion object {
        /** 服务端/配方里出现的边界名。未知名字 → null（fail-closed，按最保守处理）。 */
        fun fromWireName(name: String): PublishCompletionBoundary? =
            entries.firstOrNull { it.wireName == name }

        /** 按两个人工位组合出唯一边界。 */
        fun fromFlags(humanPrice: Boolean, humanCommit: Boolean): PublishCompletionBoundary =
            entries.first { it.humanPrice == humanPrice && it.humanCommit == humanCommit }

        /**
         * 降级格：两个边界的保守包络（人工位按位或）。判定规则的核心——
         * 声称 FULL_AUTO 但证据出现任何人工位，结果只会往人工更多的边界移动，
         * 永远不会反向「升级」。恒等元：envelope(x, x) == x；交换律成立。
         */
        fun envelope(a: PublishCompletionBoundary, b: PublishCompletionBoundary): PublishCompletionBoundary =
            fromFlags(a.humanPrice || b.humanPrice, a.humanCommit || b.humanCommit)
    }
}

/**
 * 一次发布运行的证据快照（任务卡 §1：每种边界对应不同 success 判据与证据要求）。
 *
 * @param descriptionProof 表单描述输入证明（B14：回读一致 + 提交授权，剪贴板不算）。
 * @param priceEnteredByMachine 价格是否机器填写且回读验证通过。
 * @param priceHumanConfirmed 人工在确认点填价并被检查点确认。
 * @param commitClickedByMachine 发布按钮是否机器点击（受控动作有台账）。
 * @param commitHumanConfirmed 人工完成最终点击并被检查点确认。
 * @param successObserved 发布成功页/在卖状态被观察到（机器定位或人工确认）。
 * @param mediaComplete 媒体齐全（规划张数 == 已回传张数，裁剪返回续行成功）。
 * @param requiredFieldsComplete 价格/库存/交付方式必填检查全部通过。
 */
data class PublishRunEvidence(
    val descriptionProof: Boolean = false,
    val priceEnteredByMachine: Boolean = false,
    val priceHumanConfirmed: Boolean = false,
    val commitClickedByMachine: Boolean = false,
    val commitHumanConfirmed: Boolean = false,
    val successObserved: Boolean = false,
    val mediaComplete: Boolean = false,
    val requiredFieldsComplete: Boolean = false,
)

/**
 * 边界判定结果：声称边界、证据推出的事实边界、最终记录边界（包络 = 只降不升），
 * 以及按记录边界要求的证据缺口（用于「完成度降级要写明原因」）。
 */
data class PublishBoundaryJudgment(
    val claimed: PublishCompletionBoundary,
    val evidenceBoundary: PublishCompletionBoundary,
    val recorded: PublishCompletionBoundary,
    val missingEvidence: Set<String>,
    val successEligible: Boolean,
) {
    /** 记录边界比声称的更保守 = 发生了完成度降级（禁止静默记成声称的更高级）。 */
    val downgraded: Boolean get() = recorded != claimed
}

/**
 * 纯判定器：证据 → 事实边界 + 成功资格。设备端/服务端共用同一套语义
 * （Kotlin 与 services/control-api/src/cloudctl_api/xianyu_publish.py 保持同构）。
 */
object PublishBoundaryJudge {

    /** 证据里出现的人工位。缺证据（既无机器证明也无人工确认）按人工处理——保守侧。 */
    fun evidenceBoundary(evidence: PublishRunEvidence): PublishCompletionBoundary =
        PublishCompletionBoundary.fromFlags(
            humanPrice = !evidence.priceEnteredByMachine,
            humanCommit = !evidence.commitClickedByMachine,
        )

    /** 各边界把运行记为「发布成功」所需的机器证据位（判据差异化）。 */
    fun requiredEvidence(boundary: PublishCompletionBoundary): Set<String> = buildSet {
        add("descriptionProof")
        add("mediaComplete")
        add("requiredFieldsComplete")
        add("successObserved")
        if (boundary.humanPrice) {
            add("priceHumanConfirmed")
        } else {
            add("priceEnteredByMachine")
        }
        if (boundary.humanCommit) {
            add("commitHumanConfirmed")
        } else {
            add("commitClickedByMachine")
        }
    }

    fun judge(claimed: PublishCompletionBoundary, evidence: PublishRunEvidence): PublishBoundaryJudgment {
        val evidenceBoundary = evidenceBoundary(evidence)
        val recorded = PublishCompletionBoundary.envelope(claimed, evidenceBoundary)
        val evidenceMap = mapOf(
            "descriptionProof" to evidence.descriptionProof,
            "priceEnteredByMachine" to evidence.priceEnteredByMachine,
            "priceHumanConfirmed" to evidence.priceHumanConfirmed,
            "commitClickedByMachine" to evidence.commitClickedByMachine,
            "commitHumanConfirmed" to evidence.commitHumanConfirmed,
            "successObserved" to evidence.successObserved,
            "mediaComplete" to evidence.mediaComplete,
            "requiredFieldsComplete" to evidence.requiredFieldsComplete,
        )
        val missing = requiredEvidence(recorded).filterNot { evidenceMap[it] == true }.toSet()
        return PublishBoundaryJudgment(
            claimed = claimed,
            evidenceBoundary = evidenceBoundary,
            recorded = recorded,
            missingEvidence = missing,
            // 成功资格：记录边界的全部判据证据齐 + 成功页观察到。
            successEligible = missing.isEmpty(),
        )
    }
}
