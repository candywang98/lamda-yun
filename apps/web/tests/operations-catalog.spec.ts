import { describe, expect, it } from 'vitest'
import { competitorPageSpecs } from '@/data/competitor-pages.generated'
import { findOperation, firstOperationPath, inferRisk, isRetiredOperation, operationModules, operationPath, operationsCatalog, retiredOperationIds } from '@/data/operations-catalog'

describe('operations catalog', () => {
  it('contains the complete 15-module, 134-entry competitor map', () => {
    expect(operationModules).toHaveLength(15)
    expect(operationsCatalog).toHaveLength(134)
    expect(new Set(operationsCatalog.map((operation) => operation.mode)).size).toBe(6)
    expect(operationModules.map((module) => module.operations.length)).toEqual([10, 1, 10, 14, 10, 9, 5, 3, 31, 9, 4, 4, 11, 8, 5])
    expect(operationModules.slice(8, 11).map((module) => module.label)).toEqual(['闲鱼授权任务', '转转授权任务', '小红书授权任务'])
    expect(operationsCatalog.every((operation) => Object.hasOwn(operation, 'backendOperationKey'))).toBe(true)
    expect(operationsCatalog.filter((operation) => operation.backendOperationKey)).toHaveLength(15)
    expect(findOperation('xy-tasks', 'xy-tasks-01')?.backendOperationKey).toBe('xianyu.listing.publish')
    expect([...retiredOperationIds].sort()).toEqual(['post-management-06', 'post-management-07', 'xy-tasks-02', 'xy-tasks-07'])
    expect(isRetiredOperation('xy-tasks-02')).toBe(true)
    expect(isRetiredOperation('xy-tasks-01')).toBe(false)
  })

  it('binds every entry to its PDF page, original route and page-specific profile', () => {
    expect(competitorPageSpecs).toHaveLength(134)
    expect(new Set(competitorPageSpecs.map((page) => page.route)).size).toBe(111)
    expect(operationsCatalog.map((operation) => ({
      index: operation.index,
      page: operation.sourcePage,
      module: operation.sourceModule,
      title: operation.sourceTitle,
      route: operation.sourceRoute,
    }))).toEqual(competitorPageSpecs.map((page) => ({
      index: page.index,
      page: page.page,
      module: page.module,
      title: page.title,
      route: page.route,
    })))
    expect(operationsCatalog.every((operation) => operation.sourceSummary.length > 0)).toBe(true)
    expect(operationsCatalog.every((operation) => operation.pageProfile.fields.length >= 3 && operation.pageProfile.workflow.length === 4)).toBe(true)
    expect(new Set(operationsCatalog.map((operation) => operation.pageProfile.key)).size).toBe(134)
    expect(operationsCatalog.every((operation) => operation.pageProfile.sourcePage === operation.sourcePage && operation.pageProfile.sourceRoute === operation.sourceRoute)).toBe(true)
    expect(operationsCatalog.every((operation) => new Set(operation.pageProfile.fields.map((field) => field.id)).size === operation.pageProfile.fields.length)).toBe(true)
    expect(operationsCatalog.flatMap((operation) => operation.pageProfile.fields).filter((field) => field.control === 'select').every((field) => field.options?.includes(String(field.defaultValue)))).toBe(true)
  })

  it('provides domain fields across all 15 modules instead of title-only generic templates', () => {
    const expectations = [
      ['system-home', 'system-home-02', '体检范围'],
      ['task-queue', 'task-queue-01', '任务或设备关键词'],
      ['product-editor', 'product-editor-03', '水印文字'],
      ['collection', 'collection-01', '公开链接'],
      ['product-management', 'product-management-02', '导入格式'],
      ['post-management', 'post-management-01', '帖子标题'],
      ['orders', 'orders-01', '订单时间窗'],
      ['analytics', 'analytics-02', '统计周期'],
      ['xy-tasks', 'xy-tasks-01', '内容范围'],
      ['zz-tasks', 'zz-tasks-03', '目标范围'],
      ['red-tasks', 'red-tasks-01', '内容范围'],
      ['creative', 'creative-02', '文案语气'],
      ['chat', 'chat-03', '触发关键词'],
      ['assets', 'assets-03', '素材名称'],
      ['profile', 'profile-05', 'AI 功能'],
    ] as const

    for (const [moduleId, operationId, fieldLabel] of expectations) {
      const operation = findOperation(moduleId, operationId)
      expect(operation, operationId).toBeTruthy()
      expect(operation?.pageProfile.fields.map((field) => field.label), operationId).toContain(fieldLabel)
      expect(operation?.pageProfile.purpose, operationId).toContain('原页面要点')
    }
  })

  it('creates stable dynamic paths and lookup keys', () => {
    const operation = operationModules[8].operations[0]
    expect(operation.title).toBe('发布商品')
    expect(operationPath(operation)).toBe('/operations/xy-tasks/xy-tasks-01')
    expect(firstOperationPath(operationModules[8])).toBe('/operations/xy-tasks/xy-tasks-01')
    expect(findOperation('xy-tasks', 'xy-tasks-01')).toEqual(operation)
  })

  it('gives all 134 entries unique paths that round-trip through lookup', () => {
    const paths = operationsCatalog.map(operationPath)
    expect(new Set(paths)).toHaveLength(134)

    for (const operation of operationsCatalog) {
      expect(findOperation(operation.moduleId, operation.id)).toBe(operation)
      expect(operationPath(operation)).toBe(`/operations/${operation.moduleId}/${operation.id}`)
    }
  })

  it('blocks prohibited or unsupported behavior while retaining the page', () => {
    expect(inferRisk('zz-tasks', '转转养号')).toBe('blocked')
    expect(inferRisk('zz-tasks', '流量模式')).toBe('blocked')
    expect(inferRisk('collection', '淘宝店铺解析')).toBe('blocked')
    expect(inferRisk('xy-tasks', '一键好评')).toBe('approval')
    expect(inferRisk('xy-tasks', '发布商品')).toBe('approval')
  })
})
