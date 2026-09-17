package com.company.cloudctl.companion.features.xianyu.publish

/**
 * P10 任务卡 §2：发布编排器的步骤原语（step primitives）。
 *
 * 这些原语是编排层（features/xianyu/publish）的组合单位，不改动 automation 层
 * （LocalAutomationExecutor / RecipeEngine / BuiltinRecipes 只读）。每个原语对应
 * Q03 单件发布真机验收后补齐的「完整闭环差额点」：
 *
 * - [AwaitMenuSettle]        菜单 settle：点开「卖闲置」后等发布入口菜单稳定，再点发布入口。
 * - [AwaitMediaCropReturn]   媒体裁剪返回后的续行：裁剪确认后必须等到回到发布表单页，
 *                            才允许继续填描述（页面没回来 = 续行失败，不许盲填）。
 * - [ProveTextInput]         输入证明（B14 ChatInputCommit/FlutterTextCommit 语义）：
 *                            描述文本必须回读一致 + 提交授权后才算填好，剪贴板不算证明。
 * - [VerifyRequiredFields]   价格/库存/交付方式必填检查：发布点击前三必填全部在场。
 * - [HumanCheckpoint]        WAITING_USER 检查点：按完成边界在价格点/最终点击点暂停等人。
 * - [AwaitPublishSuccess]    发布成功确认（成功页/在卖状态观察）。
 */
sealed interface PublishStepPrimitive {
    /** 原语稳定标识（事件对账用）。 */
    val id: String

    /** 菜单 settle：入口菜单出现且稳定后才继续。 */
    data class AwaitMenuSettle(val entryLocator: String = "xianyu_publish_entry") : PublishStepPrimitive {
        override val id: String get() = "menu-settle"
    }

    /** 媒体裁剪返回后的续行：等待回到发布表单页。 */
    data class AwaitMediaCropReturn(
        val pageLocator: String = "xianyu_publish_page",
        val timeoutMs: Long = 8_000,
    ) : PublishStepPrimitive {
        override val id: String get() = "media-crop-return"
    }

    /** 输入证明：文本字段的回读一致 + 提交授权双证明。 */
    data class ProveTextInput(
        val textField: TextField,
        val expected: String,
    ) : PublishStepPrimitive {
        override val id: String get() = "prove-input-${textField.wireName}"

        enum class TextField(val wireName: String) {
            DESCRIPTION("description"),
            PRICE("price"),
        }
    }

    /** 必填检查：价格 / 库存 / 交付方式。 */
    data class VerifyRequiredFields(
        val price: Boolean = true,
        val stock: Boolean = true,
        val deliveryMethod: Boolean = true,
    ) : PublishStepPrimitive {
        override val id: String get() = "verify-required-fields"
    }

    /** WAITING_USER 检查点。point 决定这是哪个人工动作位。 */
    data class HumanCheckpoint(val point: CheckpointPoint) : PublishStepPrimitive {
        override val id: String get() = "checkpoint-${point.wireName}"

        enum class CheckpointPoint(val wireName: String) {
            PRICE_ENTRY("price_entry"),
            FINAL_COMMIT("final_commit"),
        }
    }

    /** 发布成功确认（成功页/在卖状态观察）。 */
    data class AwaitPublishSuccess(val successLocator: String = "xianyu_publish_success") : PublishStepPrimitive {
        override val id: String get() = "await-publish-success"
    }
}

/** 编排器消费的执行器事件（由 automation 层接线翻译，本层只认事件语义）。 */
sealed interface PublishEvent {
    /** 菜单已 settle（入口可见且稳定）。 */
    data class MenuSettled(val entryVisible: Boolean) : PublishEvent

    /**
     * 裁剪确认后的页面状态：backToPublishPage=true 表示已回到发布表单页。
     * planned/staged 是媒体规划张数与已回传张数（B15 语义）；planned>0 且
     * staged<planned 时页面虽返回但媒体证据不齐（Q03「图全 12 态」对账）。
     */
    data class MediaCropReturned(
        val backToPublishPage: Boolean,
        val plannedImages: Int = 0,
        val stagedImages: Int = 0,
    ) : PublishEvent

