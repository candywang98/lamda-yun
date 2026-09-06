<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import type { DevicePreviewStatus } from '@cloudctl/api-contracts'
import { AlertTriangle, Wrench } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import QueryState from '@/components/QueryState.vue'
import PermissionButton from '@/components/PermissionButton.vue'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { keepAliveHint, mapControlDevice, previewCaption } from '@/api/devices'

const route = useRoute()
const deviceId = computed(() => String(route.params.id))
const activeTab = ref(isRemoteTab(route.query.tab) ? '远控' : '概览')
const showMaintenance = ref(false)
const actionResult = ref('')
const actionError = ref('')
const screenUrl = ref('')
const screenBusy = ref(false)
const screenError = ref('')
const previewStatus = ref<DevicePreviewStatus | null>(null)
const previewSessionId = ref('')
const previewEtag = ref('')
const controlApi = createControlApiClient()
let pollTimer: ReturnType<typeof setInterval> | null = null
let startingPreview = false

const query = useQuery({
  queryKey: ['control-device', deviceId],
  queryFn: async () => {
    const device = (await controlApi.devices()).map(mapControlDevice)
      .find((item) => item.id === deviceId.value)
    if (!device) throw new Error('设备不存在或当前租户无权访问')
    return device
  },
  enabled: controlApiConfigured,
})
const tabs = ['概览', '当前任务', '远控', 'App', 'APK', '日志', '证书状态', '历史']
const caption = computed(() => previewCaption({
  active: previewStatus.value?.active ?? false,
  waitingForFrame: previewStatus.value?.waitingForFrame ?? false,
  hasFrame: previewStatus.value?.hasFrame ?? Boolean(screenUrl.value),
  capturedAt: previewStatus.value?.capturedAt ?? null,
  accessibilityEnabled: query.data.value?.accessibilityEnabled ?? null,
}))

watch(
  [activeTab, () => query.data.value?.id, () => query.data.value?.status],
  async ([tab, id, status]) => {
    if (tab !== '远控' || !id) {
      if (tab !== '远控') await stopPreview()
      return
    }
    if (status !== 'ONLINE') {
      screenError.value = '设备不在线，无法投屏。请确认 Companion 心跳正常。'
      return
    }
    await startPreview()
  },
)

onUnmounted(() => {
  if (screenUrl.value) URL.revokeObjectURL(screenUrl.value)
  void stopPreview()
})

async function enterMaintenance() {
  actionResult.value = ''
  actionError.value = ''
  try {
    await controlApi.setMaintenance(deviceId.value, {
      enabled: true,
      reason: 'operator requested maintenance from device detail',
      expectedVersion: query.data.value?.version ?? undefined,
    })
    actionResult.value = 'Control API 已确认设备进入维护状态。'
    showMaintenance.value = false
    await query.refetch()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '维护请求失败'
  }
}

function health(value: number | null | undefined, suffix: string) {
  return value == null ? '未回传' : `${value}${suffix}`
}

async function startPreview() {
  if (!controlApiConfigured || startingPreview || previewSessionId.value) return
  startingPreview = true
  screenBusy.value = true
  screenError.value = ''
  try {
    const session = await controlApi.startDevicePreview(deviceId.value, {
      ttlSeconds: 120,
      captureIntervalMs: 2000,
    })
    previewSessionId.value = session.sessionId ?? ''
    previewStatus.value = session
    await pollPreview()
    if (!pollTimer) pollTimer = setInterval(() => { void pollPreview() }, 1500)
  } catch (error) {
    screenError.value = error instanceof Error ? error.message : '无法开始投屏'
  } finally {
    screenBusy.value = false
    startingPreview = false
  }
}

async function stopPreview() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  const sessionId = previewSessionId.value
  previewSessionId.value = ''
  if (sessionId) {
    try {
      previewStatus.value = await controlApi.stopDevicePreview(deviceId.value, sessionId)
    } catch {
      previewStatus.value = null
    }
  }
}

async function pollPreview() {
  try {
    const status = await controlApi.devicePreview(deviceId.value)
    previewStatus.value = status
    if (!status.active) {
      previewSessionId.value = ''
      if (activeTab.value === '远控' && query.data.value?.status === 'ONLINE') {
        await startPreview()
      } else if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
      return
    }
    previewSessionId.value = status.sessionId ?? previewSessionId.value
    if (!status.hasFrame || !status.sha256) return
    const current = previewEtag.value.replaceAll('"', '')
    if (current === status.sha256 && screenUrl.value) return
    const frame = await controlApi.devicePreviewFrame(deviceId.value, previewEtag.value || undefined)
    if (!frame) return
    if (screenUrl.value) URL.revokeObjectURL(screenUrl.value)
    screenUrl.value = URL.createObjectURL(frame.blob)
    previewEtag.value = frame.etag ?? `"${status.sha256}"`
    screenError.value = ''
  } catch (error) {
    screenError.value = error instanceof Error ? error.message : '画面刷新失败'
  }
}

function isRemoteTab(tab: unknown): boolean {
  const value = Array.isArray(tab) ? tab[0] : tab
  return value === 'remote' || value === '远控'
}
</script>

