<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { ProductView } from '@cloudctl/api-contracts'
import { createProductCatalog } from '@/api/product-catalog'
import { downloadDataUrl, formatDateTime } from '@/data/product-fields'
import {
  createProductGroup,
  DEFAULT_GROUP_NAME,
  deleteProductGroup,
  listProductGroups,
  productsUsingGroup,
  replaceProductGroupName,
  updateProductGroup,
  type ProductGroup,
} from '@/data/product-groups'

const catalog = createProductCatalog()
const products = ref<ProductView[]>([])
const groups = ref<ProductGroup[]>(listProductGroups())
const loading = ref(false)
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

function toggleSort(key: 'id' | 'createdAt') {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else {
    sortKey.value = key
    sortDir.value = key === 'createdAt' ? 'desc' : 'asc'
  }
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    products.value = await catalog.list()
    groups.value = listProductGroups(products.value)
    if (page.value > totalPages.value) page.value = 1
  } catch (error) {
    errorMessage.value = `加载分组失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    loading.value = false
  }
}

async function renameProducts(from: string, to: string) {
  if (from === to) return
  for (const product of productsUsingGroup(products.value, from)) {
    const next = replaceProductGroupName(product, from, to)
    if (!next) continue
    await catalog.save({
      id: next.id,
      expectedRevision: next.revision,
      payload: {
        spuCode: next.spuCode,
        title: next.title,
        description: next.description,
        category: next.category,
        price: next.price,
        stock: next.stock,
        mediaAssetIds: next.mediaAssetIds,
        attributes: next.attributes,
      },
    })
  }
}

function openCreate() {
  dialog.value = { mode: 'create', name: '', remark: '' }
}

function openEdit(group: ProductGroup) {
  dialog.value = { mode: 'edit', id: group.id, name: group.name, remark: group.remark }
}

function startInline(group: ProductGroup, field: 'name' | 'remark') {
  editingId.value = group.id
  editingField.value = field
  draft.value = group[field]
}

async function commitInline() {
  const id = editingId.value
  const field = editingField.value
  const value = draft.value
  editingId.value = ''
  editingField.value = ''
  if (!id || !field) return
  const group = groups.value.find((item) => item.id === id)
  if (!group || group[field] === value) return
  await saveGroup(group.id, { [field]: value })
}

async function saveDialog() {
  if (!dialog.value) return
  try {
    if (dialog.value.mode === 'create') {
      createProductGroup({ name: dialog.value.name, remark: dialog.value.remark }, products.value)
      successMessage.value = '已添加分组'
    } else if (dialog.value.id) {
      await saveGroup(dialog.value.id, { name: dialog.value.name, remark: dialog.value.remark })
    }
    dialog.value = null
    await load()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  }
}

async function saveGroup(id: string, patch: { name?: string; remark?: string }) {
  const current = groups.value.find((item) => item.id === id)
  if (!current) return
  const previousName = current.name
  const updated = updateProductGroup(id, patch, products.value)
  if (patch.name && patch.name.trim() && patch.name.trim() !== previousName) {
    await renameProducts(previousName, updated.name)
  }
  successMessage.value = '已保存分组'
  await load()
}

async function confirmDelete() {
  const group = pendingDelete.value
  pendingDelete.value = null
  if (!group) return
  try {
    await renameProducts(group.name, DEFAULT_GROUP_NAME)
    groups.value = deleteProductGroup(group.id, products.value)
    successMessage.value = `已删除「${group.name}」，相关商品已归入${DEFAULT_GROUP_NAME}`
    await load()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  }
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
  successMessage.value = '已还原筛选'
}

function exportCsv() {
  const rows = [['ID', '分组名', '备注', '添加时间'], ...filtered.value.map((item) => [item.id, item.name, item.remark, formatDateTime(item.createdAt)])]
  downloadDataUrl(`data:text/csv;charset=utf-8,${encodeURIComponent(rows.map((line) => line.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(',')).join('\n'))}`, '商品分组.csv')
}

function printList() {
  window.print()
}

function goPage(next: number) {
  page.value = Math.min(totalPages.value, Math.max(1, next))
  jumpPage.value = String(page.value)
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="group-page">
    <div class="toolbar">
      <strong>商品分组管理</strong>
    </div>

    <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
    <p v-if="successMessage" class="flash ok">{{ successMessage }}</p>

    <div class="table-card">
      <div class="action-row">
        <button class="primary" type="button" @click="openCreate">添加分组</button>
        <span class="spacer" />
        <button class="primary" type="button" @click="filterOpen = true">筛选</button>
        <button class="primary" type="button" @click="resetFilters">还原</button>
        <button class="primary" type="button" @click="exportCsv">导出</button>
        <button class="primary" type="button" @click="printList">打印</button>
      </div>
      <table>
        <thead>
          <tr>
            <th class="sortable" @click="toggleSort('id')">ID <span>{{ sortKey === 'id' ? (sortDir === 'asc' ? '↑' : '↓') : '↕' }}</span></th>
            <th>分组名</th>
            <th>备注</th>
            <th class="sortable" @click="toggleSort('createdAt')">添加时间 <span>{{ sortKey === 'createdAt' ? (sortDir === 'asc' ? '↑' : '↓') : '↕' }}</span></th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="paged.length === 0">
            <td colspan="5" class="empty">{{ loading ? '加载中...' : '还没有商品分组。点左上角「添加分组」创建一个。' }}</td>
          </tr>
          <tr v-for="group in paged" :key="group.id">
            <td>{{ group.id }}</td>
            <td>
              <input
                v-if="editingId === group.id && editingField === 'name'"
                v-model="draft"
                aria-label="分组名"
                @blur="commitInline"
                @keydown.enter.prevent="commitInline"
              />
              <button v-else class="cell" type="button" @click="startInline(group, 'name')">{{ group.name }}</button>
            </td>
            <td>
              <input
                v-if="editingId === group.id && editingField === 'remark'"
                v-model="draft"
                aria-label="备注"
                @blur="commitInline"
                @keydown.enter.prevent="commitInline"
              />
              <button v-else class="cell muted" type="button" @click="startInline(group, 'remark')">{{ group.remark || '点击填写备注' }}</button>
            </td>
            <td>{{ formatDateTime(group.createdAt) }}</td>
            <td class="ops">
              <button type="button" title="编辑" @click="openEdit(group)">✎</button>
              <button class="danger" type="button" title="删除" :disabled="Boolean(group.system)" @click="pendingDelete = group">🗑</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="pager">
        <button type="button" :disabled="page <= 1" @click="goPage(page - 1)">‹</button>
        <button class="current" type="button">{{ page }}</button>
        <button type="button" :disabled="page >= totalPages" @click="goPage(page + 1)">›</button>
        <span>到第</span>
        <input v-model="jumpPage" />
        <span>页</span>
        <button type="button" @click="goPage(Number(jumpPage) || 1)">确定</button>
        <span>共 {{ filtered.length }} 条</span>
        <select v-model.number="pageSize" @change="page = 1">
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

    <div v-if="dialog" class="mask" @click.self="dialog = null">
      <div class="modal">
        <h3>{{ dialog.mode === 'create' ? '添加分组' : '编辑分组' }}</h3>
        <label>分组名<input v-model="dialog.name" /></label>
        <label>备注<input v-model="dialog.remark" /></label>
        <div class="modal-actions">
          <button type="button" @click="dialog = null">取消</button>
          <button class="primary" type="button" @click="saveDialog">确定</button>
        </div>
      </div>
    </div>

    <div v-if="filterOpen" class="mask" @click.self="filterOpen = false">
      <div class="modal">
        <h3>筛选分组</h3>
        <label>关键字<input v-model="filterName" placeholder="ID、分组名或备注" /></label>
        <div class="modal-actions">
          <button type="button" @click="filterOpen = false">取消</button>
          <button class="primary" type="button" @click="applyFilter">确定</button>
        </div>
      </div>
    </div>

    <div v-if="pendingDelete" class="mask" @click.self="pendingDelete = null">
      <div class="modal">
        <h3>删除分组</h3>
        <p>确定删除「{{ pendingDelete.name }}」吗？该分组下的商品会归入{{ DEFAULT_GROUP_NAME }}。</p>
        <div class="modal-actions">
          <button type="button" @click="pendingDelete = null">取消</button>
          <button class="danger-fill" type="button" @click="confirmDelete">确定删除</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.group-page { display: grid; gap: 10px; color: #334155; }
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
.modal { width: min(420px, calc(100vw - 32px)); padding: 16px; background: #fff; border-radius: 8px; display: grid; gap: 10px; }
.modal h3, .modal p { margin: 0; }
.modal label { display: grid; gap: 6px; font-size: 13px; color: #64748b; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
.danger-fill { color: #fff !important; background: #dc2626 !important; border-color: #dc2626 !important; }
</style>
