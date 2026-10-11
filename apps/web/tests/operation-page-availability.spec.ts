import { describe, expect, it } from 'vitest'
import { operationsCatalog } from '@/data/operations-catalog'
import { operationPageStatus } from '@/data/operation-page-availability'

describe('static page integration status', () => {
  it.each([
    ['product-management-01', 'dedicated'], ['orders-04', 'dedicated'], ['xy-tasks-23', 'dedicated'],
    ['product-editor-04', 'preview'], ['collection-01', 'preview'], ['system-home-04', 'guide'],
    ['post-management-07', 'unavailable'], ['zz-tasks-08', 'unavailable'], ['red-tasks-03', 'unavailable'],
    ['collection-04', 'unavailable'], ['orders-02', 'unavailable'],
  ])('%s has reviewed page status %s', (id, status) => {
    const operation = operationsCatalog.find((item) => item.id === id)!
    expect(operationPageStatus(operation)).toBe(status)
    expect(operationPageStatus({ ...operation, title: '发布商品' })).toBe(status)
  })
  it('does not turn unknown IDs into dedicated pages from a familiar title', () => {
    expect(operationPageStatus({ ...operationsCatalog[0]!, id: 'future-01', mode: 'form', title: '发布商品' })).toBe('preview')
  })
})
