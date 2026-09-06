<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createPostCatalog } from '@/api/post-catalog'
import { downloadDataUrl } from '@/data/product-fields'
import { clipText, formatDateTime, type PostRecord } from '@/data/post-fields'

const router = useRouter()
const catalog = createPostCatalog()
const posts = ref<PostRecord[]>([])
const selectedIds = ref<string[]>([])
const searchQuery = ref('')
const groupFilter = ref('')
const loading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const page = ref(1)
const pageSize = ref(10)
const jumpPage = ref('1')
const dialog = ref<{ title: string; field: string; value: string } | null>(null)

const groups = computed(() => [...new Set(posts.value.map((item) => item.groupName || '默认分组'))])
const filtered = computed(() => posts.value.filter((post) => {
  const haystack = `${post.title}${post.body}${post.notes}${post.topics.join('')}`.toLowerCase()
  if (searchQuery.value && !haystack.includes(searchQuery.value.trim().toLowerCase())) return false
  if (groupFilter.value && post.groupName !== groupFilter.value) return false
  return true
}))
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const allSelected = computed({
  get: () => paged.value.length > 0 && paged.value.every((item) => selectedIds.value.includes(item.id)),
  set: (value: boolean) => {
    selectedIds.value = value
      ? [...new Set([...selectedIds.value, ...paged.value.map((item) => item.id)])]
      : selectedIds.value.filter((id) => !paged.value.some((item) => item.id === id))
  },
})

