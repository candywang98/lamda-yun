<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { compressImageFile } from '@/data/product-fields'
import {
  emptyWatermarkConfig,
  loadWatermarkConfig,
  loadWatermarkHistory,
  pushWatermarkHistory,
  renderWatermarkPreview,
  renderWatermarkThumbnail,
  saveWatermarkConfig,
  watermarkApplyOptions,
  watermarkFonts,
  watermarkModes,
  watermarkPositions,
  type WatermarkConfig,
  type WatermarkHistoryItem,
} from '@/data/post-watermark'

const form = reactive<WatermarkConfig>(emptyWatermarkConfig())
const history = ref<WatermarkHistoryItem[]>([])
const logoInput = ref<HTMLInputElement | null>(null)
const previewUrl = ref('')
const busy = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const isImageMode = computed(() => form.mode === 'image')

function applyConfig(config: WatermarkConfig) {
  Object.assign(form, emptyWatermarkConfig(config))
}

async function onPickLogo(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  form.imageDataUrl = await compressImageFile(file)
}

function removeLogo() {
  form.imageDataUrl = ''
}

async function preview() {
  busy.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    previewUrl.value = await renderWatermarkPreview(form)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    busy.value = false
  }
}

async function saveConfig() {
  busy.value = true
  errorMessage.value = ''
  try {
    const saved = saveWatermarkConfig(form)
    applyConfig(saved)
    const thumbnail = await renderWatermarkThumbnail(saved)
    history.value = pushWatermarkHistory(saved, thumbnail || previewUrl.value)
    successMessage.value = '水印配置已保存到本机浏览器'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    busy.value = false
  }
}

function reuseHistory(item: WatermarkHistoryItem) {
  applyConfig(item.config)
  previewUrl.value = item.thumbnail
  successMessage.value = '已套用历史水印参数'
}

onMounted(() => {
  applyConfig(loadWatermarkConfig())
  history.value = loadWatermarkHistory()
})
</script>

