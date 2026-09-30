<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { ProductView } from '@cloudctl/api-contracts'
import { createProductCatalog } from '@/api/product-catalog'
import { downloadDataUrl, formatDateTime } from '@/data/product-fields'
import {
  createProductGroup,
  deleteProductGroup,
  listProductGroups,
  productsUsingGroup,
  replaceProductGroupName,
  updateProductGroup,
  type ProductGroup,
} from '@/data/product-groups'

const catalog = createProductCatalog()
const products = ref<ProductView[]>([])
const groups = ref<ProductGroup[]>([])
const loading = ref(false)
const busy = ref(false)
const loadFailed = ref(false)
const root = ref<HTMLElement | null>(null)
let previousFocus: HTMLElement | null = null
const errorMessage = ref('')
const successMessage = ref('')
const page = ref(1)
const pageSize = ref(10)
const jumpPage = ref('1')
const sortKey = ref<'id' | 'createdAt'>('createdAt')
const sortDir = ref<'asc' | 'desc'>('desc')
const filterOpen = ref(false)
const filterName = ref('')
const appliedFilter = ref('')
const dialog = ref<{ mode: 'create' | 'edit'; id?: string; name: string; remark: string } | null>(null)
const editingId = ref('')
const editingField = ref<'name' | 'remark' | ''>('')
const draft = ref('')
const pendingDelete = ref<ProductGroup | null>(null)

const filtered = computed(() => {
  const keyword = appliedFilter.value.trim().toLowerCase()
  const rows = keyword
    ? groups.value.filter((item) => `${item.id}${item.name}${item.remark}`.toLowerCase().includes(keyword))
    : groups.value
  const direction = sortDir.value === 'asc' ? 1 : -1
  return [...rows].sort((left, right) => {
    const a = sortKey.value === 'id' ? left.id : left.createdAt
    const b = sortKey.value === 'id' ? right.id : right.createdAt
    return a.localeCompare(b) * direction
  })
})
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))

