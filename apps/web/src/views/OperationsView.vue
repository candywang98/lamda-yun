<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Download,
  FileAudio2,
  FileImage,
  FileVideo2,
  FolderOpen,
  ListChecks,
  Play,
  Search,
  ShieldCheck,
  ShieldX,
  X,
} from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import PostCollectView from '@/views/PostCollectView.vue'
import PostEditorView from '@/views/PostEditorView.vue'
import PostGroupView from '@/views/PostGroupView.vue'
import PostListView from '@/views/PostListView.vue'
import ListingInfoCollectView from '@/views/ListingInfoCollectView.vue'
import PostPublishView from '@/views/PostPublishView.vue'
import PostWatermarkView from '@/views/PostWatermarkView.vue'
import ProductEditView from '@/views/ProductEditView.vue'
import ProductImportView from '@/views/ProductImportView.vue'
import ProductGroupView from '@/views/ProductGroupView.vue'
import ProductManagementView from '@/views/ProductManagementView.vue'
import RetiredOperationView from '@/views/RetiredOperationView.vue'
import XianyuPublishGoodsView from '@/views/XianyuPublishGoodsView.vue'
import XianyuSimpleTaskView from '@/views/XianyuSimpleTaskView.vue'
import XianyuExtraTaskView from '@/views/XianyuExtraTaskView.vue'
import XianyuDeviceAddressPoolView from '@/views/XianyuDeviceAddressPoolView.vue'
import XianyuDescriptionPoolView from '@/views/XianyuDescriptionPoolView.vue'
import XianyuTagPoolView from '@/views/XianyuTagPoolView.vue'
import XianyuForbiddenWordView from '@/views/XianyuForbiddenWordView.vue'
import XiaohongshuNurtureView from '@/views/XiaohongshuNurtureView.vue'
import type { XianyuSimpleKind } from '@/data/xianyu-simple-tasks'
import { extraKindByOperationId } from '@/data/xianyu-extra-tasks'
import StatusBadge from '@/components/StatusBadge.vue'
import { findOperation, isRetiredOperation, operationModules, operationPath, riskLabel } from '@/data/operations-catalog'
import { workbenchActions, workbenchColumns, workbenchKind } from '@/data/operation-workbenches'
import { initialPageParameters, type OperationPageField } from '@/data/operation-page-profiles'
import { buildOperationParameters } from '@/data/operation-parameters'
import { controlApiConfigured, createControlApiClient, operationsMockEnabled } from '@/api/control'
import { keepAliveHint, mapControlDevice, presenceLabel, type DevicePresence } from '@/api/devices'
import { useDisplaySettings } from '@/stores/display-settings'
import { CloudCtlApiError, type ContentGroupView, type ContentSummary, type JsonObject, type OperationAuditEvent, type OperationCatalogEntry, type OperationTask, type ProductMediaUpdateItem, type ProductView } from '@cloudctl/api-contracts'

interface OperationRow {
  id: string
  name: string
  group: string
  device: string
  owner: string
  status: 'READY' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'PARTIAL' | 'FAILED' | 'CANCELED' | 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED' | 'BLOCKED'
  updatedAt: string
}

interface DeviceRecord {
  id: string
  group: string
  name: string
  brand: string
  account: string
  goods: number
  sales: string
  exposure: number
  model: string
  androidId: string
  ip: string
  status: DevicePresence
  onlineAt: string
  keepAlive: string | null
}

const route = useRoute()
const display = useDisplaySettings()
const controlApi = createControlApiClient()
const operation = computed(() => {
  const matchedOperation = findOperation(String(route.params.moduleId), String(route.params.operationId))
  if (!matchedOperation) throw new Error(`Unvalidated operation route: ${String(route.params.moduleId)}/${String(route.params.operationId)}`)
  return matchedOperation
})
const currentModule = computed(() => operationModules.find((module) => module.id === operation.value.moduleId) ?? operationModules[0])
const search = ref('')
const statusFilter = ref('全部状态')
const deviceFilter = ref('全部设备')
const selectedIds = ref<string[]>([])
const showConfirm = ref(false)
const confirmPhrase = ref('')
const reason = ref('')
const runResult = ref<{ requestId: string; taskId?: string; status: string; targets: number; source: 'live' | 'mock' } | null>(null)
const activeGuideStep = ref(0)
const form = ref({ deviceScope: '在线且兼容的授权设备（3 台）', executionApp: '主应用', schedule: '立即执行（加入队列）', snapshot: 'catalog-demo/revision-1', concurrency: 1, resourceIds: 'demo-resource-001' })
const pageParameters = ref<Record<string, string | number | boolean>>(initialPageParameters(operation.value.pageProfile))
type OperationConnection = 'connecting' | 'live' | 'mock' | 'unavailable'
const initialConnection: OperationConnection = controlApiConfigured ? 'connecting' : operationsMockEnabled ? 'mock' : 'unavailable'
const connection = ref<OperationConnection>(initialConnection)
const connectionDetail = ref(controlApiConfigured
  ? '正在连接 Control API'
  : operationsMockEnabled
    ? '显式开发 Mock 已启用，不会触发真实执行'
    : '未配置 VITE_CONTROL_API_URL，生产操作已关闭')
const serverCatalog = ref<OperationCatalogEntry[]>([])
const backendTasks = ref<OperationTask[]>([])
const activeTask = ref<OperationTask | null>(null)
const auditEvents = ref<OperationAuditEvent[]>([])
const apiError = ref('')
const apiBusy = ref(false)
const detailRow = ref<OperationRow | null>(null)
const viewFeedback = ref('')
const configurationVersion = ref(0)
const configurationExists = ref(false)
const configurationUpdatedAt = ref<string | null>(null)
let pollTimer: number | undefined

const mockRows = computed<OperationRow[]>(() => {
  const devices = ['杭州-内容-023', '上海-内容-014', '北京-实验-008', '广州-内容-031']
  const statuses: OperationRow['status'][] = ['READY', 'SUCCEEDED', 'RUNNING', 'PENDING_APPROVAL', 'BLOCKED', 'READY', 'SUCCEEDED', 'READY']
  return Array.from({ length: 8 }, (_, index) => ({
    id: `${operation.value.id}-row-${index + 1}`,
    name: `${operation.value.title} · ${String(index + 1).padStart(2, '0')}`,
    group: ['默认分组', '华东运营', '授权测试', '待复核'][index % 4],
    device: devices[index % devices.length],
    owner: '本机',
    status: operation.value.risk === 'blocked' ? 'BLOCKED' : statuses[index],
    updatedAt: `2026-08-30 ${String(10 + index).padStart(2, '0')}:${String(12 + index * 3).padStart(2, '0')}`,
  }))
})

const isProductList = computed(() => operation.value.id === 'product-management-01')
const isProductImport = computed(() => operation.value.id === 'product-management-02')
const isProductGroup = computed(() => operation.value.id === 'product-management-03')
const isPostCollect = computed(() => operation.value.id === 'post-management-02')
const isPostList = computed(() => operation.value.id === 'post-management-03')
const isPostGroup = computed(() => operation.value.id === 'post-management-04')
const isPostWatermark = computed(() => ['post-management-05', 'assets-01', 'xy-tasks-29', 'product-editor-03'].includes(operation.value.id))
const isDeviceAddressPool = computed(() => ['xy-tasks-26', 'product-editor-05', 'assets-06'].includes(operation.value.id))
const isDescriptionPool = computed(() => ['xy-tasks-27', 'product-editor-06', 'assets-07'].includes(operation.value.id))
const isTagPool = computed(() => ['xy-tasks-28', 'product-editor-07', 'assets-08'].includes(operation.value.id))
const isForbiddenWord = computed(() => ['xy-tasks-30', 'product-management-09', 'zz-tasks-08'].includes(operation.value.id))
const isPostPublishXianyu = computed(() => operation.value.id === 'post-management-07')
const isPostPublishXiaohongshu = computed(() => operation.value.id === 'post-management-08' || operation.value.id === 'red-tasks-01')
const isXiaohongshuNurture = computed(() => operation.value.id === 'red-tasks-03')
const isListingInfoCollect = computed(() => operation.value.id === 'analytics-01' || operation.value.id === 'xy-tasks-24')
const isRetired = computed(() => isRetiredOperation(operation.value.id))
const isXianyuPublishGoods = computed(() => operation.value.id === 'xy-tasks-01' || operation.value.id === 'product-management-05')
const xianyuSimpleKind = computed<XianyuSimpleKind | null>(() => {
  if (operation.value.id === 'xy-tasks-03') return 'polish'
  if (operation.value.id === 'xy-tasks-04') return 'shelf-up'
  if (operation.value.id === 'xy-tasks-05') return 'shelf-down'
  if (operation.value.id === 'xy-tasks-06') return 'delete-goods'
  if (operation.value.id === 'xy-tasks-08') return 'bind'
  return null
})
const xianyuExtraKind = computed(() => extraKindByOperationId[operation.value.id] ?? null)

