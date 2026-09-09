<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice } from '@/api/devices'
import { deploymentHistory, parseRecipePackage, recipeApi, RecipeApiError, rollbackExpectedVersion, type LocalRecipePackage, type RecipeVersion } from '@/api/recipes'
import { useSessionStore } from '@/stores/session'
import type { Device } from '@/types'

const session = useSessionStore()
const catalog = ref<RecipeVersion[]>([])
const devices = ref<Device[]>([])
const selectedId = ref('')
const deviceId = ref('')
const detail = ref<RecipeVersion | null>(null)
const loading = ref(true)
const detailLoading = ref(false)
const busy = ref(false)
const ready = ref(false)
const denied = ref(false)
const error = ref('')
const detailError = ref('')
const actionError = ref('')
const result = ref('')
const signedPackage = ref<LocalRecipePackage | null>(null)
const fileError = ref('')
const fileName = ref('')
const readingFile = ref(false)
let requestGeneration = 0
let detailGeneration = 0
let fileGeneration = 0
let initializing = true
const authorized = computed(() => controlApiConfigured && session.loaded && session.session !== null && session.can('recipe.publish') && !denied.value)
const canMutate = computed(() => authorized.value && ready.value && !loading.value && !detailLoading.value && !detailError.value && !busy.value)
const history = computed(() => deploymentHistory(catalog.value, deviceId.value))
const current = computed(() => history.value.filter((row) => row.deployment.status === 'PUBLISHED'))
const rollbackCandidates = computed(() => catalog.value.flatMap((version) => {
  const expected = rollbackExpectedVersion(catalog.value, deviceId.value, version)
  return expected ? [{ version, expected }] : []
}))
interface Intent {
  action: 'publish' | 'rollback'
  version: RecipeVersion
  deviceId: string
  deviceName: string
  idempotencyKey: string
  expectedCurrentVersionId?: string
}
const intent = ref<Intent | null>(null)

function message(cause: unknown) { return cause instanceof Error ? cause.message : '请求失败，请重试' }
function timestamp(value: string | null) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '未记录' }
function versionLabel(id: string | null) {
  if (!id) return '无'
  const version = catalog.value.find((item) => item.versionId === id)
  return version ? `${version.name} · ${version.version}（${id}）` : id
}

async function loadDetail(id: string) {
  const generation = ++detailGeneration
  selectedId.value = id
  detail.value = null
  detailError.value = ''
  detailLoading.value = false
  if (!id || !authorized.value) return
  detailLoading.value = true
  try {
    const value = await recipeApi.detail(id)
    if (generation === detailGeneration && authorized.value) {
      if (value.versionId !== id) throw new Error('版本详情与所选版本不一致，请刷新')
      detail.value = value
    }
  } catch (cause) {
    if (generation === detailGeneration) detailError.value = message(cause)
  } finally {
    if (generation === detailGeneration) detailLoading.value = false
  }
}

async function refresh() {
  if (!authorized.value) return
  const generation = ++requestGeneration
  ++detailGeneration
  ready.value = false
  loading.value = true
  error.value = ''
  detail.value = null
  intent.value = null
  try {
    const [versions, deviceRows] = await Promise.all([recipeApi.catalog(), createControlApiClient().devices()])
    if (generation !== requestGeneration || !authorized.value) return
    catalog.value = versions
    devices.value = deviceRows.map(mapControlDevice)
    if (!devices.value.some((device) => device.id === deviceId.value)) deviceId.value = ''
    const id = versions.some((version) => version.versionId === selectedId.value) ? selectedId.value : versions[0]?.versionId ?? ''
    ready.value = true
    await loadDetail(id)
  } catch (cause) {
    if (generation === requestGeneration) {
      error.value = message(cause)
      catalog.value = []
      devices.value = []
    }
  } finally {
    if (generation === requestGeneration) loading.value = false
  }
}

async function initialize() {
  initializing = true
  loading.value = true
  error.value = ''
  if (!controlApiConfigured) {
    error.value = '未配置 Control API，无法管理 Recipe 版本'
    loading.value = false
    initializing = false
    return
  }
  try {
    await session.loadSession()
    denied.value = false
    if (authorized.value) await refresh()
  } catch (cause) { error.value = `登录态加载失败：${message(cause)}` }
  finally { loading.value = false; initializing = false }
}