watch([totalPages, pageSize], () => goPage(page.value))
watch(() => Boolean(dialog.value || filterOpen.value || pendingDelete.value), async (opened) => {
  if (opened) {
    previousFocus = document.activeElement as HTMLElement | null
    await nextTick()
    root.value?.querySelector<HTMLElement>('.modal input, .modal button')?.focus()
  } else previousFocus?.focus()
})
function modalKeys(event: KeyboardEvent) {
  if (event.key === 'Escape' && !busy.value) { dialog.value = null; filterOpen.value = false; pendingDelete.value = null }
  if (event.key !== 'Tab') return
  const controls = [...(event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('input:not(:disabled), button:not(:disabled)')]
  const first = controls[0]
  const last = controls.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}

function toggleSort(key: 'id' | 'createdAt') {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else {
    sortKey.value = key
    sortDir.value = key === 'createdAt' ? 'desc' : 'asc'
  }
}

async function load(preserveError = false) {
  if (loading.value) return
  loading.value = true
  loadFailed.value = false
  if (!preserveError) errorMessage.value = ''
  try {
    products.value = await catalog.list()
    groups.value = listProductGroups(products.value)
    if (page.value > totalPages.value) page.value = 1
  } catch (error) {
    loadFailed.value = true
    errorMessage.value += `加载分组失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    loading.value = false
  }
}


function openCreate() {
  if (busy.value || loading.value || loadFailed.value) return
  dialog.value = { mode: 'create', name: '', remark: '' }
}

function openEdit(group: ProductGroup) {
  if (busy.value || loading.value || loadFailed.value) return
  dialog.value = { mode: 'edit', id: group.id, name: group.name, remark: group.remark }
}

function startInline(group: ProductGroup, field: 'name' | 'remark') {
  if (busy.value || loading.value || loadFailed.value || (field === 'name' && group.system)) return
  editingId.value = group.id
  editingField.value = field
  draft.value = group[field]
}

async function commitInline() {
  if (busy.value) return
  const id = editingId.value
  const field = editingField.value
  const value = draft.value
  editingId.value = ''
  editingField.value = ''
  if (!id || !field) return
  const group = groups.value.find((item) => item.id === id)
  if (!group || group[field] === value) return
  try { await saveGroup(group.id, { [field]: value }) }
  catch (error) { errorMessage.value = error instanceof Error ? error.message : String(error) }
}

async function saveDialog() {
  if (!dialog.value || busy.value) return
  const input = { ...dialog.value }
  try {
    if (input.mode === 'create') {
      busy.value = true
      createProductGroup({ name: input.name, remark: input.remark }, products.value)
      successMessage.value = '已在当前浏览器添加分组建议'
      await load()
    } else if (input.id) await saveGroup(input.id, { name: input.name, remark: input.remark })
    dialog.value = null
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : String(error) }
  finally { busy.value = false }
}

async function saveGroup(id: string, patch: { name?: string; remark?: string }) {
  if (busy.value) return
  const current = groups.value.find((item) => item.id === id)
  if (!current) throw new Error('分组不存在，请刷新后重试')
  const name = (patch.name ?? current.name).trim()
  if (!name) throw new Error('请填写分组名')
  if (current.system && name !== current.name) throw new Error('默认分组名不能修改')
  if (groups.value.some((item) => item.id !== id && item.name === name)) throw new Error('目标分组已存在，请在商品列表将剩余商品移入该组')
  const originalProducts = [...products.value]
  const frozenPatch = { name, remark: (patch.remark ?? current.remark).trim() }
  const targets = name === current.name ? [] : productsUsingGroup(originalProducts, current.name).map((product) => replaceProductGroupName(product, current.name, name)).filter((product): product is ProductView => Boolean(product))
  busy.value = true
  successMessage.value = ''
  errorMessage.value = ''
  let completed = 0
  try {
    for (const next of targets) {
      const saved = await catalog.save({ id: next.id, expectedRevision: next.revision, payload: {
        spuCode: next.spuCode, title: next.title, description: next.description,
        category: next.category, price: next.price, stock: next.stock,
        mediaAssetIds: next.mediaAssetIds, attributes: next.attributes,
      } })
      products.value = products.value.map((item) => item.id === saved.id ? saved : item)
      completed += 1
    }
    // Use the original memberships so the local helper does not synthesize a duplicate target before rename.
    updateProductGroup(id, frozenPatch, originalProducts)
    successMessage.value = '已保存当前浏览器的分组建议和备注；已确认更新 ' + completed + ' 个商品的分组'
    await load()
  } catch (error) {
    errorMessage.value = '分组保存未完成：' + (error instanceof Error ? error.message : String(error)) + '。已确认更新 ' + completed + ' 个，未确认或未发送 ' + (targets.length - completed) + ' 个。本地源分组名称未提前修改；请核对刷新后的两组，在商品列表移动剩余商品，不要重复已成功项。'
    dialog.value = null
    await load(true)
  } finally { busy.value = false }
}

function requestDelete(group: ProductGroup) {
  if (busy.value || loading.value || loadFailed.value) return
  if (productsUsingGroup(products.value, group.name).length) {
    errorMessage.value = '该分组仍有商品，请先在商品列表移组后再删除空分组建议'
    return
  }
  pendingDelete.value = { ...group }
}

async function confirmDelete() {
  if (busy.value || !pendingDelete.value) return
  const group = { ...pendingDelete.value }
  busy.value = true
  errorMessage.value = ''
  try {
    // Recheck current membership before deleting the local suggestion.
    products.value = await catalog.list()
    if (productsUsingGroup(products.value, group.name).length) throw new Error('该分组仍有商品，请先移组；不会自动迁移到默认分组')
    groups.value = deleteProductGroup(group.id, products.value)
    successMessage.value = '已删除当前浏览器中的空分组建议：' + group.name
    pendingDelete.value = null
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : String(error) }
  finally { busy.value = false }
}

function applyFilter() {
  appliedFilter.value = filterName.value
  filterOpen.value = false
  page.value = 1
}

function resetFilters() {
  filterName.value = ''
  appliedFilter.value = ''
  page.value = 1
}

function exportCsv() {
  const rows = [['本地标识', '分组名', '本地备注', '本地记录参考时间'], ...filtered.value.map((item) => [item.id, item.name, item.remark, item.system ? '系统默认（无真实创建时间）' : formatDateTime(item.createdAt)])]
  downloadDataUrl(`data:text/csv;charset=utf-8,${encodeURIComponent(rows.map((line) => line.map((cell) => `"${(/^[\s]*[=+@-]/.test(String(cell)) ? "'" + cell : String(cell)).replaceAll('"', '""')}"`).join(',')).join('\n'))}`, '商品分组.csv')
}

function printList() {
  window.print()
}

function goPage(next: number) {
  page.value = Math.min(totalPages.value, Math.max(1, Math.floor(Number.isFinite(next) ? next : 1)))
  jumpPage.value = String(page.value)
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section ref="root" class="group-page">
    <div class="toolbar">
      <strong>商品分组管理</strong>
    </div>

    <p class="boundary">分组名称建议、备注、标识和参考时间仅保存在当前浏览器，非云端分组元数据。商品归属来自商品记录；重命名会逐个保存商品，不能保证原子完成。</p>
    <p v-if="errorMessage" role="alert" class="flash error">{{ errorMessage }}</p>
    <p v-if="successMessage" role="status" class="flash ok">{{ successMessage }}</p>

    <div class="table-card">
      <div class="action-row">
        <button class="primary" type="button" :disabled="busy || loading || loadFailed" @click="openCreate">添加分组</button>
        <span class="spacer" />
        <button class="primary" type="button" @click="filterOpen = true">筛选</button>
        <button class="primary" type="button" @click="resetFilters">还原</button>
        <button class="primary" type="button" @click="exportCsv">导出</button>
        <button class="primary" type="button" @click="printList">打印</button>
      </div>
      <div class="table-wrap" tabindex="0" role="region" aria-label="分组表，可横向滚动">
        <table>
          <thead>
            <tr>
              <th><button class="cell sortable" type="button" @click="toggleSort('id')">本地标识 <span>{{ sortKey === 'id' ? (sortDir === 'asc' ? '↑' : '↓') : '↕' }}</span></button></th>
              <th>分组名</th>
              <th>本地备注</th>
              <th><button class="cell sortable" type="button" @click="toggleSort('createdAt')">本地记录参考时间 <span>{{ sortKey === 'createdAt' ? (sortDir === 'asc' ? '↑' : '↓') : '↕' }}</span></button></th>
              <th>当前商品数</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading"><td colspan="6" class="empty">加载中…</td></tr>
            <tr v-else-if="loadFailed"><td colspan="6" class="empty">无法加载分组。<button type="button" @click="load()">重试加载</button></td></tr>
            <tr v-else-if="paged.length === 0"><td colspan="6" class="empty">{{ appliedFilter ? '没有符合条件的分组，请还原筛选。' : '尚无分组建议，可添加当前浏览器的分组。' }}</td></tr>
            <tr v-for="group in (loading || loadFailed ? [] : paged)" :key="group.id">
              <td>{{ group.id }}</td>
              <td>
                <input
                  v-if="editingId === group.id && editingField === 'name'"
                  v-model="draft" :disabled="busy" @keydown.esc="editingId = ''; editingField = ''"
                  aria-label="分组名"
                  @blur="commitInline"
                  @keydown.enter.prevent="commitInline"
                />
                <button v-else class="cell" type="button" :disabled="busy || group.system" @click="startInline(group, 'name')">{{ group.name }}</button>
              </td>
              <td>
                <input
                  v-if="editingId === group.id && editingField === 'remark'"
                  v-model="draft" :disabled="busy" @keydown.esc="editingId = ''; editingField = ''"
                  aria-label="备注"
                  @blur="commitInline"
                  @keydown.enter.prevent="commitInline"
                />
                <button v-else class="cell muted" type="button" :disabled="busy" @click="startInline(group, 'remark')">{{ group.remark || '点击填写备注' }}</button>
              </td>
              <td>{{ group.system ? '系统默认（无真实创建时间）' : formatDateTime(group.createdAt) }}</td>
              <td>{{ productsUsingGroup(products, group.name).length }}</td>
              <td class="ops">
                <button type="button" :aria-label="'编辑分组 ' + group.name" title="编辑" :disabled="busy" @click="openEdit(group)">✎</button>
                <button class="danger" type="button" :aria-label="'删除分组 ' + group.name" title="删除本地空分组建议" :disabled="busy || Boolean(group.system)" @click="requestDelete(group)">🗑</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="pager">
        <button type="button" :disabled="page <= 1" @click="goPage(page - 1)">‹</button>
        <button class="current" type="button">{{ page }}</button>
        <button type="button" :disabled="page >= totalPages" @click="goPage(page + 1)">›</button>
        <span>到第</span>
        <input v-model="jumpPage" aria-label="跳转页码" inputmode="numeric" />
        <span>页</span>
        <button type="button" @click="goPage(Number(jumpPage) || 1)">确定</button>
        <span>共 {{ filtered.length }} 条</span>
        <select aria-label="每页条数" v-model.number="pageSize" @change="page = 1">
          <option :value="10">10条/页</option>
          <option :value="20">20条/页</option>
          <option :value="50">50条/页</option>
        </select>
      </div>
    </div>

    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>商品分组可以帮助您更好地管理商品，建议为每部设备或同一类别宝贝建立商品分组</li>
        <li>点击操作栏的 <span class="tag">编辑</span> 图标，或直接点击分组名/备注的单元格，可修改分组名或备注</li>
      </ol>
    </div>

    <div v-if="dialog" class="mask" @click.self="!busy && (dialog = null)">
      <div class="modal" role="dialog" aria-modal="true" aria-label="分组操作" @keydown="modalKeys">
        <h3>{{ dialog.mode === 'create' ? '添加分组' : '编辑分组' }}</h3>
        <label>分组名<input v-model="dialog.name" :disabled="busy || (dialog.mode === 'edit' && Boolean(groups.find((item) => item.id === dialog?.id)?.system))" /></label>
        <label>备注<input v-model="dialog.remark" :disabled="busy" /></label>
        <div class="modal-actions">
          <button type="button" :disabled="busy" @click="dialog = null">取消</button>
          <button class="primary" type="button" :disabled="busy" @click="saveDialog">{{ busy ? '保存中…' : '确定' }}</button>
        </div>
      </div>
    </div>

    <div v-if="filterOpen" class="mask" @click.self="filterOpen = false">
      <div class="modal" role="dialog" aria-modal="true" aria-label="分组操作" @keydown="modalKeys">
        <h3>筛选分组</h3>
        <label>关键字<input v-model="filterName" placeholder="ID、分组名或备注" /></label>
        <div class="modal-actions">
          <button type="button" @click="filterOpen = false">取消</button>
          <button class="primary" type="button" @click="applyFilter">确定</button>
        </div>
      </div>
    </div>

    <div v-if="pendingDelete" class="mask" @click.self="!busy && (pendingDelete = null)">
      <div class="modal" role="dialog" aria-modal="true" aria-label="分组操作" @keydown="modalKeys">
        <h3>删除分组</h3>
        <p>确定删除「{{ pendingDelete.name }}」吗？仅删除当前浏览器的空分组建议，不自动迁移任何内容。</p>
        <div class="modal-actions">
          <button type="button" :disabled="busy" @click="pendingDelete = null">取消</button>
          <button class="danger-fill" type="button" :disabled="busy" @click="confirmDelete">确定删除本地建议</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.group-page { min-width: 0; grid-template-columns: minmax(0, 1fr); display: grid; gap: 10px; color: #334155; }
.toolbar, .table-card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.toolbar { min-height: 44px; padding: 8px 12px; display: flex; align-items: center; }
.action-row, .pager { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.action-row { padding: 12px 12px 8px; }
.spacer { flex: 1; }
.primary, .outline, .pager button, .modal-actions button { height: 32px; padding: 0 12px; border-radius: 4px; border: 1px solid #0f766e; background: #0f766e; color: #fff; font-size: 12px; }
.outline, .pager button, .modal-actions button { color: #0f766e; background: #fff; }
.flash { margin: 0; padding: 8px 12px; border-radius: 6px; font-size: 13px; }
.flash.error { color: #b91c1c; background: #fef2f2; }
.flash.ok { color: #166534; background: #f0fdf4; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 10px 8px; border-bottom: 1px solid #f1f5f9; text-align: left; }
th { color: #64748b; font-weight: 600; background: #f8fafc; }
.sortable { cursor: pointer; white-space: nowrap; }
.cell { border: 0; background: none; padding: 0; color: inherit; text-align: left; min-height: 24px; }
.cell.muted { color: #64748b; }
td input { height: 32px; width: min(240px, 100%); padding: 0 8px; border: 1px solid #0f766e; border-radius: 4px; }
.ops { white-space: nowrap; }
.ops button { width: 26px; height: 26px; padding: 0; margin-right: 4px; color: #0f766e; background: #fff; border: 1px solid #99f6e4; }
.ops .danger { color: #ef4444; border-color: #fecaca; }
.ops .danger:disabled { color: #cbd5e1; border-color: #e2e8f0; }
.empty { padding: 48px 12px; text-align: center; color: #94a3b8; }
.pager { padding: 10px 12px 12px; color: #64748b; font-size: 12px; }
.pager .current { color: #fff; background: #0f766e; }
.pager input, .pager select, .modal input { height: 32px; padding: 0 10px; border: 1px solid #d1d5db; border-radius: 4px; }
.pager input { width: 48px; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.tag { display: inline-block; padding: 0 6px; border-radius: 4px; background: #ecfdf5; color: #0f766e; }
.mask { position: fixed; inset: 0; background: rgb(15 23 42 / 0.35); display: grid; place-items: center; z-index: 40; }
.modal { box-sizing: border-box; max-height: calc(100dvh - 32px); overflow: auto; width: min(420px, calc(100vw - 32px)); padding: 16px; background: #fff; border-radius: 8px; display: grid; gap: 10px; }
.modal h3, .modal p { margin: 0; }
.modal label { display: grid; gap: 6px; font-size: 13px; color: #64748b; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
.danger-fill { color: #fff !important; background: #dc2626 !important; border-color: #dc2626 !important; }
.boundary { margin: 0; padding: 12px; background: #f8fafc; font-size: 13px; line-height: 1.7; }
.table-card { min-width: 0; }
.table-wrap { max-width: 100%; overflow-x: auto; }
table { min-width: 680px; }
button:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible, input:focus-visible, select:focus-visible, .table-wrap:focus-visible { outline: 2px solid #0f766e; outline-offset: 2px; }
@media (max-width: 480px) { .modal input { min-width: 0; width: 100%; box-sizing: border-box; } }
</style>