const rows = computed<OperationRow[]>(() => {
  if (connection.value === 'mock') return mockRows.value
  if (connection.value !== 'live') return []
  
  // For product list, show actual products
  if (isProductList.value) {
    return productItems.value.map((product) => ({
      id: product.id,
      name: product.title,
      group: product.category,
      device: product.spuCode,
      owner: `库存 ${product.stock}`,
      status: product.status as any,
      updatedAt: formatDate(product.updatedAt ?? product.createdAt),
    }))
  }
  
  return backendTasks.value.map((task) => ({
    id: task.id,
    name: `${operation.value.title} · ${task.id.slice(0, 8)}`,
    group: task.module,
    device: `${task.totalCount} 个资源`,
    owner: task.requestedBy,
    status: task.status,
    updatedAt: formatDate(task.completedAt ?? task.startedAt ?? task.createdAt),
  }))
})

const filteredRows = computed(() => rows.value.filter((row) => {
  const matchesSearch = `${row.name}${row.group}${row.device}${row.owner}`.toLowerCase().includes(search.value.trim().toLowerCase())
  const matchesStatus = statusFilter.value === '全部状态' || row.status === statusFilter.value
  const matchesDevice = deviceFilter.value === '全部设备' || row.device === deviceFilter.value
  return matchesSearch && matchesStatus && matchesDevice
}))

const allFilteredSelected = computed(() => filteredRows.value.length > 0 && filteredRows.value.every((row) => selectedIds.value.includes(row.id)))
const catalogEntry = computed(() => serverCatalog.value.find((entry) => entry.key === operation.value.backendOperationKey))
const serverMappingConfirmed = computed(() => catalogEntry.value?.featureIds.includes(operation.value.id) === true && catalogEntry.value.risk === operation.value.risk)
const parameterContractConfirmed = computed(() => catalogEntry.value?.allowedParameters.includes('pageParameters') === true)
const targetResourceIds = computed(() => {
  if (selectedIds.value.length > 0) return [...new Set(selectedIds.value)]
  return [...new Set(form.value.resourceIds.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))]
})
const canCreate = computed(() => {
  if (operation.value.risk === 'blocked') return false
  if (isContentEditor.value) {
    const title = String((isProductEditor.value ? pageParameters.value.productTitle : pageParameters.value.contentTitle) ?? '').trim()
    const body = String((isProductEditor.value ? pageParameters.value.description : pageParameters.value.contentBody) ?? '').trim()
    return connection.value === 'live' && title.length > 0 && body.length > 0
  }
  if (!operation.value.backendOperationKey) return false
  if (connection.value === 'connecting') return false
  if (connection.value === 'live') return catalogEntry.value?.allowed === true && serverMappingConfirmed.value && parameterContractConfirmed.value
  return connection.value === 'mock'
})
const actionLabel = computed(() => {
  if (operation.value.risk === 'blocked') return '策略已阻断'
  if (isContentEditor.value) {
    if (connection.value !== 'live') return 'Control API 不可用'
    return isProductEditor.value ? '保存商品' : '保存帖子'
  }
  if (!operation.value.backendOperationKey) return '暂无执行适配器'
  if (connection.value === 'connecting') return '连接后端中'
  if (connection.value === 'live') return operation.value.risk === 'approval' ? '提交后端审批' : operation.value.mode === 'guide' ? '提交后端已读任务' : '创建后端任务'
  if (connection.value === 'mock') return operation.value.actionLabel
  return 'Control API 不可用'
})
const requiredConfirmPhrase = computed(() => connection.value === 'live' ? '确认授权范围' : '确认模拟范围')
const disabledReason = computed(() => {
  if (operation.value.risk === 'blocked') return '生产策略明确阻断该能力'
  if (isContentEditor.value) {
    if (connection.value !== 'live') return '内容编辑需要可用的 Control API，不会写入 Mock 内容'
    const title = String((isProductEditor.value ? pageParameters.value.productTitle : pageParameters.value.contentTitle) ?? '').trim()
    const body = String((isProductEditor.value ? pageParameters.value.description : pageParameters.value.contentBody) ?? '').trim()
    if (!title || !body) return '标题和正文都要填写后才能保存到内容库'
    return undefined
  }
  if (!operation.value.backendOperationKey) return '该入口可保存配置草稿，但尚无显式安全执行适配器'
  if (connection.value === 'connecting') return '正在连接 Control API'
  if (connection.value === 'live' && !serverMappingConfirmed.value) return '后端目录未确认该 featureId 与风险映射'
  if (connection.value === 'live' && catalogEntry.value?.allowed !== true) return '当前后端身份没有该操作权限'
  if (connection.value === 'live' && !parameterContractConfirmed.value) return '后端目录未声明 pageParameters 参数合同'
  if (connection.value === 'unavailable') return 'Control API 未配置或连接失败，生产操作已关闭'
  return undefined
})
const riskTone = computed(() => ({ standard: 'notice-info', approval: '', blocked: 'notice-danger' }[operation.value.risk]))
const modeLabel = computed(() => ({ guide: '教程与说明', table: '列表工作台', form: '任务表单', assets: '资产管理', insight: '分析看板', settings: '配置中心' }[operation.value.mode]))
const pagePurpose = computed(() => operation.value.pageProfile.purpose.split(/原页面要点[:：]/, 1)[0].trim())
const kind = computed(() => workbenchKind(operation.value))
const isDeviceList = computed(() => kind.value === 'device-list')
const isPostEditor = computed(() => operation.value.id === 'post-management-01')
const isProductEditor = computed(() => operation.value.id === 'product-editor-01')
const isContentEditor = computed(() => isPostEditor.value || isProductEditor.value)
const contentKind = computed(() => (isProductEditor.value ? 'product' : 'post'))
const isTaskQueue = computed(() => operation.value.id === 'task-queue-01')
const postItems = ref<ContentSummary[]>([])
const productItems = ref<ProductView[]>([])
const postGroups = ref<ContentGroupView[]>([])
const selectedPostId = ref<string | null>(null)
const postBusy = ref(false)
const productMediaItems = ref<ProductMediaUpdateItem[]>([])
const archiveReason = ref('商品已停止销售')
const dispatchDeviceId = ref('')
const tableColumns = computed(() => workbenchColumns(operation.value))
const tableActions = computed(() => workbenchActions(operation.value))
const articleBody = computed(() => operation.value.sourceSummary.replaceAll('\u0000', ' ').trim())
const deviceKeyword = ref('')
const liveDevices = ref<DeviceRecord[]>([])
const deviceRows = computed(() => (connection.value === 'live' ? liveDevices.value : []))
const visibleDevices = computed(() => deviceRows.value.filter((item) => {
  const haystack = `${item.name}${item.brand}${item.account}${item.model}`.toLowerCase()
  return haystack.includes(deviceKeyword.value.trim().toLowerCase())
}))
const onlineDeviceCount = computed(() => deviceRows.value.filter((item) => item.status === 'ONLINE').length)
const enrollmentDeviceId = ref('')
const enrollment = ref<{ code: string; expiresAt: string } | null>(null)
const enrollmentBusy = ref(false)
const enrollmentError = ref('')
const controlApiPublicUrl = 'https://43.133.243.154.sslip.io'
const controlApiTlsPin = '4aa79fab99f90aefda2a66b9456ee2839c5e5379716a8e98e49bee15ea2619bc'

