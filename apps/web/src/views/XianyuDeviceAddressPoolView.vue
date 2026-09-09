<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  downloadCsv,
  loadDeviceAddressMap,
  MAX_DEVICE_ADDRESSES,
  saveDeviceAddressMap,
  type DeviceAddressRow,
} from '@/data/xianyu-material-pools'
import { fetchXianyuTaskDevices, type XianyuTaskDevice } from '@/data/xianyu-task-devices'

const router = useRouter()
const devices = ref<XianyuTaskDevice[]>([])
const poolMap = reactive<Record<string, DeviceAddressRow>>({})
const searchQuery = ref('')
const appliedSearch = ref('')
const groupFilter = ref('')
const appliedGroup = ref('')
const page = ref(1)
const pageSize = ref(10)
const jumpPage = ref('1')
const editor = ref<DeviceAddressRow | null>(null)
const editorText = ref('')
const successMessage = ref('')

const groups = computed(() => [...new Set(devices.value.map((item) => poolMap[item.id]?.groupNo || '1'))])
const rows = computed(() => devices.value.map((device) => {
  const saved = poolMap[device.id]
  return {
    deviceId: device.id,
    groupNo: saved?.groupNo || '1',
    name: device.name,
    account: device.account || '暂无',
    note: saved?.note || '',
    addresses: saved?.addresses ?? [],
    online: device.online,
  }
}))
const filtered = computed(() => rows.value.filter((row) => {
  const haystack = `${row.name}${row.account}${row.note}${row.addresses.join(' ')}`.toLowerCase()
  if (appliedSearch.value && !haystack.includes(appliedSearch.value.trim().toLowerCase())) return false
  if (appliedGroup.value && row.groupNo !== appliedGroup.value) return false
  return true
}))
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))

function persist() {
  saveDeviceAddressMap({ ...poolMap })
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

function openEditor(row: (typeof rows.value)[number]) {
  editor.value = {
    deviceId: row.deviceId,
    groupNo: row.groupNo,
    note: row.note,
    addresses: [...row.addresses],
  }
  editorText.value = row.addresses.join('\n')
}

function saveEditor() {
  if (!editor.value) return
  const addresses = editorText.value.split(/\n+/).map((item) => item.trim()).filter(Boolean).slice(0, MAX_DEVICE_ADDRESSES)
  poolMap[editor.value.deviceId] = {
    ...editor.value,
    addresses,
  }
  persist()
  editor.value = null
  successMessage.value = '地址池已保存到当前浏览器'
}

function printPage() {
  window.print()
}

onMounted(async () => {
  Object.assign(poolMap, loadDeviceAddressMap())
  devices.value = await fetchXianyuTaskDevices()
})
</script>

<template>
  <section class="page">
    <div class="card">
      <h2>设备地址池</h2>
      <div class="filter">
        <input v-model="searchQuery" placeholder="搜索设备名、手机品牌、会员名等" />
        <select v-model="groupFilter">
          <option value="">设备组号</option>
          <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
        </select>
        <button class="primary" type="button" @click="searchTable">查找</button>
      </div>
      <p v-if="successMessage" class="ok">{{ successMessage }}</p>
      <div class="table-card">
        <div class="actions">
          <span class="spacer" />
          <button class="outline" type="button">筛选</button>
          <button class="outline" type="button" @click="resetTable">还原</button>
          <button class="outline" type="button" @click="downloadCsv('设备地址池.csv', [['组号', '设备名称', '某鱼会员名', '地址数量', '地址池', '地址池备注'], ...filtered.map((row) => [row.groupNo, row.name, row.account, String(row.addresses.length), row.addresses.join(' / ') || '暂无', row.note])])">导出</button>
          <button class="outline" type="button" @click="printPage">打印</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>组号</th>
              <th>设备名称</th>
              <th>某鱼会员名</th>
              <th>地址数量</th>
              <th>地址池（点击可编辑）</th>
              <th>地址池备注</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="paged.length === 0"><td colspan="7" class="empty">当前没有已接入设备。</td></tr>
            <tr v-for="row in paged" :key="row.deviceId">
              <td>{{ row.groupNo }}</td>
              <td>{{ row.name }}</td>
              <td>{{ row.account }}</td>
              <td>{{ row.addresses.length }}</td>
              <td><button class="link" type="button" @click="openEditor(row)">{{ row.addresses.join(' / ') || '暂无' }}</button></td>
              <td>{{ row.note }}</td>
              <td><button class="link" type="button" title="编辑" @click="openEditor(row)">✎</button></td>
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
    </div>
    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>可在本页面为每个设备设置地址池，发布商品时勾选 <span class="tag">设备地址模式</span> 模式时会使用本页地址池。</li>
        <li>若某设备地址池中配置了多个地址，系统将随机选取其中一个使用；若仅配置了一个地址，则直接使用该地址。</li>
        <li>单设备地址限制50个，建议设置为某区，或设置某市的多个区。</li>
        <li>本页仅可编辑设备的地址池、地址池备注，若需修改设备的其他信息请前往 <button class="link" type="button" @click="router.push('/operations/system-home/system-home-02')">设备列表</button> 操作。</li>
      </ol>
    </div>
    <div v-if="editor" class="mask" @click.self="editor = null">
      <div class="modal">
        <h3>编辑地址池</h3>
        <label>地址池备注<input v-model="editor.note" /></label>
        <label>地址（每行一个，最多 {{ MAX_DEVICE_ADDRESSES }} 个）<textarea v-model="editorText" rows="8" /></label>
        <div class="modal-actions">
          <button type="button" @click="editor = null">取消</button>
          <button class="primary" type="button" @click="saveEditor">保存</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page { display: grid; gap: 10px; color: #334155; }
.card, .help, .table-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; gap: 12px; }
h2 { margin: 0; font-size: 15px; }
.filter, .actions, .pager { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
input, select, textarea { height: 34px; padding: 0 10px; border: 1px solid #d1d5db; border-radius: 4px; font: inherit; }
textarea { height: auto; width: 100%; padding: 8px 10px; }
.primary { height: 34px; padding: 0 16px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; }
.outline { height: 32px; padding: 0 12px; border-radius: 4px; border: 1px solid #0f766e; background: #fff; color: #0f766e; }
.spacer { flex: 1; }
.ok { margin: 0; color: #166534; font-size: 13px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 10px 8px; border-bottom: 1px solid #f1f5f9; text-align: left; }
th { color: #64748b; background: #f8fafc; }
.empty { color: #94a3b8; }
.link { border: 0; background: none; color: #0f766e; padding: 0; }
.pager button { height: 28px; min-width: 28px; border: 1px solid #d1d5db; background: #fff; border-radius: 4px; }
.pager .current { background: #0f766e; color: #fff; border-color: #0f766e; }
.help { padding: 12px 14px 16px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.tag { display: inline-block; padding: 0 6px; border-radius: 4px; background: #ecfdf5; color: #0f766e; }
.mask { position: fixed; inset: 0; background: rgb(15 23 42 / 0.35); display: grid; place-items: center; }
.modal { width: min(480px, 92vw); background: #fff; border-radius: 8px; padding: 16px; display: grid; gap: 10px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
