<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { ProductView } from '@cloudctl/api-contracts'
import { createProductCatalog } from '@/api/product-catalog'
import MediaThumb from '@/components/MediaThumb.vue'
import { fetchMediaBlob } from '@/api/media-assets'
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
const loadFailed = ref(false)
const archiveBusy = ref(false)
const archiveTargets = ref<string[]>([])
const batchTargets = ref<ProductView[]>([])
const replacement = ref('')
const columnsOpen = ref(false)
const downloadBusy = ref(false)
const priceFilterError = computed(() => {
  if ([minPrice.value, maxPrice.value].some((value) => value !== '' && (!Number.isFinite(Number(value)) || Number(value) < 0))) return '价格筛选必须是非负数值'
  if (minPrice.value !== '' && maxPrice.value !== '' && Number(minPrice.value) > Number(maxPrice.value)) return '最低价格不能大于最高价格'
  return ''
})
const columns = ['商品分组', '商品图片/视频', '标题', '描述', '规格', '价格', '下单链接', '添加时间', '商品备注']
const visibleColumns = ref([...columns])
const visible = (name: string) => visibleColumns.value.includes(name)
const normalizeTitle = (title: string) => title.normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase()
const duplicateTitles = computed(() => {
  const counts = new Map<string, number>()
  for (const product of products.value) {
    const title = normalizeTitle(product.title)
    if (title) counts.set(title, (counts.get(title) ?? 0) + 1)
  }
  return counts
})
const replacementPreview = computed(() => batchTargets.value.flatMap((product) => {
  const search = dialog.value?.value ?? ''
  if (!search) return []
  const parts = product.description.split(search)
  return parts.length > 1 ? [{ product, count: parts.length - 1, after: parts.join(replacement.value) }] : []
}))
const replacementCount = computed(() => replacementPreview.value.reduce((sum, item) => sum + item.count, 0))
const errorMessage = ref('')
const successMessage = ref('')
const page = ref(1)
const pageSize = ref(10)
const jumpPage = ref('1')
const dialog = ref<{ title: string; field: string; value: string; placeholder: string } | null>(null)
const batchBusy = ref(false)
const confirmDelete = ref(false)
const pageRoot = ref<HTMLElement | null>(null)
let previousFocus: HTMLElement | null = null
const preview = ref<{ title: string; body: string } | null>(null)

watch(() => Boolean(dialog.value || confirmDelete.value || preview.value), async (opened) => {
  if (opened) {
    previousFocus = document.activeElement as HTMLElement | null
    await nextTick()
    pageRoot.value?.querySelector<HTMLElement>('.modal input, .modal button')?.focus()
  } else previousFocus?.focus()
})

function modalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && !batchBusy.value && !archiveBusy.value) {
    dialog.value = null
    confirmDelete.value = false
    preview.value = null
  }
  if (event.key !== 'Tab') return
  const nodes = [...(pageRoot.value?.querySelectorAll<HTMLElement>('.modal input:not(:disabled), .modal button:not(:disabled)') ?? [])]
  const first = nodes[0]
  const last = nodes[nodes.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}

const groups = computed(() => resolveProductGroups(products.value).map((item) => item.name))
const categories = computed(() => [...new Set(products.value.flatMap((item) => parseAttributes(item.attributes).brands))].sort())