async function createDeviceEnrollment(deviceId: string) {
  if (connection.value !== 'live') return
  enrollmentBusy.value = true
  enrollmentError.value = ''
  enrollmentDeviceId.value = deviceId
  try {
    enrollment.value = await controlApi.createMobileEnrollmentCode({ deviceId, ttlSeconds: 600 })
    viewFeedback.value = `入网码已创建，请在手机 Companion 填写下方三项。`
  } catch (error) {
    enrollment.value = null
    enrollmentError.value = errorDetail(error)
  } finally {
    enrollmentBusy.value = false
  }
}
const assets = [
  { name: 'brand-cover-01.jpg', type: '图片', detail: '1080×1440 · 引用 12 次', icon: FileImage },
  { name: 'product-demo-03.mp4', type: '视频', detail: '00:24 · 引用 8 次', icon: FileVideo2 },
  { name: 'service-intro.wav', type: '音频', detail: '00:31 · 引用 3 次', icon: FileAudio2 },
  { name: 'authorized-address-pool', type: '地址池', detail: '18 条 · revision 7', icon: FolderOpen },
]

watch(operation, () => {
  search.value = ''
  statusFilter.value = '全部状态'
  selectedIds.value = []
  runResult.value = null
  activeTask.value = null
  auditEvents.value = []
  apiError.value = ''
  activeGuideStep.value = 0
  detailRow.value = null
  viewFeedback.value = ''
  configurationVersion.value = 0
  configurationExists.value = false
  configurationUpdatedAt.value = null
  pageParameters.value = initialPageParameters(operation.value.pageProfile)
  selectedPostId.value = null
  productMediaItems.value = []
  dispatchDeviceId.value = ''
  postItems.value = []
  postGroups.value = []
  restoreSavedView()
  void loadOperationData()
})

function toggleAll() {
  if (allFilteredSelected.value) {
    const filtered = new Set(filteredRows.value.map((row) => row.id))
    selectedIds.value = selectedIds.value.filter((id) => !filtered.has(id))
  } else {
    selectedIds.value = [...new Set([...selectedIds.value, ...filteredRows.value.map((row) => row.id)])]
  }
}

function toggleRow(id: string) {
  selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter((item) => item !== id) : [...selectedIds.value, id]
}

function pageFieldValue(field: OperationPageField) {
  const value = pageParameters.value[field.id]
  return typeof value === 'boolean' ? '' : value
}

function updatePageField(field: OperationPageField, event: Event) {
  const rawValue = (event.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement).value
  pageParameters.value[field.id] = field.control === 'number' ? Number(rawValue) : rawValue
}

function savedViewKey() {
  return `cloudctl:operation-view:${operation.value.id}`
}

function restoreSavedView() {
  if (typeof window === 'undefined' || typeof window.localStorage?.getItem !== 'function') return
  const stored = window.localStorage.getItem(savedViewKey())
  if (!stored) return
  try {
    const parsed = JSON.parse(stored) as {
      search?: string
      statusFilter?: string
      deviceFilter?: string
      pageParameters?: Record<string, string | number | boolean>
    }
    if (typeof parsed.search === 'string') search.value = parsed.search
    if (typeof parsed.statusFilter === 'string') statusFilter.value = parsed.statusFilter
    if (typeof parsed.deviceFilter === 'string') deviceFilter.value = parsed.deviceFilter
    if (parsed.pageParameters && typeof parsed.pageParameters === 'object') {
      pageParameters.value = { ...pageParameters.value, ...parsed.pageParameters }
    }
  } catch {
    window.localStorage.removeItem(savedViewKey())
  }
}

function localViewPayload() {
  return {
    search: search.value,
    statusFilter: statusFilter.value,
    deviceFilter: deviceFilter.value,
    pageParameters: pageParameters.value,
    savedAt: new Date().toISOString(),
  }
}

function featureConfiguration(): JsonObject {
  return {
    pageParameters: { ...pageParameters.value },
    deviceScope: form.value.deviceScope,
    executionApp: form.value.executionApp,
    schedule: form.value.schedule,
    snapshot: form.value.snapshot,
    concurrency: form.value.concurrency,
    resourceIds: form.value.resourceIds,
  }
}

function applyFeatureConfiguration(configuration: JsonObject) {
  const savedParameters = configuration.pageParameters
  if (savedParameters && typeof savedParameters === 'object' && !Array.isArray(savedParameters)) {
    const allowedFields = new Set(operation.value.pageProfile.fields.map((field) => field.id))
    const safeParameters = Object.fromEntries(
      Object.entries(savedParameters).filter(([key, value]) => allowedFields.has(key) && ['string', 'number', 'boolean'].includes(typeof value)),
    ) as Record<string, string | number | boolean>
    pageParameters.value = { ...pageParameters.value, ...safeParameters }
  }
  if (typeof configuration.deviceScope === 'string') form.value.deviceScope = configuration.deviceScope
  if (typeof configuration.executionApp === 'string') form.value.executionApp = configuration.executionApp
  if (typeof configuration.schedule === 'string') form.value.schedule = configuration.schedule
  if (typeof configuration.snapshot === 'string') form.value.snapshot = configuration.snapshot
  if (typeof configuration.concurrency === 'number') form.value.concurrency = configuration.concurrency
  if (typeof configuration.resourceIds === 'string') form.value.resourceIds = configuration.resourceIds
}

async function saveCurrentView() {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(savedViewKey(), JSON.stringify(localViewPayload()))
  if (connection.value !== 'live') {
    viewFeedback.value = `配置已保存到当前浏览器 · ${operation.value.title}`
    return
  }
  apiBusy.value = true
  apiError.value = ''
  try {
    const draft = await controlApi.updateOperationFeatureConfigDraft(operation.value.id, {
      configuration: featureConfiguration(),
      expectedVersion: configurationVersion.value,
    })
    configurationVersion.value = draft.version
    configurationExists.value = draft.exists
    configurationUpdatedAt.value = draft.updatedAt
    viewFeedback.value = `后端配置草稿已保存 · v${draft.version}`
  } catch (error) {
    apiError.value = `后端配置保存失败：${errorDetail(error)}`
    viewFeedback.value = `本地视图已保存，后端配置未更新 · ${operation.value.title}`
  } finally {
    apiBusy.value = false
  }
}

