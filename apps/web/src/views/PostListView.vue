<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { createPostCatalog } from '@/api/post-catalog'
import { downloadDataUrl } from '@/data/product-fields'
import { clipText, formatDateTime, postImageIds, type PostRecord } from '@/data/post-fields'
import { fetchMediaBlob } from '@/api/media-assets'
import MediaThumb from '@/components/MediaThumb.vue'
import { resolvePostGroups } from '@/data/post-groups'

const router = useRouter()
const catalog = createPostCatalog()
const posts = ref<PostRecord[]>([])
const selectedIds = ref<string[]>([])
const searchQuery = ref('')
const groupFilter = ref('')
const loading = ref(false)
const busy = ref(false)
const loadError = ref('')
const errorMessage = ref('')
const successMessage = ref('')
const page = ref(1)
const pageSize = ref(10)
const jumpPage = ref('1')
const uncertainIds = ref<string[]>([])
type Result = { id: string; title: string; state: '已确认成功' | '结果待核实' | '尚未尝试' }
const results = ref<Result[]>([])
type Dialog = { kind: 'append' | 'replace' | 'archive' | 'detail'; targets: PostRecord[]; from: string; value: string }
const dialog = ref<Dialog | null>(null)
const modal = ref<HTMLElement | null>(null)
let returnFocus: HTMLElement | null = null
const clone = (post: PostRecord): PostRecord => JSON.parse(JSON.stringify(post)) as PostRecord
const groups = computed(() => resolvePostGroups(posts.value).map((item) => item.name))
const filtered = computed(() => posts.value.filter((post) => {
  const haystack = [post.title, post.body, post.notes, ...post.topics].join(' ').toLowerCase()
  return (!searchQuery.value.trim() || haystack.includes(searchQuery.value.trim().toLowerCase())) && (!groupFilter.value || post.groupName === groupFilter.value)
}))
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const locked = computed(() => busy.value || loading.value || !!loadError.value)
const selectable = computed(() => paged.value.filter((post) => !uncertainIds.value.includes(post.id)))
const allSelected = computed({
  get: () => selectable.value.length > 0 && selectable.value.every((post) => selectedIds.value.includes(post.id)),
  set: (value: boolean) => {
    if (locked.value) return
    selectedIds.value = value ? [...new Set([...selectedIds.value, ...selectable.value.map((post) => post.id)])] : selectedIds.value.filter((id) => !selectable.value.some((post) => post.id === id))
  },
})
const preview = computed(() => {
  if (!dialog.value || !['append', 'replace'].includes(dialog.value.kind)) return []
  const { kind, targets, from, value } = dialog.value
  return targets.map((post) => ({ ...clone(post), body: kind === 'append' ? post.body + value : from ? post.body.split(from).join(value) : post.body }))
})
const changedPreview = computed(() => preview.value.filter((post, index) => post.body !== dialog.value?.targets[index]?.body))
watch([searchQuery, groupFilter, pageSize], () => { page.value = 1 })
watch(totalPages, (total) => { page.value = Math.min(page.value, total) })
function jump() {
  const value = Number(jumpPage.value)
  page.value = Math.min(totalPages.value, Math.max(1, Number.isFinite(value) ? Math.trunc(value) : 1))
  jumpPage.value = String(page.value)
}
function toggleSelection(id: string) {
  if (locked.value || uncertainIds.value.includes(id)) return
  selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter((item) => item !== id) : [...selectedIds.value, id]
}
async function loadPosts() {
  if (busy.value || loading.value) return
  loading.value = true
  loadError.value = ''
  try {
    posts.value = await catalog.list()
    selectedIds.value = selectedIds.value.filter((id) => posts.value.some((post) => post.id === id) && !uncertainIds.value.includes(id))
  } catch (error) { loadError.value = '加载帖子失败：' + String(error) }
  finally { loading.value = false }
}
async function openDialog(kind: Dialog['kind'], targets = posts.value.filter((post) => selectedIds.value.includes(post.id))) {
  if (locked.value || !targets.length) return
  if (kind !== 'detail' && targets.some((post) => uncertainIds.value.includes(post.id))) return
  returnFocus = document.activeElement as HTMLElement | null
  dialog.value = { kind, targets: targets.map(clone), from: '', value: '' }
  await nextTick()
  modal.value?.querySelector<HTMLElement>('input, textarea, button')?.focus()
}
function closeDialog() {
  if (busy.value) return
  dialog.value = null
  returnFocus?.focus()
}
function modalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); closeDialog(); return }
  if (event.key !== 'Tab') return
  const controls = Array.from(modal.value?.querySelectorAll<HTMLElement>('input:not(:disabled), textarea:not(:disabled), button:not(:disabled)') ?? [])
  if (!controls.length) { event.preventDefault(); return }
  const first = controls[0]!, last = controls.at(-1)!
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
async function confirmDialog() {
  if (busy.value || !dialog.value || dialog.value.kind === 'detail') return
  const archive = dialog.value.kind === 'archive'
  const targets = (archive ? dialog.value.targets : changedPreview.value).map(clone)
  if (!targets.length) return
  busy.value = true
  errorMessage.value = ''
  successMessage.value = ''
  await nextTick()
  modal.value?.focus()
  results.value = targets.map((post) => ({ id: post.id, title: post.title, state: '尚未尝试' }))
  for (const [index, post] of targets.entries()) {
    try {
      if (archive) {
        await catalog.remove([post.id])
        posts.value = posts.value.filter((item) => item.id !== post.id)
      } else {
        const saved = await catalog.save({ id: post.id, post })
        posts.value = posts.value.map((item) => item.id === post.id ? saved : item)
      }
      results.value[index]!.state = '已确认成功'
    } catch (error) {
      results.value[index]!.state = '结果待核实'
      uncertainIds.value = [...new Set([...uncertainIds.value, post.id])]
      errorMessage.value = '请求中断，失败请求可能已生效。请核实结果，系统不会自动重试：' + String(error)
      break
    }
  }
  successMessage.value = '已确认成功 ' + results.value.filter((item) => item.state === '已确认成功').length + ' 条；结果待核实 ' + results.value.filter((item) => item.state === '结果待核实').length + ' 条；尚未尝试 ' + results.value.filter((item) => item.state === '尚未尝试').length + ' 条。'
  selectedIds.value = []
  busy.value = false
  closeDialog()
}
async function duplicatePost(post: PostRecord) {
  if (locked.value || uncertainIds.value.includes(post.id)) return
  busy.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const saved = await catalog.duplicate(clone(post))
    posts.value = [saved, ...posts.value]
    successMessage.value = '已确认新增 1 条副本'
  } catch (error) {
    uncertainIds.value = [...new Set([...uncertainIds.value, post.id])]
    errorMessage.value = '复制结果待核实，可能已创建副本；不会自动重试：' + String(error)
  } finally { busy.value = false }
}
async function downloadImages(targets: PostRecord[]) {
  if (locked.value) return
  busy.value = true
  errorMessage.value = ''
  try {
    let count = 0
    for (const post of targets.map(clone)) for (const [index, image] of postImageIds(post).entries()) {
      const url = URL.createObjectURL(await fetchMediaBlob(image))
      try { downloadDataUrl(url, (post.title || 'post') + '-' + (index + 1) + '.jpg'); count += 1 }
      finally { URL.revokeObjectURL(url) }
    }
    successMessage.value = count ? '已发起 ' + count + ' 张图片下载' : '所选帖子没有可下载图片'
  } catch (error) { errorMessage.value = '下载图片失败：' + String(error) }
  finally { busy.value = false }
}
function csvCell(value: string) {
  const safe = /^[\s]*[=+@-]/.test(value) || /^[\t\r\n]/.test(value) ? "'" + value : value
  return '"' + safe.replaceAll('"', '""') + '"'
}
function exportCsv() {
  const rows = [['帖子分组', '标题', '内容', '地点', '话题', '添加时间', '帖子备注'], ...filtered.value.map((post) => [post.groupName, post.title, post.body, post.location, post.topics.join(' '), formatDateTime(post.updatedAt), post.notes])]
  downloadDataUrl('data:text/csv;charset=utf-8,' + encodeURIComponent(rows.map((row) => row.map(csvCell).join(',')).join('\r\n')), '帖子列表.csv')
}
onMounted(loadPosts)
</script>

