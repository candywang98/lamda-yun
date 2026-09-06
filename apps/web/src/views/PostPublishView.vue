<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice } from '@/api/devices'
import { createPostCatalog } from '@/api/post-catalog'
import { clipText, formatDateTime, type PostRecord } from '@/data/post-fields'
import { downloadDataUrl } from '@/data/product-fields'
import {
  allocatePosts,
  emptyPublishConfig,
  loadPublishConfig,
  platformCopy,
  savePublishConfig,
  type PostPublishDevice,
  type PostPublishPlatform,
} from '@/data/post-publish'

const props = defineProps<{ platform: PostPublishPlatform }>()
const router = useRouter()
const catalog = createPostCatalog()
const copy = computed(() => platformCopy(props.platform))
const form = reactive(emptyPublishConfig())
const devices = ref<PostPublishDevice[]>([])
const posts = ref<PostRecord[]>([])
const searchQuery = ref('')
const appliedSearch = ref('')
const groupFilter = ref('')
const appliedGroup = ref('')
const page = ref(1)
const pageSize = ref(10)
const jumpPage = ref('1')
const pickerOpen = ref(false)
const busy = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const groups = computed(() => [...new Set(posts.value.map((item) => item.groupName || '默认分组'))])
const selectedPosts = computed(() => posts.value.filter((item) => form.postIds.includes(item.id)))
const filtered = computed(() => posts.value.filter((post) => {
  const haystack = `${post.title}${post.body}${post.notes}`.toLowerCase()
  if (appliedSearch.value && !haystack.includes(appliedSearch.value.trim().toLowerCase())) return false
  if (appliedGroup.value && post.groupName !== appliedGroup.value) return false
  return true
}))
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const selectedCount = computed(() => devices.value.filter((item) => form.deviceIds.includes(item.id)).length)
const assignments = computed(() => allocatePosts(form.postIds, form.deviceIds, form.allocation))
const isXianyu = computed(() => props.platform === 'xianyu')

async function loadDevices() {
  if (!controlApiConfigured) {
    devices.value = []
    return
  }
  try {
    const api = createControlApiClient()
    devices.value = (await api.devices()).map((item) => {
      const mapped = mapControlDevice(item)
      return { id: mapped.id, name: mapped.name, online: mapped.presence === 'ONLINE' }
    })
  } catch {
    devices.value = []
  }
}

async function loadPosts() {
  posts.value = await catalog.list()
}

function toggleDevice(id: string) {
  form.deviceIds = form.deviceIds.includes(id)
    ? form.deviceIds.filter((item) => item !== id)
    : [...form.deviceIds, id]
}

function selectAllDevices() {
  const ids = devices.value.map((item) => item.id)
  form.deviceIds = form.deviceIds.length === ids.length ? [] : ids
}

function selectOnlineDevices() {
  form.deviceIds = devices.value.filter((item) => item.online).map((item) => item.id)
}