function downloadFile(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function exportAssetIndex() {
  downloadFile(`cloudctl-${operation.value.id}-assets.json`, JSON.stringify({
    operationId: operation.value.id,
    sourcePage: operation.value.sourcePage,
    sourceRoute: operation.value.sourceRoute,
    exportedAt: new Date().toISOString(),
    assets: assets.map((asset) => ({ name: asset.name, type: asset.type, detail: asset.detail })),
  }, null, 2), 'application/json;charset=utf-8')
  viewFeedback.value = `已导出 ${assets.length} 条资产索引`
}

function csvCell(value: string | number) {
  return `"${String(value).replaceAll('"', '""')}"`
}

function exportCurrentRows() {
  const header = ['ID', '名称', '分组', '设备', '负责人', '状态', '更新时间']
  const lines = filteredRows.value.map((row) => [row.id, row.name, row.group, row.device, row.owner, row.status, row.updatedAt].map(csvCell).join(','))
  downloadFile(`cloudctl-${operation.value.id}-records.csv`, `\uFEFF${header.map(csvCell).join(',')}\n${lines.join('\n')}`, 'text/csv;charset=utf-8')
  viewFeedback.value = `已导出当前筛选结果 · ${filteredRows.value.length} 条`
}

function requestAction() {
  if (!canCreate.value) return
  if (isContentEditor.value) {
    void saveContentRecord()
    return
  }
  showConfirm.value = true
  confirmPhrase.value = ''
  reason.value = ''
}

function parseMediaAssetIds(value: unknown) {
  return String(value ?? '')
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function targetAppValue(label: unknown) {
  if (label === '小红书') return 'xiaohongshu'
  if (label === '抖音') return 'douyin'
  return 'unspecified'
}

function targetAppLabel(value: unknown) {
  if (value === 'xiaohongshu') return '小红书'
  if (value === 'douyin') return '抖音'
  return '未指定'
}

async function ensurePostGroupId(name: string) {
  const existing = postGroups.value.find((group) => group.name === name)
  if (existing) return existing.id
  const created = await controlApi.createContentGroup({ name, description: `${isProductEditor.value ? '商品' : '帖子'}编辑页自动创建的内容分组` })
  postGroups.value = [...postGroups.value, created]
  return created.id
}

async function loadPostLibrary() {
  if (!isContentEditor.value || connection.value !== 'live') return
  if (isProductEditor.value) {
    productItems.value = await controlApi.products()
    return
  }
  const [items, groups] = await Promise.all([controlApi.contents(contentKind.value), controlApi.contentGroups()])
  postItems.value = items
  postGroups.value = groups
}

async function openPost(contentId: string) {
  if (connection.value !== 'live') return
  postBusy.value = true
  apiError.value = ''
  try {
    if (isProductEditor.value) {
      const detail = await controlApi.product(contentId)
      selectedPostId.value = detail.id
      pageParameters.value = {
        ...pageParameters.value,
        productTitle: detail.title,
        description: detail.description,
        listingPrice: detail.price,
        category: detail.category,
        stock: detail.stock,
        mediaAssetIds: detail.media.map((item) => item.mediaAssetId).join(', '),
      }
      productMediaItems.value = detail.media.map((item, index) => ({
        mediaAssetId: item.mediaAssetId,
        sortOrder: item.sortOrder ?? index,
        role: item.role ?? (index === 0 ? 'cover' : 'detail'),
      }))
      pageParameters.value.productRevision = detail.revision
      viewFeedback.value = `已加载商品修订 r${detail.revision}`
      return
    }
    const detail = await controlApi.content(contentId)
    const payload = detail.revision.payload
    selectedPostId.value = detail.id
    const groupName = postGroups.value.find((group) => detail.groupIds.includes(group.id))?.name ?? String(pageParameters.value.contentGroup ?? '默认分组')
    const mediaIds = Array.isArray(payload.mediaAssetIds) ? payload.mediaAssetIds.filter((item): item is string => typeof item === 'string').join(', ') : ''
    if (isProductEditor.value) {
      pageParameters.value = {
        ...pageParameters.value,
        productTitle: detail.title,
        description: typeof payload.body === 'string' ? payload.body : '',
        listingPrice: typeof payload.listingPrice === 'string' ? payload.listingPrice : String(pageParameters.value.listingPrice ?? '128'),
        category: typeof payload.category === 'string' ? payload.category : String(pageParameters.value.category ?? '数码'),
        stock: typeof payload.stock === 'number' ? payload.stock : Number(pageParameters.value.stock ?? 1),
        mediaAssetIds: mediaIds,
        contentGroup: groupName,
        draftState: payload.draftState === '待复核' ? '待复核' : '草稿',
      }
    } else {
      pageParameters.value = {
        ...pageParameters.value,
        contentTitle: detail.title,
        contentBody: typeof payload.body === 'string' ? payload.body : '',
        mediaAssetIds: mediaIds,
        targetApp: targetAppLabel(payload.targetApp),
        contentGroup: groupName,
        draftState: payload.draftState === '待复核' ? '待复核' : '草稿',
      }
    }
    viewFeedback.value = `已加载${isProductEditor.value ? '商品' : '帖子'}修订 r${detail.revision.revision_no}`
  } catch (error) {
    apiError.value = `加载${isProductEditor.value ? '商品' : '内容'}失败：${errorDetail(error)}`
  } finally {
    postBusy.value = false
  }
}

function resetPostForm() {
  selectedPostId.value = null
  productMediaItems.value = []
  archiveReason.value = '商品已停止销售'
  pageParameters.value = initialPageParameters(operation.value.pageProfile)
  viewFeedback.value = `已开始新${isProductEditor.value ? '商品' : '帖'}，未写入后端`
}

async function saveContentRecord() {
  if (!isContentEditor.value || connection.value !== 'live') return
  const title = String((isProductEditor.value ? pageParameters.value.productTitle : pageParameters.value.contentTitle) ?? '').trim()
  const body = String((isProductEditor.value ? pageParameters.value.description : pageParameters.value.contentBody) ?? '').trim()
  if (!title || !body) {
    apiError.value = '标题和正文都要填写后才能保存到内容库。'
    return
  }
  postBusy.value = true
  apiBusy.value = true
  apiError.value = ''
  try {
    if (isProductEditor.value) {
      const payload = {
        spuCode: String(pageParameters.value.spuCode ?? `SPU-${Date.now()}`).trim(),
        title,
        description: body,
        category: String(pageParameters.value.category ?? '其他').trim(),
        price: String(pageParameters.value.listingPrice ?? '').trim(),
        stock: Number(pageParameters.value.stock ?? 0),
        mediaAssetIds: parseMediaAssetIds(pageParameters.value.mediaAssetIds),
      }
      const saved = selectedPostId.value
        ? await controlApi.updateProduct(selectedPostId.value, { ...payload, expectedRevision: Number(pageParameters.value.productRevision ?? 1) })
        : await controlApi.createProduct(payload)
      selectedPostId.value = saved.id
      pageParameters.value.productRevision = saved.revision
      const media = productMediaItems.value.map((item, index) => ({ ...item, sortOrder: index }))
      if (selectedPostId.value) {
        const mediaSaved = await controlApi.updateProductMedia(saved.id, { expectedRevision: saved.revision, items: media })
        pageParameters.value.productRevision = mediaSaved.revision
      }
      await loadPostLibrary()
      viewFeedback.value = `商品已保存 · ${saved.id.slice(0, 8)} · r${Number(pageParameters.value.productRevision)}`
      return
    }
    const groupId = await ensurePostGroupId(String(pageParameters.value.contentGroup ?? '默认分组'))
    const payload: JsonObject = isProductEditor.value
      ? {
          kind: 'product',
          body,
          listingPrice: String(pageParameters.value.listingPrice ?? '').trim(),
          category: String(pageParameters.value.category ?? '数码'),
          stock: Number(pageParameters.value.stock ?? 1),
          mediaAssetIds: parseMediaAssetIds(pageParameters.value.mediaAssetIds),
          draftState: pageParameters.value.draftState === '待复核' ? '待复核' : '草稿',
        }
      : {
          kind: 'post',
          body,
          mediaAssetIds: parseMediaAssetIds(pageParameters.value.mediaAssetIds),
          ...(targetAppValue(pageParameters.value.targetApp)
            ? { targetApp: targetAppValue(pageParameters.value.targetApp) }
            : {}),
          draftState: pageParameters.value.draftState === '待复核' ? '待复核' : '草稿',
        }
    const saved = selectedPostId.value
      ? await controlApi.createRevision(selectedPostId.value, { payload, groupId })
      : await controlApi.createContent({ title, payload, groupId })
    selectedPostId.value = saved.id
    await loadPostLibrary()
    viewFeedback.value = isProductEditor.value
      ? `商品已保存 · ${saved.id.slice(0, 8)} · r${saved.revision.revision_no}。选设备后可下发到闲鱼填表，不会点发布。`
      : `帖子已保存 · ${saved.id.slice(0, 8)} · r${saved.revision.revision_no}。小红书/抖音执行器尚未接入，不会下发到手机。`
  } catch (error) {
    apiError.value = isConflictError(error)
      ? '商品修订已过期：服务器已有更新，请重新打开商品后再保存。'
      : `保存失败：${errorDetail(error)}`
  } finally {
    postBusy.value = false
    apiBusy.value = false
  }
}

function addProductMedia() {
  const mediaAssetId = String(pageParameters.value.mediaAssetIds ?? '').split(/[\n,]/).map((item) => item.trim()).find(Boolean)
  if (!mediaAssetId || productMediaItems.value.some((item) => item.mediaAssetId === mediaAssetId)) return
  productMediaItems.value = [...productMediaItems.value, {
    mediaAssetId,
    sortOrder: productMediaItems.value.length,
    role: productMediaItems.value.length === 0 ? 'cover' : 'detail',
  }]
}

function removeProductMedia(index: number) {
  productMediaItems.value = productMediaItems.value.filter((_, itemIndex) => itemIndex !== index).map((item, itemIndex) => ({ ...item, sortOrder: itemIndex }))
}

function moveProductMedia(index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= productMediaItems.value.length) return
  const items = [...productMediaItems.value]
  ;[items[index], items[target]] = [items[target], items[index]]
  productMediaItems.value = items.map((item, itemIndex) => ({ ...item, sortOrder: itemIndex }))
}

async function archiveCurrentProduct() {
  if (!isProductEditor.value || connection.value !== 'live' || !selectedPostId.value) return
  if (archiveReason.value.trim().length < 3) {
    apiError.value = '归档原因至少需要 3 个字符。'
    return
  }
  postBusy.value = true
  apiBusy.value = true
  apiError.value = ''
  try {
    const archived = await controlApi.archiveProduct(selectedPostId.value, { reason: archiveReason.value.trim() })
    pageParameters.value.productRevision = archived.revision
    await loadPostLibrary()
    viewFeedback.value = `商品已归档 · ${archived.id.slice(0, 8)} · r${archived.revision}`
  } catch (error) {
    apiError.value = isConflictError(error)
      ? '商品存在活动发布计划，暂不能归档。请先取消或完成相关计划。'
      : `归档失败：${errorDetail(error)}`
  } finally {
    postBusy.value = false
    apiBusy.value = false
  }
}

async function dispatchSavedPost() {
  if (!isProductEditor.value || connection.value !== 'live' || !selectedPostId.value) {
    apiError.value = '请先在普通宝贝里保存商品，再选择设备下发。'
    return
  }
  if (!dispatchDeviceId.value) {
    apiError.value = '请选择一台已绑定 Companion 的设备。'
    return
  }
  const listingPrice = String(pageParameters.value.listingPrice ?? '').trim()
  if (!listingPrice) {
    apiError.value = '下发闲鱼前需要填写价格。'
    return
  }
  if (parseMediaAssetIds(pageParameters.value.mediaAssetIds).length > 0) {
    apiError.value = '当前闲鱼下发只支持纯文字和价格，请先清空媒体资产 ID。'
    return
  }
  postBusy.value = true
  apiBusy.value = true
  apiError.value = ''
  try {
    const result = await controlApi.dispatchContentToXianyu(
      selectedPostId.value,
      { deviceId: dispatchDeviceId.value, listingPrice },
      `product-xianyu-${selectedPostId.value}-${dispatchDeviceId.value}-${Date.now()}`,
    )
    const taskId = typeof result.mobileTask.taskId === 'string' ? result.mobileTask.taskId : result.contentId
    viewFeedback.value = `已下发到设备 ${result.deviceId.slice(0, 8)} · 任务 ${taskId.slice(0, 8)}。手机只填描述和价格，不会点发布。`
  } catch (error) {
    apiError.value = `下发闲鱼失败：${errorDetail(error)}`
  } finally {
    postBusy.value = false
    apiBusy.value = false
  }
}

function formatDate(value: string) {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false })
}

