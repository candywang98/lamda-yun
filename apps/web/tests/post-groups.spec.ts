import { describe, expect, it, beforeEach } from 'vitest'
import { emptyPost } from '@/data/post-fields'
import { createPostGroup, DEFAULT_POST_GROUP_NAME, deletePostGroup, listPostGroups, mergePostGroups, updatePostGroup } from '@/data/post-groups'

describe('post groups', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('always keeps the system default group and infers groups from posts', () => {
    const groups = mergePostGroups([], [emptyPost({ groupName: '笔记素材', createdAt: '2026-08-20T12:33:23.000Z' })])
    expect(groups.map((item) => item.name)).toEqual(['笔记素材', DEFAULT_POST_GROUP_NAME])
    expect(groups.find((item) => item.name === DEFAULT_POST_GROUP_NAME)?.id).toBe('46625')
    expect(groups.find((item) => item.name === DEFAULT_POST_GROUP_NAME)?.remark).toBe('系统建立的分组')
  })

  it('creates, updates and refuses deleting the default group', () => {
    createPostGroup({ name: '笔记素材', remark: '红薯笔记' })
    const created = listPostGroups()
    expect(created.some((item) => item.name === '笔记素材' && item.remark === '红薯笔记')).toBe(true)
    const group = created.find((item) => item.name === '笔记素材')!
    updatePostGroup(group.id, { remark: '闲鱼会玩' })
    expect(listPostGroups().find((item) => item.id === group.id)?.remark).toBe('闲鱼会玩')
    const fallback = listPostGroups().find((item) => item.name === DEFAULT_POST_GROUP_NAME)!
    expect(() => deletePostGroup(fallback.id)).toThrow('系统分组不能删除')
  })
})
