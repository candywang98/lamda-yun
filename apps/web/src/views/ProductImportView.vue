<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { ProductCreate } from '@cloudctl/api-contracts'
import { createProductCatalog } from '@/api/product-catalog'
import { createProductGroup, DEFAULT_GROUP_NAME, listProductGroups } from '@/data/product-groups'
import { imageBasename, parseImportFile, toProductCreate, type ParsedImportRow } from '@/data/product-import'

const router = useRouter()
const catalog = createProductCatalog()
const fileInput = ref<HTMLInputElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const selectedGroup = ref(DEFAULT_GROUP_NAME)
const snapshotGroup = ref('')
const groups = ref<string[]>([])
const groupLoading = ref(false)
const groupError = ref('')
const newGroup = ref('')
const showGroupModal = ref(false)
const groupNameInput = ref<HTMLInputElement | null>(null)
let previousFocus: HTMLElement | null = null
watch(showGroupModal, async (open) => {
  if (open) {
    previousFocus = document.activeElement as HTMLElement | null
    await nextTick()
    groupNameInput.value?.focus()
  } else previousFocus?.focus()
})
function groupModalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') showGroupModal.value = false
  if (event.key !== 'Tab') return
  const controls = [...(event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('input, button')]
  const first = controls[0]
  const last = controls.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
const showAddressHelp = ref(false)
const showImageHelp = ref(false)
const pendingRows = ref<ParsedImportRow[]>([])
const pendingLocals = ref<string[]>([])
const localFiles = ref<Record<string, string>>({})
const parsing = ref(false)
const resolvingImages = ref(false)
const importing = ref(false)
const warnings = ref<string[]>([])
const warningsAccepted = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
type ImportItem = { line: number; payload: ProductCreate; state: 'pending' | 'saving' | 'saved' | 'unknown'; id?: string }
const batch = ref<ImportItem[]>([])
const busy = computed(() => parsing.value || resolvingImages.value || importing.value)
const locked = computed(() => busy.value || pendingRows.value.length > 0 || batch.value.length > 0)
const needsFolder = computed(() => pendingLocals.value.some((ref) => !localFiles.value[imageBasename(ref).toLowerCase()]))
const confirmed = computed(() => batch.value.filter((item) => item.state === 'saved'))
const uncertain = computed(() => batch.value.filter((item) => item.state === 'unknown'))
const remaining = computed(() => batch.value.filter((item) => item.state === 'pending'))
const canConfirm = computed(() => !busy.value && !groupError.value && pendingRows.value.length > 0 && !needsFolder.value && (!warnings.value.length || warningsAccepted.value) && !batch.value.length)

async function loadGroups() {
  if (groupLoading.value || locked.value) return
  groupLoading.value = true
  groupError.value = ''
  try {
    const products = await catalog.list()
    groups.value = listProductGroups(products).map((item) => item.name)
    if (!groups.value.includes(selectedGroup.value)) selectedGroup.value = groups.value[0] ?? DEFAULT_GROUP_NAME
  } catch (error) {
    groupError.value = '分组加载失败：' + (error instanceof Error ? error.message : String(error))
  } finally { groupLoading.value = false }
}

function addGroup() {
  if (locked.value || groupLoading.value || groupError.value) return
  const name = newGroup.value.trim()
  if (!name) return
  try {
    createProductGroup({ name })
    if (!groups.value.includes(name)) groups.value = [...groups.value, name]
    selectedGroup.value = name
    newGroup.value = ''
    showGroupModal.value = false
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : String(error) }
}

function downloadTemplate(kind: 'csv' | 'xlsx') {
  const name = kind === 'csv' ? '商品导入模板.csv' : '商品导入模板.xlsx'
  const link = document.createElement('a')
  link.href = import.meta.env.BASE_URL + 'templates/' + name
  link.download = name
  link.click()
}

function resetPending() {
  if (busy.value) return
  pendingRows.value = []
  pendingLocals.value = []
  localFiles.value = {}
  batch.value = []
  warnings.value = []
  warningsAccepted.value = false
  selectedFile.value = null
  errorMessage.value = ''
  successMessage.value = ''
}

async function ingestFile(file: File) {
  if (locked.value || groupLoading.value || groupError.value) return
  resetPending()
  if (!/\.(xlsx|xls|csv)$/i.test(file.name)) {
    errorMessage.value = '请选择 .xlsx、.xls 或 .csv 文件'
    return
  }
  selectedFile.value = file
  snapshotGroup.value = selectedGroup.value || DEFAULT_GROUP_NAME
  parsing.value = true
  try {
    const parsed = await parseImportFile(file)
    warnings.value = [...parsed.errors]
    pendingRows.value = parsed.rows.map((row) => ({ ...row, images: [...row.images], address: [...row.address] }))
    pendingLocals.value = [...parsed.localImageRefs]
    if (!parsed.rows.length) errorMessage.value = '文件中没有可导入的有效商品，请修正文件后重新选择。'
  } catch (error) {
    errorMessage.value = '解析失败：' + (error instanceof Error ? error.message : String(error))
  } finally { parsing.value = false }
}

async function confirmImport() {
  if (!canConfirm.value) return
  // Create each payload once: continuation only sends rows never sent before.
  batch.value = pendingRows.value.map((row) => ({
    line: row.line,
    payload: toProductCreate(row, snapshotGroup.value, [...row.images]),
    state: 'pending',
  }))
  await importRemaining()
}

async function importRemaining() {
  if (busy.value || !remaining.value.length) return
  importing.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    for (const item of batch.value) {
      if (item.state !== 'pending') continue
      item.state = 'saving'
      try {
        const saved = await catalog.save({ payload: item.payload })
        item.state = 'saved'
        item.id = saved.id
      } catch (error) {
        item.state = 'unknown'
        errorMessage.value = '第 ' + item.line + ' 行保存结果未确认，可能已保存。请到商品列表核实，勿直接重新导入此行。错误：' + (error instanceof Error ? error.message : String(error))
        break
      }
    }
    successMessage.value = '已确认保存 ' + confirmed.value.length + ' 个商品；结果未确认 ' + uncertain.value.length + ' 个；尚未发送 ' + remaining.value.length + ' 个。'
  } finally { importing.value = false }
}