async function loadPosts() {
  loading.value = true
  errorMessage.value = ''
  try {
    posts.value = await catalog.list()
  } catch (error) {
    errorMessage.value = `加载帖子失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    loading.value = false
  }
}

function selectedPosts() {
  return posts.value.filter((item) => selectedIds.value.includes(item.id))
}

async function applyBatch() {
  if (!dialog.value) return
  const { field, value } = dialog.value
  for (const post of selectedPosts()) {
    if (field === 'group') post.groupName = value
    if (field === 'append') post.body = `${post.body}${value}`
    if (field === 'replace') {
      const [from, to] = value.split('=>')
      post.body = post.body.split(from ?? '').join(to ?? value)
    }
    await catalog.save({ id: post.id, post })
  }
  successMessage.value = `已更新 ${selectedIds.value.length} 条帖子`
  dialog.value = null
  selectedIds.value = []
  await loadPosts()
}

async function removeSelected() {
  if (selectedIds.value.length === 0) {
    errorMessage.value = '请先勾选帖子'
    return
  }
  await catalog.remove(selectedIds.value)
  selectedIds.value = []
  successMessage.value = '已删除选中帖子'
  await loadPosts()
}

function printList() {
  window.print()
}

function exportCsv() {
  const rows = [['帖子分组', '标题', '内容', '地点', '话题', '添加时间', '帖子备注'], ...filtered.value.map((post) => [post.groupName, post.title, post.body.replaceAll('\n', ' '), post.location, post.topics.join(' '), formatDateTime(post.updatedAt), post.notes])]
  downloadDataUrl(`data:text/csv;charset=utf-8,${encodeURIComponent(rows.map((line) => line.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(',')).join('\n'))}`, '帖子列表.csv')
}

onMounted(() => {
  void loadPosts()
})
</script>

<template>
  <section class="post-page">
    <div class="card">
      <h2>帖子/笔记列表</h2>
      <div class="filter">
        <input v-model="searchQuery" placeholder="搜索帖子标题、内容" />
        <select v-model="groupFilter">
          <option value="">帖子分组</option>
          <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
        </select>
        <button class="primary" type="button" @click="page = 1">查找</button>
      </div>
      <div class="actions">
        <button type="button" @click="removeSelected">批量删除</button>
        <button type="button" @click="dialog = { title: '修改分组', field: 'group', value: '默认分组' }">修改分组</button>
        <button type="button" @click="dialog = { title: '追加描述', field: 'append', value: '' }">追加描述</button>
        <button type="button" @click="dialog = { title: '替换内容', field: 'replace', value: '原文=>替换后' }">替换内容</button>
        <button type="button" @click="selectedPosts().forEach((post) => post.images.forEach((image, index) => downloadDataUrl(image, `${post.title}-${index + 1}.jpg`)))">下载图片</button>
        <span class="spacer" />
        <button class="outline" type="button">筛选</button>
        <button class="outline" type="button" @click="searchQuery = ''; groupFilter = ''">还原</button>
        <button class="outline" type="button" @click="exportCsv">导出</button>
        <button class="outline" type="button" @click="printList">打印</button>
      </div>
      <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok">{{ successMessage }}</p>
      <table>
        <thead>
          <tr>
            <th class="check"><input v-model="allSelected" type="checkbox" /></th>
            <th>帖子分组</th>
            <th>帖子图片/视频</th>
            <th>标题</th>
            <th>内容</th>
            <th>地点</th>
            <th>话题</th>
            <th>添加时间</th>
            <th>帖子备注</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="10" class="empty">加载中...</td></tr>
          <tr v-else-if="paged.length === 0"><td colspan="10" class="empty">还没有帖子。到「帖子编辑」保存后会出现在这里。</td></tr>
          <tr v-for="post in paged" :key="post.id">
            <td class="check"><input type="checkbox" :checked="selectedIds.includes(post.id)" @change="selectedIds = selectedIds.includes(post.id) ? selectedIds.filter((id) => id !== post.id) : [...selectedIds, post.id]" /></td>
            <td>{{ post.groupName }}</td>
            <td>
              <div class="thumbs">
                <img v-for="(image, index) in post.images.slice(0, 3)" :key="index" :src="image" alt="" />
                <span v-if="post.images.length" class="count">{{ post.images.length }}张</span>
                <span v-else class="muted">无图</span>
              </div>
            </td>
            <td>{{ clipText(post.title, 16) }}</td>
            <td>{{ clipText(post.body, 18) }}</td>
            <td>{{ post.location }}</td>
            <td>{{ post.topics.join(' ') }}</td>
            <td>{{ formatDateTime(post.updatedAt || post.createdAt) }}</td>
            <td>{{ post.notes }}</td>
            <td class="ops">
              <button type="button" title="编辑" @click="router.push(`/operations/post-management/post-management-01?id=${post.id}`)">✎</button>
              <button type="button" title="复制" @click="catalog.duplicate(post).then(loadPosts)">⧉</button>
              <button type="button" title="下载" @click="post.images.forEach((image, index) => downloadDataUrl(image, `${post.title}-${index + 1}.jpg`))">⬇</button>
              <button class="danger" type="button" title="删除" @click="selectedIds = [post.id]; removeSelected()">✕</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="pager">
        <button type="button" :disabled="page <= 1" @click="page -= 1">‹</button>
        <button class="current" type="button">{{ page }}</button>
        <button type="button" :disabled="page >= totalPages" @click="page += 1">›</button>
        <span>到第</span>
        <input v-model="jumpPage" />
        <span>页</span>
        <button type="button" @click="page = Math.max(1, Number(jumpPage) || 1)">确定</button>
        <span>共 {{ filtered.length }} 条</span>
        <select v-model.number="pageSize"><option :value="10">10 条/页</option><option :value="20">20 条/页</option></select>
      </div>
    </div>
    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>该页面可查询您所有的帖子/笔记，表格后方 ✎ 表示编辑帖子，⧉ 表示复制新增一个相同的帖子，✕ 表示删除帖子。</li>
        <li>点击表单的右上角筛选，可选择显示帖子的更多信息。</li>
        <li>页面顶端可设置帖子搜索的条件，页面底部可跳转页数和编辑每页显示数量。</li>
        <li>勾选帖子后点击替换内容，填好原文本即可批量替换，确认无误再点确定。</li>
      </ol>
    </div>
    <div v-if="dialog" class="mask" @click.self="dialog = null">
      <div class="modal">
        <h3>{{ dialog.title }}</h3>
        <input v-model="dialog.value" />
        <div class="modal-actions">
          <button type="button" @click="dialog = null">取消</button>
          <button class="primary" type="button" @click="applyBatch">确定</button>
        </div>
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
</style>
