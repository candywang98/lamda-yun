<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { createPostCatalog } from '@/api/post-catalog'
import XianyuDevicePicker from '@/components/XianyuDevicePicker.vue'
import { clipText, formatDateTime, postImageIds, type PostRecord } from '@/data/post-fields'
import MediaThumb from '@/components/MediaThumb.vue'
import { resolvePostGroups } from '@/data/post-groups'
import { downloadDataUrl } from '@/data/product-fields'
import {
  allocatePosts,
  emptyPublishConfig,
  loadPublishConfig,
  platformCopy,
  savePublishConfig,
  type PostPublishPlatform,
} from '@/data/post-publish'
import { fetchXianyuTaskDevices, type XianyuTaskDevice } from '@/data/xianyu-task-devices'

const props = defineProps<{ platform: PostPublishPlatform }>()
const router = useRouter()
const catalog = createPostCatalog()
const copy = computed(() => platformCopy(props.platform))
const form = reactive(emptyPublishConfig())
const devices = ref<XianyuTaskDevice[]>([])
const posts = ref<PostRecord[]>([])
const searchQuery = ref('')
const appliedSearch = ref('')
const groupFilter = ref('')
const appliedGroup = ref('')
const page = ref(1)
const pageSize = ref(10)
const jumpPage = ref('1')
const pickerOpen = ref(false)
const filterOpen = ref(false)
const tableSelected = ref<string[]>([])
const busy = ref(false)
const loadError = ref('')
const loaded = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const groups = computed(() => resolvePostGroups(posts.value).map((item) => item.name))
const selectedPosts = computed(() => posts.value.filter((item) => form.postIds.includes(item.id)))
const filtered = computed(() => posts.value.filter((post) => {
  const haystack = `${post.title}${post.body}${post.notes}`.toLowerCase()
  if (appliedSearch.value && !haystack.includes(appliedSearch.value.trim().toLowerCase())) return false
  if (appliedGroup.value && post.groupName !== appliedGroup.value) return false
  return true
}))
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const assignments = computed(() => allocatePosts(form.postIds, form.deviceIds, form.allocation))
const isXianyu = computed(() => props.platform === 'xianyu')
function isGraphicPost(post: PostRecord) { return !post.videoAssetId && !post.videoUrl && !post.videoName }
const selectablePage = computed(() => paged.value.filter(isGraphicPost))
const allSelected = computed({
  get: () => selectablePage.value.length > 0 && selectablePage.value.every((item) => tableSelected.value.includes(item.id)),
  set: (value: boolean) => {
    if (value) tableSelected.value = [...new Set([...tableSelected.value, ...selectablePage.value.map((item) => item.id)])]
    else tableSelected.value = tableSelected.value.filter((id) => !paged.value.some((item) => item.id === id))
  },
})

async function loadData() {
  if (busy.value) return
  busy.value = true
  loaded.value = false
  loadError.value = ''
  const results = await Promise.allSettled([
    fetchXianyuTaskDevices((message) => { loadError.value = message }),
    catalog.list(),
  ])
  const [deviceResult, postResult] = results
  if (deviceResult.status === 'fulfilled') devices.value = deviceResult.value
  else loadError.value = '设备读取失败：' + String(deviceResult.reason)
  if (postResult.status === 'fulfilled') posts.value = postResult.value
  else loadError.value += (loadError.value ? '；' : '') + '帖子读取失败：' + String(postResult.reason)
  loaded.value = !loadError.value
  if (loaded.value) {
    form.postIds = form.postIds.filter((id) => posts.value.some((item) => item.id === id && isGraphicPost(item)))
    form.deviceIds = form.deviceIds.filter((id) => devices.value.some((item) => item.id === id))
    tableSelected.value = tableSelected.value.filter((id) => posts.value.some((item) => item.id === id && isGraphicPost(item)))
  }
  busy.value = false
}

watch(totalPages, (total) => { page.value = Math.min(page.value, total) })
function jumpToPage() {
  const requested = Number(jumpPage.value)
  page.value = Math.min(totalPages.value, Math.max(1, Number.isFinite(requested) ? Math.trunc(requested) : 1))
  jumpPage.value = String(page.value)
}

