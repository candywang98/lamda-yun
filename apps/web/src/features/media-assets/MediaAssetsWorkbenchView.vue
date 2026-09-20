<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { CheckCircle2, Image, LockKeyhole, ScanSearch } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { controlApiConfigured } from '@/api/control'
import { resolveMediaPreviewUrl } from '@/api/media-assets'
import {
  freezeMediaPool,
  renderWatermark,
  runPublishPreflight,
  type MediaPoolFreezeResult,
  type PublishPreflightResult,
  type WatermarkRenderInput,
  type WatermarkRenderResult,
} from './api'
import {
  normalizedPoolInput,
  normalizedPreflightInput,
  normalizedWatermarkInput,
  preflightCounts,
} from './model'

const activeRequest = ref<'watermark' | 'pool' | 'preflight' | null>(null)
const errorMessage = ref('')
const previewUrl = ref('')
const watermarkResult = ref<WatermarkRenderResult | null>(null)
const poolResult = ref<MediaPoolFreezeResult | null>(null)
const preflightResult = ref<PublishPreflightResult | null>(null)

const watermark = reactive<WatermarkRenderInput & { sourceAssetId: string }>({
  sourceAssetId: '',
  text: 'CloudCtl',
  position: 'bottom_right',
  opacity: 70,
  fontSize: 32,
  margin: 24,
  ruleVersionId: '',
})
const pool = reactive({ taskKey: '', groupId: '', count: 1, seed: '' })
const preflight = reactive({
  productId: '',
  accountId: '',
  deviceId: '',
  platform: 'xianyu' as 'xianyu' | 'xiaohongshu',
})

const counts = computed(() => preflightCounts(preflightResult.value?.checks ?? []))
const busy = (request: typeof activeRequest.value) => activeRequest.value === request

async function execute<T>(request: NonNullable<typeof activeRequest.value>, action: () => Promise<T>) {
  activeRequest.value = request
  errorMessage.value = ''
  try {
    return await action()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
    return null
  } finally {
    activeRequest.value = null
  }
}

async function submitWatermark() {
  const sourceAssetId = watermark.sourceAssetId.trim()
  if (!sourceAssetId) {
    errorMessage.value = '源素材 ID 不能为空'
    return
  }
  const result = await execute('watermark', () => renderWatermark(
    sourceAssetId,
    normalizedWatermarkInput({
      text: watermark.text,
      position: watermark.position,
      opacity: watermark.opacity,
      fontSize: watermark.fontSize,
      margin: watermark.margin,
      ruleVersionId: watermark.ruleVersionId,
    }),
  ))
  if (!result) return
  watermarkResult.value = result
  previewUrl.value = await resolveMediaPreviewUrl(result.outputAsset.id)
}

async function submitPool() {
  const result = await execute('pool', () => freezeMediaPool(normalizedPoolInput(pool)))
  if (result) poolResult.value = result
}

async function submitPreflight() {
  const result = await execute(
    'preflight',
    () => runPublishPreflight(normalizedPreflightInput(preflight)),
  )
  if (result) preflightResult.value = result
}
</script>

