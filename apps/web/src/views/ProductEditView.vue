<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { ProductView } from '@cloudctl/api-contracts'
import { createProductCatalog } from '@/api/product-catalog'
import {
  attributesPayload,
  compressImageFile,
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

async function onPickImages(event: Event) {
  const input = event.target as HTMLInputElement
  const files = [...(input.files ?? [])]
  input.value = ''
  for (const file of files.slice(0, 9 - form.attributes.images.length)) {
    form.attributes.images.push(await compressImageFile(file))
  }
}

async function onPickVideo(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  form.attributes.videoName = file.name
  form.attributes.videoUrl = URL.createObjectURL(file)
}

function clearImages() {
  form.attributes.images = []
}

function moveImage(index: number, offset: number) {
  const next = index + offset
  if (next < 0 || next >= form.attributes.images.length) return
  const copy = [...form.attributes.images]
  const [item] = copy.splice(index, 1)
  copy.splice(next, 0, item!)
  form.attributes.images = copy
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
        mediaAssetIds: current.value?.mediaAssetIds ?? [],
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
          <textarea v-model="form.attributes.rewriteText" rows="10" placeholder="改写文本&#10;填写改写文本后系统会把改写文本作为宝贝描述" />
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
            <button class="primary" type="button" @click="imageInput?.click()">多图片上传</button>
            <button type="button" @click="clearImages">清除图片</button>
            <input ref="imageInput" class="hidden" type="file" accept="image/*" multiple @change="onPickImages" />
          </div>
          <small>Windows 按 Ctrl 多选，Mac 按 Command 多选。上传后第一张为封面，可上移下移排序。</small>
          <div class="gallery">
            <div v-for="(image, index) in form.attributes.images" :key="index" class="thumb">
              <img :src="image" alt="" />
              <button class="x" type="button" @click="form.attributes.images.splice(index, 1)">×</button>
              <div class="thumb-ops">
                <button type="button" :disabled="index === 0" @click="moveImage(index, -1)">←</button>
                <button type="button" :disabled="index === form.attributes.images.length - 1" @click="moveImage(index, 1)">→</button>
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
            <button class="primary" type="button" @click="videoInput?.click()">上传</button>
            <button type="button" @click="form.attributes.videoUrl = ''; form.attributes.videoName = ''">暂无</button>
            <button type="button" @click="form.attributes.videoUrl = ''; form.attributes.videoName = ''">清除</button>
            <input ref="videoInput" class="hidden" type="file" accept="video/mp4" @change="onPickVideo" />
          </div>
          <small>视频上传后会直接显示视频播放控件。采集宝贝后视频不会立刻显示，会有一分钟左右的上传转码过程。</small>
          <video v-if="form.attributes.videoUrl" :src="form.attributes.videoUrl" controls />
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
          <input v-model="tagDraft.address" placeholder="例如 江苏省-南京市-玄武区，回车添加" @keydown.enter.prevent="addTag(form.attributes.address, tagDraft.address); tagDraft.address = ''" />
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
      <div class="field-line"><label for="product-group">宝贝分组</label><input id="product-group" v-model="form.attributes.groupName" placeholder="例如 黄金回收" /><small>分组管理</small></div>

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
.editor { display: grid; gap: 10px; color: #334155; }
.bar, .panel, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.bar { padding: 10px 14px; font-size: 14px; }
.panel { padding: 16px 18px 20px; display: grid; gap: 14px; }
.row, .field-line { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: start; }
.field-line { align-items: center; }
.field-line.top { align-items: start; }
.label, .field-line label { padding-top: 6px; color: #64748b; font-size: 13px; }
.grow, .split { min-width: 0; display: grid; gap: 8px; }
.split { grid-template-columns: 1fr 1fr; }
input, select, textarea { width: 100%; padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 4px; background: #fff; font: inherit; }
textarea { resize: vertical; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.primary, .actions button { height: 32px; padding: 0 14px; border-radius: 4px; border: 1px solid #0f766e; background: #fff; color: #0f766e; }
.primary { color: #fff; background: #0f766e; }
.flash { margin: 0; padding: 8px 10px; border-radius: 6px; font-size: 13px; }
.flash.error { color: #b91c1c; background: #fef2f2; }
.flash.ok { color: #166534; background: #f0fdf4; }
.box { padding: 10px; border: 1px solid #e5e7eb; border-radius: 6px; }
.inline, .tags, .check { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.link { height: auto; padding: 0; border: 0; background: transparent; color: #ef4444; }
.tag { padding: 2px 8px; color: #0f766e; background: #ecfdf5; border-radius: 999px; font-size: 12px; }
.tag button { border: 0; background: transparent; color: inherit; }
.hidden { display: none; }
.gallery { display: flex; flex-wrap: wrap; gap: 8px; }
.thumb { position: relative; width: 108px; }
.thumb img { width: 108px; height: 108px; object-fit: cover; border-radius: 6px; border: 1px solid #e5e7eb; }
.thumb .x { position: absolute; top: 4px; right: 4px; width: 18px; height: 18px; padding: 0; border: 0; border-radius: 50%; background: #0f172a; color: #fff; }
.thumb-ops { margin-top: 4px; display: flex; gap: 4px; }
.thumb-ops button { height: 24px; padding: 0 6px; }
.field-line input, .field-line textarea { max-width: 360px; }
.field-line small, small, .hint { color: #94a3b8; font-size: 12px; }
video { width: min(360px, 100%); background: #000; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.check { font-size: 13px; }
@media (max-width: 900px) {
  .split, .row, .field-line { grid-template-columns: 1fr; }
}
</style>