function errorDetail(error: unknown) {
  return error instanceof Error ? error.message : '未知错误'
}

function isConflictError(error: unknown) {
  return (error instanceof CloudCtlApiError && error.status === 409)
    || (typeof error === 'object' && error !== null && 'status' in error && error.status === 409)
}

function libraryItemStatus(item: ProductView | ContentSummary) {
  return 'revision' in item ? item.status : (item.draftState ?? item.status)
}

function libraryItemRevision(item: ProductView | ContentSummary) {
  return 'revision' in item ? item.revision : item.latestRevision
}

function clearPoll() {
  if (pollTimer !== undefined) window.clearTimeout(pollTimer)
  pollTimer = undefined
}

function schedulePoll() {
  clearPoll()
  if (!activeTask.value || ['SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELED', 'REJECTED'].includes(activeTask.value.status)) return
  pollTimer = window.setTimeout(() => void refreshTask(), 2000)
}

async function loadOperationData() {
  clearPoll()
  backendTasks.value = []
  if (isProductList.value || isProductEditor.value || isProductImport.value || isProductGroup.value || isPostEditor.value || isPostCollect.value || isPostList.value || isPostGroup.value || isPostWatermark.value || isPostPublishXianyu.value || isPostPublishXiaohongshu.value || isXiaohongshuNurture.value || isListingInfoCollect.value || isXianyuPublishGoods.value) return
  if (!controlApiConfigured) {
    connection.value = operationsMockEnabled ? 'mock' : 'unavailable'
    connectionDetail.value = operationsMockEnabled
      ? '显式开发 Mock 已启用，不会触发真实执行'
      : '未配置 VITE_CONTROL_API_URL，生产操作已关闭'
    if (!operationsMockEnabled) apiError.value = 'Control API 未配置；Operations 不允许自动回退到 Mock。'
    return
  }
  connection.value = 'connecting'
  connectionDetail.value = '正在连接 Control API'
  apiError.value = ''
  try {
    const [catalog, tasks, draft, devices] = await Promise.all([
      controlApi.operationCatalog(),
      controlApi.operationTasks({ limit: 200 }),
      controlApi.operationFeatureConfigDraft(operation.value.id),
      controlApi.devices(),
    ])
    serverCatalog.value = catalog
    backendTasks.value = operation.value.backendOperationKey
      ? tasks.filter((task) => task.operationKey === operation.value.backendOperationKey)
      : []
    liveDevices.value = devices.map((item) => {
      const mapped = mapControlDevice(item)
      return {
        id: mapped.id,
        group: '1',
        name: mapped.name,
        brand: mapped.android === '未回传' ? 'Android' : 'OnePlus',
        account: mapped.account,
        goods: 0,
        sales: '0',
        exposure: 0,
        model: mapped.android,
        androidId: mapped.id.slice(0, 16),
        ip: mapped.edge,
        status: mapped.presence ?? 'BOUND_UNSEEN',
        onlineAt: mapped.lastSeenAt ?? '未回传',
        keepAlive: keepAliveHint(mapped),
      } satisfies DeviceRecord
    })
    configurationVersion.value = draft.version
    configurationExists.value = draft.exists
    configurationUpdatedAt.value = draft.updatedAt
    if (draft.exists) applyFeatureConfiguration(draft.configuration)
    connection.value = 'live'
    if (isContentEditor.value) {
      await loadPostLibrary()
      connectionDetail.value = isProductEditor.value
        ? 'Control API 已连接，闲鱼商品写入内容库后可下发填表，不会点发布'
        : 'Control API 已连接，帖子写入内容库；小红书/抖音执行器尚未接入'
    } else if (isProductList.value) {
      // Load products for product list page
      try {
        productItems.value = await controlApi.products()
        connectionDetail.value = `Control API 已连接，已加载 ${productItems.value.length} 个商品`
      } catch (error) {
        apiError.value = `加载商品列表失败：${errorDetail(error)}`
      }
    } else {
      connectionDetail.value = draft.exists
        ? `Control API 已连接，配置草稿 v${draft.version}`
        : 'Control API 已连接，当前页面尚未保存配置草稿'
    }
  } catch (error) {
    connection.value = 'unavailable'
    connectionDetail.value = `Control API 请求失败，生产操作已关闭：${errorDetail(error)}`
    apiError.value = `Control API 初始化失败：${errorDetail(error)}`
  }
}

function createMockRun() {
  const targets = Math.max(targetResourceIds.value.length, 1)
  runResult.value = {
    requestId: `req-op-${operation.value.index}-${Date.now().toString().slice(-5)}`,
    status: operation.value.risk === 'approval' ? 'PENDING_APPROVAL' : operation.value.mode === 'guide' ? 'ACKNOWLEDGED' : 'QUEUED',
    targets,
    source: 'mock',
  }
  showConfirm.value = false
}

async function createRun() {
  if (!canCreate.value || !operation.value.backendOperationKey) return
  if (connection.value === 'mock') {
    createMockRun()
    return
  }
  const resources = targetResourceIds.value
  if (resources.length === 0) {
    apiError.value = '至少填写一个资源 ID，或从列表选择已有任务作为目标引用。'
    return
  }
  if (resources.length > 1 && catalogEntry.value?.batchAllowed !== true) {
    apiError.value = '该后端操作不允许批量提交，请只保留一个资源 ID。'
    return
  }
  apiBusy.value = true
  apiError.value = ''
  try {
    const idempotencyKey = `web-${operation.value.id}-${crypto.randomUUID()}`
    const catalog = catalogEntry.value
    if (!catalog) throw new Error('Control API 目录不存在当前操作，已阻止提交')
    const operationParameters = buildOperationParameters(operation.value.pageProfile, pageParameters.value, catalog)
    const context = {
      deviceScope: form.value.deviceScope,
      executionApp: form.value.executionApp,
      schedule: form.value.schedule,
      snapshot: form.value.snapshot,
      reason: reason.value.trim(),
      source: 'web',
      mode: operation.value.mode,
      sourcePage: operation.value.sourcePage,
      sourceRoute: operation.value.sourceRoute,
    }
    const task = resources.length > 1
      ? await controlApi.createBatchOperation({ operationKey: operation.value.backendOperationKey, featureId: operation.value.id, resourceIds: resources, parameters: operationParameters, context }, idempotencyKey)
      : await controlApi.createOperationTask({ operationKey: operation.value.backendOperationKey, featureId: operation.value.id, resourceId: resources[0]!, parameters: operationParameters, context }, idempotencyKey)
    activeTask.value = task
    runResult.value = { requestId: task.requestSha256.slice(0, 16), taskId: task.id, status: task.status, targets: task.totalCount, source: 'live' }
    backendTasks.value = [task, ...backendTasks.value.filter((item) => item.id !== task.id)]
    showConfirm.value = false
    await loadAudit()
    schedulePoll()
  } catch (error) {
    apiError.value = `任务提交失败：${errorDetail(error)}`
  } finally {
    apiBusy.value = false
  }
}

