<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { ProductView } from '@cloudctl/api-contracts'
import { createProductCatalog } from '@/api/product-catalog'
import { controlApiConfigured } from '@/api/control'
import { uploadMediaFile } from '@/api/media-assets'
import MediaThumb from '@/components/MediaThumb.vue'
import {
  attributesPayload,
  emptyAttributes,
  normalizePrice,
  parseAttributes,
  type ProductAttributes,
} from '@/data/product-fields'

interface ProductForm {
  title: string
  description: string
  price: string
  stock: string
  spuCode: string
  attributes: ProductAttributes
}

const route = useRoute()
const router = useRouter()
const catalog = createProductCatalog()
const busy = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const current = ref<ProductView | null>(null)
const tagDraft = reactive({ spec: '', label: '', theme: '', brand: '', address: '' })
const imageInput = ref<HTMLInputElement | null>(null)
const videoInput = ref<HTMLInputElement | null>(null)

const form = reactive<ProductForm>({
  title: '',
  description: '',
  price: '',
  stock: '1',
  spuCode: '',
  attributes: emptyAttributes(),
})

const productId = computed(() => {
  const value = route.query.id
  return typeof value === 'string' && value.length > 0 ? value : ''
})

function resetForm() {
  form.title = ''
  form.description = ''
  form.price = ''
  form.stock = '1'
  form.spuCode = current.value?.spuCode ?? ''
  form.attributes = emptyAttributes()
  successMessage.value = '已重置，尚未保存'
}

function applyProduct(product: ProductView) {
  current.value = product
  const attributes = parseAttributes(product.attributes)
  form.title = product.title
  form.description = product.description
  form.price = product.price
  form.stock = String(product.stock)
  form.spuCode = product.spuCode
  if (!attributes.groupName) attributes.groupName = product.category
  form.attributes = attributes
}

async function loadProduct() {
  errorMessage.value = ''
  if (!productId.value) {
    resetForm()
    successMessage.value = ''
    return
  }
  busy.value = true
  try {
    applyProduct(await catalog.get(productId.value))
  } catch (error) {
    errorMessage.value = `加载商品失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    busy.value = false
  }
}

function addTag(list: string[], value: string) {
  const next = value.trim()
  if (!next || list.includes(next)) return
  list.push(next)
}

function removeTag(list: string[], index: number) {
  list.splice(index, 1)
}

async function normalizeProductImage(file: File): Promise<File> {
  const name = file.name.toLowerCase()
  const looksLikeWebp = file.type === 'image/webp' || name.endsWith('.webp') || name.includes('.jpg_.webp')
  const messyName = /!/.test(file.name) || name.includes('.jpg_q')
  if (!looksLikeWebp && !messyName) return file
  if (!looksLikeWebp) {
    const ext = file.type === 'image/png' ? 'png' : file.type === 'image/jpeg' ? 'jpg' : 'bin'
    return new File([file], `product-${Date.now()}.${ext}`, { type: file.type || 'application/octet-stream' })
  }
  const bitmap = await createImageBitmap(file)
  const canvas = document.createElement('canvas')
  canvas.width = bitmap.width
  canvas.height = bitmap.height
  const context = canvas.getContext('2d')
  if (!context) throw new Error('无法转码图片')
  context.drawImage(bitmap, 0, 0)
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((next) => (next ? resolve(next) : reject(new Error('WebP 转 JPEG 失败'))), 'image/jpeg', 0.9)
  })
  return new File([blob], `product-${Date.now()}.jpg`, { type: 'image/jpeg' })
}

async function onPickImages(event: Event) {
  const input = event.target as HTMLInputElement
  const files = [...(input.files ?? [])]
  input.value = ''
  if (!controlApiConfigured) {
    errorMessage.value = '未配置 Control API，禁止把图片写成 blob/dataURL'
    return
  }
  errorMessage.value = ''
  try {
    for (const file of files.slice(0, 9 - form.attributes.imageAssetIds.length)) {
      const normalized = await normalizeProductImage(file)
      const asset = await uploadMediaFile(normalized, { role: 'product-image' })
      form.attributes.imageAssetIds.push(asset.id)
      form.attributes.images.push(asset.id)
    }
  } catch (error) {
    errorMessage.value = `图片上传失败：${error instanceof Error ? error.message : String(error)}`
  }
}

async function onPickVideo(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!controlApiConfigured) {
    errorMessage.value = '未配置 Control API，禁止把视频写成 blob URL'
    return
  }
  const asset = await uploadMediaFile(file, { role: 'product-video' })
  form.attributes.videoName = file.name
  form.attributes.videoAssetId = asset.id
  form.attributes.videoUrl = asset.id
}

function clearImages() {
  form.attributes.images = []
  form.attributes.imageAssetIds = []
}

function moveImage(index: number, offset: number) {
  const next = index + offset
  if (next < 0 || next >= form.attributes.imageAssetIds.length) return
  const copy = [...form.attributes.imageAssetIds]
  const [item] = copy.splice(index, 1)
  copy.splice(next, 0, item!)
  form.attributes.imageAssetIds = copy
  form.attributes.images = [...copy]
}

async function saveProduct() {
  const title = form.title.trim()
  if (!title) {
    errorMessage.value = '请填写标题后再保存'
    return
  }
  busy.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const saved = await catalog.save({
        id: current.value?.id ?? (productId.value || null),
      expectedRevision: current.value?.revision ?? 1,
      payload: {
        spuCode: form.spuCode.trim() || `SPU-${Date.now()}`,
        title,
        description: form.description,
        category: form.attributes.groupName.trim() || '默认分组',
        price: normalizePrice(form.price),
        stock: Number(form.stock) || 0,
        mediaAssetIds: [
          ...form.attributes.imageAssetIds,
          ...(form.attributes.videoAssetId ? [form.attributes.videoAssetId] : []),
        ],
        attributes: attributesPayload(form.attributes),
      },
    })
    applyProduct(saved)
    if (!productId.value) {
      await router.replace({ path: route.path, query: { id: saved.id } })
    }
    successMessage.value = '已保存编辑'
  } catch (error) {
    errorMessage.value = `保存失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    busy.value = false
  }
}

