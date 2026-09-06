<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { ProductView } from '@cloudctl/api-contracts'
import { createProductCatalog } from '@/api/product-catalog'
import {
  clipText,
  downloadDataUrl,
  formatDateTime,
  normalizePrice,
  parseAttributes,
  productGroupName,
  productImages,
  productSpecLabel,
} from '@/data/product-fields'
import { createProductGroup, resolveProductGroups } from '@/data/product-groups'

const router = useRouter()
const catalog = createProductCatalog()
const products = ref<ProductView[]>([])
const selectedIds = ref<string[]>([])
const searchQuery = ref('')
const categoryFilter = ref('')
const groupFilter = ref('')
const minPrice = ref('')
const maxPrice = ref('')
const loading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const page = ref(1)
const pageSize = ref(10)
const jumpPage = ref('1')
const dialog = ref<{ title: string; field: string; value: string; placeholder: string } | null>(null)
const confirmDelete = ref(false)
const preview = ref<{ title: string; body: string } | null>(null)

const groups = computed(() => resolveProductGroups(products.value).map((item) => item.name))
const categories = computed(() => [...new Set(products.value.flatMap((item) => parseAttributes(item.attributes).brands))].sort())

const filteredProducts = computed(() => {
  return products.value.filter((product) => {
    const attributes = parseAttributes(product.attributes)
    const haystack = `${product.id}${product.title}${product.description}${product.spuCode}${attributes.notes}`.toLowerCase()
    if (searchQuery.value && !haystack.includes(searchQuery.value.trim().toLowerCase())) return false
    if (groupFilter.value && productGroupName(product) !== groupFilter.value) return false
    if (categoryFilter.value && !attributes.brands.includes(categoryFilter.value)) return false
    const price = Number(product.price)
    if (minPrice.value && Number.isFinite(price) && price < Number(minPrice.value)) return false
    if (maxPrice.value && Number.isFinite(price) && price > Number(maxPrice.value)) return false
    return true
  })
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredProducts.value.length / pageSize.value)))
const pagedProducts = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredProducts.value.slice(start, start + pageSize.value)
})
const pageNumbers = computed(() => {
  const pages = []
  for (let index = 1; index <= totalPages.value; index += 1) pages.push(index)
  return pages.slice(0, 8)
})

const allSelected = computed({
  get: () => pagedProducts.value.length > 0 && pagedProducts.value.every((item) => selectedIds.value.includes(item.id)),
  set: (value: boolean) => {
    if (value) selectedIds.value = [...new Set([...selectedIds.value, ...pagedProducts.value.map((item) => item.id)])]
    else selectedIds.value = selectedIds.value.filter((id) => !pagedProducts.value.some((item) => item.id === id))
  },
})

