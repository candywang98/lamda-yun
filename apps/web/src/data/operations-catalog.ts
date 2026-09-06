import { competitorPageSpecByIndex } from './competitor-pages.generated'
import { buildOperationPageProfile, type OperationPageProfile } from './operation-page-profiles'

export type OperationMode = 'guide' | 'table' | 'form' | 'assets' | 'insight' | 'settings'
export type OperationRisk = 'standard' | 'approval' | 'blocked'
export type BackendOperationKey =
  | 'accounts.authorization.health_check'
  | 'devices.capabilities.refresh'
  | 'groups.membership.reindex'
  | 'media.derivative.generate'
  | 'watermarks.preview.render'
  | 'works.revision.validate'
  | 'publish_plans.snapshot.validate'
  | 'xianyu.listing.publish'
  | 'task_runs.evidence.export'

export interface OperationDefinition {
  id: string
  index: number
  moduleId: string
  moduleLabel: string
  title: string
  mode: OperationMode
  risk: OperationRisk
  backendOperationKey: BackendOperationKey | null
  description: string
  actionLabel: string
  sourcePage: number
  sourceModule: string
  sourceTitle: string
  sourceRoute: string
  sourceSummary: string
  pageProfile: OperationPageProfile
}

export interface OperationModule {
  id: string
  label: string
  stage: '资产准备' | '内容生产' | '分发执行' | '互动交易' | '数据复盘'
  titles: string[]
  operations: OperationDefinition[]
}

const moduleDefinitions: Array<Omit<OperationModule, 'operations'>> = [
  {
    id: 'system-home',
    label: '系统主页',
    stage: '数据复盘',
    titles: ['产品介绍', '设备列表', '系统授权', '常见问题', '常用工具', '更新日志', '超级擦亮', '建议反馈', '公告通知', '视频教程'],
  },
  { id: 'task-queue', label: '任务队列', stage: '分发执行', titles: ['任务队列'] },
  {
    id: 'product-editor',
    label: '产品编辑',
    stage: '内容生产',
    titles: ['普通宝贝', '拍卖宝贝', '宝贝水印', '通用地址池', '设备地址池', '宝贝描述池', '宝贝标签池', '房屋出租', '免费送宝贝', '视频操作教程'],
  },
  {
    id: 'collection',
    label: '采集管理',
    stage: '资产准备',
    titles: ['商品链接采集', '闲鱼店铺解析', '搜索闲鱼宝贝', '淘宝店铺解析', '转转店铺解析', '微商相册解析', '孔网店铺解析', '阿里巴巴解析', '宝贝详情解析', '宝贝视频解析', '文章链接采集', '多多宝贝采集', '采集任务列表', '视频操作教程'],
  },
  {
    id: 'product-management',
    label: '商品管理',
    stage: '内容生产',
    titles: ['商品列表', '商品导入', '商品分组', '货源共享', '发布闲鱼', '发布转转', '多多数据包', '淘宝数据包', '违禁词检测', '视频操作教程'],
  },
  {
    id: 'post-management',
    label: '帖子管理',
    stage: '内容生产',
    titles: ['帖子编辑', '帖子采集', '帖子列表', '帖子分组', '帖子水印', '删除帖子', '发布闲鱼', '发布小红书', '视频教程'],
  },
  {
    id: 'orders',
    label: '订单管理',
    stage: '互动交易',
    titles: ['同步闲鱼订单', '去拼多多采购', '取拼多多单号', '查看全部订单', '视频操作教程'],
  },
  { id: 'analytics', label: '统计分析', stage: '数据复盘', titles: ['采集宝贝信息', '宝贝流量变化', '视频操作教程'] },
  {
    id: 'xy-tasks',
    label: '闲鱼授权任务',
    stage: '分发执行',
    titles: ['发布商品', '发布帖子', '擦亮商品', '上架商品', '下架商品', '删除商品', '删除帖子', '绑定闲鱼', '签到鱼币', '鱼币抵扣', '鱼币推广', '一键小刀', '一键降价', '一键好评', '重启闲鱼', '删除动态', '删除消息', '删除留言', '草稿上架', '编辑重发', '托管无忧卖', '快速编辑重发', '快速下架商品', '采集宝贝信息', '通用地址池', '设备地址池', '描述池', '标签池', '图片水印', '违禁词检测', '视频操作教程'],
  },
  {
    id: 'zz-tasks',
    label: '转转授权任务',
    stage: '分发执行',
    titles: ['发布商品', '擦亮商品', '下架商品', '上架商品', '删除商品', '转转养号', '流量模式', '违禁词检测', '视频操作教程'],
  },
  { id: 'red-tasks', label: '小红书授权任务', stage: '分发执行', titles: ['发布笔记', '删除笔记', '小红书养号', '搜索养号'] },
  { id: 'creative', label: '创意中心', stage: '内容生产', titles: ['爆款商品分析', '创意文案', 'TOP5000蓝海词', '视频教程'] },
  {
    id: 'chat',
    label: '聊天管理',
    stage: '互动交易',
    titles: ['开启消息回复', '关闭消息回复', '关键词回复', '场景回复组', '手机端回复', '消息回复格式', '快捷回复管理', '表情素材管理', '图片素材管理', '音频素材管理', '视频素材管理'],
  },
  {
    id: 'assets',
    label: '系统素材',
    stage: '资产准备',
    titles: ['图片水印', '图片素材', '音频素材', '视频素材', '通用地址池', '设备地址池', '描述池', '标签池'],
  },
  { id: 'profile', label: '个人中心', stage: '数据复盘', titles: ['基本资料', '修改密码', '邀请好友', '积分明细', 'AI功能设置'] },
]