async function refreshTask() {
  if (!activeTask.value || connection.value !== 'live') return
  try {
    const task = await controlApi.operationTask(activeTask.value.id)
    activeTask.value = task
    if (runResult.value) runResult.value = { ...runResult.value, status: task.status, targets: task.totalCount }
    backendTasks.value = [task, ...backendTasks.value.filter((item) => item.id !== task.id)]
    await loadAudit()
    schedulePoll()
  } catch (error) {
    apiError.value = `状态刷新失败：${errorDetail(error)}`
  }
}

async function cancelTask() {
  if (!activeTask.value || connection.value !== 'live') return
  apiBusy.value = true
  try {
    const task = await controlApi.cancelOperationTask(activeTask.value.id, { reason: reason.value.trim() || 'operator requested cancellation' })
    activeTask.value = task
    if (runResult.value) runResult.value = { ...runResult.value, status: task.status }
    backendTasks.value = [task, ...backendTasks.value.filter((item) => item.id !== task.id)]
    await loadAudit()
    clearPoll()
  } catch (error) {
    apiError.value = `取消失败：${errorDetail(error)}`
  } finally {
    apiBusy.value = false
  }
}

async function decideTask(approved: boolean) {
  if (!activeTask.value || activeTask.value.status !== 'PENDING_APPROVAL' || connection.value !== 'live') return
  apiBusy.value = true
  apiError.value = ''
  try {
    const body = { reason: reason.value.trim() || (approved ? 'scope reviewed and approved' : 'scope rejected by approver') }
    const task = approved
      ? await controlApi.approveOperationTask(activeTask.value.id, body)
      : await controlApi.rejectOperationTask(activeTask.value.id, body)
    activeTask.value = task
    if (runResult.value) runResult.value = { ...runResult.value, status: task.status }
    backendTasks.value = [task, ...backendTasks.value.filter((item) => item.id !== task.id)]
    await loadAudit()
    schedulePoll()
  } catch (error) {
    apiError.value = `审批操作失败：${errorDetail(error)}`
  } finally {
    apiBusy.value = false
  }
}

async function loadAudit() {
  if (!activeTask.value || connection.value !== 'live') return
  try {
    auditEvents.value = (await controlApi.operationAuditResult(activeTask.value.id)).auditEvents
  } catch (error) {
    apiError.value = `审计读取失败：${errorDetail(error)}`
  }
}

onMounted(() => {
  restoreSavedView()
  void loadOperationData()
})
onUnmounted(clearPoll)
</script>

