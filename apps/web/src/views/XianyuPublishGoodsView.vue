<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { ProductView } from '@cloudctl/api-contracts'
import { controlApiConfigured } from '@/api/control'
import { useSessionStore } from '@/stores/session'
import { createProductCatalog } from '@/api/product-catalog'
import XianyuDevicePicker from '@/components/XianyuDevicePicker.vue'
import MediaThumb from '@/components/MediaThumb.vue'
import {
  buildXianyuPublishQueueItems,
  createXianyuPublishQueue,
  getXianyuPublishQueue,
  persistXianyuPublishQueue,
  publishQueueScope,
  emptyPublishGoodsConfig,
  FAN_DISCOUNT_OPTIONS,
  loadPublishGoodsConfig,
  savePublishGoodsConfig,
  type XianyuPublishQueueView,
  type XianyuPublishQueueRequest,
  VIDEO_MUSIC_OPTIONS,
} from '@/data/xianyu-publish-goods'
import { clipText, downloadDataUrl, parseAttributes, productGroupName, productImages, productSpecLabel } from '@/data/product-fields'
import { resolveProductGroups } from '@/data/product-groups'
import { fetchXianyuTaskDevices, type XianyuTaskDevice } from '@/data/xianyu-task-devices'

const router = useRouter()
const sessionStore = useSessionStore()
const scope = computed(() => publishQueueScope(sessionStore.session))
const loadedScope = ref('')
const catalog = createProductCatalog()
const form = reactive(emptyPublishGoodsConfig())
const devices = ref<XianyuTaskDevice[]>([])
const products = ref<ProductView[]>([])
const searchQuery = ref('')
const appliedSearch = ref('')
const categoryFilter = ref('')
const appliedCategory = ref('')
const groupFilter = ref('')
const appliedGroup = ref('')
const page = ref(1)
const pageSize = ref(10)
const jumpPage = ref('1')
const pickerOpen = ref(false)
const filterOpen = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const tableSelected = ref<string[]>([])
const busy = ref(false)
const loading = ref(true)
const loadError = ref('')
const attemptQueueId = ref('')
const queueResult = ref<XianyuPublishQueueView | null>(null)
const attempts = new Map<string, { request: XianyuPublishQueueRequest; confirmed: boolean }>()
const creationBlock = computed(() => {
  if (!controlApiConfigured) return '未配置 Control API；不能创建服务端队列'
  if (!scope.value || sessionStore.loading) return '缺少已验证的租户和用户会话，不能创建队列'
  if (!sessionStore.can('task.create')) return '缺少 task.create 权限，不能创建队列'
  if (loading.value) return '正在读取 API 设备、账号与商品目录'
  if (JSON.stringify(scope.value) !== loadedScope.value) return '会话或 API 环境已变化，请重新加载设备、账号与商品目录'
  if (form.deviceIds.length !== 1) return '请只选择 1 台设备'
  const device = devices.value.find((item) => item.id === form.deviceIds[0])
  if (!device) return '所选设备不在当前 Control API 返回列表中'
  if (!device.accountId) return device.accountError || '设备没有明确的 accountId'
  if (!form.productIds.length) return '请先选择待发布宝贝'
  return ''
})
const queueStatus = computed(() => queueResult.value?.targets.every((target) =>
  target.state === 'PENDING' && target.taskIds.length === 0 && target.externalItemId === null)
  ? '尚未派发、尚未发布（服务端状态快照）'
  : '服务端队列状态已变化，以各 target 状态为准；本页面未执行派发或发布')
watch(scope, () => {
  queueResult.value = null
  successMessage.value = ''
  attemptQueueId.value = ''
})

const groups = computed(() => resolveProductGroups(products.value).map((item) => item.name))
const categories = computed(() => [...new Set(products.value.flatMap((item) => parseAttributes(item.attributes).brands))].sort())
const selectedProducts = computed(() => products.value.filter((item) => form.productIds.includes(item.id)))
const filtered = computed(() => products.value.filter((product) => {
  const haystack = `${product.title}${product.description}${productGroupName(product)}`.toLowerCase()
  if (appliedSearch.value && !haystack.includes(appliedSearch.value.trim().toLowerCase())) return false
  if (appliedGroup.value && productGroupName(product) !== appliedGroup.value) return false
  if (appliedCategory.value && !parseAttributes(product.attributes).brands.includes(appliedCategory.value)) return false
  return true
}))
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
function searchTable() {
  appliedSearch.value = searchQuery.value
  appliedCategory.value = categoryFilter.value
  appliedGroup.value = groupFilter.value
  page.value = 1
}