const guideTerms = ['介绍', '问题', '工具', '日志', '公告', '教程']
const tableTerms = ['列表', '队列', '订单', '明细', '变化', '反馈']
const assetTerms = ['素材', '水印', '地址池', '描述池', '标签池', '分组', '数据包', '回复组']
const insightTerms = ['分析', '流量', 'TOP5000', '宝贝信息']
const settingsTerms = ['授权', '资料', '密码', '功能设置', '回复格式']
const approvalTerms = ['发布', '上架', '下架', '删除', '重启', '绑定', '降价', '小刀', '擦亮', '回复', '共享', '同步', '托管', '编辑重发', '草稿上架']
const blockedTerms = ['养号', '流量模式', '一键好评', '签到鱼币', '鱼币抵扣', '鱼币推广']

// The competitor information architecture is broader than the safe Control API catalog.
// Every entry receives an explicit key or null; no title-based runtime inference is allowed.
const backendOperationMappings: Partial<Record<string, BackendOperationKey>> = {
  'system-home-02': 'devices.capabilities.refresh',
  'system-home-03': 'accounts.authorization.health_check',
  'task-queue-01': 'task_runs.evidence.export',
  'product-editor-03': 'watermarks.preview.render',
  'product-management-03': 'groups.membership.reindex',
  'product-management-05': 'publish_plans.snapshot.validate',
  'product-management-09': 'works.revision.validate',
  'post-management-05': 'watermarks.preview.render',
  'post-management-07': 'publish_plans.snapshot.validate',
  'post-management-08': 'publish_plans.snapshot.validate',
  'xy-tasks-01': 'xianyu.listing.publish',
  'xy-tasks-02': 'publish_plans.snapshot.validate',
  'zz-tasks-01': 'publish_plans.snapshot.validate',
  'red-tasks-01': 'publish_plans.snapshot.validate',
  'assets-01': 'watermarks.preview.render',
  'assets-02': 'media.derivative.generate',
}

function inferMode(moduleId: string, title: string): OperationMode {
  if (guideTerms.some((term) => title.includes(term))) return 'guide'
  if (insightTerms.some((term) => title.includes(term))) return 'insight'
  if (assetTerms.some((term) => title.includes(term))) return 'assets'
  if (settingsTerms.some((term) => title.includes(term))) return 'settings'
  if (tableTerms.some((term) => title.includes(term)) || moduleId === 'task-queue') return 'table'
  return 'form'
}

export function inferRisk(moduleId: string, title: string): OperationRisk {
  if (blockedTerms.some((term) => title.includes(term))) return 'blocked'
  if (moduleId === 'collection' && !title.includes('任务列表') && !title.includes('教程')) return 'blocked'
  if (['去拼多多采购', '取拼多多单号'].includes(title)) return 'blocked'
  if (approvalTerms.some((term) => title.includes(term))) return 'approval'
  return 'standard'
}

