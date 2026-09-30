import { isRetiredOperation, type OperationDefinition } from './operations-catalog'

// Reviewed explicit OperationsView component branches: WEB-MD-NAVIGATION/20260930.1.
// Static page classification, never execution authorization.
const dedicatedIds = new Set([
  'system-home-02', 'task-queue-01', 'orders-01', 'orders-04',
  'product-editor-01', 'product-editor-03', 'product-editor-05', 'product-editor-06', 'product-editor-07',
  'product-management-01', 'product-management-02', 'product-management-03', 'product-management-05', 'product-management-09',
  'post-management-01', 'post-management-02', 'post-management-03', 'post-management-04', 'post-management-05', 'post-management-08',
  'assets-01', 'assets-06', 'assets-07', 'assets-08', 'analytics-01', 'red-tasks-01',
  'xy-tasks-01', 'xy-tasks-03', 'xy-tasks-04', 'xy-tasks-05', 'xy-tasks-06', 'xy-tasks-08',
  'xy-tasks-09', 'xy-tasks-10', 'xy-tasks-11', 'xy-tasks-12', 'xy-tasks-13', 'xy-tasks-14',
  'xy-tasks-15', 'xy-tasks-16', 'xy-tasks-17', 'xy-tasks-18', 'xy-tasks-19', 'xy-tasks-20',
  'xy-tasks-21', 'xy-tasks-22', 'xy-tasks-23', 'xy-tasks-24', 'xy-tasks-26', 'xy-tasks-27',
  'xy-tasks-28', 'xy-tasks-29', 'xy-tasks-30',
])
const outsideVersionIds = new Set([
  'collection-04', 'collection-05', 'collection-06', 'collection-07', 'collection-08', 'collection-12',
  'product-management-06', 'product-management-07', 'product-management-08', 'orders-02', 'orders-03',
  'red-tasks-03', 'red-tasks-04',
])
export const pageStatusLabels = {
  dedicated: '已有专用页面', preview: '配置预览', guide: '说明页面', unavailable: '当前版本未接入',
} as const
export type PageStatus = keyof typeof pageStatusLabels
export function operationPageStatus(operation: OperationDefinition): PageStatus {
  if (isRetiredOperation(operation.id) || outsideVersionIds.has(operation.id) || operation.moduleId === 'zz-tasks') return 'unavailable'
  if (dedicatedIds.has(operation.id)) return 'dedicated'
  if (operation.mode === 'guide') return 'guide'
  return 'preview'
}
export const moduleDescriptions: Record<string, string> = {
  'system-home': '设备入口、使用说明与账户授权。', 'task-queue': '跟踪任务进度，查看执行记录与结果。',
  'product-editor': '编辑商品内容，维护水印与文案。', collection: '查找采集配置与来源整理入口。',
  'product-management': '管理商品、导入内容，查看已同步订单。', 'post-management': '整理帖子内容、分组与发布配置。',
  orders: '配置订单同步任务；结果归入商品管理。', analytics: '查看宝贝信息采集与分析入口。',
  'xy-tasks': '查找闲鱼发布、商品维护与素材配置。', 'zz-tasks': '保留转转功能索引，当前版本未接入。',
  'red-tasks': '小红书笔记发布及功能范围说明。', creative: '查找文案与选品分析配置。',
  chat: '查找回复配置；会话处理请进入消息聚合。', assets: '整理水印、地址、描述与标签素材。',
  profile: '查找个人资料与账户配置。',
}
export const orderResultsPath = '/operations/product-management/product-management-01?tab=orders'
export const quickPaths = [
  { title: '连接设备', description: '查看设备与连接状态', to: '/fleet' },
  { title: '采集 / 导入', description: '整理内容来源与导入数据', to: '/content-io' },
  { title: '编辑 / 管理', description: '管理商品与内容', to: '/operations/product-management/product-management-01' },
  { title: '下发 / 发布', description: '配置闲鱼商品发布', to: '/operations/xy-tasks/xy-tasks-01' },
  { title: '任务结果', description: '跟踪任务进度与记录', to: '/operations/task-queue/task-queue-01' },
  { title: '聊天 / 订单', description: '查看已同步订单', to: orderResultsPath },
] as const