function resetTable() {
  searchQuery.value = ''
  categoryFilter.value = ''
  groupFilter.value = ''
  appliedSearch.value = ''
  appliedCategory.value = ''
  appliedGroup.value = ''
  page.value = 1
}

function toggleProduct(id: string) {
  form.productIds = form.productIds.includes(id)
    ? form.productIds.filter((item) => item !== id)
    : [...form.productIds, id]
}

function toggleTableSelected(id: string) {
  tableSelected.value = tableSelected.value.includes(id)
    ? tableSelected.value.filter((item) => item !== id)
    : [...tableSelected.value, id]
}

function addSelectedToQueue() {
  form.productIds = [...new Set([...form.productIds, ...tableSelected.value])]
}

function printList() {
  window.print()
}

function exportCsv() {
  const rows = [['宝贝分组', '标题', '描述', '规格'], ...filtered.value.map((product) => [
    productGroupName(product),
    product.title,
    product.description.replaceAll('\n', ' '),
    productSpecLabel(product),
  ])]
  downloadDataUrl(`data:text/csv;charset=utf-8,${encodeURIComponent(rows.map((line) => line.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(',')).join('\n'))}`, '待发布宝贝.csv')
}

function saveConfig() {
  errorMessage.value = ''
  try {
    savePublishGoodsConfig(form)
    successMessage.value = '选择已保存到当前浏览器，不代表服务端任务'
  } catch {
    errorMessage.value = '浏览器配置保存失败，不影响已创建的服务端队列'
  }
}