<template>
  <section class="wm-page">
    <div class="card">
      <h2>图片水印</h2>
      <div class="row">
        <span class="label">水印形式</span>
        <div>
          <label v-for="item in watermarkModes" :key="item.id" class="radio" :for="`wm-mode-${item.id}`">
            <input :id="`wm-mode-${item.id}`" v-model="form.mode" type="radio" :value="item.id" />
            {{ item.label }}
          </label>
          <p class="hint">某鱼会员名/某鱼昵称可有效防止同行采集</p>
        </div>
      </div>

      <div v-if="!isImageMode" class="row">
        <label class="label" for="wm-text">水印文字</label>
        <div class="inline">
          <input id="wm-text" v-model="form.text" />
          <span class="hint">如选了“某鱼会员名/某鱼昵称”但设备未绑定某鱼号，则默认使用该项</span>
        </div>
      </div>

      <div v-if="isImageMode" class="row top">
        <span class="label">水印图片</span>
        <div>
          <input ref="logoInput" class="hidden" type="file" accept="image/png,image/*" @change="onPickLogo" />
          <button class="logo-box" type="button" @click="logoInput?.click()">
            <img v-if="form.imageDataUrl" :src="form.imageDataUrl" alt="水印 logo" />
            <span v-else>+<small>上传logo</small></span>
          </button>
          <button v-if="form.imageDataUrl" class="link" type="button" @click="removeLogo">清除</button>
          <p class="hint">建议使用透明底PNG，水印随图片尺寸等比缩放</p>
        </div>
      </div>

      <div class="row top">
        <span class="label">历史水印</span>
        <div>
          <div class="history">
            <button v-for="item in history" :key="item.id" class="history-item" type="button" :title="item.savedAt" @click="reuseHistory(item)">
              <img v-if="item.thumbnail" :src="item.thumbnail" alt="" />
              <span v-else>{{ item.config.mode === 'image' ? '图片水印' : item.config.text }}</span>
            </button>
            <span v-if="history.length === 0" class="hint">上传/保存过的图片或文字水印会自动记在本机浏览器里</span>
          </div>
          <p class="hint">上传/保存过的图片或文字水印会自动记在本机浏览器里，点击即可套用当时的全部参数（换账号登录同一浏览器也能用）</p>
        </div>
      </div>

      <template v-if="!isImageMode">
        <div class="row">
          <label class="label" for="wm-font">水印字体</label>
          <select id="wm-font" v-model="form.fontFamily">
            <option v-for="item in watermarkFonts" :key="item.id" :value="item.id">{{ item.label }}</option>
          </select>
        </div>
        <div class="row">
          <label class="label" for="wm-font-size">文字大小</label>
          <div class="inline">
            <input id="wm-font-size" v-model.number="form.fontSize" type="number" min="10" max="100" />
            <span class="hint">10-100磅</span>
          </div>
        </div>
        <div class="row">
          <label class="label" for="wm-color">字体颜色</label>
          <div class="inline">
            <input id="wm-color" v-model="form.color" />
            <input v-model="form.color" type="color" aria-label="选择字体颜色" />
          </div>
        </div>
      </template>

      <div v-else class="row">
        <label class="label" for="wm-size">水印大小</label>
        <div class="inline">
          <input id="wm-size" v-model.number="form.sizePercent" type="number" min="1" max="100" />
          <span class="hint">水印高度占主图高度的百分比，取值1-100，默认30</span>
        </div>
      </div>

      <div class="row">
        <label class="label" for="wm-opacity">透明度</label>
        <div class="inline">
          <input id="wm-opacity" v-model.number="form.opacity" type="number" min="1" max="100" />
          <span class="hint">水印透明度，取值1-100，默认100（完全不透明）</span>
        </div>
      </div>
      <div class="row">
        <label class="label" for="wm-position">水印位置</label>
        <select id="wm-position" v-model="form.position">
          <option v-for="item in watermarkPositions" :key="item">{{ item }}</option>
        </select>
      </div>
      <div class="row">
        <label class="label" for="wm-mx">水平边距</label>
        <div class="inline">
          <input id="wm-mx" v-model.number="form.marginX" type="number" min="0" />
          <span class="hint">水平（横轴）边距，单位为像素，默认20</span>
        </div>
      </div>
      <div class="row">
        <label class="label" for="wm-my">垂直边距</label>
        <div class="inline">
          <input id="wm-my" v-model.number="form.marginY" type="number" min="0" />
          <span class="hint">垂直（纵轴）边距，单位为像素，默认20</span>
        </div>
      </div>
      <div v-if="!isImageMode" class="row">
        <label class="label" for="wm-shadow">文字阴影</label>
        <div class="inline">
          <input id="wm-shadow" v-model.number="form.shadow" type="number" min="0" max="100" />
          <span class="hint">文字阴影效果，取值1-100，默认为0（表示无阴影）</span>
        </div>
      </div>
      <div class="row">
        <span class="label">铺满全图</span>
        <div>
          <label class="radio"><input v-model="form.tile" type="radio" :value="false" /> 关闭</label>
          <label class="radio"><input v-model="form.tile" type="radio" :value="true" /> 开启</label>
        </div>
      </div>
      <div class="row">
        <label class="label" for="wm-rotation">旋转角度</label>
        <div class="inline">
          <input id="wm-rotation" v-model.number="form.rotation" type="number" min="0" max="360" />
          <span class="hint">水印的旋转角度设置，取值范围为0-360，铺满与非铺满均生效</span>
        </div>
      </div>
      <div class="row">
        <label class="label" for="wm-apply">应用图片</label>
        <select id="wm-apply" v-model="form.applyTo">
          <option v-for="item in watermarkApplyOptions" :key="item">{{ item }}</option>
        </select>
      </div>
      <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok">{{ successMessage }}</p>
      <div class="footer">
        <button class="primary" type="button" :disabled="busy" @click="preview">预览</button>
        <button class="primary" type="button" :disabled="busy" @click="saveConfig">保存配置</button>
      </div>
      <img v-if="previewUrl" class="preview" :src="previewUrl" alt="水印预览 960×540" />
    </div>
    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>您可在此设置某鱼宝贝、转转宝贝、某鱼帖子、红薯笔记的图片水印</li>
        <li>水印文字会随图片尺寸等比缩放，实际比例与预览一致（预览图片的尺寸为960×540）</li>
        <li>如应用图片选择尾张，且图片数&gt;=10，将在第9第和10张图片添加水印</li>
        <li>水印在宝贝发布时生效，宝贝编辑页面无法预览水印效果</li>
        <li>发布宝贝、帖子时开启 图片水印 既可应用该页面的配置</li>
        <li>如果您修改了某鱼昵称，请运行绑定某鱼任务重新同步到系统</li>
        <li>图片水印与文字水印二选一，logo建议使用透明底PNG，水印随图片尺寸等比缩放</li>
        <li>上传/保存过的图片水印和文字水印会自动记入历史水印（保存在本机浏览器，各留最近12条），点击即可一键套用当时的全部参数，换账号登录同一浏览器也能使用</li>
      </ol>
    </div>
  </section>
</template>

<style scoped>
.wm-page { display: grid; gap: 10px; color: #334155; }
.card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; gap: 14px; }
h2 { margin: 0; font-size: 15px; }
.row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: center; }
.row.top { align-items: start; }
.label { color: #64748b; font-size: 13px; }
input, select { width: min(280px, 100%); height: 34px; padding: 0 10px; border: 1px solid #d1d5db; border-radius: 4px; font: inherit; }
input[type='color'] { width: 36px; padding: 2px; }
.inline { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.radio { display: inline-flex; align-items: center; gap: 6px; margin-right: 16px; color: #334155; }
.hint { margin: 6px 0 0; color: #94a3b8; font-size: 12px; }
.hidden { display: none; }
.logo-box { width: 84px; height: 84px; border: 1px dashed #cbd5e1; border-radius: 8px; background: #f8fafc; color: #94a3b8; display: grid; place-items: center; }
.logo-box img { width: 76px; height: 76px; object-fit: contain; }
.logo-box small { display: block; font-size: 12px; }
.link { border: 0; background: none; color: #0f766e; }
.history { display: flex; flex-wrap: wrap; gap: 8px; }
.history-item { width: 72px; height: 54px; padding: 0; overflow: hidden; border: 1px solid #e5e7eb; border-radius: 6px; background: #f8fafc; }
.history-item img { width: 100%; height: 100%; object-fit: cover; }
.footer { padding-left: 100px; display: flex; gap: 10px; }
.primary { height: 34px; padding: 0 16px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; }
.flash { margin: 0; padding-left: 100px; font-size: 13px; }
.flash.error { color: #b91c1c; }
.flash.ok { color: #166534; }
.preview { width: min(640px, 100%); margin-left: 100px; border: 1px solid #e5e7eb; border-radius: 6px; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
</style>