async function chooseFile(event: Event) {
  const generation = ++fileGeneration
  signedPackage.value = null
  fileError.value = ''
  fileName.value = ''
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file || !canMutate.value || intent.value) return
  readingFile.value = true
  try {
    const parsed = parseRecipePackage(await file.text())
    if (generation === fileGeneration && authorized.value) {
      signedPackage.value = parsed
      fileName.value = file.name
    }
  } catch (cause) { if (generation === fileGeneration) fileError.value = message(cause) }
  finally { if (generation === fileGeneration) readingFile.value = false }
}

function handleActionFailure(cause: unknown) {
  actionError.value = message(cause)
  if (cause instanceof RecipeApiError && [401, 403, 409].includes(cause.status)) {
    intent.value = null
    ready.value = false
    if (cause.status !== 409) denied.value = true
  }
}

async function register() {
  if (!canMutate.value || !signedPackage.value || readingFile.value || intent.value) return
  busy.value = true
  actionError.value = ''
  result.value = ''
  try {
    const version = await recipeApi.register(signedPackage.value)
    selectedId.value = version.versionId
    signedPackage.value = null
    fileName.value = ''
    result.value = `已登记版本 ${version.version}。尚未发布到设备。`
    await refresh()
  } catch (cause) { handleActionFailure(cause) }
  finally { busy.value = false }
}

function prepare(action: Intent['action'], version: RecipeVersion, expected?: string) {
  if (!canMutate.value || intent.value) return
  const device = devices.value.find((item) => item.id === deviceId.value)
  if (!device) return
  if (action === 'rollback' && (!expected || rollbackExpectedVersion(catalog.value, device.id, version) !== expected)) return
  actionError.value = ''
  result.value = ''
  intent.value = { action, version, deviceId: device.id, deviceName: device.name, idempotencyKey: crypto.randomUUID(), expectedCurrentVersionId: expected }
}

async function confirm() {
  const pending = intent.value
  if (!pending || !canMutate.value) return
  busy.value = true
  actionError.value = ''
  try {
    const body = { targetDeviceIds: [pending.deviceId], idempotencyKey: pending.idempotencyKey }
    if (pending.action === 'rollback') {
      if (!pending.expectedCurrentVersionId) return
      await recipeApi.rollback(pending.version.versionId, { ...body, expectedCurrentVersionId: pending.expectedCurrentVersionId })
    } else {
      await recipeApi.publish(pending.version.versionId, body)
    }
    result.value = `服务端已确认${pending.action === 'publish' ? '发布' : '回滚'} ${pending.version.version}；设备将在空闲时激活，运行中的任务保持原版本。`
    intent.value = null
    await refresh()
  } catch (cause) { handleActionFailure(cause) }
  finally { busy.value = false }
}

watch(deviceId, () => { if (!busy.value) intent.value = null })
watch([() => session.user.tenant, authorized], () => {
  if (initializing) return
  ++requestGeneration
  ++detailGeneration
  ++fileGeneration
  catalog.value = []
  devices.value = []
  detail.value = null
  intent.value = null
  signedPackage.value = null
  ready.value = false
  loading.value = false
  detailLoading.value = false
  readingFile.value = false
  result.value = ''
  if (authorized.value) void refresh()
})
onMounted(initialize)
onUnmounted(() => { ++requestGeneration; ++detailGeneration; ++fileGeneration })
</script>

