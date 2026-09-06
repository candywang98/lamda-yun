<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { ProductView } from '@cloudctl/api-contracts'
import { createProductCatalog } from '@/api/product-catalog'
import XianyuDevicePicker from '@/components/XianyuDevicePicker.vue'
import {
  allocateProducts,
  emptyPublishGoodsConfig,
  FAN_DISCOUNT_OPTIONS,
  loadPublishGoodsConfig,
  recordPublishGoodsTask,
  savePublishGoodsConfig,
  VIDEO_MUSIC_OPTIONS,
} from '@/data/xianyu-publish-goods'
import { clipText, downloadDataUrl, parseAttributes, productGroupName, productImages, productSpecLabel } from '@/data/product-fields'
import { resolveProductGroups } from '@/data/product-groups'
import { fetchXianyuTaskDevices, type XianyuTaskDevice } from '@/data/xianyu-task-devices'

const router = useRouter()
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
const assignments = computed(() => allocateProducts(form.productIds, form.deviceIds, form.allocation))

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
  savePublishGoodsConfig(form)
  errorMessage.value = ''
  successMessage.value = '配置已保存到当前浏览器'
}

function createTask() {
  errorMessage.value = ''
  successMessage.value = ''
  if (form.deviceIds.length === 0) {
    errorMessage.value = '请先选择执行设备'
    return
  }
  if (form.productIds.length === 0) {
    errorMessage.value = '请先选择待发布宝贝'
    return
  }
  savePublishGoodsConfig(form)
  recordPublishGoodsTask(form)
  successMessage.value = `已保存发布计划：${assignments.value.length} 条分配记录。不会登录闲鱼，也不会下发到手机。`
}

onMounted(async () => {
  Object.assign(form, loadPublishGoodsConfig())
  const [deviceList, productList] = await Promise.all([fetchXianyuTaskDevices(), catalog.list()])
  devices.value = deviceList
  products.value = productList
  form.deviceIds = form.deviceIds.filter((id) => devices.value.some((item) => item.id === id))
  form.productIds = form.productIds.filter((id) => products.value.some((item) => item.id === id))
})
</script>

<template>
  <section class="page">
    <div class="card">
      <h2>发布某鱼商品</h2>
      <div class="row">
        <span class="label">执行操作</span>
        <div class="footer flush">
          <button class="primary" type="button" @click="createTask">创建任务</button>
          <button class="primary" type="button" @click="saveConfig">保存配置</button>
        </div>
      </div>
      <XianyuDevicePicker v-model="form.deviceIds" :devices="devices" />
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
          <label class="radio" for="xy-app-sub"><input id="xy-app-sub" v-model="form.app" type="radio" value="sub" /> 副闲鱼</label>
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
      <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok">{{ successMessage }}</p>
      <div class="footer">
        <button class="primary" type="button" @click="createTask">创建任务</button>
        <button class="primary" type="button" @click="saveConfig">保存配置</button>
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
                <img v-for="(image, index) in productImages(product).slice(0, 3)" :key="index" :src="image" alt="" />
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

    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>在下方表格选择要发布的宝贝，前方复选框可多选后点「添加至待发布」，每一列后面的 + 可单选。</li>
        <li>
          商品分配方式分为“默认”和“均匀分配”两种：
          <p><span class="tag">默认</span> 所选宝贝会在每台选定的设备上发布一次。</p>
          <p><span class="tag">均匀分配</span> 系统尽可能将宝贝平均分配到每台设备上。</p>
        </li>
        <li>默认地址使用宝贝编辑页地点；随机地址从所选地址池抽取；多地铺货会按地址池每个地点发一遍。</li>
        <li>仅当设备在线时，才能创建定时执行任务和每天重复执行的任务。</li>
      </ol>
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
.page { display: grid; gap: 10px; color: #334155; }
.card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; gap: 14px; }
h2 { margin: 0; font-size: 15px; }
.row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: center; }
.row.top { align-items: start; }
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
.footer { padding-left: 100px; display: flex; gap: 10px; }
.footer.flush { padding-left: 0; }
.primary { height: 34px; padding: 0 16px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; }
.outline { height: 32px; padding: 0 12px; border-radius: 4px; border: 1px solid #0f766e; background: #fff; color: #0f766e; }
.flash { margin: 0; padding-left: 100px; font-size: 13px; }
.flash.error { color: #b91c1c; }
.flash.ok { color: #166534; }
.filter, .actions, .pager { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.spacer { flex: 1; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 10px 8px; border-bottom: 1px solid #f1f5f9; text-align: left; }
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