<template>
  <section class="media-workbench">
    <PageHeader
      kicker="F10 / 媒体资产"
      title="素材处理与发布预检"
      description="真实派生、可重放冻结和只读预检使用同一组租户资产。"
    >
      <template #actions>
        <StatusBadge
          :status="controlApiConfigured ? 'ONLINE' : 'BLOCKED'"
          :label="controlApiConfigured ? 'Control API 已连接' : 'Control API 未配置'"
        />
      </template>
    </PageHeader>

    <p v-if="errorMessage" class="alert" role="alert">{{ errorMessage }}</p>

    <div class="tool-grid">
      <form class="tool-panel" @submit.prevent="submitWatermark">
        <header><Image :size="18" /><h3>水印派生</h3></header>
        <label>源素材 ID<input v-model="watermark.sourceAssetId" autocomplete="off" /></label>
        <label>水印文字<input v-model="watermark.text" maxlength="200" /></label>
        <div class="field-pair">
          <label>位置
            <select v-model="watermark.position">
              <option value="top_left">左上</option><option value="top_right">右上</option>
              <option value="center">居中</option><option value="bottom_left">左下</option>
              <option value="bottom_right">右下</option>
            </select>
          </label>
          <label>透明度<input v-model.number="watermark.opacity" type="number" min="1" max="100" /></label>
        </div>
        <div class="field-pair">
          <label>字号<input v-model.number="watermark.fontSize" type="number" min="8" max="256" /></label>
          <label>边距<input v-model.number="watermark.margin" type="number" min="0" max="2048" /></label>
        </div>
        <label>规则版本<input v-model="watermark.ruleVersionId" placeholder="可选" /></label>
        <button type="submit" :disabled="!controlApiConfigured || busy('watermark')">
          <Image :size="16" />生成派生图
        </button>
      </form>

      <form class="tool-panel" @submit.prevent="submitPool">
        <header><LockKeyhole :size="18" /><h3>素材池冻结</h3></header>
        <label>任务键<input v-model="pool.taskKey" autocomplete="off" /></label>
        <label>媒体分组 ID<input v-model="pool.groupId" autocomplete="off" /></label>
        <label>选取数量<input v-model.number="pool.count" type="number" min="1" max="49" /></label>
        <label>随机种子<input v-model="pool.seed" placeholder="留空时由任务键派生" /></label>
        <button type="submit" :disabled="!controlApiConfigured || busy('pool')">
          <LockKeyhole :size="16" />冻结有序素材
        </button>
      </form>

      <form class="tool-panel" @submit.prevent="submitPreflight">
        <header><ScanSearch :size="18" /><h3>发布预检</h3></header>
        <label>平台
          <select v-model="preflight.platform">
            <option value="xianyu">闲鱼</option><option value="xiaohongshu">小红书</option>
          </select>
        </label>
        <label>商品 ID<input v-model="preflight.productId" autocomplete="off" /></label>
        <label>账号 ID<input v-model="preflight.accountId" autocomplete="off" /></label>
        <label>设备 ID<input v-model="preflight.deviceId" autocomplete="off" /></label>
        <button type="submit" :disabled="!controlApiConfigured || busy('preflight')">
          <ScanSearch :size="16" />执行只读预检
        </button>
      </form>
    </div>

    <section v-if="watermarkResult" class="result-band">
      <div class="result-heading"><CheckCircle2 :size="18" /><h3>派生结果</h3></div>
      <div class="result-columns">
        <img v-if="previewUrl" :src="previewUrl" alt="服务端水印派生预览" />
        <dl>
          <dt>输出素材</dt><dd>{{ watermarkResult.outputAsset.id }}</dd>
          <dt>输出 SHA256</dt><dd class="mono">{{ watermarkResult.previewSha256 }}</dd>
          <dt>发布派生 SHA256</dt><dd class="mono">{{ watermarkResult.publishDerivativeSha256 }}</dd>
          <dt>规则 SHA256</dt><dd class="mono">{{ watermarkResult.profileSha256 }}</dd>
        </dl>
      </div>
    </section>

    <section v-if="poolResult" class="result-band">
      <div class="result-heading"><LockKeyhole :size="18" /><h3>冻结快照</h3>
        <StatusBadge :status="poolResult.replayed ? 'CANDIDATE' : 'SUCCEEDED'" :label="poolResult.replayed ? '幂等重放' : '首次冻结'" />
      </div>
      <p class="mono checksum">{{ poolResult.snapshotSha256 }}</p>
      <ol class="asset-order"><li v-for="assetId in poolResult.mediaAssetIds" :key="assetId" class="mono">{{ assetId }}</li></ol>
    </section>

    <section v-if="preflightResult" class="result-band">
      <div class="result-heading"><ScanSearch :size="18" /><h3>预检结果</h3>
        <StatusBadge :status="preflightResult.ready ? 'SUCCEEDED' : 'BLOCKED'" :label="preflightResult.ready ? '可进入任务创建' : '阻止任务创建'" />
      </div>
      <div class="summary-line"><span>通过 {{ counts.PASS }}</span><span>告警 {{ counts.WARNING }}</span><span>阻断 {{ counts.BLOCKED }}</span></div>
      <ul class="check-list">
        <li v-for="check in preflightResult.checks" :key="check.id">
          <StatusBadge :status="check.status === 'PASS' ? 'SUCCEEDED' : check.status" :label="check.status" />
          <span class="check-id">{{ check.id }}</span><span>{{ check.detail }}</span>
        </li>
      </ul>
      <p class="mono checksum">快照 {{ preflightResult.snapshotSha256 }}</p>
    </section>
  </section>
</template>

<style scoped>
.media-workbench { display: grid; gap: 16px; color: #24313d; }
.alert { margin: 0; padding: 10px 12px; border-left: 3px solid #b42318; background: #fff3f2; color: #8a1c13; font-size: 13px; }
.tool-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; align-items: stretch; }
.tool-panel { min-width: 0; padding: 14px; border: 1px solid #dce3e8; border-radius: 6px; background: #fff; display: grid; gap: 12px; align-content: start; }
.tool-panel header, .result-heading { display: flex; align-items: center; gap: 8px; min-height: 28px; }
h3 { margin: 0; font-size: 14px; color: #17232c; }
label { display: grid; gap: 5px; color: #60717e; font-size: 12px; }
input, select { width: 100%; min-width: 0; height: 34px; box-sizing: border-box; padding: 0 9px; border: 1px solid #cbd5dc; border-radius: 4px; background: #fff; color: #17232c; font: inherit; }
.field-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
button { height: 36px; padding: 0 12px; border: 0; border-radius: 4px; background: #116466; color: #fff; display: inline-flex; justify-content: center; align-items: center; gap: 7px; font: inherit; cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: .5; }
.result-band { padding: 14px; border-top: 1px solid #dce3e8; background: #f8fafb; display: grid; gap: 12px; }
.result-heading { justify-content: flex-start; }
.result-heading :deep(.status-badge) { margin-left: auto; }
.result-columns { display: grid; grid-template-columns: minmax(180px, 320px) minmax(0, 1fr); gap: 16px; }
.result-columns img { width: 100%; aspect-ratio: 8 / 5; object-fit: contain; border: 1px solid #dce3e8; background: #fff; }
dl { margin: 0; display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 8px 12px; align-content: start; }
dt { color: #71818d; font-size: 12px; } dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.checksum { margin: 0; overflow-wrap: anywhere; color: #475866; }
.asset-order { margin: 0; padding-left: 28px; display: grid; gap: 6px; }
.summary-line { display: flex; flex-wrap: wrap; gap: 16px; color: #60717e; font-size: 13px; }
.check-list { list-style: none; margin: 0; padding: 0; display: grid; }
.check-list li { min-height: 38px; padding: 7px 0; border-top: 1px solid #e4e9ed; display: grid; grid-template-columns: 92px minmax(140px, 220px) minmax(0, 1fr); gap: 10px; align-items: center; font-size: 13px; }
.check-id { color: #475866; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
@media (max-width: 1050px) { .tool-grid { grid-template-columns: 1fr; } }
@media (max-width: 680px) { .field-pair, .result-columns { grid-template-columns: 1fr; } .check-list li { grid-template-columns: 92px 1fr; } .check-list li > :last-child { grid-column: 1 / -1; } dl { grid-template-columns: 1fr; } }
</style>
