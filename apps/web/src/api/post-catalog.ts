import { CloudCtlApiError, type JsonObject } from '@cloudctl/api-contracts'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { emptyPost, payloadFromPost, postFromPayload, type PostRecord } from '@/data/post-fields'

const STORAGE_KEY = 'cloudctl.local-posts'

function loadLocal(): PostRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as PostRecord[]
    return Array.isArray(parsed) ? parsed.filter((item) => item.status !== 'ARCHIVED') : []
  } catch {
    return []
  }
}

function saveLocal(posts: PostRecord[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(posts))
}

function isMissingApi(error: unknown): boolean {
  return error instanceof CloudCtlApiError && (error.status === 404 || error.status === 501)
}

export function createPostCatalog() {
  const api = createControlApiClient()
  let usingLocal = !controlApiConfigured

  return {
    usingLocal: () => usingLocal,
    async list(): Promise<PostRecord[]> {
      if (!controlApiConfigured) {
        usingLocal = true
        return loadLocal()
      }
      try {
        const summaries = await api.contents('post')
        usingLocal = false
        const details = await Promise.all(summaries.map((item) => api.content(item.id)))
        return details.map((item) => {
          const payload = (item.revision.payload ?? {}) as JsonObject
          return postFromPayload(item.id, item.title, payload, {
            status: item.status,
            updatedAt: item.revision.created_at,
          })
        })
      } catch (error) {
        if (!isMissingApi(error)) throw error
        usingLocal = true
        return loadLocal()
      }
    },
    async get(id: string): Promise<PostRecord> {
      if (!usingLocal && controlApiConfigured) {
        try {
          const item = await api.content(id)
          return postFromPayload(item.id, item.title, (item.revision.payload ?? {}) as JsonObject, { status: item.status })
        } catch (error) {
          if (!isMissingApi(error)) throw error
          usingLocal = true
        }
      }
      const found = loadLocal().find((item) => item.id === id)
      if (!found) throw new Error('帖子不存在')
      return found
    },
    async save(input: { id?: string | null; post: PostRecord }): Promise<PostRecord> {
      const next = emptyPost({ ...input.post, id: input.id || input.post.id, updatedAt: new Date().toISOString() })
      if (!usingLocal && controlApiConfigured) {
        try {
          const payload = payloadFromPost(next)
          const saved = input.id
            ? await api.createRevision(input.id, { payload })
            : await api.createContent({ title: next.title, payload })
          return postFromPayload(saved.id, saved.title, (saved.revision.payload ?? payload) as JsonObject, { status: saved.status })
        } catch (error) {
          if (!isMissingApi(error)) throw error
          usingLocal = true
        }
      }
      const current = loadLocal()
      if (input.id) {
        const index = current.findIndex((item) => item.id === input.id)
        if (index < 0) throw new Error('帖子不存在')
        current[index] = next
        saveLocal(current)
        return next
      }
      saveLocal([next, ...current])
      return next
    },
    async remove(ids: string[]): Promise<void> {
      if (!usingLocal && controlApiConfigured) {
        try {
          const keep = (await this.list()).filter((item) => !ids.includes(item.id))
          saveLocal(keep)
          return
        } catch (error) {
          if (!isMissingApi(error)) throw error
          usingLocal = true
        }
      }
      saveLocal(loadLocal().filter((item) => !ids.includes(item.id)))
    },
    async duplicate(post: PostRecord): Promise<PostRecord> {
      return this.save({
        post: emptyPost({
          ...post,
          id: crypto.randomUUID(),
          title: `${post.title} 副本`,
        }),
      })
    },
  }
}
