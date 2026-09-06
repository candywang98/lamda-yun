import { describe, expect, it } from 'vitest'
import { allocatePosts } from '@/data/post-publish'

describe('post publish allocation', () => {
  it('repeats every post on every device in default mode', () => {
    expect(allocatePosts(['p1', 'p2'], ['d1', 'd2'], 'default')).toEqual([
      { deviceId: 'd1', postId: 'p1' },
      { deviceId: 'd1', postId: 'p2' },
      { deviceId: 'd2', postId: 'p1' },
      { deviceId: 'd2', postId: 'p2' },
    ])
  })

  it('spreads leftover posts onto earlier devices in even mode', () => {
    expect(allocatePosts(['1', '2', '3', '4', '5'], ['A', 'B'], 'even')).toEqual([
      { deviceId: 'A', postId: '1' },
      { deviceId: 'A', postId: '2' },
      { deviceId: 'A', postId: '3' },
      { deviceId: 'B', postId: '4' },
      { deviceId: 'B', postId: '5' },
    ])
  })
})