async function createTask() {
  if (busy.value) return
  errorMessage.value = ''
  successMessage.value = ''
  if (creationBlock.value) {
    errorMessage.value = creationBlock.value
    return
  }
  const device = devices.value.find((item) => item.id === form.deviceIds[0])
  if (!device?.accountId) return
  busy.value = true
  const requestScope = scope.value
  const scopeIdentity = JSON.stringify(requestScope)
  try {
    const productIds = [...form.productIds].sort()
    const input = { deviceId: device.id, accountId: device.accountId, items: buildXianyuPublishQueueItems(products.value, productIds) }
    const key = JSON.stringify({ scope: requestScope, productIds, ...input })
    let attempt = attempts.get(key)
    const request = await persistXianyuPublishQueue(requestScope, input, productIds, attempt?.request)
    if (JSON.stringify(scope.value) !== scopeIdentity || sessionStore.loading) throw new Error('会话已变化，请重新加载页面')
    if (!sessionStore.can('task.create')) throw new Error('缺少 task.create 权限，已阻止队列请求')
    if (!attempt) {
      attempt = { request, confirmed: false }
      attempts.set(key, attempt)
    }
    attemptQueueId.value = attempt.request.queueId
    const result = await (attempt.confirmed
      ? getXianyuPublishQueue(attempt.request)
      : createXianyuPublishQueue(attempt.request))
    if (JSON.stringify(scope.value) !== scopeIdentity || sessionStore.loading) throw new Error('会话已变化，未展示旧会话结果')
    queueResult.value = result
    attempt.confirmed = true
    successMessage.value = `服务端队列 ${queueResult.value.queueId} 已确认。${queueStatus.value}`
  } catch (error) {
    errorMessage.value = `${error instanceof Error ? error.message : '队列请求失败'}。未确认本次结果，保留已有结果；相同会话、商品与设备重试复用原 queueId。`
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  Object.assign(form, loadPublishGoodsConfig())
  // Local preferences are selections only; neither identity nor products come from them.
  form.deviceIds = Array.isArray(form.deviceIds) ? form.deviceIds.filter((id) => typeof id === 'string') : []
  form.productIds = Array.isArray(form.productIds) ? form.productIds.filter((id) => typeof id === 'string') : []
  try {
    if (!controlApiConfigured) return
    if (!sessionStore.loaded) await sessionStore.loadSession()
    if (!scope.value) return
    const loadingScope = JSON.stringify(scope.value)
    const [deviceList, productList] = await Promise.all([
      fetchXianyuTaskDevices((message) => { loadError.value = message }),
      catalog.list().catch(() => { loadError.value = 'API 商品目录读取失败，不能使用本地商品替代'; return [] }),
    ])
    devices.value = deviceList
    products.value = productList
    loadedScope.value = loadingScope
  } catch {
    loadError.value = 'API 数据读取失败；创建已阻止'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="page">
    <div class="card">
      <h2>闲鱼商品发布前队列</h2>
      <div class="row">
        <span class="label">执行操作</span>
        <div class="footer flush">
          <button class="primary" type="button" :disabled="busy || !!creationBlock" @click="createTask">{{ busy ? '请求中...' : '创建或查询队列' }}</button>
          <button class="primary" type="button" :disabled="busy" @click="saveConfig">保存选择</button>
        </div>
      </div>
      <p class="hint">仅创建单机商品队列；不执行派发、排期、手机填表或发布。媒体暂存 ID 不代表图片已送达。</p>
      <p v-if="loadError" class="flash error" role="alert">{{ loadError }}</p>
      <p v-if="creationBlock" class="flash error" data-testid="creation-block">{{ creationBlock }}</p>
      <fieldset class="selection" :disabled="busy">
        <XianyuDevicePicker v-model="form.deviceIds" :devices="devices" show-account />
        <div class="row top">
          <span class="label">待发布宝贝</span>
          <div>
            <button class="picker" type="button" @click="pickerOpen = true">{{ selectedProducts.length ? selectedProducts.map((item) => item.title).join('，') : '点击选择宝贝' }}</button>
            <div class="links">
              已选 <b>{{ form.productIds.length }}</b> 件
              <button type="button" @click="pickerOpen = true">选择宝贝</button>
              <button type="button" @click="form.productIds = []">清空</button>
            </div>
          </div>
        </div>
      </fieldset>
      <details class="legacy-settings">
        <summary>旧配置（未接线，已禁用）</summary>
        <fieldset disabled>
          <div class="row">
            <span class="label">商品分配</span>
            <div>
              <label class="radio" for="xy-alloc-default"><input id="xy-alloc-default" v-model="form.allocation" type="radio" value="default" /> 默认</label>
              <label class="radio" for="xy-alloc-even"><input id="xy-alloc-even" v-model="form.allocation" type="radio" value="even" /> 均匀分配</label>
              <p class="hint">分配规则具体解释可阅读本页面底部说明</p>
            </div>
          </div>
          <div class="row">
            <span class="label">执行应用</span>
            <div>
              <label class="radio" for="xy-app-main"><input id="xy-app-main" v-model="form.app" type="radio" value="main" /> 主闲鱼</label>
              <p class="hint">一期每设备仅绑定一个闲鱼账号，副闲鱼已禁用。</p>
            </div>
          </div>
          <div class="row">
            <span class="label">智能视频</span>
            <div>
              <label class="radio" for="xy-video-on"><input id="xy-video-on" v-model="form.smartVideo" type="radio" value="on" /> 开启</label>
              <label class="radio" for="xy-video-off"><input id="xy-video-off" v-model="form.smartVideo" type="radio" value="off" /> 关闭</label>
              <p class="hint">智能视频可将宝贝图片自动合成视频，发布时添加智能视频可增加宝贝权重</p>
            </div>
          </div>
          <div class="row top">
            <span class="label">视频音乐</span>
            <div>
              <label v-for="item in VIDEO_MUSIC_OPTIONS" :key="item" class="radio wrap" :for="`xy-music-${item}`">
                <input :id="`xy-music-${item}`" v-model="form.music" type="radio" :value="item" /> {{ item }}
              </label>
            </div>
          </div>
          <div class="row">
            <label class="label" for="xy-circle">同步到圈子</label>
            <div>
              <select id="xy-circle" v-model="form.circle">
                <option value="">直接选择或搜索选择</option>
              </select>
              <p class="hint">如无选项请<button class="link" type="button" @click="router.push('/operations/xy-tasks/xy-tasks-08')">绑定闲鱼</button>并选中一台执行设备</p>
            </div>
          </div>
          <div class="row">
            <label class="label" for="xy-fan">粉丝优惠</label>
            <div class="inline">
              <select id="xy-fan" v-model="form.fanDiscount">
                <option v-for="item in FAN_DISCOUNT_OPTIONS" :key="item" :value="item">{{ item }}</option>
              </select>
              <span class="hint">粉丝价</span>
            </div>
          </div>
          <div class="row">
            <label class="label" for="xy-interval">发布间隔</label>
            <div class="inline">
              <input id="xy-interval" v-model.number="form.intervalSeconds" type="number" min="1" />
              <span>秒</span>
            </div>
          </div>
          <div class="row">
            <span class="label">多规格发布</span>
            <div>
              <label class="radio" for="xy-spec-on"><input id="xy-spec-on" v-model="form.multiSpec" type="radio" value="on" /> 开启</label>
              <label class="radio" for="xy-spec-off"><input id="xy-spec-off" v-model="form.multiSpec" type="radio" value="off" /> 关闭</label>
            </div>
          </div>
          <div class="row">
            <span class="label">自动短标题</span>
            <div>
              <label class="radio" for="xy-short-on"><input id="xy-short-on" v-model="form.autoShortTitle" type="radio" value="on" /> 开启</label>
              <label class="radio" for="xy-short-off"><input id="xy-short-off" v-model="form.autoShortTitle" type="radio" value="off" /> 关闭</label>
              <p class="hint">闲鱼7.23.20会给部分宝贝自动生成短标题，不想要的话勾选「关闭」就行了</p>
            </div>
          </div>
          <div class="row">
            <span class="label">AI帮你润色</span>
            <div>
              <label class="radio" for="xy-ai-on"><input id="xy-ai-on" v-model="form.aiPolish" type="radio" value="on" /> 开启</label>
              <label class="radio" for="xy-ai-off"><input id="xy-ai-off" v-model="form.aiPolish" type="radio" value="off" /> 关闭</label>
              <p class="hint">发布时自动调用闲鱼APP内部AI功能，润色商品描述，闲鱼版本需要为7.23.20</p>
            </div>
          </div>
          <div class="row">
            <span class="label">去除表情</span>
            <div>
              <label class="radio" for="xy-emoji-on"><input id="xy-emoji-on" v-model="form.stripEmoji" type="radio" value="on" /> 开启</label>
              <label class="radio" for="xy-emoji-off"><input id="xy-emoji-off" v-model="form.stripEmoji" type="radio" value="off" /> 关闭</label>
              <p class="hint">闲鱼不支持4字节的Emoji表情，勾选开启后会自动过滤，闲鱼支持的2字节表情不会被过滤，建议开启</p>
            </div>
          </div>
          <div class="row">
            <span class="label">验货宝</span>
            <div>
              <label class="radio" for="xy-inspect-none"><input id="xy-inspect-none" v-model="form.inspect" type="radio" value="none" /> 不操作</label>
              <label class="radio" for="xy-inspect-on"><input id="xy-inspect-on" v-model="form.inspect" type="radio" value="on" /> 开启</label>
              <label class="radio" for="xy-inspect-off"><input id="xy-inspect-off" v-model="form.inspect" type="radio" value="off" /> 关闭</label>
            </div>
          </div>
          <div class="row">
            <span class="label">图片标签</span>
            <div>
              <label class="radio" for="xy-label-on"><input id="xy-label-on" v-model="form.imageLabels" type="radio" value="on" /> 开启</label>
              <label class="radio" for="xy-label-off"><input id="xy-label-off" v-model="form.imageLabels" type="radio" value="off" /> 关闭</label>
            </div>
          </div>
          <div class="row">
            <span class="label">图片水印</span>
            <div>
              <label class="radio" for="xy-wm-on"><input id="xy-wm-on" v-model="form.watermark" type="radio" value="on" /> 开启</label>
              <label class="radio" for="xy-wm-off"><input id="xy-wm-off" v-model="form.watermark" type="radio" value="off" /> 关闭</label>
              <div class="links"><button type="button" @click="router.push('/operations/assets/assets-01')">设置水印</button></div>
            </div>
          </div>
          <div class="row">
            <span class="label">创意文案</span>
            <div>
              <label class="radio" for="xy-copy-on"><input id="xy-copy-on" v-model="form.creativeCopy" type="radio" value="on" /> 开启</label>
              <label class="radio" for="xy-copy-off"><input id="xy-copy-off" v-model="form.creativeCopy" type="radio" value="off" /> 关闭</label>
              <div class="links"><button type="button" @click="router.push('/operations/creative/creative-02')">查看创意文案</button></div>
            </div>
          </div>
          <div class="row">
            <span class="label">发布形式</span>
            <div>
              <label class="radio" for="xy-mode-direct"><input id="xy-mode-direct" v-model="form.formMode" type="radio" value="direct" /> 直接发布</label>
              <label class="radio" for="xy-mode-draft"><input id="xy-mode-draft" v-model="form.formMode" type="radio" value="draft" /> 存草稿</label>
              <div class="links"><button type="button" @click="router.push('/operations/xy-tasks/xy-tasks-19')">草稿上架</button></div>
            </div>
          </div>
          <div class="row">
            <span class="label">清除缓存</span>
            <div>
              <label class="radio" for="xy-cache-on"><input id="xy-cache-on" v-model="form.clearCache" type="radio" value="on" /> 开启</label>
              <label class="radio" for="xy-cache-off"><input id="xy-cache-off" v-model="form.clearCache" type="radio" value="off" /> 关闭</label>
              <p class="hint">发布后是否删除手机相册中的宝贝图片，建议开启</p>
            </div>
          </div>
          <div class="row">
            <label class="label" for="xy-insert">插入图片</label>
            <div class="inline">
              <select id="xy-insert" v-model="form.insertImage">
                <option value="">插入位置</option>
                <option value="first">第一张</option>
                <option value="last">最后一张</option>
              </select>
              <button class="outline" type="button" @click="router.push('/operations/assets/assets-02')">编辑图片素材</button>
            </div>
          </div>
          <div class="row">
            <label class="label" for="xy-desc-pool">追加描述</label>
            <div class="inline">
              <select id="xy-desc-pool" v-model="form.descPool">
                <option value="">选择描述池</option>
              </select>
              <button class="outline" type="button" @click="router.push('/operations/xy-tasks/xy-tasks-27')">编辑描述池</button>
            </div>
          </div>
          <div class="row">
            <span class="label">随机主图</span>
            <div>
              <label class="radio" for="xy-cover-on"><input id="xy-cover-on" v-model="form.randomCover" type="radio" value="on" /> 开启</label>
              <label class="radio" for="xy-cover-off"><input id="xy-cover-off" v-model="form.randomCover" type="radio" value="off" /> 关闭</label>
            </div>
          </div>
          <div class="row">
            <span class="label">随机标题</span>
            <div>
              <label class="radio" for="xy-title-on"><input id="xy-title-on" v-model="form.randomTitle" type="radio" value="on" /> 开启</label>
              <label class="radio" for="xy-title-off"><input id="xy-title-off" v-model="form.randomTitle" type="radio" value="off" /> 关闭</label>
              <p class="hint">需前往编辑宝贝处设置标题池</p>
            </div>
          </div>
          <div class="row">
            <span class="label">地址模式</span>
            <div>
              <label class="radio" for="xy-addr-default"><input id="xy-addr-default" v-model="form.addressMode" type="radio" value="default" /> 默认地址</label>
              <label class="radio" for="xy-addr-device"><input id="xy-addr-device" v-model="form.addressMode" type="radio" value="device" /> 设备地址模式</label>
              <label class="radio" for="xy-addr-random"><input id="xy-addr-random" v-model="form.addressMode" type="radio" value="random" /> 随机地址模式</label>
              <label class="radio" for="xy-addr-multi"><input id="xy-addr-multi" v-model="form.addressMode" type="radio" value="multi" /> 多地铺货模式</label>
              <p class="hint">请注意阅读页面底部关于地址模式的说明</p>
            </div>
          </div>
          <div class="row">
            <label class="label" for="xy-addr-pool">发布地址</label>
            <div>
              <select id="xy-addr-pool" v-model="form.addressPool">
                <option value="">地址池</option>
              </select>
              <div class="links"><button type="button" @click="form.addressPool = ''">清空地址</button></div>
            </div>
          </div>
          <div class="row">
            <label class="label" for="xy-schedule">执行时间</label>
            <select id="xy-schedule" v-model="form.schedule">
              <option>立即执行</option>
            </select>
          </div>
        </fieldset>
      </details>
      <p v-if="attemptQueueId" class="hint" data-testid="attempt-queue-id">本次请求 queueId：{{ attemptQueueId }}（当前标签页已保存重试身份）</p>
      <p v-if="errorMessage" class="flash error" role="alert">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok" role="status">{{ successMessage }}</p>
      <div v-if="queueResult" class="queue-result" data-testid="xianyu-publish-queue-result">
        <strong>最近已核实的服务端队列</strong>
        <span>queueId：{{ queueResult.queueId }}</span>
        <span>设备：{{ queueResult.deviceId }} · 账号：{{ queueResult.accountId }}</span>
        <span>{{ queueStatus }}</span>
        <span v-for="target in queueResult.targets" :key="target.targetId">
          targetId：{{ target.targetId }} · {{ target.state }} · 商品 {{ target.position + 1 }} · 任务 {{ target.taskIds.length }}
        </span>
      </div>
      <div class="footer">
        <button class="primary" type="button" :disabled="busy || !!creationBlock" @click="createTask">{{ busy ? '请求中...' : '创建或查询队列' }}</button>
        <button class="primary" type="button" :disabled="busy" @click="saveConfig">保存选择</button>
      </div>
    </div>

    <div class="card table-card">
      <div class="filter">
        <input v-model="searchQuery" placeholder="搜索标题或内容" />
        <select v-model="categoryFilter">
          <option value="">商品类别</option>
          <option v-for="item in categories" :key="item" :value="item">{{ item }}</option>
        </select>
        <select v-model="groupFilter">
          <option value="">商品分组</option>
          <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
        </select>
        <button class="primary" type="button" @click="searchTable">查找</button>
      </div>
      <div class="actions">
        <button class="primary" type="button" @click="addSelectedToQueue">添加至待发布</button>
        <span class="spacer" />
        <button class="primary" type="button" @click="filterOpen = true">筛选</button>
        <button class="primary" type="button" @click="resetTable">还原</button>
        <button class="primary" type="button" @click="exportCsv">导出</button>
        <button class="primary" type="button" @click="printList">打印</button>
      </div>
      <div class="table-scroll" role="region" aria-label="商品目录" tabindex="0">
        <table>
          <thead>
            <tr>
              <th class="check"></th>
              <th>宝贝分组</th>
              <th>商品图片/视频</th>
              <th>标题</th>
              <th>描述</th>
              <th>规格</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="paged.length === 0"><td colspan="7" class="empty">无商品数据，请先到商品列表编辑后再发布。</td></tr>
            <tr v-for="product in paged" :key="product.id">
              <td class="check"><input type="checkbox" :checked="tableSelected.includes(product.id)" @change="toggleTableSelected(product.id)" /></td>
              <td>{{ productGroupName(product) }}</td>
              <td>
                <div class="thumbs">
                  <MediaThumb v-for="(image, index) in productImages(product).slice(0, 3)" :key="`${product.id}-${image}-${index}`" :asset-id="image" :alt="product.title" />
                  <span v-if="productImages(product).length === 0" class="muted">无图</span>
                </div>
              </td>
              <td>{{ clipText(product.title, 16) }}</td>
              <td>{{ clipText(product.description, 18) }}</td>
              <td>{{ productSpecLabel(product) }}</td>
              <td class="ops">
                <button type="button" title="添加发布" @click="toggleProduct(product.id)">+</button>
                <button type="button" title="编辑" @click="router.push(`/operations/product-editor/product-editor-01?id=${product.id}`)">✎</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="pager">
        <button type="button" :disabled="page <= 1" @click="page -= 1">‹</button>
        <button class="current" type="button">{{ page }}</button>
        <button type="button" :disabled="page >= totalPages" @click="page += 1">›</button>
        <span>到第</span>
        <input v-model="jumpPage" />
        <span>页</span>
        <button type="button" @click="page = Math.max(1, Number(jumpPage) || 1)">确定</button>
        <span>共 {{ filtered.length }} 条</span>
        <select v-model.number="pageSize"><option :value="10">10条/页</option><option :value="20">20条/页</option></select>
      </div>
    </div>

    <div v-if="filterOpen" class="mask" @click.self="filterOpen = false">
      <div class="modal">
        <h3>筛选商品</h3>
        <input v-model="searchQuery" placeholder="搜索标题或内容" />
        <select v-model="categoryFilter">
          <option value="">商品类别</option>
          <option v-for="item in categories" :key="item" :value="item">{{ item }}</option>
        </select>
        <select v-model="groupFilter">
          <option value="">商品分组</option>
          <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
        </select>
        <div class="modal-actions"><button class="primary" type="button" @click="searchTable(); filterOpen = false">确定</button></div>
      </div>
    </div>

    <div v-if="pickerOpen" class="mask" @click.self="pickerOpen = false">
      <div class="modal">
        <h3>选择宝贝</h3>
        <label v-for="product in products" :key="product.id" class="pick-row">
          <input type="checkbox" :checked="form.productIds.includes(product.id)" @change="toggleProduct(product.id)" />
          <strong>{{ product.title || '未命名' }}</strong>
          <small>{{ productGroupName(product) }}</small>
        </label>
        <p v-if="products.length === 0" class="hint">还没有商品。</p>
        <div class="modal-actions"><button class="primary" type="button" @click="pickerOpen = false">确定</button></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page { display: grid; grid-template-columns: minmax(0, 1fr); min-width: 0; gap: 10px; color: #334155; }
.card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; grid-template-columns: minmax(0, 1fr); min-width: 0; gap: 14px; }
h2 { margin: 0; font-size: 15px; }
.row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: center; }
.row.top { align-items: start; }
.row > * { min-width: 0; }
.label { color: #64748b; font-size: 13px; }
.radio { display: inline-flex; align-items: center; gap: 6px; margin: 0 12px 8px 0; }
.radio.wrap { margin-bottom: 8px; }
.inline { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
input, select { height: 34px; padding: 0 10px; border: 1px solid #d1d5db; border-radius: 4px; font: inherit; }
select { width: min(280px, 100%); }
.picker { width: 100%; min-height: 34px; text-align: left; background: #fff; border: 1px solid #d1d5db; border-radius: 4px; }
.hint { margin: 6px 0 0; color: #94a3b8; font-size: 12px; }
.links { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 6px; color: #0f766e; font-size: 13px; }
.links button, .link { border: 0; background: none; color: #0f766e; padding: 0; }
.footer { padding-left: 100px; display: flex; flex-wrap: wrap; gap: 10px; }
.footer.flush { padding-left: 0; }
.primary { height: 34px; padding: 0 16px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; }
.primary:disabled { opacity: 0.6; cursor: not-allowed; }
.outline { height: 32px; padding: 0 12px; border-radius: 4px; border: 1px solid #0f766e; background: #fff; color: #0f766e; }
.flash { margin: 0; padding-left: 100px; font-size: 13px; }
.flash.error { color: #b91c1c; }
.flash.ok { color: #166534; }
.queue-result { display: grid; gap: 4px; border-top: 1px solid #bbf7d0; padding-top: 12px; color: #166534; font-size: 13px; overflow-wrap: anywhere; }
.selection, .legacy-settings fieldset { border: 0; padding: 0; margin: 0; min-width: 0; display: grid; gap: 14px; }
.selection :deep(.chip) { box-sizing: border-box; max-width: calc(100% - 10px); }
.selection :deep(.chip-name) { min-width: 0; overflow-wrap: anywhere; }
.selection :deep(.chip small) { flex-shrink: 0; white-space: nowrap; }
.legacy-settings summary { color: #64748b; cursor: pointer; margin-bottom: 10px; }
.legacy-settings fieldset { opacity: 0.6; }
.picker { overflow-wrap: anywhere; height: auto; }
.flash, .hint { overflow-wrap: anywhere; }
@media (max-width: 720px) {
  .row { grid-template-columns: 1fr; }
  .footer, .flash { padding-left: 0; }
}
.filter, .actions, .pager { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.spacer { flex: 1; }
.table-scroll { min-width: 0; overflow-x: auto; }
table { width: 100%; min-width: 640px; border-collapse: collapse; font-size: 13px; }
th, td { padding: 10px 8px; border-bottom: 1px solid #f1f5f9; text-align: left; overflow-wrap: anywhere; }
th { color: #64748b; background: #f8fafc; }
.thumbs { display: flex; gap: 4px; align-items: center; }
.thumbs img { width: 42px; height: 42px; object-fit: cover; border-radius: 4px; border: 1px solid #e5e7eb; }
.muted, .empty { color: #94a3b8; }
.ops button { border: 0; background: none; color: #0f766e; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.tag { display: inline-block; margin-right: 6px; padding: 0 6px; border-radius: 4px; background: #ecfdf5; color: #0f766e; }
.mask { position: fixed; inset: 0; background: rgb(15 23 42 / 0.35); display: grid; place-items: center; }
.modal { width: min(520px, 92vw); max-height: 80vh; overflow: auto; background: #fff; border-radius: 8px; padding: 16px; display: grid; gap: 10px; }
.pick-row { display: flex; gap: 8px; align-items: center; }
.modal-actions { display: flex; justify-content: flex-end; }
</style>
