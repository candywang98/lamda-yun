<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createPostCatalog } from '@/api/post-catalog'
import { controlApiConfigured } from '@/api/control'
import { resolveMediaPreviewUrl, uploadMediaFile } from '@/api/media-assets'
import { emptyPost, postImageIds, type PostRecord } from '@/data/post-fields'
import MediaThumb from '@/components/MediaThumb.vue'
import { DEFAULT_POST_GROUP_NAME, resolvePostGroups } from '@/data/post-groups'

const route = useRoute()
const router = useRouter()
const catalog = createPostCatalog()
const busy = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const currentId = ref('')
const topicDraft = ref('')
const imageInput = ref<HTMLInputElement | null>(null)
const videoInput = ref<HTMLInputElement | null>(null)
const groups = ref<string[]>([DEFAULT_POST_GROUP_NAME])
const form = reactive<PostRecord>(emptyPost())
const videoPreviewUrl = ref('')
const previewImages = computed(() => postImageIds(form))

const postId = computed(() => (typeof route.query.id === 'string' ? route.query.id : ''))

async function loadGroups() {
  try {
    groups.value = resolvePostGroups(await catalog.list()).map((item) => item.name)
  } catch {
    groups.value = [DEFAULT_POST_GROUP_NAME]
  }
}

function applyPost(post: PostRecord) {
  currentId.value = post.id
  Object.assign(form, emptyPost(post))
}

function resetForm() {
  Object.assign(form, emptyPost({ id: currentId.value, groupName: form.groupName }))
  successMessage.value = '已重置，尚未保存'
}