async function loadProducts() {
  loading.value = true
  errorMessage.value = ''
  try {
    products.value = await catalog.list()
    if (page.value > totalPages.value) page.value = 1
  } catch (error) {
    errorMessage.value = `加载商品失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    loading.value = false
  }
}

function toggleSelection(productId: string) {
  if (selectedIds.value.includes(productId)) selectedIds.value = selectedIds.value.filter((id) => id !== productId)
  else selectedIds.value = [...selectedIds.value, productId]
}

function selectedProducts() {
  return products.value.filter((item) => selectedIds.value.includes(item.id))
}

function openEdit(productId: string) {
  void router.push(`/operations/product-editor/product-editor-01?id=${productId}`)
}

async function copyProduct(product: ProductView) {
  try {
    await catalog.duplicate(product)
    successMessage.value = '已复制一个相同的宝贝'
    await loadProducts()
  } catch (error) {
    errorMessage.value = `复制失败：${error instanceof Error ? error.message : String(error)}`
  }
}

function downloadImages(product: ProductView) {
  const images = productImages(product)
  if (images.length === 0) {
    errorMessage.value = '这个宝贝还没有可下载的图片'
    return
  }
  images.forEach((image, index) => downloadDataUrl(image, `${product.title || 'product'}-${index + 1}.jpg`))
}

function showQr(product: ProductView) {
  const attributes = parseAttributes(product.attributes)
  preview.value = {
    title: '宝贝二维码',
    body: `标题：${product.title}\nID：${product.id}\n分享码：${attributes.shareCode || '未设置'}`,
  }
}

function openBatch(title: string, field: string, placeholder: string) {
  if (selectedIds.value.length === 0) {
    errorMessage.value = '请先勾选商品'
    return
  }
  dialog.value = { title, field, value: '', placeholder }
}

async function applyBatch() {
  if (!dialog.value) return
  const field = dialog.value.field
  const value = dialog.value.value
  const targets = selectedProducts()
  try {
    for (const product of targets) {
      const attributes = parseAttributes(product.attributes)
      if (field === 'price') product.price = normalizePrice(value)
      else if (field === 'stock') product.stock = Number(value) || 0
      else if (field === 'group') {
        attributes.groupName = value
        product.category = value || product.category
        if (value.trim()) {
          try { createProductGroup({ name: value.trim() }) } catch { /* already exists */ }
        }
      } else if (field === 'description') product.description = value
      else if (field === 'replace') product.description = product.description.split(dialog.value.value.split('=>')[0] ?? '').join(dialog.value.value.split('=>')[1] ?? dialog.value.value)
      else if (field === 'insertTitle') product.title = `${value}${product.title}`
      else if (field === 'insertDesc') product.description = `${value}${product.description}`
      else if (field === 'shipping') attributes.shippingFee = normalizePrice(value)
      else if (field === 'cost') attributes.costPrice = normalizePrice(value)
      else if (field === 'notes') attributes.notes = value
      else if (field === 'theme') attributes.theme = value.split(/[,，\s]+/).filter(Boolean)
      else if (field === 'share') attributes.shareCode = value
      else if (field === 'virtual') attributes.virtualProduct = value
      else if (field === 'brands') attributes.brands = value.split(/[,，\s]+/).filter(Boolean)
      else if (field === 'labels') attributes.imageLabels = value.split(/[,，\s]+/).filter(Boolean)
      else if (field === 'spec') attributes.specValues = value.split(/[,，\s]+/).filter(Boolean)
      else if (field === 'selfPickup') attributes.selfPickup = value !== '0'
      else if (field === 'freeShipping') attributes.freeShipping = value !== '0'
      await catalog.save({
        id: product.id,
        expectedRevision: product.revision,
        payload: {
          spuCode: product.spuCode,
          title: product.title,
          description: product.description,
          category: product.category,
          price: normalizePrice(product.price),
          stock: product.stock,
          mediaAssetIds: product.mediaAssetIds,
          attributes: { ...attributes },
        },
      })
    }
    successMessage.value = `已更新 ${targets.length} 个商品`
    dialog.value = null
    selectedIds.value = []
    await loadProducts()
  } catch (error) {
    errorMessage.value = `批量操作失败：${error instanceof Error ? error.message : String(error)}`
  }
}

async function deleteSelected() {
  if (selectedIds.value.length === 0) return
  try {
    await catalog.archive(selectedIds.value, '商品列表删除')
    successMessage.value = `已删除 ${selectedIds.value.length} 个商品，可在回收站规则下保留 3 天`
    confirmDelete.value = false
    selectedIds.value = []
    await loadProducts()
  } catch (error) {
    errorMessage.value = `删除失败：${error instanceof Error ? error.message : String(error)}`
  }
}

async function deleteOne(product: ProductView) {
  selectedIds.value = [product.id]
  confirmDelete.value = true
}

function requestDelete() {
  if (selectedIds.value.length === 0) {
    errorMessage.value = '请先勾选商品'
    return
  }
  confirmDelete.value = true
}

function printList() {
  window.print()
}

function exportCsv() {
  const header = ['商品分组', '标题', '描述', '规格', '价格', '下单链接', '添加时间', '商品备注']
  const rows = filteredProducts.value.map((product) => {
    const attributes = parseAttributes(product.attributes)
    return [
      productGroupName(product),
      product.title,
      product.description.replaceAll('\n', ' '),
      productSpecLabel(product),
      product.price,
      attributes.orderLink,
      formatDateTime(product.updatedAt ?? product.createdAt),
      attributes.notes,
    ]
  })
  const csv = [header, ...rows].map((line) => line.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(',')).join('\n')
  downloadDataUrl(`data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`, '商品列表.csv')
}

function resetFilters() {
  searchQuery.value = ''
  categoryFilter.value = ''
  groupFilter.value = ''
  minPrice.value = ''
  maxPrice.value = ''
  page.value = 1
}

function goPage(next: number) {
  page.value = Math.min(totalPages.value, Math.max(1, next))
  jumpPage.value = String(page.value)
}

onMounted(() => {
  void loadProducts()
})
</script>

<template>
  <section class="goods-page">
    <div class="goods-toolbar">
      <strong>商品列表</strong>
      <button class="ghost" type="button" @click="successMessage = '删除的宝贝会进入回收站，超过 3 天自动清除'">回收站</button>
    </div>

    <div class="filter-row">
      <input v-model="searchQuery" class="search" placeholder="搜索ID、标题或内容" @keyup.enter="page = 1" />
      <select v-model="categoryFilter">
        <option value="">商品类别</option>
        <option v-for="item in categories" :key="item" :value="item">{{ item }}</option>
      </select>
      <select v-model="groupFilter">
        <option value="">商品分组</option>
        <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
      </select>
      <input v-model="minPrice" class="price" type="number" placeholder="¥" />
      <span>-</span>
      <input v-model="maxPrice" class="price" type="number" placeholder="¥" />
      <button class="primary" type="button" @click="page = 1">查找</button>
    </div>

    <div class="action-row">
      <button type="button" @click="requestDelete">删除</button>
      <button type="button" @click="openBatch('改价', 'price', '输入新价格')">改价</button>
      <button type="button" @click="openBatch('运费', 'shipping', '输入运费')">运费</button>
      <button type="button" @click="openBatch('分组', 'group', '输入分组名称')">分组</button>
      <button type="button" @click="openBatch('修改描述', 'description', '输入新的描述')">修改描述</button>
      <button type="button" @click="openBatch('替换内容', 'replace', '原文=>替换后')">替换内容</button>
      <button type="button" @click="openBatch('插入标题', 'insertTitle', '插入到标题前的文本')">插入标题</button>
      <button type="button" @click="openBatch('插入描述', 'insertDesc', '插入到描述前的文本')">插入描述</button>
      <button type="button" @click="openBatch('库存', 'stock', '输入库存')">库存</button>
      <button type="button" @click="openBatch('自提', 'selfPickup', '1 开启 / 0 关闭')">自提</button>
      <button type="button" @click="openBatch('商品规格', 'spec', '规格值，逗号分隔')">商品规格</button>
      <button type="button" @click="openBatch('无需邮寄', 'freeShipping', '1 开启 / 0 关闭')">无需邮寄</button>
      <button type="button" @click="openBatch('入手价', 'cost', '输入入手价')">入手价</button>
      <button type="button" @click="openBatch('分享码', 'share', '输入分享码')">分享码</button>
      <button type="button" @click="openBatch('虚拟宝贝', 'virtual', '输入虚拟内容')">虚拟宝贝</button>
      <button type="button" @click="openBatch('备注', 'notes', '输入备注')">备注</button>
      <button type="button" @click="openBatch('主题', 'theme', '主题，逗号分隔')">主题</button>
      <span class="spacer" />
      <button class="outline" type="button" @click="successMessage = '当前列表已按上方条件筛选'">筛选</button>
      <button class="outline" type="button" @click="resetFilters">还原</button>
      <button class="outline" type="button" @click="exportCsv">导出</button>
      <button class="outline" type="button" @click="printList">打印</button>
    </div>
    <div class="action-row compact">
      <button type="button" @click="openBatch('图片标签', 'labels', '标签，逗号分隔')">图片标签</button>
      <button type="button" @click="openBatch('分类/品牌', 'brands', '分类或品牌，逗号分隔')">分类/品牌</button>
      <button type="button" @click="successMessage = '同步管家需要对应授权账号，当前先保存到本系统商品库'">同步管家</button>
      <button type="button" @click="successMessage = '批量 AI 改写请到普通宝贝编辑页单条处理'">批量AI</button>
      <button type="button" @click="selectedProducts().forEach(downloadImages)">下载图片</button>
    </div>

    <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
    <p v-if="successMessage" class="flash ok">{{ successMessage }}</p>

    <div class="table-card">
      <table>
        <thead>
          <tr>
            <th class="check"><input v-model="allSelected" type="checkbox" /></th>
            <th>商品分组</th>
            <th>商品图片/视频</th>
            <th>标题</th>
            <th>描述</th>
            <th>规格</th>
            <th>价格</th>
            <th>下单链接</th>
            <th>添加时间</th>
            <th>商品备注</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="11" class="empty">加载中...</td>
          </tr>
          <tr v-else-if="pagedProducts.length === 0">
            <td colspan="11" class="empty">还没有商品。到左侧「产品编辑 / 普通宝贝」新建，保存后会出现在这里。</td>
          </tr>
          <tr v-for="product in pagedProducts" :key="product.id" :class="{ selected: selectedIds.includes(product.id) }">
            <td class="check"><input type="checkbox" :checked="selectedIds.includes(product.id)" @change="toggleSelection(product.id)" /></td>
            <td>{{ productGroupName(product) }}</td>
            <td>
              <div class="thumbs">
                <img v-for="(image, index) in productImages(product).slice(0, 3)" :key="index" :src="image" alt="" />
                <span v-if="productImages(product).length" class="count">{{ productImages(product).length }}张</span>
                <span v-else class="no-media">无图</span>
              </div>
            </td>
            <td class="title">{{ clipText(product.title, 16) }}</td>
            <td class="desc">{{ clipText(product.description, 18) }}</td>
            <td>{{ productSpecLabel(product) }}</td>
            <td>{{ product.price }}</td>
            <td>{{ parseAttributes(product.attributes).orderLink }}</td>
            <td>{{ formatDateTime(product.updatedAt ?? product.createdAt) }}</td>
            <td>{{ parseAttributes(product.attributes).notes }}</td>
            <td class="ops">
              <button type="button" title="编辑" @click="openEdit(product.id)">✎</button>
              <button type="button" title="二维码" @click="showQr(product)">▦</button>
              <button type="button" title="复制" @click="copyProduct(product)">⧉</button>
              <button type="button" title="下载图片" @click="downloadImages(product)">⬇</button>
              <button class="danger" type="button" title="删除" @click="deleteOne(product)">✕</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="pager">
        <button type="button" :disabled="page <= 1" @click="goPage(page - 1)">‹</button>
        <button v-for="item in pageNumbers" :key="item" type="button" :class="{ current: item === page }" @click="goPage(item)">{{ item }}</button>
        <button type="button" :disabled="page >= totalPages" @click="goPage(page + 1)">›</button>
        <span>到第</span>
        <input v-model="jumpPage" />
        <span>页</span>
        <button type="button" @click="goPage(Number(jumpPage) || 1)">确定</button>
        <span>共 {{ filteredProducts.length }} 条</span>
        <select v-model.number="pageSize" @change="page = 1">
          <option :value="10">10 条/页</option>
          <option :value="20">20 条/页</option>
          <option :value="50">50 条/页</option>
        </select>
      </div>
    </div>

    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>表格后方 ✎ 表示编辑宝贝，▦ 显示宝贝信息，⧉ 复制一个相同的宝贝，⬇ 打包下载宝贝图片，✕ 删除当前宝贝。</li>
        <li>点击表单右上角的筛选，可选择显示更多商品信息。</li>
        <li>页面底部可跳转页数和选择每页显示数量。页面顶端可设置商品搜索的条件。</li>
        <li>在搜索 ID、标题或内容输入框输入关键字，会显示所有标题或内容匹配的宝贝。</li>
        <li>勾选宝贝后点击改价、分组、库存等按钮，会直接改这些商品并保存。</li>
        <li>删除的宝贝可点右上角回收站查看说明，超过 3 天按归档规则清除。</li>
      </ol>
    </div>

    <div v-if="dialog" class="mask" @click.self="dialog = null">
      <div class="modal">
        <h3>{{ dialog.title }}</h3>
        <p>已选择 {{ selectedIds.length }} 个商品</p>
        <input v-model="dialog.value" :placeholder="dialog.placeholder" />
        <div class="modal-actions">
          <button type="button" @click="dialog = null">取消</button>
          <button class="primary" type="button" @click="applyBatch">确定</button>
        </div>
      </div>
    </div>

    <div v-if="confirmDelete" class="mask" @click.self="confirmDelete = false">
      <div class="modal">
        <h3>删除商品</h3>
        <p>确定删除选中的 {{ selectedIds.length }} 个商品吗？</p>
        <div class="modal-actions">
          <button type="button" @click="confirmDelete = false">取消</button>
          <button class="danger-fill" type="button" @click="deleteSelected">确定删除</button>
        </div>
      </div>
    </div>

    <div v-if="preview" class="mask" @click.self="preview = null">
      <div class="modal">
        <h3>{{ preview.title }}</h3>
        <pre>{{ preview.body }}</pre>
        <div class="modal-actions">
          <button class="primary" type="button" @click="preview = null">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.goods-page { display: grid; gap: 10px; color: #334155; }
.goods-toolbar, .filter-row, .action-row, .table-card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.goods-toolbar { min-height: 44px; padding: 8px 12px; display: flex; align-items: center; justify-content: space-between; }
.filter-row, .action-row, .pager { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.filter-row { padding: 10px 12px; }
.search { width: 220px; }
.filter-row input, .filter-row select, .pager input, .pager select, .modal input { height: 32px; padding: 0 10px; border: 1px solid #d1d5db; border-radius: 4px; background: #fff; }
.price { width: 72px; }
.primary, .action-row button, .ghost, .outline, .pager button, .modal-actions button { height: 32px; padding: 0 12px; border-radius: 4px; border: 1px solid #0f766e; background: #0f766e; color: #fff; font-size: 12px; }
.ghost, .outline, .pager button, .modal-actions button { color: #0f766e; background: #fff; }
.action-row { padding: 8px 12px 4px; }
.action-row.compact { padding-top: 0; border-top: 0; }
.spacer { flex: 1; }
.flash { margin: 0; padding: 8px 12px; border-radius: 6px; font-size: 13px; }
.flash.error { color: #b91c1c; background: #fef2f2; }
.flash.ok { color: #166534; background: #f0fdf4; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 10px 8px; border-bottom: 1px solid #f1f5f9; text-align: left; vertical-align: middle; }
th { color: #64748b; font-weight: 600; background: #f8fafc; }
tr.selected { background: #f0fdfa; }
.check { width: 36px; }
.thumbs { display: flex; gap: 4px; align-items: center; }
.thumbs img { width: 42px; height: 42px; object-fit: cover; border-radius: 4px; border: 1px solid #e5e7eb; }
.count { padding: 1px 4px; color: #fff; background: #0f766e; border-radius: 3px; font-size: 10px; }
.no-media { color: #94a3b8; font-size: 12px; }
.title, .desc { max-width: 160px; }
.ops { white-space: nowrap; }
.ops button { width: 26px; height: 26px; padding: 0; margin-right: 4px; color: #0f766e; background: #fff; border: 1px solid #99f6e4; }
.ops .danger { color: #ef4444; border-color: #fecaca; }
.empty { padding: 48px 12px; text-align: center; color: #94a3b8; }
.pager { padding: 10px 12px 12px; color: #64748b; font-size: 12px; }
.pager .current { color: #fff; background: #0f766e; }
.pager input { width: 48px; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.mask { position: fixed; inset: 0; background: rgba(15, 23, 42, .35); display: grid; place-items: center; z-index: 40; }
.modal { width: min(420px, calc(100vw - 32px)); padding: 16px; background: #fff; border-radius: 8px; display: grid; gap: 10px; }
.modal h3, .modal p { margin: 0; }
.modal pre { margin: 0; white-space: pre-wrap; font-size: 12px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
.danger-fill { color: #fff !important; background: #dc2626 !important; border-color: #dc2626 !important; }
</style>