async function onFolderPicked(event: Event) {
  if (busy.value || batch.value.length || !pendingRows.value.length) return
  const input = event.target as HTMLInputElement
  const files = [...(input.files ?? [])]
  input.value = ''
  if (!files.length) return
  resolvingImages.value = true
  errorMessage.value = ''
  localFiles.value = {}
  try {
    const matched: Record<string, File[]> = {}
    for (const file of files) {
      const key = file.name.toLowerCase()
      matched[key] = [...(matched[key] ?? []), file]
    }
    const required = [...new Set(pendingLocals.value.map((ref) => imageBasename(ref).toLowerCase()))]
    const missing = required.filter((key) => !matched[key]?.length)
    const ambiguous = required.filter((key) => (matched[key]?.length ?? 0) > 1)
    if (missing.length || ambiguous.length) {
      errorMessage.value = [missing.length ? '缺少图片：' + missing.join('、') : '', ambiguous.length ? '同名图片无法唯一匹配：' + ambiguous.join('、') : ''].filter(Boolean).join('；')
      return
    }
    const resolved: Record<string, string> = {}
    for (const key of required) resolved[key] = matched[key]![0]!.name
    localFiles.value = resolved
  } catch (error) {
    errorMessage.value = '图片匹配失败：' + (error instanceof Error ? error.message : String(error))
  } finally { resolvingImages.value = false }
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
        <p>先解析并预览，确认后才保存；单次最多检查前 100 行商品，超出行数会提示并要求确认。</p>
        <p>字段说明：图片、标题、价格为必填字段。描述、入手价、库存、运费、采集链接、备注、地址等为选填字段</p>
        <p>
          地址说明：地址格式为"省-市-区"，建议从系统的地址选择功能中复制
          <button type="button" class="link" @click="showAddressHelp = !showAddressHelp">{{ showAddressHelp ? '收起说明 ▲' : '查看详细说明 ▼' }}</button>
        </p>
        <div v-if="showAddressHelp" class="help-block">
          <strong>地址格式要求：</strong>
          <p>格式：省-市-区（使用半角连字符 - 分隔）</p>
          <p>示例：山东省-济南市-长清区</p>
          <p class="warn">建议直接从系统的地址选择功能中复制，避免格式错误或行政区错误</p>
        </div>
        <p>
          图片说明：仅保存原始图片路径或网址作为来源引用；图片文件未上传到媒体库，不代表可直接发布。本地路径在其他设备上不可访问。
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
        <select v-model="selectedGroup" aria-label="导入到分组" :disabled="locked || groupLoading || !!groupError">
          <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
        </select>
        <button type="button" class="link" :disabled="busy" @click="router.push('/operations/product-management/product-management-03')">分组管理</button>
        <button type="button" class="link" :disabled="locked || groupLoading || !!groupError" @click="showGroupModal = true">新增分组</button>
      </div>

      <p v-if="groupLoading" role="status">正在加载分组…</p>
      <p v-if="groupError" role="alert" class="flash error">{{ groupError }} <button type="button" :disabled="groupLoading" @click="loadGroups">重试加载分组</button></p>
      <div class="actions" @dragover.prevent @drop.prevent="onDrop">
        <input ref="fileInput" aria-label="商品表格文件" :disabled="locked || groupLoading || !!groupError" class="hidden" type="file" accept=".xlsx,.xls,.csv,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" @change="onFile" />
        <input ref="folderInput" aria-label="本地图片文件夹" :disabled="busy || !!batch.length" class="hidden" type="file" multiple @change="onFolderPicked" />
        <button class="primary" type="button" :disabled="locked || groupLoading || !!groupError" @click="fileInput?.click()">选择文件并解析</button>
        <button type="button" @click="downloadTemplate('xlsx')">下载 Excel 模板</button>
        <button type="button" @click="downloadTemplate('csv')">下载 CSV 模板</button>
        <button v-if="pendingLocals.length && !batch.length" class="primary" type="button" :disabled="busy" @click="folderInput?.click()">选择图片文件夹</button>
      </div>
      <p v-if="selectedFile" class="file-name">已选择：{{ selectedFile.name }}</p>
      <p v-if="errorMessage" role="alert" class="flash error">{{ errorMessage }}</p>
      <p v-if="busy" role="status">{{ parsing ? '正在解析文件…' : resolvingImages ? '正在核对图片文件名…' : '正在保存商品，请勿关闭页面…' }}</p>
      <div v-if="warnings.length" class="warnings" role="alert">
        <strong>解析提示 {{ warnings.length }} 项</strong>
        <ul><li v-for="warning in warnings" :key="warning">{{ warning }}</li></ul>
        <label v-if="pendingRows.length && !batch.length"><input v-model="warningsAccepted" type="checkbox" :disabled="busy" />我已了解上述跳过行和错误，仅导入下方有效商品</label>
      </div>
      <div v-if="pendingRows.length" class="preview">
        <h3>导入预览</h3>
        <p>本批次分组：{{ snapshotGroup }}；有效商品 {{ pendingRows.length }} 个，图片引用 {{ pendingRows.reduce((sum, row) => sum + row.images.length, 0) }} 个。</p>
        <p v-if="pendingLocals.length">本地图片 {{ pendingLocals.length }} 个引用：{{ needsFolder ? '尚未完整匹配，请选择文件夹' : '已匹配文件名，仅保存原始路径引用，不上传文件' }}</p>
        <p>请核对后确认。分组、表格行和图片来源引用将在本批次固定；如需修改，请重新选择文件。</p>
        <div class="table-wrap" tabindex="0" role="region" aria-label="导入预览，可横向滚动">
          <table><thead><tr><th>数据行号（含表头）</th><th>标题</th><th>价格</th><th>库存</th><th>图片引用数</th></tr></thead>
            <tbody><tr v-for="row in pendingRows" :key="row.line"><td>{{ row.line }}</td><td>{{ row.title }}</td><td>{{ row.price }}</td><td>{{ row.stock }}</td><td>{{ row.images.length }}</td></tr></tbody>
          </table>
        </div>
        <div class="actions">
          <button v-if="!batch.length" class="primary" type="button" :disabled="!canConfirm" @click="confirmImport">确认导入 {{ pendingRows.length }} 个商品</button>
          <button v-if="batch.length && remaining.length" class="primary" type="button" :disabled="busy" @click="importRemaining">仅继续尚未发送的 {{ remaining.length }} 行</button>
          <button v-if="!uncertain.length" type="button" :disabled="busy" @click="resetPending">{{ batch.length ? '结束本批次，选择其他文件' : '取消预览，重新选择文件' }}</button>
        </div>
      </div>
      <div v-if="batch.length" class="results" aria-live="polite">
        <h3>保存结果</h3>
        <p>{{ successMessage }}</p>
        <ul><li v-for="item in batch" :key="item.line">第 {{ item.line }} 行：{{ item.state === 'saved' ? '已确认保存，商品 ID：' + item.id : item.state === 'unknown' ? '结果未确认，可能已保存，请人工核实' : item.state === 'saving' ? '保存中' : '尚未发送' }} · SPU：{{ item.payload.spuCode }}</li></ul>
        <RouterLink to="/operations/product-management/product-management-01">查看商品列表并核实</RouterLink>
        <p v-if="uncertain.length" class="warn">本页不重试结果未确认的行。请先记录行号与 SPU 并核实商品列表，避免重新导入造成重复商品。离开页面后本批次进度不会保留。</p>
      </div>
    </div>

    <div v-if="showGroupModal" class="mask" @click.self="showGroupModal = false">
      <div class="modal" role="dialog" aria-modal="true" aria-label="新增导入分组" @keydown="groupModalKeydown">
        <h3>分组管理</h3>
        <p>新增一个导入目标分组</p>
        <input ref="groupNameInput" v-model="newGroup" aria-label="分组名称" placeholder="分组名称" @keydown.enter.prevent="addGroup" />
        <div class="modal-actions">
          <button type="button" @click="showGroupModal = false">取消</button>
          <button class="primary" type="button" @click="addGroup">确定</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.import-page { min-width: 0; color: #334155; }
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
button:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible, input:focus-visible, select:focus-visible, .table-wrap:focus-visible { outline: 2px solid #0f766e; outline-offset: 2px; }
.preview, .results, .warnings { margin-top: 16px; font-size: 13px; overflow-wrap: anywhere; }
.warnings { padding: 12px; background: #fff7ed; }
.table-wrap { overflow-x: auto; max-width: 100%; max-height: 340px; }
table { width: 100%; min-width: 480px; border-collapse: collapse; }
th, td { padding: 8px; text-align: left; border-bottom: 1px solid #e5e7eb; }
th { background: #f8fafc; }
.modal { box-sizing: border-box; }
@media (max-width: 480px) { .card { padding: 12px; } .notice { padding: 10px; overflow-wrap: anywhere; } .group-row select { min-width: 0; max-width: 100%; } .modal input { min-width: 0; } .actions button { height: auto; min-height: 36px; } }
</style>
