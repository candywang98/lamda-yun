import { describe, expect, it } from 'vitest'
import { allocateProducts } from '@/data/xianyu-publish-goods'

describe('xianyu publish goods allocation', () => {
  it('repeats every product on every device in default mode', () => {
    expect(allocateProducts(['p1', 'p2'], ['d1', 'd2'], 'default')).toEqual([
      { deviceId: 'd1', productId: 'p1' },
      { deviceId: 'd1', productId: 'p2' },
      { deviceId: 'd2', productId: 'p1' },
      { deviceId: 'd2', productId: 'p2' },
    ])
  })

  it('spreads products across devices in even mode', () => {
    expect(allocateProducts(['p1', 'p2', 'p3'], ['d1', 'd2'], 'even')).toEqual([
      { deviceId: 'd1', productId: 'p1' },
      { deviceId: 'd2', productId: 'p2' },
      { deviceId: 'd1', productId: 'p3' },
    ])
  })
})