watch(productId, () => {
  void loadProduct()
})

onMounted(() => {
  void loadProduct()
})
</script>

<template>
  <section class="editor">
    <header class="bar">
      <strong>编辑普通宝贝</strong>
    </header>

    <div class="panel">
      <div class="row">
        <span class="label">执行操作</span>
        <div class="actions">
          <button class="primary" type="button" :disabled="busy" @click="saveProduct">保存编辑</button>
          <button type="button" :disabled="busy" @click="resetForm">重置</button>
        </div>
      </div>

      <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok">{{ successMessage }}</p>

      <div class="row">
        <label class="label" for="product-title">标题</label>
        <div class="grow">
          <input id="product-title" v-model="form.title" />
          <textarea v-model="form.attributes.titlePool" rows="5" placeholder="第二个标题&#10;第三个标题&#10;第四个标题&#10;更多标题..." />
          <small>发布商品时勾选“随机标题”可以在上面的标题和标题池中随机</small>
        </div>
      </div>

      <div class="row">
        <label class="label" for="product-description">描述</label>
        <div class="split">
          <textarea id="product-description" v-model="form.description" rows="10" />
          <div class="grow">
            <textarea v-model="form.attributes.rewriteText" rows="10" placeholder="改写文本（可选）" />
            <small>填写改写文本后，系统会将它作为宝贝描述</small>
          </div>
        </div>
      </div>

      <div class="row">
        <span class="label">宝贝规格</span>
        <div class="grow box">
          <div class="inline">
            <span>规格1</span>
            <select v-model="form.attributes.specType">
              <option value="">请选择规格类型</option>
              <option>成色</option>
              <option>克重</option>
              <option>颜色</option>
              <option>尺寸</option>
            </select>
            <button class="link" type="button" @click="form.attributes.specValues = []">清空</button>
          </div>
          <div class="tags">
            <span v-for="(item, index) in form.attributes.specValues" :key="item" class="tag">{{ item }} <button type="button" @click="removeTag(form.attributes.specValues, index)">×</button></span>
            <input v-model="tagDraft.spec" placeholder="+ 添加规格值" @keydown.enter.prevent="addTag(form.attributes.specValues, tagDraft.spec); tagDraft.spec = ''" />
          </div>
        </div>
      </div>

      <div class="row">
        <span class="label">宝贝图片</span>
        <div class="grow">
          <div class="actions">
            <button type="button" @click="imageInput?.click()">多图片上传</button>
            <button class="danger" type="button" @click="clearImages">清除图片</button>
            <input ref="imageInput" class="hidden" type="file" accept="image/*" multiple @change="onPickImages" />
          </div>
          <small>Windows 按 Ctrl 多选，Mac 按 Command 多选。上传后第一张为封面，可上移下移排序。</small>
          <div class="gallery">
            <div v-for="(image, index) in form.attributes.imageAssetIds" :key="image" class="thumb">
              <MediaThumb :asset-id="image" :size="108" :alt="`图片 ${index + 1}`" />
              <button class="x" type="button" @click="form.attributes.imageAssetIds.splice(index, 1); form.attributes.images.splice(index, 1)">×</button>
              <div class="thumb-ops">
                <button type="button" :disabled="index === 0" @click="moveImage(index, -1)">←</button>
                <button type="button" :disabled="index === form.attributes.imageAssetIds.length - 1" @click="moveImage(index, 1)">→</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="row">
        <span class="label">图片标签</span>
        <div class="grow tags">
          <span v-for="(item, index) in form.attributes.imageLabels" :key="item" class="tag">{{ item }} <button type="button" @click="removeTag(form.attributes.imageLabels, index)">×</button></span>
          <input v-model="tagDraft.label" placeholder="输入后回车" @keydown.enter.prevent="addTag(form.attributes.imageLabels, tagDraft.label); tagDraft.label = ''" />
        </div>
      </div>

      <div class="row">
        <span class="label">视频</span>
        <div class="grow">
          <div class="actions">
            <button type="button" @click="videoInput?.click()">上传</button>
            <button type="button" @click="form.attributes.videoUrl = ''; form.attributes.videoName = ''; form.attributes.videoAssetId = ''">暂无</button>
            <button class="danger" type="button" @click="form.attributes.videoUrl = ''; form.attributes.videoName = ''; form.attributes.videoAssetId = ''">清除</button>
            <input ref="videoInput" class="hidden" type="file" accept="video/mp4" @change="onPickVideo" />
          </div>
          <small>视频上传后会直接显示视频播放控件。采集宝贝后视频不会立刻显示，会有一分钟左右的上传转码过程。</small>
          <p v-if="form.attributes.videoAssetId" class="hint">已入库 MediaAsset {{ form.attributes.videoAssetId }}</p>
          <p v-else-if="form.attributes.videoName" class="hint">已选择 {{ form.attributes.videoName }}</p>
        </div>
      </div>

      <div class="field-line"><label for="product-price">价格</label><input id="product-price" v-model="form.price" /></div>
      <div class="field-line"><label for="product-cost">入手价</label><input id="product-cost" v-model="form.attributes.costPrice" /><small>非必选</small></div>
      <div class="field-line"><label for="product-fan">粉丝价</label><input id="product-fan" v-model="form.attributes.fanPrice" /><small>非必选，多规格宝贝无法设置粉丝价</small></div>
      <div class="field-line"><label for="product-stock">库存</label><input id="product-stock" v-model="form.stock" /><small>鱼小铺、玩家号、Pro 号可设置</small></div>
      <div class="field-line"><label for="product-ship">运费</label><input id="product-ship" v-model="form.attributes.shippingFee" /><small>不填写则为包邮</small></div>

      <div class="row">
        <span class="label">地址1</span>
        <div class="grow tags">
          <span v-for="(item, index) in form.attributes.address" :key="item" class="tag">{{ item }} <button type="button" @click="removeTag(form.attributes.address, index)">×</button></span>
          <input v-model="tagDraft.address" class="wide" placeholder="江苏省-南京市-玄武区，回车添加" @keydown.enter.prevent="addTag(form.attributes.address, tagDraft.address); tagDraft.address = ''" />
        </div>
      </div>

      <div class="row">
        <span class="label">其他项</span>
        <label class="check"><input v-model="form.attributes.selfPickup" type="checkbox" /> 自提</label>
        <label class="check"><input v-model="form.attributes.freeShipping" type="checkbox" /> 无需邮寄</label>
      </div>

      <div class="row">
        <span class="label">宝贝主题</span>
        <div class="grow tags">
          <span v-for="(item, index) in form.attributes.theme" :key="item" class="tag">{{ item }} <button type="button" @click="removeTag(form.attributes.theme, index)">×</button></span>
          <input v-model="tagDraft.theme" placeholder="输入后回车" @keydown.enter.prevent="addTag(form.attributes.theme, tagDraft.theme); tagDraft.theme = ''" />
        </div>
      </div>

      <div class="row">
        <span class="label">分类/品牌</span>
        <div class="grow tags">
          <span v-for="(item, index) in form.attributes.brands" :key="item" class="tag">{{ item }} <button type="button" @click="removeTag(form.attributes.brands, index)">×</button></span>
          <input v-model="tagDraft.brand" placeholder="输入后回车" @keydown.enter.prevent="addTag(form.attributes.brands, tagDraft.brand); tagDraft.brand = ''" />
        </div>
      </div>

      <div class="field-line top"><label for="product-collect">采集链接</label><textarea id="product-collect" v-model="form.attributes.collectionLink" rows="2" placeholder="宝贝的来源（宝贝采集自）" /></div>
      <div class="field-line top"><label for="product-virtual">虚拟宝贝</label><textarea id="product-virtual" v-model="form.attributes.virtualProduct" rows="3" placeholder="填写虚拟宝贝的网盘链接或者卡密。买家拍下后发送此段内容并发货。" /></div>
      <div class="field-line"><label for="product-notes">宝贝备注</label><input id="product-notes" v-model="form.attributes.notes" placeholder="宝贝备注" /></div>
      <div class="field-line"><label for="product-share">分享码</label><input id="product-share" v-model="form.attributes.shareCode" placeholder="宝贝分享码" /><small>设置后可将宝贝共享给别人</small></div>
      <div class="field-line"><label for="product-group">宝贝分组</label><input id="product-group" v-model="form.attributes.groupName" placeholder="例如 黄金回收" /><small><button class="group-link" type="button" @click="router.push('/operations/product-management/product-management-03')">分组管理</button></small></div>

      <div class="row">
        <span class="label" />
        <div class="actions">
          <button class="primary" type="button" :disabled="busy" @click="saveProduct">保存编辑</button>
          <button type="button" :disabled="busy" @click="resetForm">重置</button>
        </div>
      </div>
    </div>

    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>闲鱼一口价最多上传 9 张图片，另外也可多上传 7 张作为备用图片。</li>
        <li>标题、描述、价格、图片都可以直接改，点保存编辑后会写入商品库，商品列表里能马上看到。</li>
        <li>从商品列表点编辑进入时，会打开对应宝贝；没有带 ID 时就是新建普通宝贝。</li>
        <li>视频仅支持 MP4 格式。</li>
        <li>分享码格式为“用户名#分享码”。</li>
      </ol>
    </div>
  </section>