    /** 输入证明结果（B14）：回读一致 + 提交授权。 */
    data class InputProof(
        val textField: PublishStepPrimitive.ProveTextInput.TextField,
        val readbackMatches: Boolean,
        val commitAuthorized: Boolean,
    ) : PublishEvent

    /** 必填字段快照。 */
    data class RequiredFieldSnapshot(
        val priceFilled: Boolean,
        val stockFilled: Boolean,
        val deliveryFilled: Boolean,
    ) : PublishEvent

    /** 人工在检查点完成动作（确认点回执）。 */
    data class HumanConfirmed(val point: PublishStepPrimitive.HumanCheckpoint.CheckpointPoint) : PublishEvent

    /** 发布成功页/在卖状态被观察到。byHuman=true 表示是人工确认而非机器定位。 */
    data class PublishSuccessObserved(val byHuman: Boolean) : PublishEvent

    /** 执行器报某步失败。 */
    data class StepFailed(val primitiveId: String, val code: String) : PublishEvent
}

/** 编排器决策。 */
sealed interface PublishDecision {
    /** 原语通过，推进到下一个原语（finished=true 表示计划走完）。 */
    data class Advance(val next: PublishStepPrimitive, val finished: Boolean) : PublishDecision

    /** 按完成边界暂停等人（WAITING_USER）。 */
    data class WaitingUser(val point: PublishStepPrimitive.HumanCheckpoint.CheckpointPoint) : PublishDecision

    /** 失败（带稳定机器码）。 */
    data class Failed(val code: String) : PublishDecision

    /**
     * 计划完成并给出边界判定。只有判定 successEligible=true 才允许上报
     * 「发布成功 + 记录边界」；否则调用方必须按失败/降级处置。
     */
    data class Succeeded(val judgment: PublishBoundaryJudgment) : PublishDecision
}

/**
 * 发布编排器：按计划推进原语，收口四种完成边界语义。
 *
 * 计划（plan）由调用方按任务的完成边界组合（见 [planFor]）：
 * - 全自动：菜单 settle → 裁剪返回 → 描述证明 → 必填检查 → 价格机器证明 → 成功确认。
 * - 人工价格（现生产）：… → PRICE_ENTRY 检查点（人工填价）→ 价格证明 → 成功确认。
 * - 人工点击：… → 价格机器证明 → FINAL_COMMIT 检查点 → 成功确认。
 * - 人工价格+人工点击：… → PRICE_ENTRY → FINAL_COMMIT → 成功确认。
 *
 * 编排器是纯决策器（无 IO），事件由 automation 层接线喂入（接缝留给主会话：
 * ClaimedTaskInterpreter/RecipeEngine 事件 → PublishEvent 的翻译层）；这保证语义
 * 可单测，与 RecipeEngine 的有界运行时解耦（B16）。
 */
