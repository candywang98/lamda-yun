import { describe, expect, it } from 'vitest'
import { payloadFromPost, postFromPayload, postImageIds, emptyPost } from '@/data/post-fields'

describe('post image assets', () => {
  it('prefers mediaAssetIds over raw images when both exist', () => {
    const post = postFromPayload('post-1', '示例笔记', {
      mediaAssetIds: ['11111111-1111-4111-8111-111111111111'],
      images: ['https://example.com/broken.jpg'],
    })
    expect(postImageIds(post)).toEqual(['11111111-1111-4111-8111-111111111111'])
    expect(payloadFromPost(post)).toEqual({
      kind: 'post',
      body: '示例笔记',
      mediaAssetIds: ['11111111-1111-4111-8111-111111111111'],
      targetApp: 'unspecified',
      draftState: '草稿',
    })
  })

  it('falls back to images when asset ids are missing', () => {
    const post = postFromPayload('post-2', '采集笔记', {
      images: ['22222222-2222-4222-8222-222222222222'],
    })
    expect(post.imageAssetIds).toEqual(['22222222-2222-4222-8222-222222222222'])
    expect(postImageIds(post)).toEqual(['22222222-2222-4222-8222-222222222222'])
  })

  it('keeps empty posts without fabricating preview urls', () => {
    expect(postImageIds(emptyPost())).toEqual([])
  })

  it('does not send extra editor fields that the content contract forbids', () => {
    const payload = payloadFromPost(emptyPost({
      title: '标题',
      body: '正文',
      topics: ['话题'],
      location: '杭州',
      notes: '备注',
      groupName: '笔记素材',
      images: ['https://example.com/x.jpg'],
    }))
    expect(Object.keys(payload).sort()).toEqual(['body', 'draftState', 'kind', 'mediaAssetIds', 'targetApp'].sort())
    expect(payload.mediaAssetIds).toEqual([])
  })
})