const filteredProducts = computed(() => {
  if (priceFilterError.value) return []
  return products.value.filter((product) => {
    const attributes = parseAttributes(product.attributes)
    const haystack = `${product.id}${product.title}${product.description}${product.spuCode}${attributes.notes}`.toLowerCase()
    const query = searchQuery.value.trim().toLowerCase()
    if (query === '查重') {
      if ((duplicateTitles.value.get(normalizeTitle(product.title)) ?? 0) < 2) return false
    } else if (query && !haystack.includes(query)) return false
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

watch([searchQuery, categoryFilter, groupFilter, minPrice, maxPrice, pageSize], () => goPage(1))

const allSelected = computed({
  get: () => pagedProducts.value.length > 0 && pagedProducts.value.every((item) => selectedIds.value.includes(item.id)),
  set: (value: boolean) => {
    if (value) selectedIds.value = [...new Set([...selectedIds.value, ...pagedProducts.value.map((item) => item.id)])]
    else selectedIds.value = selectedIds.value.filter((id) => !pagedProducts.value.some((item) => item.id === id))
  },
})

async function loadProducts() {
  if (loading.value) return
  loading.value = true
  loadFailed.value = false
  errorMessage.value = ''
  try {
    products.value = await catalog.list()
    selectedIds.value = selectedIds.value.filter((id) => products.value.some((item) => item.id === id))
    if (page.value > totalPages.value) page.value = 1
  } catch (error) {
    loadFailed.value = true
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

async function downloadImages(product: ProductView) {
  const images = productImages(product)
  if (images.length === 0) {
    errorMessage.value = '这个宝贝还没有可下载的图片'
    return
  }
  try {
    for (const [index, image] of images.entries()) {
      const blob = await fetchMediaBlob(image)
      downloadDataUrl(URL.createObjectURL(blob), `${product.title || 'product'}-${index + 1}.jpg`)
    }
  } catch (error) {
    errorMessage.value = `下载图片失败：${error instanceof Error ? error.message : String(error)}`
  }
}

async function downloadSelectedImages() {
  if (downloadBusy.value) return
  downloadBusy.value = true
  try { for (const product of selectedProducts()) await downloadImages(product) }
  finally { downloadBusy.value = false }
}

function showQr(product: ProductView) {
  const attributes = parseAttributes(product.attributes)
  preview.value = {
    title: '商品信息',
    body: `标题：${product.title}\nID：${product.id}\n分享码：${attributes.shareCode || '未设置'}`,
  }
}

function openBatch(title: string, field: string, placeholder: string) {
  if (batchBusy.value) return
  if (selectedIds.value.length === 0) {
    errorMessage.value = '请先勾选商品'
    return
  }
  batchTargets.value = selectedProducts().map((product) => ({ ...product }))
  replacement.value = ''
  errorMessage.value = ''
  dialog.value = { title, field, value: '', placeholder }
}

async function applyBatch() {
  if (!dialog.value || batchBusy.value) return
  const field = dialog.value.field
  const value = dialog.value.value
  if (['price', 'shipping', 'cost', 'stock'].includes(field) && (!value.trim() || !Number.isFinite(Number(value)) || Number(value) < 0 || (field === 'stock' && !Number.isSafeInteger(Number(value))))) {
    errorMessage.value = field === 'stock' ? '库存必须是非负整数' : '金额必须是非负有限数值'
    return
  }
  if (field === 'replace' && !value) { errorMessage.value = '请输入要替换的原文'; return }
  const targets = field === 'replace' ? replacementPreview.value.map((item) => item.product) : [...batchTargets.value]
  if (!targets.length) return
  batchBusy.value = true
  errorMessage.value = ''
  successMessage.value = ''
  let completed = 0
  try {
    for (const original of targets) {
      const product = { ...original }
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
      else if (field === 'replace') product.description = product.description.split(value).join(replacement.value)
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
      const saved = await catalog.save({
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
          attributes: { ...product.attributes, ...attributes },
        },
      })
      products.value = products.value.map((item) => item.id === saved.id ? saved : item)
      selectedIds.value = selectedIds.value.filter((id) => id !== saved.id)
      batchTargets.value = batchTargets.value.filter((item) => item.id !== saved.id)
      completed += 1
    }
    successMessage.value = `已更新 ${targets.length} 个商品`
    dialog.value = null
    await loadProducts()
  } catch (error) {
    errorMessage.value = `批量操作失败：${error instanceof Error ? error.message : String(error)}。已保存 ${completed} 个，剩余 ${targets.length - completed} 个未确认，可重试剩余商品。`
  } finally {
    batchBusy.value = false
  }
}

async function deleteSelected() {
  if (!archiveTargets.value.length || archiveBusy.value) return
  const targets = [...archiveTargets.value]
  archiveBusy.value = true
  errorMessage.value = ''
  try {
    await catalog.archive(targets, '商品列表归档')
    successMessage.value = '已归档 ' + targets.length + ' 个商品'
    confirmDelete.value = false
    selectedIds.value = selectedIds.value.filter((id) => !targets.includes(id))
    await loadProducts()
  } catch (error) {
    errorMessage.value = '归档失败：' + (error instanceof Error ? error.message : String(error))
  } finally {
    archiveBusy.value = false
  }
}

function deleteOne(product: ProductView) {
  archiveTargets.value = [product.id]
  confirmDelete.value = true
}

function requestDelete() {
  if (!selectedIds.value.length || archiveBusy.value) return
  archiveTargets.value = [...selectedIds.value]
  confirmDelete.value = true
}

function printList() {
  window.print()
}

function exportCsv() {
  const header = columns.filter((name) => visible(name) && name !== '商品图片/视频')
  const rows = filteredProducts.value.map((product) => {
    const attributes = parseAttributes(product.attributes)
    const cells: Record<string, string> = {
      商品分组: productGroupName(product), 标题: product.title, 描述: product.description,
      规格: productSpecLabel(product), 价格: product.price, 下单链接: attributes.orderLink,
      添加时间: formatDateTime(product.createdAt), 商品备注: attributes.notes,
    }
    return header.map((name) => {
      const value = cells[name] ?? ''
      // CSV quotes do not prevent spreadsheet formula evaluation.
      const numericPrice = name === '价格' && value.trim() !== '' && Number.isFinite(Number(value))
      return !numericPrice && /^\s*[=+@-]/.test(value) ? "'" + value : value
    })
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
  <section ref="pageRoot" class="goods-page">
    <div class="goods-toolbar">
      <strong>商品列表</strong>
      <span class="availability">归档后从列表隐藏；当前不支持恢复</span>
    </div>

    <div class="filter-row">
      <input v-model="searchQuery" class="search" aria-label="搜索商品（输入查重查找重复标题）" placeholder="搜索ID、标题或内容" @keyup.enter="page = 1" />
      <select v-model="categoryFilter" aria-label="商品类别">
        <option value="">商品类别</option>
        <option v-for="item in categories" :key="item" :value="item">{{ item }}</option>
      </select>
      <select v-model="groupFilter" aria-label="商品分组">
        <option value="">商品分组</option>
        <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
      </select>
      <input v-model="minPrice" aria-label="最低价格" min="0" class="price" type="number" placeholder="¥" />
      <span>-</span>
      <input v-model="maxPrice" aria-label="最高价格" min="0" class="price" type="number" placeholder="¥" />
      <button class="primary" type="button" @click="page = 1">查找</button>
    </div>

    <p v-if="priceFilterError" role="alert" class="flash error">{{ priceFilterError }}</p>

    <div class="action-row">
      <button type="button" :disabled="!selectedIds.length || archiveBusy || loading" @click="requestDelete">归档</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('改价', 'price', '输入新价格')">改价</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('运费', 'shipping', '输入运费')">运费</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('分组', 'group', '输入分组名称')">分组</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('修改描述', 'description', '输入新的描述')">修改描述</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('替换内容', 'replace', '输入要替换的原文')">替换内容</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('插入标题', 'insertTitle', '插入到标题前的文本')">插入标题</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('插入描述', 'insertDesc', '插入到描述前的文本')">插入描述</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('库存', 'stock', '输入库存')">库存</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('自提', 'selfPickup', '1 开启 / 0 关闭')">自提</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('商品规格', 'spec', '规格值，逗号分隔')">商品规格</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('无需邮寄', 'freeShipping', '1 开启 / 0 关闭')">无需邮寄</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('入手价', 'cost', '输入入手价')">入手价</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('分享码', 'share', '输入分享码')">分享码</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('虚拟宝贝', 'virtual', '输入虚拟内容')">虚拟宝贝</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('备注', 'notes', '输入备注')">备注</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('主题', 'theme', '主题，逗号分隔')">主题</button>
      <span class="spacer" />
      <button class="outline" type="button" :aria-expanded="columnsOpen" aria-controls="product-columns" @click="columnsOpen = !columnsOpen">显示列</button>
      <button class="outline" type="button" @click="resetFilters">还原</button>
      <button class="outline" type="button" :disabled="loading || loadFailed || !filteredProducts.length || !visibleColumns.some((name) => name !== '商品图片/视频')" @click="exportCsv">导出</button>
      <button class="outline" type="button" :disabled="loading || loadFailed || !filteredProducts.length" @click="printList">打印</button>
    </div>
    <div class="action-row compact">
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('图片标签', 'labels', '标签，逗号分隔')">图片标签</button>
      <button type="button" :disabled="!selectedIds.length || batchBusy || loading || archiveBusy" @click="openBatch('分类/品牌', 'brands', '分类或品牌，逗号分隔')">分类/品牌</button>
      <button type="button" disabled title="当前尚未接入同步管家">同步管家（未接入）</button>
      <button type="button" disabled title="当前尚未接入批量 AI">批量AI（未接入）</button>
      <button type="button" :disabled="!selectedIds.length || loading || downloadBusy" @click="downloadSelectedImages">逐张下载图片</button>
    </div>

    <fieldset v-if="columnsOpen" id="product-columns" class="column-options">
      <legend>显示列（导出包含所选文字列）</legend>
      <label v-for="column in columns" :key="column"><input v-model="visibleColumns" type="checkbox" :value="column" />{{ column }}</label>
    </fieldset>
    <p class="selection-summary" role="status">已选择 {{ selectedIds.length }} 个商品（跨页保留）<button type="button" :disabled="!selectedIds.length || batchBusy" @click="selectedIds = []">清空选择</button></p>
    <p v-if="errorMessage" role="alert" class="flash error">{{ errorMessage }}</p>
    <p v-if="successMessage" role="status" class="flash ok">{{ successMessage }}</p>

    <div class="table-card">
      <div class="table-wrap" role="region" aria-label="商品列表，可横向滚动" tabindex="0">
        <table>
          <thead>
            <tr>
              <th class="check"><input v-model="allSelected" aria-label="选择本页全部商品" :disabled="loading || batchBusy || archiveBusy" type="checkbox" /></th>
              <th v-if="visible('商品分组')">商品分组</th>
              <th v-if="visible('商品图片/视频')">商品图片/视频</th>
              <th v-if="visible('标题')">标题</th>
              <th v-if="visible('描述')">描述</th>
              <th v-if="visible('规格')">规格</th>
              <th v-if="visible('价格')">价格</th>
              <th v-if="visible('下单链接')">下单链接</th>
              <th v-if="visible('添加时间')">添加时间</th>
              <th v-if="visible('商品备注')">商品备注</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td :colspan="visibleColumns.length + 2" class="empty">加载中...</td>
            </tr>
            <tr v-else-if="loadFailed"><td :colspan="visibleColumns.length + 2" class="empty">商品加载失败。<button type="button" @click="loadProducts">重试加载</button></td></tr>
            <tr v-else-if="priceFilterError"><td :colspan="visibleColumns.length + 2" class="empty">请修正价格范围。</td></tr>
            <tr v-else-if="pagedProducts.length === 0">
              <td :colspan="visibleColumns.length + 2" class="empty"><template v-if="products.length">没有符合条件的商品。<button type="button" @click="resetFilters">清除筛选</button></template><template v-else>还没有商品。<RouterLink to="/operations/product-editor/product-editor-01">新建商品</RouterLink> · <RouterLink to="/operations/product-management/product-management-02">导入商品</RouterLink></template></td>
            </tr>
            <tr v-for="product in (loading || loadFailed ? [] : pagedProducts)" :key="product.id" :class="{ selected: selectedIds.includes(product.id) }">
              <td class="check"><input :aria-label="'选择商品 ' + product.title" :disabled="batchBusy || archiveBusy" type="checkbox" :checked="selectedIds.includes(product.id)" @change="toggleSelection(product.id)" /></td>
              <td v-if="visible('商品分组')">{{ productGroupName(product) }}</td>
              <td v-if="visible('商品图片/视频')">
                <div class="thumbs">
                  <MediaThumb v-for="(image, index) in productImages(product).slice(0, 3)" :key="`${product.id}-${image}-${index}`" :asset-id="image" :alt="product.title" />
                  <span v-if="productImages(product).length" class="count">{{ productImages(product).length }}张</span>
                  <span v-else class="no-media">无图</span>
                </div>
              </td>
              <td v-if="visible('标题')" class="title">{{ clipText(product.title, 16) }}</td>
              <td v-if="visible('描述')" class="desc">{{ clipText(product.description, 18) }}</td>
              <td v-if="visible('规格')">{{ productSpecLabel(product) }}</td>
              <td v-if="visible('价格')">{{ product.price }}</td>
              <td v-if="visible('下单链接')">{{ parseAttributes(product.attributes).orderLink }}</td>
              <td v-if="visible('添加时间')">{{ formatDateTime(product.createdAt) }}</td>
              <td v-if="visible('商品备注')">{{ parseAttributes(product.attributes).notes }}</td>
              <td class="ops">
                <button type="button" title="编辑" aria-label="编辑商品" @click="openEdit(product.id)">✎</button>
                <button type="button" title="商品信息" aria-label="商品信息" @click="showQr(product)">▦</button>
                <button type="button" title="复制" aria-label="复制商品" @click="copyProduct(product)">⧉</button>
                <button type="button" title="逐张下载图片" aria-label="逐张下载商品图片" @click="downloadImages(product)">⬇</button>
                <button class="danger" type="button" title="归档" aria-label="归档商品" :disabled="archiveBusy || batchBusy" @click="deleteOne(product)">✕</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="pager">
        <button type="button" :disabled="page <= 1" @click="goPage(page - 1)">‹</button>
        <button v-for="item in pageNumbers" :key="item" type="button" :class="{ current: item === page }" @click="goPage(item)">{{ item }}</button>
        <button type="button" :disabled="page >= totalPages" @click="goPage(page + 1)">›</button>
        <span>到第</span>
        <input v-model="jumpPage" aria-label="跳转页码" inputmode="numeric" />
        <span>页</span>
        <button type="button" @click="goPage(Number(jumpPage) || 1)">确定</button>
        <span>共 {{ filteredProducts.length }} 条</span>
        <select aria-label="每页数量" v-model.number="pageSize" @change="page = 1">
          <option :value="10">10 条/页</option>
          <option :value="20">20 条/页</option>
          <option :value="50">50 条/页</option>
        </select>
      </div>
    </div>

    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>表格后方 ✎ 表示编辑宝贝，▦ 显示宝贝信息，⧉ 复制一个相同的宝贝，⬇ 逐张下载商品图片（非 ZIP），✕ 归档当前商品。</li>
        <li>点击表单右上角的显示列，可选择显示更多商品信息。</li>
        <li>页面底部可跳转页数和选择每页显示数量。页面顶端可设置商品搜索的条件。</li>
        <li>在搜索 ID、标题或内容输入框输入关键字，会显示匹配商品；输入「查重」仅显示标准化后标题完全相同的商品（忽略大小写、首尾空白及连续空白差异）。</li>
        <li>勾选宝贝后点击改价、分组、库存等按钮，确认后才会修改并保存；替换内容会先展示描述替换预览。</li>
        <li>归档商品会从当前列表隐藏；当前未提供回收站或恢复接口，也不承诺自动清除期限。</li>
      </ol>
    </div>

    <div v-if="dialog" class="mask" @keydown="modalKeydown" @click.self="!batchBusy && (dialog = null)">
      <div class="modal" role="dialog" aria-modal="true" :aria-label="dialog.title" @keydown.esc="!batchBusy && (dialog = null)">
        <h3>{{ dialog.title }}</h3>
        <p>本次操作 {{ batchTargets.length }} 个商品（打开时固定）</p>
        <input v-model="dialog.value" :aria-label="dialog.field === 'replace' ? '替换原文' : dialog.title" :placeholder="dialog.placeholder" :disabled="batchBusy" />
        <template v-if="dialog.field === 'replace'">
          <input v-model="replacement" aria-label="替换为" placeholder="替换为（留空表示删除原文）" :disabled="batchBusy" />
          <p role="status">命中 {{ replacementPreview.length }} 个商品，共 {{ replacementCount }} 处（仅替换描述）</p>
          <div class="replace-preview"><article v-for="item in replacementPreview" :key="item.product.id"><strong>{{ item.product.title }} · {{ item.count }} 处</strong><p>替换前</p><pre>{{ item.product.description }}</pre><p>替换后</p><pre>{{ item.after }}</pre></article></div>
        </template>
        <p v-if="errorMessage" role="alert" class="flash error">{{ errorMessage }}</p>
        <div class="modal-actions">
          <button type="button" :disabled="batchBusy" @click="dialog = null">取消</button>
          <button class="primary" type="button" :disabled="batchBusy || (dialog.field === 'replace' && !replacementPreview.length)" @click="applyBatch">{{ batchBusy ? '保存中…' : '确定' }}</button>
        </div>
      </div>
    </div>

    <div v-if="confirmDelete" class="mask" @keydown="modalKeydown" @click.self="!archiveBusy && (confirmDelete = false)">
      <div class="modal" role="dialog" aria-modal="true" aria-label="归档商品">
        <h3>归档商品</h3>
        <p>确定归档 {{ archiveTargets.length }} 个商品吗？商品将从列表隐藏，当前不支持恢复。</p>
        <div class="modal-actions">
          <button type="button" :disabled="archiveBusy" @click="confirmDelete = false">取消</button>
          <button class="danger-fill" type="button" :disabled="archiveBusy" @click="deleteSelected">{{ archiveBusy ? '归档中…' : '确定归档' }}</button>
        </div>
      </div>
    </div>

    <div v-if="preview" class="mask" @keydown="modalKeydown" @click.self="preview = null">
      <div class="modal" role="dialog" aria-modal="true" :aria-label="preview.title">
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
.table-card { min-width: 0; }
.table-wrap { overflow-x: auto; max-width: 100%; }
button:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible, input:focus-visible, select:focus-visible, .table-wrap:focus-visible { outline: 2px solid #0f766e; outline-offset: 2px; }
.column-options { display: flex; flex-wrap: wrap; gap: 12px; border: 1px solid #e5e7eb; }
.column-options label { display: inline-flex; gap: 4px; align-items: center; }
.selection-summary, .availability { margin: 0; font-size: 12px; color: #64748b; }
.selection-summary button { margin-left: 8px; }
.replace-preview { max-height: 260px; overflow: auto; overflow-wrap: anywhere; }
.replace-preview article { border-bottom: 1px solid #e5e7eb; padding: 8px 0; }
.goods-page { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; color: #334155; }
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
table { width: 100%; min-width: 920px; border-collapse: collapse; font-size: 13px; }
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
.modal { box-sizing: border-box; max-height: calc(100dvh - 32px); overflow-y: auto; width: min(420px, calc(100vw - 32px)); padding: 16px; background: #fff; border-radius: 8px; display: grid; gap: 10px; }
.modal h3, .modal p { margin: 0; }
.modal pre { margin: 0; white-space: pre-wrap; font-size: 12px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
.danger-fill { color: #fff !important; background: #dc2626 !important; border-color: #dc2626 !important; }
@media (max-width: 480px) { .goods-toolbar { align-items: flex-start; gap: 12px; } .availability { max-width: 160px; } .filter-row .search { width: 100%; box-sizing: border-box; } .filter-row select { max-width: 100%; } .modal input { width: 100%; box-sizing: border-box; } }
</style>