function describe(mode: OperationMode, risk: OperationRisk, title: string) {
  if (risk === 'blocked') return `${title} 已纳入完整功能地图，但生产策略禁止直接执行；页面仅提供边界说明、授权检查与审计记录。`
  if (risk === 'approval') return `${title} 支持范围选择、参数预览与模拟任务创建；生产执行需要后端 RBAC、审批和不可变快照。`
  const descriptions: Record<OperationMode, string> = {
    guide: `${title} 的操作说明、版本记录与可检索教程。`,
    table: `${title} 的密集列表、筛选、批量选择、导出与结果回执。`,
    form: `${title} 的结构化参数、设备范围、计划时间与配置预览。`,
    assets: `${title} 的版本化资产、引用次数、来源与批量管理。`,
    insight: `${title} 的关键指标、趋势、筛选和异常定位。`,
    settings: `${title} 的租户配置、权限状态与审计信息。`,
  }
  return descriptions[mode]
}

function actionLabel(mode: OperationMode, risk: OperationRisk) {
  if (risk === 'blocked') return '策略已阻断'
  if (risk === 'approval') return '提交审批'
  if (mode === 'guide') return '标记已读'
  if (mode === 'settings') return '保存模拟配置'
  return '创建模拟任务'
}

let operationIndex = 0

function normalizeSourceLabel(value: string) {
  return value
    .replaceAll('某鱼', '闲鱼')
    .replaceAll('红薯', '小红书')
    .replaceAll('转传', '转转')
    .replace('闲鱼任务', '闲鱼授权任务')
    .replace('转转任务', '转转授权任务')
    .replace('小红书任务', '小红书授权任务')
}

export const operationModules: OperationModule[] = moduleDefinitions.map((module) => ({
  ...module,
  operations: module.titles.map((title, localIndex) => {
    operationIndex += 1
    const mode = inferMode(module.id, title)
    const risk = inferRisk(module.id, title)
    const id = `${module.id}-${String(localIndex + 1).padStart(2, '0')}`
    const source = competitorPageSpecByIndex.get(operationIndex)
    if (!source) throw new Error(`Missing competitor page metadata for operation ${operationIndex}: ${module.label}/${title}`)
    if (normalizeSourceLabel(source.module) !== module.label || normalizeSourceLabel(source.title) !== title) {
      throw new Error(`Competitor page metadata mismatch at operation ${operationIndex}: expected ${module.label}/${title}, received ${source.module}/${source.title}`)
    }
    return {
      id,
      index: operationIndex,
      moduleId: module.id,
      moduleLabel: module.label,
      title,
      mode,
      risk,
      backendOperationKey: backendOperationMappings[id] ?? null,
      description: describe(mode, risk, title),
      actionLabel: actionLabel(mode, risk),
      sourcePage: source.page,
      sourceModule: source.module,
      sourceTitle: source.title,
      sourceRoute: source.route,
      sourceSummary: source.summary,
      pageProfile: buildOperationPageProfile(module.id, title, source),
    }
  }),
}))

export const operationsCatalog = operationModules.flatMap((module) => module.operations)

export function operationPath(operation: OperationDefinition) {
  return `/operations/${operation.moduleId}/${operation.id}`
}

/** 闲鱼已下线帖子能力：目录仍保留 134 页编号，侧栏和功能目录不再展示。 */
export const retiredOperationIds = new Set([
  'xy-tasks-02',
  'xy-tasks-07',
  'post-management-06',
  'post-management-07',
])

export function isRetiredOperation(operationId: string) {
  return retiredOperationIds.has(operationId)
}

export function firstOperationPath(module: OperationModule) {
  const first = module.operations.find((operation) => !isRetiredOperation(operation.id)) ?? module.operations[0]
  return operationPath(first)
}

export function findOperation(moduleId: string, operationId: string) {
  return operationsCatalog.find((operation) => operation.moduleId === moduleId && operation.id === operationId)
}

export function visibleOperationModules(modules: OperationModule[] = operationModules) {
  return modules
    .map((module) => ({
      ...module,
      operations: module.operations.filter((operation) => !isRetiredOperation(operation.id)),
    }))
    .filter((module) => module.operations.length > 0)
}

export function riskLabel(risk: OperationRisk) {
  return { standard: '可模拟', approval: '需审批', blocked: '策略阻断' }[risk]
}