<template>
  <div v-if="!controlApiConfigured" class="notice notice-danger">未配置 Control API，设备详情不会显示 Mock 数据。</div>
  <QueryState :loading="query.isPending.value && controlApiConfigured" :error="query.error.value">
    <PageHeader :title="query.data.value?.name ?? deviceId" description="健康、当前租约、手机直连状态与受控调试入口。" :kicker="deviceId">
      <template #actions><PermissionButton permission="device:operate" label="进入维护" :icon="Wrench" kind="primary" @click="showMaintenance = true" /></template>
    </PageHeader>
    <div v-if="actionResult" class="notice notice-info">{{ actionResult }}</div>
    <div v-if="actionError" class="notice notice-danger">{{ actionError }}</div>
    <div v-if="query.data.value && keepAliveHint(query.data.value)" class="notice notice-info">{{ keepAliveHint(query.data.value) }}</div>
    <div class="definition-grid">
      <div class="definition-item"><span>连接状态</span><strong><StatusBadge :status="query.data.value?.status ?? 'OFFLINE'" /></strong></div>
      <div class="definition-item"><span>当前租约</span><strong class="mono">{{ query.data.value?.lease ?? '无' }}</strong></div>
      <div class="definition-item"><span>系统版本</span><strong>Android {{ query.data.value?.android }}</strong></div>
      <div class="definition-item"><span>LAMDA / App</span><strong>{{ query.data.value?.lamda }} / {{ query.data.value?.app }}</strong></div>
      <div class="definition-item"><span>Edge 节点</span><strong class="mono">{{ query.data.value?.edge }}</strong></div>
      <div class="definition-item"><span>网络</span><strong>Wi-Fi · 38 ms · -52 dBm</strong></div>
      <div class="definition-item"><span>电量 / 温度</span><strong>{{ health(query.data.value?.battery, '%') }} / {{ health(query.data.value?.temperature, '°C') }}</strong></div>
      <div class="definition-item"><span>无障碍</span><strong>{{ query.data.value?.accessibilityEnabled == null ? '未回传' : query.data.value.accessibilityEnabled ? '已开启' : '未开启' }}</strong></div>
      <div class="definition-item"><span>电池优化</span><strong>{{ query.data.value?.batteryOptimizationIgnored == null ? '未回传' : query.data.value.batteryOptimizationIgnored ? '已忽略' : '未忽略' }}</strong></div>
      <div class="definition-item"><span>数据来源</span><strong>Control API 实时设备记录</strong></div>
    </div>
    <section class="panel" style="margin-top:12px">
      <div class="tabs"><button v-for="tab in tabs" :key="tab" class="tab" :class="{ active: activeTab === tab }" @click="activeTab = tab">{{ tab }}</button></div>
      <div class="panel-body">
        <div v-if="activeTab === '概览'" class="two-grid">
          <div><h3>能力画像</h3><div class="tag-list"><span class="tag">{{ query.data.value?.capability }}</span><span class="tag">截图</span><span class="tag">UI 树</span><span class="tag">文件推送</span><span class="tag">APK 安装需审批</span></div></div>
          <div><h3>授权与绑定</h3><p class="cell-sub">{{ query.data.value?.account }} · 账号授权状态从独立账号 API 获取</p></div>
        </div>
        <div v-else-if="activeTab === '远控'" class="two-grid">
          <div class="device-screen">
            <img v-if="screenUrl" class="preview-frame" :src="screenUrl" alt="当前 Companion 投屏画面" />
            <div v-else class="phone-frame"><div class="phone-content"><div class="phone-status"><span>投屏</span><span>Companion</span></div><div class="phone-banner" /><div class="phone-line" /><div class="phone-line short" /><div class="phone-button">{{ screenBusy ? '连接中' : '等待画面' }}</div></div></div>
            <span class="simulation-label">{{ caption }}</span>
          </div>
          <div>
            <div class="notice notice-info"><AlertTriangle :size="17" /><p>网页投屏走手机 Companion 无障碍截图，经 Control API 回传，不依赖电脑 ADB。适合短时盯机确认画面；生产任务仍由手机本机执行。</p></div>
            <div class="page-actions" style="margin-top:10px">
              <button class="button button-primary" type="button" :disabled="screenBusy || query.data.value?.status !== 'ONLINE'" @click="startPreview">{{ previewSessionId ? '保持投屏' : '开始投屏' }}</button>
              <button class="button" type="button" :disabled="!previewSessionId" @click="stopPreview">停止</button>
              <button class="button" type="button" :disabled="!previewSessionId" @click="pollPreview">刷新画面</button>
            </div>
            <p v-if="previewStatus?.expiresAt" class="cell-sub" style="margin-top:8px">会话将在 {{ new Date(previewStatus.expiresAt).toLocaleTimeString() }} 到期，停留在本页会自动续约。</p>
            <p v-if="screenError" class="cell-sub" style="color:var(--bad); margin-top:8px">{{ screenError }}</p>
          </div>
        </div>
        <div v-else-if="activeTab === '证书状态'" class="notice"><AlertTriangle :size="17" /><p>手机直连设备使用 Companion 内保存的 Control API TLS 指纹；服务端不会返回或展示手机端密钥材料。</p></div>
        <p v-else class="cell-sub">{{ activeTab }} 尚无对应真实 API，因此保持不可用状态，不生成模拟记录。</p>
      </div>
    </section>
  </QueryState>

  <div v-if="showMaintenance" class="modal-backdrop" @click.self="showMaintenance = false"><div class="modal" role="dialog" aria-modal="true" aria-label="进入维护确认"><div class="modal-header"><h3>进入设备维护</h3><button class="icon-button" title="关闭" @click="showMaintenance = false">×</button></div><div class="modal-body"><div class="notice notice-danger"><AlertTriangle :size="18" /><div><strong>等待当前任务安全点</strong><p>不会抢占 Runner。若已进入 COMMITTING，仅记录请求并等待对账完成。</p></div></div><ul class="preview-list"><li><span>目标</span><strong>{{ deviceId }}</strong></li><li><span>影响</span><strong>暂停新任务调度，释放租约后允许调试</strong></li><li><span>审计</span><strong>记录操作者、用途、request_id</strong></li></ul></div><div class="modal-actions"><button class="button" @click="showMaintenance = false">返回</button><button class="button button-primary" @click="enterMaintenance">确认请求</button></div></div></div>
</template>