<template>
  <section class="post-page">
    <div class="card" :inert="dialog ? true : undefined">
      <h2>帖子/笔记列表</h2>
      <div class="filter"><input v-model="searchQuery" aria-label="搜索帖子标题、内容" placeholder="搜索帖子标题、内容" /><select v-model="groupFilter" aria-label="筛选帖子分组"><option value="">全部分组</option><option v-for="group in groups" :key="group">{{ group }}</option></select><button class="primary" type="button" @click="searchQuery = ''; groupFilter = ''">还原筛选</button><button class="primary" type="button" :disabled="locked" @click="loadPosts">刷新列表</button></div>
      <div class="actions">
        <button type="button" :disabled="locked || !selectedIds.length" @click="openDialog('archive')">批量归档</button>
        <button type="button" disabled title="当前保存接口不支持分组修改">修改分组（暂不可用）</button>
        <button type="button" :disabled="locked || !selectedIds.length" @click="openDialog('append')">追加描述</button>
        <button type="button" :disabled="locked || !selectedIds.length" @click="openDialog('replace')">替换内容</button>
        <button type="button" :disabled="locked || !selectedIds.length" @click="downloadImages(posts.filter((post) => selectedIds.includes(post.id)))">下载图片</button>
        <span class="spacer" /><button type="button" :disabled="loading || !!loadError" @click="exportCsv">导出当前筛选</button>
      </div>
      <p class="selection-summary">已选 {{ selectedIds.length }} 条（含其他页或筛选外项目）<button type="button" :disabled="busy" @click="selectedIds = []">清空选择</button></p>
      <p class="muted">当前接口不保存分组修改。批量更新前请查看预览；接口不支持版本冲突检测，请避免多人同时修改同一帖子。</p>
      <div v-if="loadError" role="alert" class="flash error">{{ loadError }} <button type="button" :disabled="loading || busy" @click="loadPosts">重试加载</button></div>
      <p v-if="errorMessage" class="flash error" role="alert">{{ errorMessage }}</p><p v-if="successMessage" class="flash ok" role="status">{{ successMessage }}</p>
      <div v-if="uncertainIds.length" class="notice">{{ uncertainIds.length }} 条请求结果待核实，相关修改操作已锁定。可刷新查看当前记录；此页不会自动重放请求。</div>
      <ul v-if="results.length" aria-label="批量处理结果"><li v-for="result in results" :key="result.id">{{ result.title || result.id }}：{{ result.state }}</li></ul>
      <div class="table-scroll"><table>
        <thead><tr><th class="check"><input v-model="allSelected" type="checkbox" aria-label="选择本页帖子" :disabled="locked" /></th><th>帖子分组</th><th>帖子图片/视频</th><th>标题</th><th>内容</th><th>地点</th><th>话题</th><th>添加时间</th><th>帖子备注</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-if="loading"><td colspan="10" class="empty" role="status">正在加载帖子…</td></tr>
          <tr v-else-if="loadError"><td colspan="10" class="empty">加载失败，请重试。</td></tr>
          <tr v-else-if="!posts.length"><td colspan="10" class="empty">还没有帖子。到「帖子编辑」保存后会出现在这里。</td></tr>
          <tr v-else-if="!paged.length"><td colspan="10" class="empty">没有符合筛选条件的帖子。</td></tr>
          <template v-else><tr v-for="post in paged" :key="post.id">
            <td class="check"><input type="checkbox" :aria-label="'选择 ' + post.title" :disabled="locked || uncertainIds.includes(post.id)" :checked="selectedIds.includes(post.id)" @change="toggleSelection(post.id)" /></td><td>{{ post.groupName }}</td>
            <td><div class="thumbs"><MediaThumb v-for="(image, index) in postImageIds(post).slice(0, 3)" :key="post.id + image + index" :asset-id="image" :alt="post.title" /><span v-if="postImageIds(post).length" class="count">{{ postImageIds(post).length }}张</span><span v-else class="muted">无图</span></div></td>
            <td><button class="detail-link" type="button" :title="post.title" :disabled="locked" @click="openDialog('detail', [post])">{{ clipText(post.title, 16) }}</button></td><td :title="post.body">{{ clipText(post.body, 18) }}</td><td>{{ post.location }}</td><td>{{ post.topics.join(' ') }}</td><td>{{ formatDateTime(post.updatedAt || post.createdAt) }}</td><td>{{ post.notes }}</td>
            <td class="ops"><button type="button" title="编辑" :disabled="locked || uncertainIds.includes(post.id)" @click="router.push('/operations/post-management/post-management-01?id=' + post.id)">✎</button><button type="button" title="复制" :aria-label="'复制 ' + post.title" :disabled="locked || uncertainIds.includes(post.id)" @click="duplicatePost(post)">⧉</button><button type="button" title="下载" :disabled="locked" @click="downloadImages([post])">⬇</button><button class="danger" type="button" :aria-label="'归档 ' + post.title" :disabled="locked || uncertainIds.includes(post.id)" @click="openDialog('archive', [post])">归档</button></td>
          </tr></template>
        </tbody>
      </table></div>
      <div class="pager"><button type="button" aria-label="上一页" :disabled="page <= 1" @click="page -= 1">‹</button><span>第 {{ page }} / {{ totalPages }} 页</span><button type="button" aria-label="下一页" :disabled="page >= totalPages" @click="page += 1">›</button><label>跳转页码 <input v-model="jumpPage" aria-label="跳转页码" inputmode="numeric" @keyup.enter="jump" /></label><button type="button" @click="jump">确定</button><span>共 {{ filtered.length }} 条</span><select v-model.number="pageSize" aria-label="每页条数"><option :value="10">10 条/页</option><option :value="20">20 条/页</option></select></div>
    </div>
    <div v-if="dialog" class="mask" @click.self="closeDialog">
      <div ref="modal" class="modal" tabindex="-1" role="dialog" aria-modal="true" aria-labelledby="post-dialog-title" @keydown="modalKeydown">
        <h3 id="post-dialog-title">{{ dialog.kind === 'detail' ? '帖子详情' : dialog.kind === 'archive' ? '确认归档' : '批量修改预览' }}</h3>
        <template v-if="dialog.kind === 'detail'"><h4>{{ dialog.targets[0]?.title }}</h4><pre>{{ dialog.targets[0]?.body }}</pre></template>
        <template v-else-if="dialog.kind === 'archive'"><p>将归档 {{ dialog.targets.length }} 条帖子并移出当前列表。本页不提供恢复功能。</p><ul><li v-for="post in dialog.targets" :key="post.id">{{ post.title }}</li></ul></template>
        <template v-else><p>已冻结 {{ dialog.targets.length }} 条目标。仅保存实际变化的内容，替换按原文精确匹配。</p><label v-if="dialog.kind === 'replace'">查找原文<input v-model="dialog.from" :disabled="busy" /></label><label>{{ dialog.kind === 'append' ? '追加文本' : '替换文本' }}<textarea v-model="dialog.value" :disabled="busy" /></label><p>命中 {{ changedPreview.length }} 条帖子</p><section v-for="(post, index) in preview" :key="post.id" class="preview-row"><strong>{{ post.title }}</strong><p>修改前</p><pre>{{ dialog.targets[index]?.body }}</pre><p>修改后</p><pre>{{ post.body }}</pre></section></template>
        <div class="modal-actions"><button type="button" :disabled="busy" @click="closeDialog">{{ dialog.kind === 'detail' ? '关闭' : '取消' }}</button><button v-if="dialog.kind !== 'detail'" class="primary" type="button" :disabled="busy || (dialog.kind !== 'archive' && !changedPreview.length)" @click="confirmDialog">{{ busy ? '正在处理…' : dialog.kind === 'archive' ? '确认归档' : '确认保存修改' }}</button></div>
      </div>
    </div>
  </section>