</template>

<style scoped>
.editor { display: grid; gap: 14px; color: #334155; }
.bar, .panel, .help { background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 10px 28px -20px rgba(15, 23, 42, 0.25); }
.bar { padding: 14px 18px; font-size: 16px; font-weight: 700; color: #1f2d3d; }
.panel { padding: 20px 22px 24px; display: grid; gap: 16px; }
.row, .field-line { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 14px; align-items: start; }
.field-line { align-items: center; }
.field-line.top { align-items: start; }
.label, .field-line label { padding-top: 8px; color: #1f2d3d; font-size: 14px; font-weight: 600; }
.field-line label { padding-top: 0; }
.field-line.top label { padding-top: 8px; }
.grow, .split { min-width: 0; display: grid; gap: 8px; }
.split { grid-template-columns: 1fr 1fr; }
input, select, textarea { width: 100%; padding: 9px 12px; border: 1px solid #d1d5db; border-radius: 10px; background: #fff; font: inherit; transition: border-color 0.15s, box-shadow 0.15s; }
input:focus, select:focus, textarea:focus { outline: none; border-color: #14b8a6; box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.15); }
textarea { resize: vertical; }
.row .grow > input:not([type="checkbox"]) { max-width: 560px; }
.actions { display: flex; gap: 10px; flex-wrap: wrap; }
.actions button { height: 34px; padding: 0 16px; border-radius: 10px; border: 1px solid #cbd5e1; background: #fff; color: #475569; cursor: pointer; transition: border-color 0.15s, color 0.15s, background 0.15s; }
.actions button:hover:not(:disabled) { border-color: #14b8a6; color: #0f766e; }
.actions button.primary, button.primary { border-color: #0f766e; background: #0f766e; color: #fff; font-weight: 600; box-shadow: 0 4px 10px -4px rgba(15, 118, 110, 0.5); }
.actions button.primary:hover:not(:disabled), button.primary:hover:not(:disabled) { border-color: #115e59; background: #115e59; color: #fff; }
.actions button:disabled { opacity: 0.55; cursor: not-allowed; }
.actions button.danger { border-color: #fca5a5; color: #dc2626; background: #fff; }
.actions button.danger:hover:not(:disabled) { border-color: #ef4444; color: #b91c1c; background: #fef2f2; }
.flash { margin: 0; padding: 8px 12px; border-radius: 10px; font-size: 13px; border: 1px solid transparent; }
.flash.error { color: #b91c1c; background: #fef2f2; border-color: #fecaca; }
.flash.ok { color: #166534; background: #f0fdf4; border-color: #bbf7d0; }
.box { padding: 12px 14px; border: 1px solid #e2e8f0; border-radius: 10px; background: #f8fafc; display: grid; gap: 10px; }
.inline, .tags, .check { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.inline > span { font-size: 13px; font-weight: 600; color: #475569; }
.inline select { width: auto; min-width: 170px; }
.link { margin-left: auto; height: 26px; padding: 0 12px; border: 1px solid #fca5a5; border-radius: 999px; background: #fff; color: #dc2626; font-size: 12px; cursor: pointer; transition: background 0.15s, border-color 0.15s; }
.link:hover { background: #fef2f2; border-color: #ef4444; }
.tag { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; color: #0f766e; background: #f0fdfa; border: 1px solid #99f6e4; border-radius: 999px; font-size: 12px; }
.tag button { border: 0; background: transparent; color: inherit; cursor: pointer; padding: 0; font-size: 13px; }
.tags input { width: 130px; flex: none; border-style: dashed; }
.tags input.wide { width: 260px; }
.hidden { display: none; }
.gallery { display: flex; flex-wrap: wrap; gap: 10px; }
.thumb { position: relative; width: 108px; }
.thumb img { width: 108px; height: 108px; object-fit: cover; border-radius: 10px; border: 1px solid #e2e8f0; }
.thumb .x { position: absolute; top: 4px; right: 4px; width: 18px; height: 18px; padding: 0; border: 0; border-radius: 50%; background: rgba(15, 23, 42, 0.75); color: #fff; cursor: pointer; }
.thumb-ops { margin-top: 4px; display: flex; gap: 4px; }
.thumb-ops button { height: 24px; padding: 0 8px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; color: #475569; cursor: pointer; }
.field-line input, .field-line textarea { max-width: 360px; }
.field-line small { grid-column: 2; }
.field-line small, small, .hint { color: #94a3b8; font-size: 12px; line-height: 1.6; }
.group-link { border: 0; background: none; padding: 0; color: #0f766e; cursor: pointer; }
video { width: min(360px, 100%); background: #000; border-radius: 10px; }
.help { padding: 16px 18px 18px; }
.help h3 { margin: 0 0 10px; font-size: 15px; color: #1f2d3d; }
.help ol { margin: 0; padding: 0; list-style: none; counter-reset: h; display: grid; gap: 8px; font-size: 13px; line-height: 1.7; color: #475569; }
.help li { counter-increment: h; display: flex; gap: 10px; align-items: flex-start; }
.help li::before { content: counter(h); flex: none; width: 20px; height: 20px; margin-top: 1px; display: grid; place-items: center; border-radius: 50%; background: #f0fdfa; color: #0f766e; font-size: 12px; font-weight: 700; border: 1px solid #99f6e4; }
.check { font-size: 13px; grid-column: 2; }
.check input { width: auto; }
@media (max-width: 900px) {
  .split, .row, .field-line { grid-template-columns: 1fr; }
  .label, .field-line label { padding-top: 0; }
  .check, .field-line small { grid-column: 1; }
}
</style>
