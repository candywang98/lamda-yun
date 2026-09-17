/**
 * I10（fleet-first-20260916.1）：IM 回复 outbox 一致性模型。
 *
 * 镜像后端 cloudctl_api.im_service 的裁决规则（只读复用语义，不重复实现
 * 服务端逻辑；这里只做操作员可见的一致性视图与告警判断）：
 *  - 回复任务的终态决定 OUT 消息投递态：SUCCEEDED -> DELIVERED，
 *    FAILED / CANCELLED(双拼) / CANCELED(单拼) / EXPIRED -> FAILED。
 *  - DELIVERED 是吸收态：已确认送达的回复永不被迟到的失败/取消报告回退。
 *  - 任务取消后，本地（设备）与云端 outbox 必须一致：取消的任务在 outbox
 *    只能是 FAILED，绝不能停留在 PENDING（那意味着"待发"仍然成立）。
 */

export type OutboxDeliveryState = 'PENDING' | 'DELIVERED' | 'FAILED'

export type ReplyTaskBusinessState =
  | 'RUNNING'
  | 'RECONCILING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELLED'
  | 'CANCELED'
  | 'EXPIRED'

/** 终态 -> OUT 投递态（镜像 im_service.TASK_TERMINAL_DELIVERY）。 */
const TERMINAL_DELIVERY: Readonly<Record<string, OutboxDeliveryState>> = {
  SUCCEEDED: 'DELIVERED',
  FAILED: 'FAILED',
  CANCELLED: 'FAILED',
  CANCELED: 'FAILED',
  EXPIRED: 'FAILED',
}

/** 非终态任务对应的合法 in-flight outbox 态。 */
const IN_FLIGHT_STATES: readonly OutboxDeliveryState[] = ['PENDING']

export function isTerminalReplyState(state: string): state is ReplyTaskBusinessState {
  return state in TERMINAL_DELIVERY
}

/**
 * 任务进入终态后 outbox 应处的投递态；非终态返回 null（不裁决）。
 * DELIVERED 吸收：当前已是 DELIVERED 时，任何终态报告都不改变它。
 */
export function settleOutboxDelivery(
  current: OutboxDeliveryState,
  taskState: string,
): OutboxDeliveryState | null {
  if (!isTerminalReplyState(taskState)) return null
  if (current === 'DELIVERED') return 'DELIVERED'
  return TERMINAL_DELIVERY[taskState]
}

export type OutboxConsistency =
  | { consistent: true; expected: OutboxDeliveryState }
  | { consistent: false; expected: OutboxDeliveryState; actual: OutboxDeliveryState; reason: string }

/**
 * 本地（任务）态与云端 outbox 态的一致性裁决：
 *  - 终态任务：outbox 必须等于 settle 结果，否则不一致（例如取消后仍
 *    PENDING —— 本地已不待发，云端却还挂着待发）；
 *  - 非终态任务：outbox 必须仍是 in-flight（PENDING）；出现 FAILED/
 *    DELIVERED 说明两端状态错位（本地还在跑，云端已裁决）。
 */
export function outboxConsistency(
  taskState: string,
  outbox: OutboxDeliveryState,
): OutboxConsistency {
  const settled = settleOutboxDelivery(outbox, taskState)
  if (settled !== null) {
    if (settled === outbox) return { consistent: true, expected: settled }
    return {
      consistent: false,
      expected: settled,
      actual: outbox,
      reason:
        taskState === 'SUCCEEDED'
          ? `任务已成功但 outbox=${outbox}`
          : `任务已终态(${taskState})但 outbox=${outbox}`,
    }
  }
  if (IN_FLIGHT_STATES.includes(outbox)) {
    return { consistent: true, expected: outbox }
  }
  return {
    consistent: false,
    expected: 'PENDING',
    actual: outbox,
    reason: `任务仍在 ${taskState}，outbox 却已是 ${outbox}`,
  }
}

const STATE_LABELS: Readonly<Record<OutboxDeliveryState, string>> = {
  PENDING: '待发（任务执行中）',
  DELIVERED: '已送达',
  FAILED: '未送达（任务失败/取消）',
}

export function outboxStateLabel(state: OutboxDeliveryState): string {
  return STATE_LABELS[state] ?? state
}