</template>
<style scoped>
.post-page { display: grid; gap: 10px; color: #334155; }
.card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 14px 16px 16px; }
h2 { margin: 0 0 12px; font-size: 15px; }
.filter, .actions, .pager, .thumbs, .ops { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.filter { margin-bottom: 12px; }
.filter input { width: 220px; }
input, select { height: 32px; padding: 0 10px; border: 1px solid #d1d5db; border-radius: 4px; }
.actions { margin-bottom: 10px; }
.actions button, .pager button, .modal-actions button { height: 32px; padding: 0 12px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; font-size: 12px; }
.outline { background: #0f766e; }
.spacer { flex: 1; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 8px; border-bottom: 1px solid #f1f5f9; text-align: left; }
th { background: #f8fafc; color: #64748b; }
.check { width: 36px; }
.thumbs img { width: 42px; height: 42px; object-fit: cover; border-radius: 4px; }
.count { padding: 1px 4px; background: #0f766e; color: #fff; border-radius: 3px; font-size: 10px; }
.muted, .empty { color: #94a3b8; }
.empty { text-align: center; padding: 36px 8px; }
.ops button { width: 26px; height: 26px; padding: 0; background: #fff; color: #0f766e; border: 1px solid #99f6e4; }
.ops .danger { color: #ef4444; border-color: #fecaca; }
.pager { margin-top: 10px; color: #64748b; font-size: 12px; }
.pager .current { background: #0f766e; }
.pager input { width: 48px; }
.flash { font-size: 13px; }
.flash.error { color: #b91c1c; }
.flash.ok { color: #166534; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.mask { position: fixed; inset: 0; display: grid; place-items: center; background: rgba(15,23,42,.35); }
.modal { width: min(380px, calc(100vw - 32px)); padding: 16px; display: grid; gap: 10px; background: #fff; border-radius: 8px; }
.primary { background: #0f766e; color: #fff; border: 0; border-radius: 4px; height: 32px; padding: 0 12px; }
.table-scroll { overflow-x: auto; }
.table-scroll table { min-width: 1000px; }
.modal { width: min(720px, calc(100vw - 32px)); max-height: 85vh; overflow: auto; }
.modal label { display: grid; gap: 6px; }
.modal textarea { min-height: 80px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; background: #f8fafc; padding: 8px; }
.preview-row { border-top: 1px solid #e5e7eb; }
.detail-link { color: #0f766e; background: none; border: 0; padding: 0; text-align: left; }
.selection-summary, .muted, .notice { font-size: 12px; line-height: 1.6; }
.notice { padding: 10px; background: #fff7ed; }
button:disabled { opacity: .5; cursor: not-allowed; }
.ops .danger { width: auto; }
@media (max-width: 600px) { .filter input { max-width: 100%; } .card { min-width: 0; padding: 12px; } }
</style>
