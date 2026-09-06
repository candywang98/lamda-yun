import { describe, expect, it } from 'vitest'
import { commentCandidates, DEFAULT_COMMENT_POOL, emptyNurtureConfig } from '@/data/xiaohongshu-nurture'

describe('xiaohongshu nurture config', () => {
  it('splits comment pool by hash', () => {
    expect(commentCandidates(DEFAULT_COMMENT_POOL).length).toBeGreaterThan(5)
    expect(commentCandidates('太赞了#马上种草')).toEqual(['太赞了', '马上种草'])
  })

  it('starts with discover / recommended defaults from the screenshot', () => {
    const config = emptyNurtureConfig()
    expect(config.browseType).toBe('discover')
    expect(config.channel).toBe('推荐')
    expect(config.multiOpen).toBe('off')
    expect(config.flipCount).toBe(20)
    expect(config.clickRate).toBe(30)
    expect(config.commentRate).toBe(0)
  })
})
