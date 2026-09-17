/**
 * I10（fleet-first-20260916.1）：IM 回复边界 —— 只对授权会话回复，fail-closed。
 *
 * 汇聚两端的拒发原因码（只读复用语义）：
 *  - 云端 im_routes/im_service 的 409 码：THREAD_REPLY_RATE_LIMITED /
 *    DEVICE_BUSY / THREAD_HAS_NO_INBOUND；
 *  - 设备端 im.ImReplyBoundary 的会话级拒发码与
 *    automation/ChatInputCommit 的字段级失败码。
 * 未知码一律按"拒发"处理（fail-closed）：宁可多拦一条，不可错发一条。
 */

export type ReplyRefusalCode =
  | 'THREAD_REPLY_RATE_LIMITED'
  | 'DEVICE_BUSY'
  | 'THREAD_HAS_NO_INBOUND'
  | 'REPLY_WRONG_CONVERSATION'
  | 'REPLY_CONVERSATION_UNVERIFIED'
  | 'REPLY_CHAT_TARGET_CHANGED'
  | 'REPLY_NO_INBOUND_TRIGGER'
  | 'REPLY_SYSTEM_SESSION'
  | 'REPLY_HARASSMENT_SESSION'
  | 'INPUT_TARGET_CHANGED'
  | 'INPUT_IME_REQUIRED'
  | 'INPUT_REJECTED'

const REFUSAL_LABELS: Readonly<Record<ReplyRefusalCode, string>> = {
  THREAD_REPLY_RATE_LIMITED: '该会话 60 秒内只能回复一条，请稍后再试',
  DEVICE_BUSY: '设备正在执行任务，等任务结束后再回复',
  THREAD_HAS_NO_INBOUND: '该会话没有可回复的买家消息',
  REPLY_WRONG_CONVERSATION: '当前打开的会话与授权会话不一致，已拒发（错会话/转转发错）',
  REPLY_CONVERSATION_UNVERIFIED: '无法确认当前打开的是授权会话，已拒发（fail-closed）',
  REPLY_CHAT_TARGET_CHANGED: '回复期间会话焦点发生变化，已拒发',
  REPLY_NO_INBOUND_TRIGGER: '没有可追溯的买家入站触发，主动群发一律拒发',
  REPLY_SYSTEM_SESSION: '系统通知/营销会话不是买家会话，不回复',
  REPLY_HARASSMENT_SESSION: '该会话已被标记为骚扰类，不回复',
  INPUT_TARGET_CHANGED: '输入目标在输入过程中发生变化，已拒发',
  INPUT_IME_REQUIRED: '未选择 CloudCtl 输入法，无法安全输入，已拒发',
  INPUT_REJECTED: '输入内容未通过完整回读校验，已拒发',
}

/** 未知码也按拒发处理（fail-closed），显示通用拒发文案。 */
export function replyRefusalLabel(code: string): string {
  const known = REFUSAL_LABELS[code as ReplyRefusalCode]
  return known ?? '回复未获授权，已拒发（未知原因码）'
}

/** 该拒发是否值得操作员换一个动作重试（vs 需要先处理设备/会话状态）。 */
export function replyRefusalRetryable(code: string): boolean {
  switch (code) {
    case 'THREAD_REPLY_RATE_LIMITED':
    case 'DEVICE_BUSY':
      return true
    default:
      return false
  }
}

/** 错会话/焦点/群发/骚扰/系统类拒发的归类，供 UI 分组与统计。 */
export type ReplyRefusalClass = 'wrong-session' | 'focus' | 'unsolicited' | 'session-type' | 'device-busy' | 'field-input' | 'unknown'

export function replyRefusalClass(code: string): ReplyRefusalClass {
  switch (code) {
    case 'REPLY_WRONG_CONVERSATION':
    case 'REPLY_CONVERSATION_UNVERIFIED':
      return 'wrong-session'
    case 'REPLY_CHAT_TARGET_CHANGED':
    case 'INPUT_TARGET_CHANGED':
      return 'focus'
    case 'REPLY_NO_INBOUND_TRIGGER':
    case 'THREAD_HAS_NO_INBOUND':
      return 'unsolicited'
    case 'REPLY_SYSTEM_SESSION':
    case 'REPLY_HARASSMENT_SESSION':
      return 'session-type'
    case 'DEVICE_BUSY':
    case 'THREAD_REPLY_RATE_LIMITED':
      return 'device-busy'
    case 'INPUT_IME_REQUIRED':
    case 'INPUT_REJECTED':
      return 'field-input'
    default:
      return 'unknown'
  }
}
