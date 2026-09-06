<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createProductCatalog } from '@/api/product-catalog'
import { compressImageFile } from '@/data/product-fields'
import { createProductGroup, DEFAULT_GROUP_NAME, listProductGroups } from '@/data/product-groups'
import { imageBasename, isRemoteImage, parseImportFile, toProductCreate, type ParsedImportRow } from '@/data/product-import'

const router = useRouter()
const catalog = createProductCatalog()
const fileInput = ref<HTMLInputElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const selectedGroup = ref(DEFAULT_GROUP_NAME)
const groups = ref<string[]>([DEFAULT_GROUP_NAME])
const newGroup = ref('')
const showGroupModal = ref(false)
const showAddressHelp = ref(false)
const showImageHelp = ref(false)
const pendingRows = ref<ParsedImportRow[]>([])
const pendingLocals = ref<string[]>([])
const importing = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const needsFolder = computed(() => pendingLocals.value.length > 0)

async function loadGroups() {
  try {
    const products = await catalog.list()
    groups.value = listProductGroups(products).map((item) => item.name)
    if (!groups.value.includes(selectedGroup.value)) selectedGroup.value = groups.value[0] ?? DEFAULT_GROUP_NAME
  } catch {
    groups.value = [DEFAULT_GROUP_NAME]
  }
}

function addGroup() {
  const name = newGroup.value.trim()
  if (!name) return
  try {
    createProductGroup({ name })
    if (!groups.value.includes(name)) groups.value = [...groups.value, name]
    selectedGroup.value = name
    newGroup.value = ''
    showGroupModal.value = false
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  }
}

function downloadTemplate(kind: 'csv' | 'xlsx') {
  const name = kind === 'csv' ? '商品导入模板.csv' : '商品导入模板.xlsx'
  const link = document.createElement('a')
  link.href = `/templates/${name}`
  link.download = name
  link.click()
}

function resetPending() {
  pendingRows.value = []
  pendingLocals.value = []
}

async function ingestFile(file: File) {
  errorMessage.value = ''
  successMessage.value = ''
  resetPending()
  if (!/\.(xlsx|xls|csv)$/i.test(file.name)) {
    errorMessage.value = '请选择 .xlsx、.xls 或 .csv 文件'
    return
  }
  selectedFile.value = file
  importing.value = true
  try {
    const parsed = await parseImportFile(file)
    if (parsed.rows.length === 0) {
      errorMessage.value = parsed.errors[0] ?? '文件中没有有效的商品数据'
      return
    }
    pendingRows.value = parsed.rows
    pendingLocals.value = parsed.localImageRefs
    if (parsed.errors.length) errorMessage.value = parsed.errors.join('；')
    if (pendingLocals.value.length > 0) {
      successMessage.value = `已读取 ${parsed.rows.length} 个商品。检测到本地图片路径，请选择图片所在文件夹。`
      return
    }
    await importRows(parsed.rows, {})
  } catch (error) {
    errorMessage.value = `解析失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    importing.value = false
  }
}

async function importRows(rows: ParsedImportRow[], localFiles: Record<string, string>) {
  importing.value = true
  errorMessage.value = ''
  let imported = 0
  const missing: string[] = []
  try {
    for (const row of rows) {
      const images: string[] = []
      for (const ref of row.images) {
        if (isRemoteImage(ref)) {
          images.push(ref)
          continue
        }
        const matched = localFiles[imageBasename(ref).toLowerCase()]
        if (matched) images.push(matched)
        else missing.push(imageBasename(ref))
      }
      await catalog.save({
        payload: toProductCreate(row, selectedGroup.value || DEFAULT_GROUP_NAME, images),
      })
      imported += 1
    }
    successMessage.value = `导入成功，共 ${imported} 个商品，可在商品列表查看。`
    if (missing.length) errorMessage.value = `有 ${[...new Set(missing)].length} 张本地图片没有匹配到：${[...new Set(missing)].slice(0, 6).join('、')}`
    resetPending()
    selectedFile.value = null
  } catch (error) {
    errorMessage.value = `导入失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    importing.value = false
  }
}

async function onFolderPicked(event: Event) {
  const input = event.target as HTMLInputElement
  const files = [...(input.files ?? [])]
  input.value = ''
  const localFiles: Record<string, string> = {}
  for (const file of files) {
    const key = file.name.toLowerCase()
    if (pendingLocals.value.some((item) => imageBasename(item).toLowerCase() === key)) {
      localFiles[key] = await compressImageFile(file)
    }
  }
  await importRows(pendingRows.value, localFiles)
}

function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) void ingestFile(file)
}

function onDrop(event: DragEvent) {
  const file = event.dataTransfer?.files?.[0]
  if (file) void ingestFile(file)
}

onMounted(() => {
  folderInput.value?.setAttribute('webkitdirectory', '')
  folderInput.value?.setAttribute('directory', '')
  void loadGroups()
})
</script>

