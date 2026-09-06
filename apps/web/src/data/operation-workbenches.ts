import type { OperationDefinition, OperationMode } from './operations-catalog'

export type WorkbenchKind = 'device-list' | 'article' | 'table' | 'editor' | 'task' | 'pool' | 'settings'

export interface WorkbenchColumn {
  key: 'name' | 'group' | 'device' | 'owner' | 'status' | 'updatedAt'
  label: string
}

export function workbenchKind(operation: Pick<OperationDefinition, 'id' | 'moduleId' | 'title' | 'mode'>): WorkbenchKind {
  if (operation.id === 'system-home-02') return 'device-list'
  if (operation.title.includes('水印') || operation.title.includes('地址池') || operation.title.includes('描述池') || operation.title.includes('标签池')) return 'pool'
  if (operation.mode === 'guide') return 'article'
  if (operation.mode === 'settings') return 'settings'
  if (operation.mode === 'table' || operation.mode === 'insight') return 'table'
  if (operation.mode === 'assets') return 'pool'
  if (isTaskPage(operation)) return 'task'
  if (operation.mode === 'form') return 'editor'
  return layoutFromMode(operation.mode)
}

function isTaskPage(operation: Pick<OperationDefinition, 'moduleId' | 'title'>) {
  if (['xy-tasks', 'zz-tasks', 'red-tasks'].includes(operation.moduleId) && !operation.title.includes('教程')) return true
  return ['发布', '同步', '删除帖子', '开启消息', '关闭消息', '采集宝贝信息'].some((term) => operation.title.includes(term))
}

function layoutFromMode(mode: OperationMode): WorkbenchKind {
  if (mode === 'guide') return 'article'
  if (mode === 'table' || mode === 'insight') return 'table'
  if (mode === 'assets') return 'pool'
  if (mode === 'settings') return 'settings'
  return 'editor'
}

export function workbenchColumns(operation: Pick<OperationDefinition, 'id' | 'moduleId' | 'title' | 'mode' | 'pageProfile'>): WorkbenchColumn[] {
  const kind = workbenchKind(operation)
  if (operation.id === 'task-queue-01') {
    return [
      { key: 'device', label: '设备名' },
      { key: 'status', label: '状态' },
      { key: 'name', label: '任务类型' },
      { key: 'group', label: '任务备注' },
      { key: 'owner', label: '执行应用' },
      { key: 'updatedAt', label: '添加时间' },
    ]
  }
  if (operation.id === 'product-management-01') {
    return [
      { key: 'name', label: '商品标题' },
      { key: 'group', label: '商品分组' },
      { key: 'device', label: 'SPU编码' },
      { key: 'owner', label: '库存' },
      { key: 'status', label: '状态' },
      { key: 'updatedAt', label: '更新时间' },
    ]
  }
  if (operation.title.includes('订单')) {
    return [
      { key: 'device', label: '设备' },
      { key: 'name', label: '商品标题' },
      { key: 'owner', label: '买家' },
      { key: 'group', label: '交易状态' },
      { key: 'status', label: '状态' },
      { key: 'updatedAt', label: '更新时间' },
    ]
  }
  if (kind === 'table') {
    return [
      { key: 'name', label: operation.pageProfile.recordLabel },
      { key: 'group', label: '分组' },
      { key: 'device', label: '设备' },
      { key: 'status', label: '状态' },
      { key: 'updatedAt', label: '更新时间' },
    ]
  }
  return [
    { key: 'name', label: '对象' },
    { key: 'group', label: '分组' },
    { key: 'device', label: '设备' },
    { key: 'owner', label: '负责人' },
    { key: 'status', label: '状态' },
    { key: 'updatedAt', label: '更新时间' },
  ]
}

export function workbenchActions(operation: Pick<OperationDefinition, 'id' | 'title' | 'mode' | 'actionLabel'>): string[] {
  if (operation.id === 'product-management-01') return ['批量改价', '批量分组', '批量删除', '导出']
  if (operation.title.includes('队列')) return ['批量删除', '批量运行']
  if (operation.title.includes('列表')) return ['删除', '改分组', '导出']
  if (operation.mode === 'table') return ['筛选', '还原', '导出', '打印']
  return []
}
