import { describe, expect, it } from 'vitest'
import { operationsCatalog } from '@/data/operations-catalog'
import { workbenchKind } from '@/data/operation-workbenches'

describe('operation workbenches', () => {
  it('maps every catalog page to a competitor workbench instead of a generic shell', () => {
    expect(operationsCatalog).toHaveLength(134)
    expect(workbenchKind(operationsCatalog.find((item) => item.id === 'system-home-02')!)).toBe('device-list')
    expect(workbenchKind(operationsCatalog.find((item) => item.id === 'system-home-01')!)).toBe('article')
    expect(workbenchKind(operationsCatalog.find((item) => item.id === 'task-queue-01')!)).toBe('table')
    expect(workbenchKind(operationsCatalog.find((item) => item.id === 'product-editor-01')!)).toBe('editor')
    expect(workbenchKind(operationsCatalog.find((item) => item.id === 'product-editor-03')!)).toBe('pool')
    expect(workbenchKind(operationsCatalog.find((item) => item.id === 'xy-tasks-01')!)).toBe('task')
    expect(workbenchKind(operationsCatalog.find((item) => item.id === 'profile-01')!)).toBe('settings')
    expect(new Set(operationsCatalog.map(workbenchKind))).toEqual(new Set(['device-list', 'article', 'table', 'editor', 'task', 'pool', 'settings']))
  })
})