class PublishOrchestrator(
    private val plan: List<PublishStepPrimitive>,
    private val claimedBoundary: PublishCompletionBoundary,
) {
    init {
        require(plan.isNotEmpty()) { "publish plan must not be empty" }
    }

    private var index: Int = 0
    private var waiting: PublishStepPrimitive.HumanCheckpoint? = null
    private val events = mutableListOf<PublishEvent>()

    val current: PublishStepPrimitive get() = plan[index]
    val progress: Int get() = index
    val waitingAt: PublishStepPrimitive.HumanCheckpoint? get() = waiting

    /** 当前累积证据（终态判定 + 上报）。 */
    fun evidence(): PublishRunEvidence {
        var descriptionProof = false
        var priceMachine = false
        var priceHuman = false
        var commitHuman = false
        var successObserved = false
        var successByHuman = false
        var successByMachine = false
        var requiredFields = false
        var mediaReturn = false
        for (event in events) {
            when (event) {
                is PublishEvent.InputProof -> when (event.textField) {
                    PublishStepPrimitive.ProveTextInput.TextField.DESCRIPTION ->
                        descriptionProof = descriptionProof ||
                            (event.readbackMatches && event.commitAuthorized)
                    PublishStepPrimitive.ProveTextInput.TextField.PRICE ->
                        priceMachine = priceMachine ||
                            (event.readbackMatches && event.commitAuthorized)
                }
                is PublishEvent.HumanConfirmed -> when (event.point) {
                    PublishStepPrimitive.HumanCheckpoint.CheckpointPoint.PRICE_ENTRY -> priceHuman = true
                    PublishStepPrimitive.HumanCheckpoint.CheckpointPoint.FINAL_COMMIT -> commitHuman = true
                }
                is PublishEvent.PublishSuccessObserved -> {
                    successObserved = true
                    if (event.byHuman) successByHuman = true else successByMachine = true
                }
                is PublishEvent.RequiredFieldSnapshot ->
                    requiredFields = requiredFields ||
                        (event.priceFilled && event.stockFilled && event.deliveryFilled)
                is PublishEvent.MediaCropReturned -> mediaReturn = mediaReturn || (
                    event.backToPublishPage &&
                        (event.plannedImages <= 0 || event.stagedImages >= event.plannedImages)
                    )
                else -> Unit
            }
        }
        // 机器点击发布：计划里没有 FINAL_COMMIT 检查点而成功页被机器定位到——
        // 受控点击由执行器台账佐证（automation 层接线翻译时携带）。
        val machineCommit = successByMachine && !planHasFinalCommitCheckpoint()
        val humanCommit = commitHuman || successByHuman
        return PublishRunEvidence(
            descriptionProof = descriptionProof,
            priceEnteredByMachine = priceMachine,
            priceHumanConfirmed = priceHuman,
            commitClickedByMachine = machineCommit,
            commitHumanConfirmed = humanCommit,
            successObserved = successObserved,
            mediaComplete = mediaReturn,
            requiredFieldsComplete = requiredFields,
        )
    }

    fun submit(event: PublishEvent): PublishDecision {
        events.add(event)
        val step = plan[index]
        if (event is PublishEvent.StepFailed) {
            return if (event.primitiveId == step.id || waiting?.id == event.primitiveId) {
                PublishDecision.Failed(event.code)
            } else {
                PublishDecision.Failed("OUT_OF_BAND_STEP_FAILURE:${event.primitiveId}")
            }
        }
        val decision = if (waiting != null) onWaitingEvent(event) else evaluate(step, event)
        if (decision is PublishDecision.Advance && !decision.finished) {
            index += 1
            val entered = plan[index]
            if (entered is PublishStepPrimitive.HumanCheckpoint) {
                // 进入检查点立即转 WAITING_USER，不吞下一个事件。
                waiting = entered
                return PublishDecision.WaitingUser(entered.point)
            }
        }
        return decision
    }

    private fun onWaitingEvent(event: PublishEvent): PublishDecision {
        val checkpoint = waiting ?: error("checkpoint expected")
        return when {
            event is PublishEvent.HumanConfirmed && event.point == checkpoint.point -> {
                waiting = null
                advanceFromCheckpoint()
            }
            // 价格检查点人工填价后仍需输入证明（回读一致 + 授权）才算价格证据齐。
            event is PublishEvent.InputProof && checkpoint.point ==
                PublishStepPrimitive.HumanCheckpoint.CheckpointPoint.PRICE_ENTRY &&
                event.textField == PublishStepPrimitive.ProveTextInput.TextField.PRICE -> {
                if (event.readbackMatches && event.commitAuthorized) {
                    advanceFromCheckpoint()
                } else {
                    PublishDecision.Failed("INPUT_PROOF_FAILED:price")
                }
            }
            event is PublishEvent.HumanConfirmed ->
                PublishDecision.Failed("CHECKPOINT_MISMATCH:${event.point.wireName}")
            else -> PublishDecision.WaitingUser(checkpoint.point)
        }
    }

    private fun advanceFromCheckpoint(): PublishDecision {
        val nextIndex = index + 1
        val next = plan.getOrNull(nextIndex)
        return PublishDecision.Advance(next ?: plan.last(), finished = next == null)
    }

    private fun evaluate(step: PublishStepPrimitive, event: PublishEvent): PublishDecision = when (step) {
        is PublishStepPrimitive.AwaitMenuSettle ->
            if (event is PublishEvent.MenuSettled && event.entryVisible) {
                advance()
            } else {
                stagnate(step, event)
            }
        is PublishStepPrimitive.AwaitMediaCropReturn ->
            if (event is PublishEvent.MediaCropReturned) {
                if (event.backToPublishPage) advance() else PublishDecision.Failed("CROP_RETURN_LOST_PAGE")
            } else {
                stagnate(step, event)
            }
        is PublishStepPrimitive.ProveTextInput ->
            if (event is PublishEvent.InputProof && event.textField == step.textField) {
                if (event.readbackMatches && event.commitAuthorized) {
                    advance()
                } else {
                    // B14：证明失败（回读不一致 / 未授权提交）不允许静默放行。
                    PublishDecision.Failed("INPUT_PROOF_FAILED:${step.textField.wireName}")
                }
            } else {
                stagnate(step, event)
            }
        is PublishStepPrimitive.VerifyRequiredFields ->
            if (event is PublishEvent.RequiredFieldSnapshot) {
                val checks = listOf(
                    step.price to event.priceFilled,
                    step.stock to event.stockFilled,
                    step.deliveryMethod to event.deliveryFilled,
                )
                if (checks.all { (required, filled) -> !required || filled }) {
                    advance()
                } else {
                    PublishDecision.Failed("REQUIRED_FIELD_MISSING")
                }
            } else {
                stagnate(step, event)
            }
        is PublishStepPrimitive.HumanCheckpoint -> {
            // 正常流程在进入检查点时就转 WaitingUser；走不到这里，防御式兜底。
            waiting = step
            PublishDecision.WaitingUser(step.point)
        }
        is PublishStepPrimitive.AwaitPublishSuccess ->
            if (event is PublishEvent.PublishSuccessObserved) {
                val evidence = evidence()
                val judgment = PublishBoundaryJudge.judge(claimedBoundary, evidence)
                if (judgment.successEligible) {
                    PublishDecision.Succeeded(judgment)
                } else {
                    // 缺证据（媒体不齐全 / 价格未验证 / 描述无证明）→ 不许记成功，
                    // 明确按证据缺口失败（完成度不虚标）。
                    PublishDecision.Failed(
                        "EVIDENCE_INCOMPLETE:${judgment.missingEvidence.sorted().joinToString(",")}",
                    )
                }
            } else {
                stagnate(step, event)
            }
    }

    private fun advance(): PublishDecision {
        val next = plan.getOrNull(index + 1)
        return PublishDecision.Advance(next ?: plan.last(), finished = next == null)
    }

    private fun stagnate(step: PublishStepPrimitive, event: PublishEvent): PublishDecision =
        if (event is PublishEvent.PublishSuccessObserved) {
            PublishDecision.Failed("SUCCESS_OUT_OF_ORDER")
        } else {
            PublishDecision.Failed("UNEXPECTED_EVENT:${step.id}")
        }

    private fun planHasFinalCommitCheckpoint(): Boolean =
        plan.any {
            it is PublishStepPrimitive.HumanCheckpoint &&
                it.point == PublishStepPrimitive.HumanCheckpoint.CheckpointPoint.FINAL_COMMIT
        }

    companion object {
        /**
         * 按完成边界生成标准计划（菜单 settle + 媒体裁剪返回续行 + 描述输入证明 +
         * 必填检查 + 价格位（人工检查点/机器证明）+ 点击位（人工检查点/机器）+ 成功确认）。
         */
        fun planFor(boundary: PublishCompletionBoundary): List<PublishStepPrimitive> = buildList {
            add(PublishStepPrimitive.AwaitMenuSettle())
            add(PublishStepPrimitive.AwaitMediaCropReturn())
            add(
                PublishStepPrimitive.ProveTextInput(
                    PublishStepPrimitive.ProveTextInput.TextField.DESCRIPTION,
                    expected = "",
                ),
            )
            add(PublishStepPrimitive.VerifyRequiredFields())
            if (boundary.humanPrice) {
                add(
                    PublishStepPrimitive.HumanCheckpoint(
                        PublishStepPrimitive.HumanCheckpoint.CheckpointPoint.PRICE_ENTRY,
                    ),
                )
            } else {
                add(
                    PublishStepPrimitive.ProveTextInput(
                        PublishStepPrimitive.ProveTextInput.TextField.PRICE,
                        expected = "",
                    ),
                )
            }
            if (boundary.humanCommit) {
                add(
                    PublishStepPrimitive.HumanCheckpoint(
                        PublishStepPrimitive.HumanCheckpoint.CheckpointPoint.FINAL_COMMIT,
                    ),
                )
            }
            add(PublishStepPrimitive.AwaitPublishSuccess())
        }
    }
}