async function loadPost() {
  errorMessage.value = ''
  if (!postId.value) {
    Object.assign(form, emptyPost())
    currentId.value = ''
    return
  }
  busy.value = true
  try {
    applyPost(await catalog.get(postId.value))
  } catch (error) {
    errorMessage.value = `加载帖子失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    busy.value = false
  }
}

async function addImageFiles(files: File[]) {
  if (!controlApiConfigured) {
    errorMessage.value = '未配置 Control API，禁止把帖子图片写成 blob/dataURL'
    return
  }
  errorMessage.value = ''
  try {
    const ids = postImageIds(form)
    for (const file of files.filter((item) => item.type.startsWith('image/')).slice(0, 16 - ids.length)) {
      const asset = await uploadMediaFile(file, { role: 'post-image' })
      ids.push(asset.id)
    }
    form.imageAssetIds = ids
    form.images = [...ids]
  } catch (error) {
    errorMessage.value = `图片上传失败：${error instanceof Error ? error.message : String(error)}`
  }
}

async function onPickImages(event: Event) {
  const input = event.target as HTMLInputElement
  const files = [...(input.files ?? [])]
  input.value = ''
  await addImageFiles(files)
}

async function onDropImages(event: DragEvent) {
  await addImageFiles([...(event.dataTransfer?.files ?? [])])
}

async function onPickVideo(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!controlApiConfigured) {
    errorMessage.value = '未配置 Control API，禁止把帖子视频写成 blob URL'
    return
  }
  try {
    const asset = await uploadMediaFile(file, { role: 'post-video' })
    form.videoName = file.name
    form.videoAssetId = asset.id
    form.videoUrl = asset.id
  } catch (error) {
    errorMessage.value = `视频上传失败：${error instanceof Error ? error.message : String(error)}`
  }
}

function removeImage(index: number) {
  const ids = postImageIds(form)
  ids.splice(index, 1)
  form.imageAssetIds = ids
  form.images = [...ids]
}

function clearVideo() {
  form.videoUrl = ''
  form.videoName = ''
  form.videoAssetId = ''
  videoPreviewUrl.value = ''
}

function addTopic() {
  const value = topicDraft.value.trim()
  if (!value || form.topics.includes(value) || form.topics.length >= 10) return
  form.topics.push(value)
  topicDraft.value = ''
}
function formatSaveError(error: unknown): string {
  if (error && typeof error === 'object' && 'problem' in error) {
    const problem = (error as { problem?: { detail?: string; fields?: Record<string, string> } }).problem
    const fields = problem?.fields ? Object.entries(problem.fields).map(([key, value]) => `${key}: ${value}`).join('；') : ''
    if (fields) return `${problem?.detail ?? '请求字段无效'}（${fields}）`
    if (problem?.detail) return problem.detail
  }
  return error instanceof Error ? error.message : String(error)
}


async function savePost() {
  if (!form.title.trim() && !form.body.trim()) {
    errorMessage.value = '请填写标题或内容后再保存'
    return
  }
  busy.value = true
  errorMessage.value = ''
  try {
    const saved = await catalog.save({
      id: currentId.value || postId.value || null,
      post: { ...form, title: form.title.trim() || '未命名帖子' },
    })
    applyPost(saved)
    if (!postId.value) await router.replace({ path: route.path, query: { id: saved.id } })
    successMessage.value = '帖子已保存'
  } catch (error) {
    errorMessage.value = `保存失败：${formatSaveError(error)}`
  } finally {
    busy.value = false
  }
}
watch(
  () => form.videoAssetId || form.videoUrl,
  async (source) => {
    videoPreviewUrl.value = ''
    if (!source) return
    try {
      videoPreviewUrl.value = await resolveMediaPreviewUrl(source)
    } catch {
      videoPreviewUrl.value = ''
    }
  },
  { immediate: true },
)


watch(postId, () => {
  void loadPost()
})

onMounted(() => {
  void loadGroups()
  void loadPost()
})
</script>

<template>
  <section class="post-page">
    <div class="card">
      <h2>编辑帖子/笔记</h2>
      <div class="row"><label for="post-title">帖子标题</label><input id="post-title" v-model="form.title" placeholder="写标题，能吸引更多人看哦" /></div>
      <div class="row top"><label for="post-body">帖子内容</label><textarea id="post-body" v-model="form.body" rows="8" placeholder="说点好玩的" /></div>
      <div class="row top">
        <span class="label">帖子图片</span>
        <div class="grow">
          <div class="actions">
            <button class="primary" type="button" @click="imageInput?.click()">多图片上传</button>
            <small>1.Windows按Ctrl多选，Mac按Command多选 2.上传后可拖拽排序，第一张为封面 3.双击查看大图</small>
          </div>
          <small>4.支持把图片文件直接拖进下方预览区上传，截图后按 Ctrl+V（Mac 为 ⌘V）粘贴也可上传</small>
          <input ref="imageInput" class="hidden" type="file" accept="image/*" multiple @change="onPickImages" />
          <div class="preview" @dragover.prevent @drop.prevent="onDropImages">
            <span v-if="previewImages.length === 0">预览图：</span>
            <div v-for="(image, index) in previewImages" :key="`${image}-${index}`" class="thumb">
              <MediaThumb :asset-id="image" :size="72" :alt="`帖子图片 ${index + 1}`" />
              <button type="button" @click="removeImage(index)">×</button>
            </div>
          </div>
        </div>
      </div>
      <div class="row top">
        <span class="label">帖子视频</span>
        <div class="grow">
          <div class="actions">
            <button class="primary" type="button" @click="videoInput?.click()">上传</button>
            <button class="primary" type="button" @click="clearVideo">暂无</button>
            <button class="primary" type="button" @click="clearVideo">清除</button>
          </div>
          <input ref="videoInput" class="hidden" type="file" accept="video/mp4" @change="onPickVideo" />
          <small>视频上传后会直接显示视频播放控件。采集帖子后视频不会立刻显示，会有一分钟左右的上传转码过程。</small>
          <video v-if="videoPreviewUrl" :src="videoPreviewUrl" controls />
        </div>
      </div>
      <div class="row">
        <span class="label">帖子话题</span>
        <div class="grow tags">
          <span v-for="(item, index) in form.topics" :key="item" class="tag">{{ item }} <button type="button" @click="form.topics.splice(index, 1)">×</button></span>
          <input v-model="topicDraft" placeholder="输入话题后按回车" @keydown.enter.prevent="addTopic" />
        </div>
      </div>
      <div class="row"><label for="post-location">帖子地点</label><div class="grow inline"><input id="post-location" v-model="form.location" /><small>手动输入一个地点，系统将尽可能搜索该地点</small></div></div>
      <div class="row"><label for="post-notes">帖子备注</label><input id="post-notes" v-model="form.notes" placeholder="帖子备注" /></div>
      <div class="row">
        <label for="post-group">帖子分组</label>
        <div class="grow inline">
          <select id="post-group" v-model="form.groupName">
            <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
          </select>
          <button class="link" type="button" @click="router.push('/operations/post-management/post-management-04')">分组管理</button>
        </div>
      </div>
      <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok">{{ successMessage }}</p>
      <div class="footer">
        <button class="primary" type="button" :disabled="busy" @click="savePost">保存帖子</button>
        <button type="button" :disabled="busy" @click="resetForm">重置</button>
      </div>
    </div>
    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>该页面的功能为编辑帖子/笔记，编辑后可发布到某鱼或红薯。</li>
        <li>如内容文本过长，可拖拽文本框右下角调整文本框大小，闲鱼限制帖子内容最多为1000字。</li>
        <li>闲鱼会玩帖子最多上传9张图片，红薯最多上传16张图片。</li>
        <li>闲鱼会玩帖子最多添加一个话题，红薯最多添加十个话题。</li>
        <li>发到闲鱼平台时，话题的名称需跟闲鱼保持一致。</li>
        <li>闲鱼仅支持 mp4 格式的视频，视频时长至少 3s。</li>
      </ol>
    </div>
  </section>
</template>

<style scoped>
.post-page { display: grid; gap: 10px; color: #334155; }
.card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; gap: 14px; }
h2 { margin: 0; font-size: 15px; }
.row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: center; }
.row.top { align-items: start; }
.label, label { color: #64748b; font-size: 13px; padding-top: 6px; }
input, select, textarea { width: 100%; padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 4px; font: inherit; }
.grow { min-width: 0; display: grid; gap: 8px; }
.actions, .tags, .inline, .footer { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.primary, .footer button { height: 32px; padding: 0 14px; border-radius: 4px; border: 1px solid #0f766e; background: #fff; color: #0f766e; }
.primary { color: #fff; background: #0f766e; }
.hidden { display: none; }
small { color: #94a3b8; font-size: 12px; }
.preview { min-height: 72px; padding: 10px; border: 1px solid #e5e7eb; border-left: 4px solid #0f766e; border-radius: 6px; display: flex; flex-wrap: wrap; gap: 8px; color: #94a3b8; }
.thumb { position: relative; }
.thumb img { width: 72px; height: 72px; object-fit: cover; border-radius: 4px; }
.thumb button { position: absolute; top: 2px; right: 2px; width: 18px; height: 18px; padding: 0; border: 0; border-radius: 50%; background: #0f172a; color: #fff; }
.tag { padding: 2px 8px; background: #ecfdf5; color: #0f766e; border-radius: 999px; font-size: 12px; }
.link { height: 32px; padding: 0 10px; border: 0; background: none; color: #0f766e; cursor: pointer; }
.flash { margin: 0; font-size: 13px; }
.flash.error { color: #b91c1c; }
.flash.ok { color: #166534; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
video { width: min(360px, 100%); }
</style>