function togglePost(id: string) {
  if (!loaded.value || !posts.value.some((item) => item.id === id && isGraphicPost(item))) return
  form.postIds = form.postIds.includes(id)
    ? form.postIds.filter((item) => item !== id)
    : [...form.postIds, id]
}

function toggleTableSelected(id: string) {
  if (!loaded.value || !posts.value.some((item) => item.id === id && isGraphicPost(item))) return
  tableSelected.value = tableSelected.value.includes(id)
    ? tableSelected.value.filter((item) => item !== id)
    : [...tableSelected.value, id]
}

function addSelectedToQueue() {
  if (!loaded.value) return
  form.postIds = [...new Set([...form.postIds, ...tableSelected.value])]
}

function searchTable() {
  appliedSearch.value = searchQuery.value
  appliedGroup.value = groupFilter.value
  page.value = 1
}

function resetTable() {
  searchQuery.value = ''
  groupFilter.value = ''
  appliedSearch.value = ''
  appliedGroup.value = ''
  page.value = 1
}

function printList() {
  window.print()
}

function exportCsv() {
  const rows = [[copy.value.tableGroup, '标题', '内容', '添加时间'], ...filtered.value.map((post) => [post.groupName, post.title, post.body.replaceAll('\n', ' '), formatDateTime(post.updatedAt)])]
  downloadDataUrl(`data:text/csv;charset=utf-8,${encodeURIComponent(rows.map((line) => line.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(',')).join('\n'))}`, `${copy.value.title}.csv`)
}

function savePlan() {
  if (busy.value || !loaded.value) return
  errorMessage.value = ''
  successMessage.value = ''
  if (isXianyu.value) {
    errorMessage.value = '当前 CloudCtl 版本未接入闲鱼帖子发布。'
    return
  }
  if (!form.deviceIds.length || !form.postIds.length) {
    errorMessage.value = '请先选择计划设备和笔记'
    return
  }
  const snapshot = emptyPublishConfig({ ...form, deviceIds: [...form.deviceIds], postIds: [...form.postIds], autoVideo: false, watermark: false })
  try {
    savePublishConfig(props.platform, snapshot)
    const count = allocatePosts(snapshot.postIds, snapshot.deviceIds, snapshot.allocation).length
    successMessage.value = '计划已保存到当前浏览器：' + count + ' 条分配记录。未创建任务，未下发到手机，未发布内容。'
  } catch (error) {
    errorMessage.value = '浏览器计划保存失败：' + (error instanceof Error ? error.message : String(error))
  }
}

onMounted(() => {
  Object.assign(form, loadPublishConfig(props.platform), { autoVideo: false, watermark: false })
  void loadData()
})
</script>