<template>
  <div class="recipe-view">
    <PageHeader title="Recipe 版本管理" subtitle="登记签名包，按设备手动发布或回滚。运行中的任务继续使用已锁定版本。" />
    <div class="recipe-toolbar">
      <button class="button" :disabled="loading || busy || !!intent" @click="authorized ? refresh() : initialize()">刷新版本与设备</button>
      <span v-if="busy" role="status">正在提交，请勿重复操作…</span>
    </div>
    <p v-if="loading" role="status">正在加载登录态、版本与设备…</p>
    <p v-if="error" role="alert" class="recipe-error">{{ error }}</p>
    <p v-if="!loading && !authorized && !error" role="alert" class="recipe-error">需要 recipe.publish 权限才能查看、登记、发布或回滚版本。</p>
    <p v-if="actionError" role="alert" class="recipe-error">{{ actionError }} <span v-if="!ready">请刷新版本与设备后重新确认。</span></p>
    <p v-if="result" role="status" class="recipe-result">{{ result }}</p>

    <template v-if="authorized">
      <section class="panel">
        <div class="panel-header"><h3>登记签名包</h3></div>
        <div class="panel-body">
          <label for="recipe-file">已签名 JSON 文件</label>
          <input id="recipe-file" type="file" accept=".json,application/json" :disabled="!canMutate || !!intent || readingFile" @change="chooseFile" />
          <p class="recipe-hint">选择文件后检查清单，再点击登记。服务端会验证受信签名、哈希和引擎兼容信息。</p>
          <p v-if="readingFile" role="status">正在读取文件…</p>
          <p v-if="fileError" role="alert" class="recipe-error">{{ fileError }}</p>
          <dl v-if="signedPackage" class="recipe-metadata" aria-label="待登记清单">
            <dt>文件</dt><dd>{{ fileName }}</dd>
            <dt>版本</dt><dd>{{ signedPackage.manifest.id }} · {{ signedPackage.manifest.version }}</dd>
            <dt>签名密钥</dt><dd>{{ signedPackage.manifest.signingKeyId }}</dd>
            <dt>最低引擎版本</dt><dd>{{ signedPackage.manifest.minEngineVersion }}</dd>
            <dt>SHA-256</dt><dd><code>{{ signedPackage.manifest.hash }}</code></dd>
          </dl>
          <button class="button button-primary" :disabled="!canMutate || !signedPackage || readingFile || !!intent" @click="register">登记签名包</button>
        </div>
      </section>

      <div v-if="ready" class="recipe-columns">
        <section class="panel">
          <div class="panel-header"><h3>租户版本目录 · {{ catalog.length }}</h3></div>
          <div class="panel-body">
            <p v-if="!catalog.length">暂无已登记版本，请先登记签名包。</p>
            <label v-else for="recipe-version">查看版本</label>
            <select v-if="catalog.length" id="recipe-version" class="select-field" :value="selectedId" :disabled="busy || !!intent || loading" @change="loadDetail(($event.target as HTMLSelectElement).value)">
              <option v-for="version in catalog" :key="version.versionId" :value="version.versionId">{{ version.name }} · {{ version.version }}（{{ version.versionId }}）</option>
            </select>
            <p v-if="detailLoading" role="status">正在加载版本详情…</p>
            <p v-if="detailError" role="alert" class="recipe-error">{{ detailError }}</p>
            <dl v-if="detail" class="recipe-metadata" aria-label="版本详情">
              <dt>名称 / 版本</dt><dd>{{ detail.name }} · {{ detail.version }}</dd>
              <dt>版本 ID</dt><dd>{{ detail.versionId }}</dd>
              <dt>签名密钥</dt><dd>{{ detail.signingKeyId }}</dd>
              <dt>最低引擎版本</dt><dd>{{ detail.package.manifest.minEngineVersion }}</dd>
              <dt>SHA-256</dt><dd><code>{{ detail.artifactSha256 }}</code></dd>
              <dt>应用</dt><dd>{{ detail.package.manifest.app }}</dd>
              <dt>命令类型</dt><dd>{{ detail.package.manifest.commandTypes.join('、') }}</dd>
              <dt>登记时间</dt><dd>{{ timestamp(detail.createdAt) }}</dd>
            </dl>
          </div>
        </section>
        <section class="panel">
          <div class="panel-header"><h3>设备发布</h3></div>
          <div class="panel-body">
            <label for="recipe-device">目标设备</label>
            <select id="recipe-device" v-model="deviceId" class="select-field" :disabled="!canMutate || !!intent">
              <option value="">请选择设备</option>
              <option v-for="device in devices" :key="device.id" :value="device.id">{{ device.name }}（{{ device.id }}）</option>
            </select>
            <p v-if="!devices.length">当前租户暂无可选设备。</p>
            <p class="recipe-hint">每次明确选择一台设备。发布覆盖包内全部命令类型，设备空闲后激活。</p>
            <button class="button button-primary" :disabled="!canMutate || !detail || !deviceId || !!intent" @click="detail && prepare('publish', detail)">手动发布所选版本</button>
            <h4>回滚到历史版本</h4>
            <p v-if="!rollbackCandidates.length" class="recipe-hint">暂无可回滚版本。目标包内每个命令都需有该设备的部署历史，且当前版本必须一致。</p>
            <div v-for="candidate in rollbackCandidates" :key="candidate.version.versionId" class="recipe-rollback">
              <span>{{ candidate.version.name }} · {{ candidate.version.version }}</span>
              <button class="button" :disabled="!canMutate || !!intent" @click="prepare('rollback', candidate.version, candidate.expected)">回滚到 {{ candidate.version.version }}</button>
            </div>
          </div>
        </section>
      </div>

      <section v-if="intent" class="panel recipe-confirm" aria-labelledby="recipe-confirm-title">
        <div class="panel-header"><h3 id="recipe-confirm-title">确认{{ intent.action === 'publish' ? '发布' : '回滚' }}</h3></div>
        <div class="panel-body">
          <p>目标设备：{{ intent.deviceName }}（{{ intent.deviceId }}）</p>
          <p>目标版本：{{ intent.version.name }} · {{ intent.version.version }}（{{ intent.version.versionId }}）</p>
          <p>影响命令：{{ intent.version.package.manifest.commandTypes.join('、') }}</p>
          <p v-if="intent.expectedCurrentVersionId">预期当前版本：{{ versionLabel(intent.expectedCurrentVersionId) }}。若已改变，服务端将拒绝回滚。</p>
          <p>确认后提交到服务端。已有运行任务保持原版本。</p>
          <div class="recipe-toolbar">
            <button class="button button-primary" :disabled="!canMutate" @click="confirm">确认{{ intent.action === 'publish' ? '发布' : '回滚' }}</button>
            <button class="button" :disabled="busy" @click="intent = null">取消</button>
          </div>
        </div>
      </section>

      <section v-if="ready && deviceId" class="panel">
        <div class="panel-header"><h3>设备当前版本与部署历史</h3></div>
        <div class="panel-body">
          <p v-if="!current.length">当前没有已发布的 Recipe 版本。</p>
          <p v-for="row in current" :key="row.deployment.id">当前 · {{ row.deployment.commandType }}：{{ versionLabel(row.version.versionId) }}</p>
        </div>
        <div class="table-wrap">
          <table>
            <caption class="sr-only">所选设备部署历史</caption>
            <thead><tr><th>版本 / 命令</th><th>状态</th><th>前一版本</th><th>操作人</th><th>创建时间</th><th>更新时间</th></tr></thead>
            <tbody>
              <tr v-for="row in history" :key="row.deployment.id">
                <td>{{ row.version.version }}<small>{{ row.deployment.commandType }}</small></td>
                <td>{{ row.deployment.status === 'PUBLISHED' ? '当前发布' : '已撤销 / 历史' }}</td>
                <td>{{ versionLabel(row.deployment.previousVersionId) }}</td>
                <td>{{ row.deployment.publishedBy ?? '未记录' }}</td>
                <td>{{ timestamp(row.deployment.createdAt) }}</td>
                <td>{{ timestamp(row.deployment.updatedAt) }}</td>
              </tr>
              <tr v-if="!history.length"><td colspan="6">该设备暂无部署历史。</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.recipe-view { max-width: 1400px; }
.recipe-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.recipe-columns { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; margin: 14px 0; }
.recipe-columns .panel { margin: 0; }
.recipe-view label { display: block; margin-bottom: 8px; font-weight: 600; }
.recipe-view select { width: 100%; }
.recipe-view input[type='file'] { max-width: 100%; }
.recipe-metadata { display: grid; grid-template-columns: 100px minmax(0, 1fr); gap: 10px; font-size: 12px; }
.recipe-metadata dt, .recipe-hint { color: var(--muted); }
.recipe-metadata dd { margin: 0; overflow-wrap: anywhere; }
.recipe-view p { line-height: 1.7; }
.recipe-error { color: #9f3130; }
.recipe-result { color: var(--accent); }
.recipe-rollback { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 10px 0; }
.recipe-confirm { border-color: var(--accent); margin-bottom: 14px; }
.recipe-view td { overflow-wrap: anywhere; }
.recipe-view td small { display: block; margin-top: 4px; color: var(--muted); }
@media (max-width: 850px) { .recipe-columns { grid-template-columns: minmax(0, 1fr); } }
</style>