function togglePost(id: string) {
  form.postIds = form.postIds.includes(id)
    ? form.postIds.filter((item) => item !== id)
    : [...form.postIds, id]
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

function saveConfig() {
  savePublishConfig(props.platform, form)
  successMessage.value = '配置已保存到当前浏览器'
  errorMessage.value = ''
}

function createTask() {
  errorMessage.value = ''
  successMessage.value = ''
  if (form.deviceIds.length === 0) {
    errorMessage.value = '请先选择执行设备'
    return
  }
  if (form.postIds.length === 0) {
    errorMessage.value = `请先选择要发布的${copy.value.itemLabel}`
    return
  }
  if (isXianyu.value) {
    errorMessage.value = '闲鱼已下线「发布帖子」功能，本任务暂无法执行。配置已保留，入口恢复后无需重新设置。'
    savePublishConfig(props.platform, form)
    return
  }
  savePublishConfig(props.platform, form)
  successMessage.value = `已保存发布计划：${assignments.value.length} 条分配记录。不会登录小红书，也不会下发到手机。`
}

onMounted(async () => {
  Object.assign(form, loadPublishConfig(props.platform))
  await Promise.all([loadDevices(), loadPosts()])
  form.postIds = form.postIds.filter((id) => posts.value.some((item) => item.id === id))
  form.deviceIds = form.deviceIds.filter((id) => devices.value.some((item) => item.id === id))
})
</script>

<template>
  <section class="pub-page">
    <div class="card">
      <h2>{{ copy.title }}</h2>
      <div v-if="isXianyu" class="notice">闲鱼已下线「发布帖子」功能，本任务暂无法执行。若后续入口恢复，无需重新配置即可直接使用。</div>
      <div class="row top">
        <span class="label">执行设备</span>
        <div>
          <div v-if="devices.length === 0" class="hint">当前没有已接入设备。接入 Companion 后会出现在这里。</div>
          <label v-for="device in devices" :key="device.id" class="chip">
            <input type="checkbox" :checked="form.deviceIds.includes(device.id)" @change="toggleDevice(device.id)" />
            {{ device.name }}
            <small :class="device.online ? 'on' : 'off'">{{ device.online ? '在线' : '离线' }}</small>
          </label>
          <div class="links">
            <button type="button" @click="selectAllDevices">全选/反选设备</button>
            <button type="button" @click="selectOnlineDevices">全选在线设备</button>
            <button type="button" @click="form.deviceIds = []">全部取消选择</button>
            <span class="count">{{ selectedCount }}</span>
          </div>
        </div>
      </div>
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
          <label class="radio" for="pub-app-sub"><input id="pub-app-sub" v-model="form.app" type="radio" value="sub" /> 副闲鱼</label>
        </div>
      </div>
      <template v-else>
        <div class="row">
          <span class="label">适配多开</span>
          <div>
            <label class="radio" for="pub-multi-off"><input id="pub-multi-off" v-model="form.multiOpen" type="radio" :value="false" /> 关闭</label>
            <label class="radio" for="pub-multi-on"><input id="pub-multi-on" v-model="form.multiOpen" type="radio" :value="true" /> 红薯多开</label>
          </div>
        </div>
        <div class="row">
          <span class="label">一键成片</span>
          <div>
            <label class="radio" for="pub-video-off"><input id="pub-video-off" v-model="form.autoVideo" type="radio" :value="false" /> 关</label>
            <label class="radio" for="pub-video-on"><input id="pub-video-on" v-model="form.autoVideo" type="radio" :value="true" /> 开</label>
          </div>
        </div>
      </template>
      <div class="row">
        <span class="label">图片水印</span>
        <div>
          <label class="radio" for="pub-wm-on"><input id="pub-wm-on" v-model="form.watermark" type="radio" :value="true" /> 开启</label>
          <label class="radio" for="pub-wm-off"><input id="pub-wm-off" v-model="form.watermark" type="radio" :value="false" /> 关闭</label>
          <div class="links"><button type="button" @click="router.push('/operations/post-management/post-management-05')">设置水印</button></div>
        </div>
      </div>
      <div class="row">
        <label class="label" for="pub-interval">发布间隔</label>
        <div class="inline">
          <input id="pub-interval" v-model.number="form.intervalSeconds" type="number" min="1" />
          <span>秒</span>
        </div>
      </div>
      <div class="row">
        <span class="label">发布形式</span>
        <div>
          <label class="radio" for="pub-mode-direct"><input id="pub-mode-direct" v-model="form.formMode" type="radio" value="direct" /> 直接发布</label>
          <label v-if="!isXianyu" class="radio" for="pub-mode-draft"><input id="pub-mode-draft" v-model="form.formMode" type="radio" value="draft" /> 存草稿</label>
        </div>
      </div>
      <div class="row">
        <label class="label" for="pub-schedule">执行时间</label>
        <select id="pub-schedule" v-model="form.schedule">
          <option>立即执行</option>
        </select>
      </div>
      <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok">{{ successMessage }}</p>
      <div class="footer">
        <button class="primary" type="button" :disabled="busy" @click="createTask">创建任务</button>
        <button class="primary" type="button" :disabled="busy" @click="saveConfig">保存配置</button>
      </div>
    </div>

    <div class="card table-card">
      <div class="filter">
        <input v-model="searchQuery" :placeholder="`搜索标题、内容`" />
        <select v-model="groupFilter">
          <option value="">{{ copy.groupPlaceholder }}</option>
          <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
        </select>
        <button class="primary" type="button" @click="searchTable">查找</button>
      </div>
      <div class="actions">
        <button class="primary" type="button" @click="pickerOpen = true">添加发布</button>
        <span class="spacer" />
        <button class="outline" type="button">筛选</button>
        <button class="outline" type="button" @click="resetTable">还原</button>
        <button class="outline" type="button" @click="exportCsv">导出</button>
        <button class="outline" type="button" @click="printList">打印</button>
      </div>
      <table>
        <thead>
          <tr>
            <th class="check"></th>
            <th>{{ copy.tableGroup }}</th>
            <th>{{ copy.tableMedia }}</th>
            <th>标题</th>
            <th>内容</th>
            <th>添加时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="paged.length === 0"><td colspan="7" class="empty">无{{ copy.itemLabel }}数据，请先编辑{{ copy.itemLabel }}或采集后再发布。</td></tr>
          <tr v-for="post in paged" :key="post.id">
            <td class="check"><input type="checkbox" :checked="form.postIds.includes(post.id)" @change="togglePost(post.id)" /></td>
            <td>{{ post.groupName }}</td>
            <td>
              <div class="thumbs">
                <img v-for="(image, index) in post.images.slice(0, 1)" :key="index" :src="image" alt="" />
                <span v-if="post.images.length" class="badge">{{ post.images.length }}张</span>
                <span v-else class="muted">无图</span>
              </div>
            </td>
            <td>{{ clipText(post.title, 16) }}</td>
            <td>{{ clipText(post.body, 18) }}</td>
            <td>{{ formatDateTime(post.updatedAt || post.createdAt) }}</td>
            <td class="ops">
              <button type="button" title="添加发布" @click="togglePost(post.id)">+</button>
              <button type="button" title="编辑" @click="router.push(`/operations/post-management/post-management-01?id=${post.id}`)">✎</button>
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
        <li>{{ copy.helpLead }}</li>
        <li>在下方的表格选择要发布的{{ copy.itemLabel }}，前方的复选框可多选，每一列后面的+可单选</li>
        <li>您可在<a href="javascript:void(0)" @click="router.push('/operations/post-management/post-management-05')">水印设置</a>为发布的{{ copy.itemLabel }}设置水印，包括内容、字体样式、字体大小、颜色、透明度、水印位置</li>
        <li>
          {{ copy.itemLabel }}分配方式分为“默认”和“均匀分配”两种：
          <p><span class="tag">默认</span> 所选{{ copy.itemLabel }}会在每台选定的设备上发布一次，例如若选择了五个{{ copy.itemLabel }}（编号为1、2、3、4、5）并选定了设备A和B，则每个{{ copy.itemLabel }}都会在这两个设备上各发布一次，总共发布十个{{ copy.itemLabel }}。</p>
          <p><span class="tag">均匀分配</span> 系统尽可能将{{ copy.itemLabel }}平均地分配到每台设备上。例如，若{{ copy.itemLabel }}总数能被设备数整除，则每台设备上的{{ copy.itemLabel }}数相同；若不能整除，则多出的{{ copy.itemLabel }}将依次分配给前面的设备。</p>
          <p>按照均匀分配的规则，如果还是五个{{ copy.itemLabel }}（1、2、3、4、5）分配给设备A和B，那么设备A会发布{{ copy.itemLabel }}1、2、3，而设备B发布{{ copy.itemLabel }}4、5，总共发布五个{{ copy.itemLabel }}。</p>
        </li>
        <li v-if="!isXianyu"><span class="tag">适配多开</span> 红薯多开运行任务前，请手动切换红薯分身到前台，暂无法像闲鱼那样选择主副应用</li>
      </ol>
    </div>

    <div v-if="pickerOpen" class="mask" @click.self="pickerOpen = false">
      <div class="modal">
        <h3>选择{{ copy.itemLabel }}</h3>
        <label v-for="post in posts" :key="post.id" class="pick-row">
          <input type="checkbox" :checked="form.postIds.includes(post.id)" @change="togglePost(post.id)" />
          <strong>{{ post.title || '未命名' }}</strong>
          <small>{{ post.groupName }}</small>
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
</style>