<template>
  <section class="pub-page">
    <div class="card">
      <h2>{{ isXianyu ? '闲鱼帖子' : '小红书图文' }}分配计划</h2>
      <div class="notice">此页仅预览内容与设备的分配，并将计划保存到当前浏览器。不会创建任务、下发手机或发布内容；清理浏览器数据会丢失计划。</div>
      <p v-if="busy" role="status">正在读取设备与帖子…</p>
      <div v-if="loadError" role="alert">{{ loadError }} <button type="button" :disabled="busy" @click="loadData">重试读取</button></div>
      <fieldset :disabled="busy || !loaded || isXianyu">
        <div v-if="isXianyu" class="notice">当前 CloudCtl 版本未接入闲鱼帖子发布。</div>
        <XianyuDevicePicker v-model="form.deviceIds" :devices="devices" />
        <div class="row top">
          <span class="label">发布的{{ copy.itemLabel }}</span>
          <div>
            <button class="picker" type="button" @click="pickerOpen = true">{{ selectedPosts.length ? selectedPosts.map((item) => item.title).join('，') : copy.pickerPlaceholder }}</button>
            <div class="links">
              已选 <b>{{ form.postIds.length }}</b> {{ copy.itemUnit }}
              <button type="button" @click="pickerOpen = true">选择{{ copy.itemLabel }}</button>
              <button type="button" @click="form.postIds = []">清空</button>
            </div>
          </div>
        </div>
        <div class="row">
          <span class="label">{{ copy.itemLabel }}分配</span>
          <div>
            <label class="radio" for="pub-alloc-default"><input id="pub-alloc-default" v-model="form.allocation" type="radio" value="default" /> 默认</label>
            <label class="radio" for="pub-alloc-even"><input id="pub-alloc-even" v-model="form.allocation" type="radio" value="even" /> 均匀分配</label>
            <p class="hint">分配规则具体解释可阅读本页面底部说明</p>
          </div>
        </div>
        <div v-if="isXianyu" class="row">
          <span class="label">执行应用</span>
          <div>
            <label class="radio" for="pub-app-main"><input id="pub-app-main" v-model="form.app" type="radio" value="main" /> 主闲鱼</label>
            <p class="hint">一期每设备仅绑定一个闲鱼账号，副闲鱼已禁用。</p>
          </div>
        </div>
        <div class="row"><span class="label">媒体处理</span><p class="hint">当前仅规划图文内容，不支持一键成片、视频发布、多开或自动应用水印。</p></div>
        <div class="row">
          <label class="label" for="pub-interval">计划间隔（仅记录）</label>
          <div class="inline">
            <input id="pub-interval" v-model.number="form.intervalSeconds" type="number" min="1" />
            <span>秒</span>
          </div>
        </div>
        <div class="row">
          <span class="label">计划形式（仅记录）</span>
          <div>
            <label class="radio" for="pub-mode-direct"><input id="pub-mode-direct" v-model="form.formMode" type="radio" value="direct" /> 发布意向</label>
            <label v-if="!isXianyu" class="radio" for="pub-mode-draft"><input id="pub-mode-draft" v-model="form.formMode" type="radio" value="draft" /> 草稿意向</label>
          </div>
        </div>
        <div class="row">
          <label class="label" for="pub-schedule">计划时间（仅记录）</label>
          <select id="pub-schedule" v-model="form.schedule">
            <option value="立即执行">暂不安排执行</option>
          </select>
        </div>
        <p v-if="errorMessage" class="flash error" role="alert">{{ errorMessage }}</p>
        <p v-if="successMessage" class="flash ok" role="status">{{ successMessage }}</p>
        <div class="footer">
          <button class="primary" type="button" :disabled="busy || !loaded || isXianyu" @click="savePlan">保存浏览器计划</button>
        </div>
      </fieldset>
      <details class="allocation-preview"><summary>分配预览 · {{ assignments.length }} 条计划记录</summary><p v-if="!assignments.length">选择内容和设备后查看分配；不会自动执行。</p><ul><li v-for="assignment in assignments" :key="assignment.deviceId + ':' + assignment.postId">{{ devices.find((item) => item.id === assignment.deviceId)?.name ?? assignment.deviceId }} → {{ posts.find((item) => item.id === assignment.postId)?.title ?? assignment.postId }}</li></ul></details>
    </div>

    <div class="card table-card">
      <div class="filter">
        <input v-model="searchQuery" aria-label="搜索标题、内容" @keyup.enter="searchTable" :placeholder="`搜索标题、内容`" />
        <select v-model="groupFilter">
          <option value="">{{ copy.groupPlaceholder }}</option>
          <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
        </select>
        <button class="primary" type="button" @click="searchTable">查找</button>
      </div>
      <div class="actions">
        <button class="primary" type="button" @click="addSelectedToQueue">加入计划</button>
        <span class="spacer" />
        <button class="primary" type="button" @click="filterOpen = true">筛选</button>
        <button class="primary" type="button" @click="resetTable">还原</button>
        <button class="primary" type="button" @click="exportCsv">导出</button>
        <button class="primary" type="button" @click="printList">打印</button>
      </div>
      <div class="table-scroll"><table>
        <thead>
          <tr>
            <th class="check"><input v-model="allSelected" type="checkbox" /></th>
            <th>{{ copy.tableGroup }}</th>
            <th>{{ copy.tableMedia }}</th>
            <th>标题</th>
            <th>内容</th>
            <th>添加时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="paged.length === 0"><td colspan="7" class="empty">{{ busy ? '正在读取…' : loadError ? '读取失败，请重试。' : '没有符合条件的内容。可先编辑帖子或调整筛选。' }}</td></tr>
          <tr v-for="post in paged" :key="post.id">
            <td class="check"><input type="checkbox" :disabled="!loaded || !isGraphicPost(post)" :checked="tableSelected.includes(post.id)" @change="toggleTableSelected(post.id)" /></td>
            <td>{{ post.groupName }}</td>
            <td>
              <div class="thumbs">
                <MediaThumb v-for="(image, index) in postImageIds(post).slice(0, 1)" :key="`${post.id}-${image}-${index}`" :asset-id="image" :size="48" :alt="post.title" />
                <span v-if="postImageIds(post).length" class="badge">{{ postImageIds(post).length }}张</span>
                <span v-else class="muted">无图</span>
              </div>
            </td>
            <td>{{ clipText(post.title, 16) }}<small v-if="!isGraphicPost(post)">（视频内容暂不支持）</small></td>
            <td>{{ clipText(post.body, 18) }}</td>
            <td>{{ formatDateTime(post.updatedAt || post.createdAt) }}</td>
            <td class="ops">
              <button type="button" title="加入或移出计划" aria-label="加入或移出计划" :disabled="!loaded || !isGraphicPost(post)" @click="togglePost(post.id)">+</button>
              <button type="button" title="编辑" @click="router.push(`/operations/post-management/post-management-01?id=${post.id}`)">✎</button>
            </td>
          </tr>
        </tbody>
      </table></div>
      <div class="pager">
        <button type="button" :disabled="page <= 1" @click="page -= 1">‹</button>
        <button class="current" type="button">{{ page }}</button>
        <button type="button" :disabled="page >= totalPages" @click="page += 1">›</button>
        <span>到第</span>
        <input v-model="jumpPage" aria-label="跳转页码" inputmode="numeric" @keyup.enter="jumpToPage" />
        <span>页</span>
        <button type="button" @click="jumpToPage">确定</button>
        <span>共 {{ filtered.length }} 条</span>
        <select v-model.number="pageSize"><option :value="10">10条/页</option><option :value="20">20条/页</option></select>
      </div>
    </div>

    <div class="help"><h3>计划说明</h3><ol><li>默认分配：每台所选设备对应全部所选内容。</li><li>均匀分配：内容按所选顺序分配给设备，余数优先分配给前面的设备。</li><li>分配预览与浏览器计划均不代表设备就绪、账号授权或发布成功。</li></ol></div>

    <div v-if="filterOpen" class="mask" @click.self="filterOpen = false">
      <div class="modal">
        <h3>筛选{{ copy.itemLabel }}</h3>
        <input v-model="searchQuery" aria-label="搜索标题、内容" @keyup.enter="searchTable" placeholder="搜索标题、内容" />
        <select v-model="groupFilter">
          <option value="">{{ copy.groupPlaceholder }}</option>
          <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
        </select>
        <div class="modal-actions"><button class="primary" type="button" @click="searchTable(); filterOpen = false">确定</button></div>
      </div>
    </div>

    <div v-if="pickerOpen" class="mask" @click.self="pickerOpen = false">
      <div class="modal">
        <h3>选择{{ copy.itemLabel }}</h3>
        <label v-for="post in posts" :key="post.id" class="pick-row">
          <input type="checkbox" :disabled="!loaded || !isGraphicPost(post)" :checked="form.postIds.includes(post.id)" @change="togglePost(post.id)" />
          <strong>{{ post.title || '未命名' }}</strong>
          <small>{{ isGraphicPost(post) ? post.groupName : '视频内容暂不支持' }}</small>
        </label>
        <p v-if="posts.length === 0" class="hint">还没有{{ copy.itemLabel }}。</p>
        <div class="modal-actions"><button class="primary" type="button" @click="pickerOpen = false">确定</button></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.pub-page { display: grid; gap: 10px; color: #334155; }
.card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; gap: 14px; }
h2 { margin: 0; font-size: 15px; }
.notice { padding: 12px 14px; background: #f8fafc; border-left: 4px solid #0f766e; color: #475569; font-size: 13px; }
.row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: center; }
.row.top { align-items: start; }
.label { color: #64748b; font-size: 13px; padding-top: 6px; }
input[type='number'], select, .picker { width: min(280px, 100%); height: 34px; padding: 0 10px; border: 1px solid #d1d5db; border-radius: 4px; font: inherit; background: #fff; text-align: left; }
.picker { width: 100%; color: #94a3b8; }
.inline { display: flex; align-items: center; gap: 8px; }
.radio, .chip { display: inline-flex; align-items: center; gap: 6px; margin: 0 12px 8px 0; }
.chip { padding: 4px 8px; border: 1px solid #e5e7eb; border-radius: 6px; }
.chip small { padding: 0 6px; border-radius: 4px; font-size: 11px; background: #f1f5f9; }
.chip small.on { background: #dcfce7; color: #166534; }
.chip small.off { color: #64748b; }
.links { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 6px; color: #0f766e; font-size: 13px; }
.links button { border: 0; background: none; color: #0f766e; padding: 0; }
.count { min-width: 22px; height: 22px; padding: 0 6px; border-radius: 4px; background: #f1f5f9; color: #334155; text-align: center; }
.hint { margin: 6px 0 0; color: #94a3b8; font-size: 12px; }
.footer { padding-left: 100px; display: flex; gap: 10px; }
.primary, .outline { height: 32px; padding: 0 14px; border-radius: 4px; border: 1px solid #0f766e; background: #0f766e; color: #fff; }
.outline { background: #fff; color: #0f766e; }
.flash { margin: 0; padding-left: 100px; font-size: 13px; }
.flash.error { color: #b91c1c; }
.flash.ok { color: #166534; }
.filter, .actions, .pager { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.filter input, .filter select, .pager input, .pager select { width: auto; }
.spacer { flex: 1; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 10px 8px; border-bottom: 1px solid #eef2f7; text-align: left; }
.check { width: 36px; }
.thumbs { display: flex; align-items: center; gap: 6px; }
.thumbs img { width: 48px; height: 48px; object-fit: cover; border-radius: 4px; }
.badge { font-size: 11px; color: #0f766e; }
.muted, .empty { color: #94a3b8; }
.ops button { width: 24px; height: 24px; margin-right: 4px; border: 0; background: none; color: #0f766e; }
.pager .current { background: #0f766e; color: #fff; border: 0; border-radius: 4px; min-width: 28px; height: 28px; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.help a { color: #0f766e; }
.tag { display: inline-block; padding: 1px 6px; margin-right: 6px; background: #f1f5f9; border-radius: 4px; font-size: 12px; }
.mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.35); display: grid; place-items: center; }
.modal { width: min(520px, 92vw); background: #fff; border-radius: 8px; padding: 16px; display: grid; gap: 10px; }
.pick-row { display: grid; grid-template-columns: auto 1fr auto; gap: 8px; align-items: center; }
.modal-actions { display: flex; justify-content: flex-end; }
fieldset { margin: 0; padding: 0; border: 0; display: grid; gap: 14px; min-width: 0; }
.allocation-preview { font-size: 13px; overflow-wrap: anywhere; }
.allocation-preview ul { max-height: 240px; overflow: auto; }
.table-scroll { overflow-x: auto; }
.table-scroll table { min-width: 650px; }
.modal { max-height: 85vh; overflow: auto; }
button:disabled { opacity: .5; cursor: not-allowed; }
@media (max-width: 600px) { .row { grid-template-columns: 1fr; } .footer, .flash { padding-left: 0; } .picker { height: auto; min-height: 34px; overflow-wrap: anywhere; } }
</style>