<template>
  <section class="import-page">
    <div class="card">
      <h2>Excel / CSV 导入商品</h2>
      <div class="notice">
        <p>支持导入 .xlsx、.xls 和 .csv 格式的文件，建议使用标准模板（CSV 文件兼容 UTF-8 和 GBK 编码）</p>
        <p>单次最多可导入100个商品，导入成功后，可以在商品列表查看导入成功的商品</p>
        <p>字段说明：图片、标题、价格为必填字段。描述、入手价、库存、运费、采集链接、备注、地址等为选填字段</p>
        <p>
          地址说明：地址格式为"省-市-区"，建议从系统的地址选择功能中复制
          <button type="button" class="link" @click="showAddressHelp = !showAddressHelp">{{ showAddressHelp ? '收起说明 ▲' : '查看详细说明 ▼' }}</button>
        </p>
        <div v-if="showAddressHelp" class="help-block">
          <strong>地址格式要求：</strong>
          <p>格式：省-市-区（使用中文横杠分隔）</p>
          <p>示例：山东省-济南市-长清区</p>
          <p class="warn">建议直接从系统的地址选择功能中复制，避免格式错误或行政区错误</p>
        </div>
        <p>
          图片说明：支持导入本地图片和网络图片链接
          <button type="button" class="link" @click="showImageHelp = !showImageHelp">{{ showImageHelp ? '收起说明 ▲' : '查看详细说明 ▼' }}</button>
        </p>
        <div v-if="showImageHelp" class="help-block">
          <strong>支持的图片路径类型：</strong>
          <p><b>1. 网络图片链接</b></p>
          <p>支持 http:// 或 https:// 开头的完整 URL</p>
          <p>示例：https://example.com/image.jpg</p>
          <p><b>2. 本地图片路径</b></p>
          <p>支持相对路径和绝对路径。路径首尾的引号会自动去除。</p>
          <p>示例：</p>
          <ul>
            <li>1.jpg</li>
            <li>images/product.png</li>
            <li>C:\Users\Photos\item.jpg（Windows）</li>
            <li>/Users/photos/item.jpg（Mac）</li>
          </ul>
          <p><b>图片分隔符：</b>多张图片可以用换行符（推荐）、空格、逗号，或分号分隔。</p>
          <div class="examples">
            <pre>1.jpg
2.jpg
3.jpg</pre>
            <span>或</span>
            <pre>image1.jpg image2.jpg image3.jpg</pre>
          </div>
          <p class="hint">提示：导入本地图片时，需使用 Chrome 系浏览器，导入时会提示选择图片所在文件夹。</p>
        </div>
      </div>

      <div class="group-row">
        <span>导入到分组</span>
        <select v-model="selectedGroup">
          <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
        </select>
        <button type="button" class="link" @click="router.push('/operations/product-management/product-management-03')">分组管理</button>
        <button type="button" class="link" @click="showGroupModal = true">新增分组</button>
      </div>

      <div class="actions" @dragover.prevent @drop.prevent="onDrop">
        <input ref="fileInput" class="hidden" type="file" accept=".xlsx,.xls,.csv,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" @change="onFile" />
        <input ref="folderInput" class="hidden" type="file" multiple @change="onFolderPicked" />
        <button class="primary" type="button" :disabled="importing" @click="fileInput?.click()">上传文件</button>
        <button type="button" @click="downloadTemplate('xlsx')">下载 Excel 模板</button>
        <button type="button" @click="downloadTemplate('csv')">下载 CSV 模板</button>
        <button v-if="needsFolder" class="primary" type="button" @click="folderInput?.click()">选择图片文件夹</button>
      </div>
      <p v-if="selectedFile" class="file-name">已选择：{{ selectedFile.name }}</p>
      <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok">
        {{ successMessage }}
        <button v-if="successMessage.includes('导入成功')" type="button" class="link" @click="router.push('/operations/product-management/product-management-01')">查看商品列表</button>
      </p>
    </div>

    <div v-if="showGroupModal" class="mask" @click.self="showGroupModal = false">
      <div class="modal">
        <h3>分组管理</h3>
        <p>新增一个导入目标分组</p>
        <input v-model="newGroup" placeholder="分组名称" @keydown.enter.prevent="addGroup" />
        <div class="modal-actions">
          <button type="button" @click="showGroupModal = false">取消</button>
          <button class="primary" type="button" @click="addGroup">确定</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.import-page { color: #334155; }
.card { padding: 18px 20px 22px; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; }
h2 { margin: 0 0 14px; font-size: 16px; }
.notice { padding: 14px 16px; background: #f5f7f8; border-left: 4px solid #0f766e; border-radius: 6px; font-size: 13px; line-height: 1.8; }
.notice p { margin: 0 0 6px; }
.link { padding: 0; border: 0; background: transparent; color: #0f766e; font: inherit; text-decoration: underline; cursor: pointer; }
.help-block { margin: 8px 0 12px; padding: 10px 12px; background: #fff; border-radius: 6px; }
.help-block p, .help-block ul { margin: 6px 0; }
.warn { color: #ea580c; }
.hint { color: #64748b; }
.examples { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.examples pre { margin: 0; padding: 8px 10px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 12px; }
.group-row, .actions { margin-top: 18px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.group-row select, .modal input { height: 34px; min-width: 180px; padding: 0 10px; border: 1px solid #d1d5db; border-radius: 4px; background: #fff; }
.actions button, .modal-actions button { height: 36px; padding: 0 14px; border: 1px solid #d1d5db; border-radius: 4px; background: #fff; color: #334155; }
.primary { color: #fff !important; background: #0f766e !important; border-color: #0f766e !important; }
.hidden { display: none; }
.file-name, .flash { margin: 10px 0 0; font-size: 13px; }
.flash.error { color: #b91c1c; }
.flash.ok { color: #166534; }
.mask { position: fixed; inset: 0; display: grid; place-items: center; background: rgba(15, 23, 42, .35); z-index: 40; }
.modal { width: min(380px, calc(100vw - 32px)); padding: 16px; display: grid; gap: 10px; background: #fff; border-radius: 8px; }
.modal h3, .modal p { margin: 0; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