<template>
  <ProductManagementView v-if="isProductList" />
  <ProductImportView v-else-if="isProductImport" />
  <ProductGroupView v-else-if="isProductGroup" />
  <ProductEditView v-else-if="isProductEditor" />
  <PostEditorView v-else-if="isPostEditor" />
  <PostCollectView v-else-if="isPostCollect" />
  <PostListView v-else-if="isPostList" />
  <PostGroupView v-else-if="isPostGroup" />
  <PostWatermarkView v-else-if="isPostWatermark" />
  <XianyuDeviceAddressPoolView v-else-if="isDeviceAddressPool" />
  <XianyuDescriptionPoolView v-else-if="isDescriptionPool" />
  <XianyuTagPoolView v-else-if="isTagPool" />
  <XianyuForbiddenWordView v-else-if="isForbiddenWord" />
  <RetiredOperationView v-else-if="isRetired" :title="operation.title" />
  <XianyuPublishGoodsView v-else-if="isXianyuPublishGoods" />
  <XianyuSimpleTaskView v-else-if="xianyuSimpleKind" :kind="xianyuSimpleKind" />
  <XianyuExtraTaskView v-else-if="xianyuExtraKind" :kind="xianyuExtraKind" />
  <PostPublishView v-else-if="isPostPublishXianyu" platform="xianyu" />
  <PostPublishView v-else-if="isPostPublishXiaohongshu" platform="xiaohongshu" />
  <XiaohongshuNurtureView v-else-if="isXiaohongshuNurture" />
  <ListingInfoCollectView v-else-if="isListingInfoCollect" />
  <template v-else>
  <PageHeader v-if="!isDeviceList" :title="operation.title" :description="operation.moduleLabel">
    <template #actions>
      <button class="button" @click="isContentEditor ? resetPostForm() : (pageParameters = initialPageParameters(operation.pageProfile))">重置</button>
      <button v-if="!isContentEditor" class="button" :disabled="apiBusy" @click="saveCurrentView">保存配置</button>
      <button class="button button-primary" :disabled="!canCreate || postBusy" :title="canCreate ? undefined : disabledReason" @click="requestAction"><Play :size="15" />{{ actionLabel }}</button>
      <button v-if="isProductEditor" class="button" type="button" :disabled="postBusy || connection !== 'live' || !selectedPostId || !dispatchDeviceId" @click="dispatchSavedPost">下发到闲鱼填表</button>
    </template>
  </PageHeader>

  <div v-if="false" class="operation-context-strip"></div>

  <section v-if="isDeviceList" class="panel yy-workbench">
    <div class="page-header yy-workbench-head">
      <h2>设备列表</h2>
      <span class="yy-health-flag">{{ deviceRows.length }} 台 · {{ onlineDeviceCount }} 在线</span>
    </div>
    <div class="yy-search-row">
      <input v-model="deviceKeyword" class="field" aria-label="筛选当前功能记录" placeholder="搜索设备名、品牌、型号" />
      <button class="button" type="button" @click="loadOperationData">刷新</button>
    </div>
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>设备名称</th><th>品牌</th><th>状态</th><th>保活</th><th>型号</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="visibleDevices.length === 0">
            <td colspan="6">还没有设备。点「绑定」生成入网码，在手机 Companion 里填写。</td>
          </tr>
          <tr v-for="item in visibleDevices" :key="item.id">
            <td>{{ item.name }}</td>
            <td>{{ item.brand }}</td>
            <td>{{ presenceLabel(item.status) }}</td>
            <td>{{ item.keepAlive ?? '正常' }}</td>
            <td>{{ item.model }}</td>
            <td>
              <button class="button button-quiet" type="button" :disabled="enrollmentBusy || connection !== 'live'" @click="createDeviceEnrollment(item.id)">绑定</button>
              <RouterLink class="button button-quiet" :to="`/devices/${item.id}?tab=remote`">投屏</RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="enrollmentError" class="notice notice-danger" style="margin-top:12px"><p>{{ enrollmentError }}</p></div>
    <div v-if="enrollment" class="notice notice-info" style="margin-top:12px">
      <div>
        <strong>在手机 Companion 里输入这三项完成绑定</strong>
        <p>Control API 地址：<span class="mono">{{ controlApiPublicUrl }}</span></p>
        <p>一次性入网码：<span class="mono">{{ enrollment.code }}</span>（过期 {{ formatDate(enrollment.expiresAt) }}）</p>
        <p>TLS SHA-256 指纹：<span class="mono">{{ controlApiTlsPin }}</span></p>
        <p>当前设备：<span class="mono">{{ enrollmentDeviceId }}</span>。绑定成功后刷新列表，状态会变成在线。</p>
      </div>
    </div>
    <div class="yy-help">
      <h3>使用说明</h3>
      <ol>
        <li>手机安装 Companion，打开无障碍。</li>
        <li>点这一行的「绑定」，把地址、入网码、指纹填进手机。</li>
        <li>绑定成功后点「刷新」。投屏只用来看画面，不是绑定入口。</li>
      </ol>
    </div>
    <section class="sr-only operation-source-panel"></section>
    <section class="sr-only operation-page-spec">页面规格 {{ String(operation.index).padStart(3, '0') }}</section>
    <ol class="sr-only" aria-label="页面工作流程"><li v-for="step in operation.pageProfile.workflow" :key="step">{{ step }}</li></ol>
    <div class="sr-only">
      <div v-for="field in operation.pageProfile.fields" :key="field.id" class="form-field">
        <label :for="`page-field-${field.id}`">{{ field.label }}</label>
        <select v-if="field.control === 'select'" :id="`page-field-${field.id}`" :value="pageFieldValue(field)" @change="updatePageField(field, $event)">
          <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
        </select>
        <input v-else :id="`page-field-${field.id}`" :value="pageFieldValue(field)" @input="updatePageField(field, $event)" />
      </div>
    </div>
  </section>

  <section v-if="!isDeviceList" class="panel yy-workbench">
    <div class="yy-workbench-head">
      <h3>{{ operation.title }}</h3>
    </div>

    <article v-if="kind === 'article'" class="yy-article">
      <p>{{ articleBody }}</p>
      <ol class="yy-help-list">
        <li v-for="step in operation.pageProfile.workflow" :key="step">{{ step }}</li>
      </ol>
    </article>

    <div v-if="kind === 'task'" class="form-grid operation-form yy-task-form">
      <div class="form-field"><label>执行设备</label><select v-model="form.deviceScope"><option>在线且兼容的授权设备（3 台）</option><option>仅北京实验设备（1 台）</option><option>保存配置但不选择设备</option></select></div>
      <div class="form-field"><label>执行应用</label><select v-model="form.executionApp"><option>主应用</option><option>副应用</option><option>先主后副</option></select></div>
      <div class="form-field"><label>执行时间</label><select v-model="form.schedule"><option>立即执行（加入队列）</option><option>2026-08-31 09:00</option><option>仅保存配置</option></select></div>
      <div class="form-field"><label>同设备并发</label><input v-model="form.concurrency" type="number" min="1" max="1" disabled /></div>
    </div>

    <div v-if="isProductEditor && connection === 'live'" class="form-grid operation-specific-fields" style="margin-bottom:12px">
      <div class="form-field">
        <label for="post-dispatch-device">下发设备</label>
        <select id="post-dispatch-device" v-model="dispatchDeviceId">
          <option value="">选择已绑定 Companion 的设备</option>
          <option v-for="item in liveDevices" :key="item.id" :value="item.id">{{ item.name }} · {{ presenceLabel(item.status) }}</option>
        </select>
        <small>会把当前保存的正文和价格发给这台手机填写闲鱼发布页，不会点发布，也不会传图。</small>
      </div>
    </div>
    <div v-if="kind !== 'article' && kind !== 'table'" class="form-grid operation-specific-fields">
      <div v-for="field in operation.pageProfile.fields" :key="field.id" class="form-field" :class="{ full: field.control === 'textarea' }">
        <label :for="`page-field-${field.id}`">{{ field.label }}</label>
        <select v-if="field.control === 'select'" :id="`page-field-${field.id}`" :value="pageFieldValue(field)" @change="updatePageField(field, $event)">
          <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
        </select>
        <textarea v-else-if="field.control === 'textarea'" :id="`page-field-${field.id}`" :value="pageFieldValue(field)" :placeholder="field.placeholder" @input="updatePageField(field, $event)" />
        <label v-else-if="field.control === 'toggle'" class="operation-toggle" :for="`page-field-${field.id}`">
          <input :id="`page-field-${field.id}`" type="checkbox" :checked="Boolean(pageParameters[field.id])" @change="pageParameters[field.id] = ($event.target as HTMLInputElement).checked" />
          <span>{{ pageParameters[field.id] ? '已开启' : '已关闭' }}</span>
        </label>
        <input v-else :id="`page-field-${field.id}`" :value="pageFieldValue(field)" :type="field.control === 'datetime' ? 'datetime-local' : field.control" :placeholder="field.placeholder" @input="updatePageField(field, $event)" />
        <small v-if="field.help">{{ field.help }}</small>
      </div>
    </div>

    <div v-if="isProductEditor && connection === 'live'" class="panel-body product-media-editor">
      <div class="page-header"><h3>商品媒体编排</h3><button class="button button-quiet" type="button" :disabled="postBusy" @click="addProductMedia">加入当前媒体 ID</button></div>
      <p class="cell-sub">先在“媒体资产 ID”输入框填写 ID，再加入列表；保存商品时会按当前顺序提交角色和排序。</p>
      <div v-if="productMediaItems.length === 0" class="cell-sub">尚未配置商品媒体。</div>
      <div v-for="(item, index) in productMediaItems" :key="`${item.mediaAssetId}-${index}`" class="product-media-row">
        <span class="mono">{{ index + 1 }}</span><span class="mono">{{ item.mediaAssetId }}</span>
        <select v-model="item.role" aria-label="媒体角色"><option value="cover">封面</option><option value="detail">详情</option><option value="video">视频</option></select>
        <button class="button button-quiet" type="button" :disabled="index === 0 || postBusy" @click="moveProductMedia(index, -1)">上移</button>
        <button class="button button-quiet" type="button" :disabled="index === productMediaItems.length - 1 || postBusy" @click="moveProductMedia(index, 1)">下移</button>
        <button class="button button-danger" type="button" :disabled="postBusy" @click="removeProductMedia(index)">移除</button>
      </div>
      <div v-if="selectedPostId" class="form-field"><label for="product-archive-reason">归档原因</label><input id="product-archive-reason" v-model="archiveReason" /><button class="button button-danger" type="button" :disabled="postBusy" @click="archiveCurrentProduct">归档商品</button></div>
    </div>

    <div v-if="kind === 'pool'" class="panel-body operation-assets-grid">
      <button v-for="asset in assets" :key="asset.name" class="operation-asset" @click="search = asset.name"><span><component :is="asset.icon" :size="28" /></span><div><strong>{{ asset.name }}</strong><small>{{ asset.type }} · {{ asset.detail }}</small></div></button>
    </div>
    <div v-if="kind === 'pool'" class="yy-action-row"><button class="button" @click="exportAssetIndex"><Download :size="14" />导出索引</button></div>

    <div v-if="operation.mode === 'insight'" class="panel-body">
      <div class="operation-chart" aria-label="模拟运营趋势图"><div v-for="(height, index) in [42, 56, 38, 74, 62, 88, 71, 92, 68, 81, 95, 78]" :key="index" :style="{ height: `${height}%` }"><span>{{ index + 1 }}</span></div></div>
    </div>

    <div v-if="isContentEditor && connection === 'live'" class="table-wrap" style="margin-top:16px">
      <table class="data-table">
        <thead>
          <tr>
            <th>标题</th>
            <th>状态</th>
            <th>修订</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="(isProductEditor ? productItems.length : postItems.length) === 0">
            <td colspan="4">还没有{{ isProductEditor ? '商品' : '帖子' }}。填写标题和正文后点「{{ isProductEditor ? '保存商品' : '保存帖子' }}」，会写入租户内容库。</td>
          </tr>
          <tr v-for="item in (isProductEditor ? productItems : postItems)" :key="item.id" :class="{ selected: selectedPostId === item.id }">
            <td>{{ item.title }}</td>
            <td>{{ libraryItemStatus(item) }}</td>
            <td>r{{ libraryItemRevision(item) }}</td>
            <td><button class="button button-quiet" type="button" :disabled="postBusy" @click="openPost(item.id)">打开</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="kind === 'editor' || kind === 'settings'" class="yy-action-row">
      <button class="button" @click="exportCurrentRows"><Download :size="14" />导出结果</button>
    </div>

    <div v-if="kind === 'table' || kind === 'task' || kind === 'pool'" class="filter-bar operation-filter-bar">
      <label class="catalog-search"><Search :size="14" /><input v-model="search" aria-label="筛选当前功能记录" placeholder="名称、设备、分组、负责人" /></label>
      <select v-model="deviceFilter" class="select-field" aria-label="设备筛选"><option>全部设备</option><option>杭州-内容-023</option><option>上海-内容-014</option><option>北京-实验-008</option><option>广州-内容-031</option></select>
      <select v-model="statusFilter" class="select-field" aria-label="状态筛选"><option>全部状态</option><option>READY</option><option>RUNNING</option><option>SUCCEEDED</option><option>PENDING_APPROVAL</option><option>BLOCKED</option></select>
      <button v-if="isTaskQueue" class="button button-danger" type="button" :disabled="selectedIds.length === 0">批量删除</button>
      <button v-if="isTaskQueue" class="button button-primary" type="button" :disabled="selectedIds.length === 0 || !canCreate" @click="requestAction">批量运行</button>
      <button class="button" @click="exportCurrentRows"><Download :size="14" />导出结果</button>
      <button v-for="action in tableActions" :key="action" class="yy-chip" type="button">{{ action }}</button>
      <span class="filter-spacer" /><span class="cell-sub">{{ filteredRows.length }} 条</span>
    </div>

    <div v-if="viewFeedback" class="notice notice-info operation-view-feedback" role="status"><CheckCircle2 :size="16" /><p>{{ viewFeedback }}</p></div>

    <div v-if="kind === 'table' || kind === 'task' || kind === 'pool'" class="operation-bulk-bar" :class="{ active: selectedIds.length > 0 }"><div><ListChecks :size="16" /><strong>已选择 {{ selectedIds.length }} 项</strong></div><button class="button" @click="selectedIds = []">取消选择</button><button class="button button-primary" :disabled="selectedIds.length === 0 || !canCreate" @click="requestAction">{{ actionLabel }}</button></div>

    <div v-if="kind === 'table' || kind === 'task' || kind === 'pool'" class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th><input type="checkbox" aria-label="选择当前筛选全部记录" :checked="allFilteredSelected" @change="toggleAll" /></th>
            <th v-for="column in tableColumns" :key="column.key">{{ column.label }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredRows" :key="row.id" :class="{ selected: selectedIds.includes(row.id) }">
            <td><input type="checkbox" :aria-label="`选择 ${row.name}`" :checked="selectedIds.includes(row.id)" @change="toggleRow(row.id)" /></td>
            <td v-for="column in tableColumns" :key="column.key">
              <StatusBadge v-if="column.key === 'status'" :status="row.status" :label="row.status === 'READY' ? '就绪' : undefined" />
              <template v-else>{{ row[column.key] }}</template>
            </td>
            <td><button class="button button-quiet" @click="detailRow = row">查看</button></td>
          </tr>
          <tr v-if="filteredRows.length === 0"><td :colspan="tableColumns.length + 2"><div class="query-state"><Search :size="20" />没有符合筛选条件的记录</div></td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <div v-if="!isDeviceList && kind === 'article'" class="sr-only">
    <div v-for="field in operation.pageProfile.fields" :key="field.id" class="form-field">
      <label :for="`page-field-${field.id}`">{{ field.label }}</label>
      <select v-if="field.control === 'select'" :id="`page-field-${field.id}`" :value="pageFieldValue(field)" @change="updatePageField(field, $event)">
        <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
      </select>
      <input v-else :id="`page-field-${field.id}`" :value="pageFieldValue(field)" @input="updatePageField(field, $event)" />
    </div>
  </div>

  <div v-if="false" class="notice operation-policy"></div>

  <div v-if="apiError && !isDeviceList && display.visible('apiErrorBanner')" class="notice notice-danger operation-result" role="alert"><AlertTriangle :size="18" /><div><strong>Control API 请求未完成</strong><p>{{ apiError }}</p></div></div>
  <div v-if="runResult && display.visible('runResultBanner')" class="notice notice-info operation-result" role="status"><CheckCircle2 :size="18" /><div><strong>{{ runResult.source === 'live' ? '后端任务已接收' : 'Mock 请求已接收' }}</strong><p><span class="mono">{{ runResult.taskId ?? runResult.requestId }}</span> · {{ runResult.status }} · {{ runResult.targets }} 个目标。{{ runResult.source === 'live' ? '状态将从 Control API 轮询并读取审计。' : '未触发真实设备或外部平台动作。' }}</p><div v-if="runResult.source === 'live'" class="page-actions" style="margin-top:8px"><button class="button" :disabled="apiBusy" @click="refreshTask">刷新状态</button><button class="button" :disabled="apiBusy" @click="loadAudit">刷新审计</button><button v-if="runResult.status === 'PENDING_APPROVAL'" class="button button-primary" :disabled="apiBusy" @click="decideTask(true)">批准任务</button><button v-if="runResult.status === 'PENDING_APPROVAL'" class="button button-danger" :disabled="apiBusy" @click="decideTask(false)">拒绝任务</button><button class="button button-danger" :disabled="apiBusy || ['SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELED', 'REJECTED'].includes(runResult.status)" @click="cancelTask">取消任务</button></div></div></div>

  <section v-if="false" class="panel operation-source-panel"></section>
  <section v-if="!isDeviceList" class="sr-only operation-page-spec">页面规格 {{ String(operation.index).padStart(3, '0') }}</section>
  <section v-if="auditEvents.length && display.visible('auditPanel')" class="panel"><div class="panel-header"><div><h3>后端审计</h3><p>{{ auditEvents.length }} 条不可变事件</p></div></div><div class="panel-body"><ol class="timeline"><li v-for="event in auditEvents" :key="event.id"><strong>{{ event.action }}</strong><span>{{ event.actorType }} · {{ event.actorId }}</span><small>{{ formatDate(event.occurredAt) }} · {{ event.requestId }}</small></li></ol></div></section>

  <div v-if="showConfirm" class="modal-backdrop" @click.self="showConfirm = false"><div class="modal operation-confirm" role="dialog" aria-modal="true" aria-label="批量操作确认"><div class="modal-header"><h3>{{ connection === 'live' ? '确认创建后端任务' : '确认创建 Mock 任务' }}</h3><button class="icon-button" title="关闭" @click="showConfirm = false"><X :size="16" /></button></div><div class="modal-body"><div class="notice notice-info"><AlertTriangle :size="18" /><div><strong>{{ operation.title }} · {{ Math.max(targetResourceIds.length, 1) }} 个目标</strong><p>{{ connection === 'live' ? '请求将携带幂等键提交到 Control API；后续状态、取消和审计均读取后端。' : 'Control API 当前不可用，本次仅生成有明确标识的 Mock 回执。' }}</p></div></div><ul class="preview-list"><li><span>后端操作</span><strong class="mono">{{ operation.backendOperationKey }}</strong></li><li><span>设备范围</span><strong>{{ form.deviceScope }}</strong></li><li><span>执行时间</span><strong>{{ form.schedule }}</strong></li><li><span>快照</span><strong class="mono">{{ form.snapshot }}</strong></li></ul><div class="form-field" style="margin-top:12px"><label>操作理由</label><textarea v-model="reason" placeholder="填写授权依据或业务用途，写入审计" /></div><div class="form-field" style="margin-top:10px"><label>输入确认短语：{{ requiredConfirmPhrase }}</label><input v-model="confirmPhrase" :placeholder="requiredConfirmPhrase" /></div></div><div class="modal-actions"><button class="button" @click="showConfirm = false">返回检查</button><button class="button button-primary" :disabled="apiBusy || confirmPhrase !== requiredConfirmPhrase || reason.trim().length < 2" @click="createRun">确认提交</button></div></div></div>

  <div v-if="detailRow" class="modal-backdrop" @click.self="detailRow = null"><div class="modal operation-detail-modal" role="dialog" aria-modal="true" aria-label="记录详情"><div class="modal-header"><div><h3>{{ detailRow.name }}</h3><span class="cell-sub mono">{{ detailRow.id }}</span></div><button class="icon-button" title="关闭" @click="detailRow = null"><X :size="16" /></button></div><div class="modal-body"><div class="operation-detail-grid"><div><span>分组</span><strong>{{ detailRow.group }}</strong></div><div><span>设备或范围</span><strong>{{ detailRow.device }}</strong></div><div><span>负责人</span><strong>{{ detailRow.owner }}</strong></div><div><span>当前状态</span><StatusBadge :status="detailRow.status" /></div><div><span>更新时间</span><strong>{{ detailRow.updatedAt }}</strong></div><div><span>来源页面</span><strong class="mono">PDF {{ operation.sourcePage }} · {{ operation.sourceRoute }}</strong></div></div><div class="operation-detail-parameters"><h4>页面参数快照</h4><dl><div v-for="field in operation.pageProfile.fields" :key="field.id"><dt>{{ field.label }}</dt><dd>{{ typeof pageParameters[field.id] === 'boolean' ? (pageParameters[field.id] ? '已开启' : '已关闭') : pageParameters[field.id] }}</dd></div></dl></div></div><div class="modal-actions"><button class="button button-primary" @click="detailRow = null">关闭详情</button></div></div></div>
  </template>
</template>
