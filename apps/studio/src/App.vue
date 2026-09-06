<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref } from 'vue'
import {
  AlertTriangle,
  Bug,
  Camera,
  ChevronDown,
  CircleStop,
  Code2,
  Crosshair,
  ExternalLink,
  FileArchive,
  MonitorSmartphone,
  MousePointer2,
  Pause,
  Play,
  RotateCw,
  Save,
  ShieldCheck,
  SkipForward,
  Square,
  TerminalSquare,
} from 'lucide-vue-next'
import { canReplay, canSafelyCancel, generateLocator } from '@/domain'
import type { RunnerStage, StudioLog, UiNode } from '@/types'
import type { DebugSession, DebugSessionEvidence } from '@cloudctl/api-contracts'
import { createStudioControlApiClient, studioControlApiConfigured } from '@/api/control'
import { DebugRelayClient } from '@/api/relay'
import type { RelayEvidence } from '@/api/relay'

const MonacoWorkspace = defineAsyncComponent(() => import('@/components/MonacoWorkspace.vue'))
const launchParameters = new URLSearchParams(window.location.search)
const launchCode = launchParameters.get('launchCode') ?? ''
const expectedSessionId = launchParameters.get('sessionId') ?? ''

function safeReturnUrl(value: string | null) {
  const fallback = import.meta.env.VITE_CLOUDCTL_WEB_URL?.trim() || 'http://127.0.0.1:5173/studio'
  if (!value) return fallback
  try {
    const parsed = new URL(value, window.location.origin)
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.toString() : fallback
  } catch {
    return fallback
  }
}

const returnUrl = safeReturnUrl(launchParameters.get('returnUrl'))
const relayToken = ref('')
const controlApi = createStudioControlApiClient(() => relayToken.value || undefined)

const fallbackNodes: UiNode[] = [
  { id: 'root', className: 'android.widget.FrameLayout', bounds: '[0,0][1080,2400]', depth: 0 },
  { id: 'toolbar', className: 'android.view.ViewGroup', resourceId: 'com.target:id/toolbar', bounds: '[0,80][1080,240]', depth: 1 },
  { id: 'title', className: 'android.widget.TextView', resourceId: 'com.target:id/title', text: '创建内容', bounds: '[96,105][440,200]', depth: 2 },
  { id: 'body', className: 'android.widget.EditText', resourceId: 'com.target:id/content', text: '新品已经到店…', bounds: '[54,380][1026,1030]', depth: 1, clickable: true },
  { id: 'media', className: 'android.widget.ImageView', description: '已选择 3 个媒体', bounds: '[54,1080][342,1368]', depth: 1, clickable: true },
  { id: 'publish', className: 'android.widget.Button', resourceId: 'com.target:id/publish', text: '发布', bounds: '[744,2210][1026,2320]', depth: 1, clickable: true },
]

const source = ref(`from cloudctl_automation_sdk import (
    AutomationContext,
    AutomationPackage,
    DeviceDriver,
    ReconcileResult,
)

TARGET_PACKAGE = "com.target"


class PublishAutomation:
    async def validate(self, context: AutomationContext) -> None:
        body = context.parameters.get("body")
        if not isinstance(body, str) or not body.strip():
            raise ValueError("body is required")
        if context.commit_intent_id is None:
            raise ValueError("durable commit_intent_id is required")

    async def preflight(
        self, driver: DeviceDriver, context: AutomationContext
    ) -> None:
        await driver.app_start(TARGET_PACKAGE)
        if await driver.observe("content") is None:
            raise RuntimeError("signed locator content was not found")

    async def prepare(
        self, driver: DeviceDriver, context: AutomationContext
    ) -> None:
        body = context.parameters["body"]
        assert isinstance(body, str)
        await driver.input_text("content", body, replace=True)

    async def before_commit(
        self, driver: DeviceDriver, context: AutomationContext
    ) -> None:
        await driver.screenshot("before-commit")
        await driver.dump_ui("before-commit")

    async def commit_once(
        self, driver: DeviceDriver, context: AutomationContext
    ) -> None:
        # LifecycleRunner consumes the durable intent before this single attempt.
        await driver.tap("publish")

    async def reconcile(
        self, driver: DeviceDriver, context: AutomationContext
    ) -> ReconcileResult:
        if await driver.observe("publish_success") is not None:
            return ReconcileResult.SUCCEEDED
        return ReconcileResult.UNKNOWN

    async def cleanup(
        self, driver: DeviceDriver, context: AutomationContext
    ) -> None:
        pass


package: AutomationPackage = PublishAutomation()
`)
const fallbackCapabilities = ['view.frame', 'view.layout', 'input.tap', 'evidence.capture'] as const
const sessionActive = ref(false)
const sessionId = ref('')
const debugSession = ref<DebugSession | null>(null)
const relayUrl = ref('')
const relayClient = ref<DebugRelayClient | null>(null)
const remoteFrame = ref('')
const apiError = ref('')
const ttlSeconds = ref(0)
const fallbackExpiresAt = ref<number | null>(null)
const remoteNodes = ref<UiNode[]>([])
const uiNodes = computed(() => liveSession.value ? remoteNodes.value : fallbackMode.value ? fallbackNodes : [])
const selectedNode = ref<UiNode | null>(fallbackNodes[5]!)
const pendingEvidence = ref(new Map<string, 'SCREENSHOT' | 'UI_TREE'>())
const recordedEvidence = ref<DebugSessionEvidence[]>([])
const selectedInspector = ref<'Selector' | '变量' | '证据'>('Selector')
const lowerPanel = ref<'日志' | '调用' | '时间线'>('日志')
const stage = ref<RunnerStage>('VALIDATE')
const remoteOrientation = ref<'portrait' | 'landscape'>('portrait')
const logs = ref<StudioLog[]>([
  { time: '10:42:04.121', level: 'INFO', event: 'workspace.loaded', detail: 'rednote-publish@2.5.0-rc1' },
])

const locator = computed(() => selectedNode.value ? generateLocator(selectedNode.value) : '—')
const replayAllowed = computed(() => canReplay(stage.value))
const cancelAllowed = computed(() => canSafelyCancel(stage.value))
const liveSession = computed(() => Boolean(debugSession.value && relayToken.value))
const fallbackMode = computed(() => !studioControlApiConfigured)
const grantedCapabilities = computed<readonly string[]>(() => {
  if (liveSession.value) return debugSession.value?.capabilities ?? []
  if (fallbackMode.value && sessionActive.value) return fallbackCapabilities
  return []
})
const ttlLabel = computed(() => {
  const minutes = Math.floor(ttlSeconds.value / 60).toString().padStart(2, '0')
  const seconds = (ttlSeconds.value % 60).toString().padStart(2, '0')
  return `${minutes}:${seconds}`
})
let ttlTimer: number | undefined

function now() {
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3, hour12: false }).format(new Date())
}

function addLog(level: StudioLog['level'], event: string, detail: string) {
  logs.value.unshift({ time: now(), level, event, detail })
}

function startSession() {
  if (studioControlApiConfigured) {
    apiError.value = '缺少一次性 launch code，请返回 CloudCtl 创建调试会话。'
    return
  }
  sessionActive.value = true
  sessionId.value = 'dbg-mock-830-7fa2'
  fallbackExpiresAt.value = Date.now() + 15 * 60 * 1000
  startTtlClock()
  addLog('AUDIT', 'debug_session.created', `15 分钟 · dev-bj-008 · ${fallbackCapabilities.join('/')}`)
}

function refreshTtl() {
  const expiresAt = debugSession.value
    ? new Date(debugSession.value.expiresAt).getTime()
    : fallbackExpiresAt.value
  if (expiresAt === null) return
  if (!Number.isFinite(expiresAt)) {
    sessionActive.value = false
    stopTtlClock()
    apiError.value = '调试会话到期时间无效'
    addLog('WARN', 'debug_session.invalid_expiry', debugSession.value?.id ?? sessionId.value)
    return
  }
  ttlSeconds.value = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000))
  if (ttlSeconds.value === 0 && sessionActive.value) {
    sessionActive.value = false
    stopTtlClock()
    addLog('WARN', 'debug_session.expired', debugSession.value?.id ?? sessionId.value)
  }
}

function stopTtlClock() {
  if (ttlTimer !== undefined) window.clearInterval(ttlTimer)
  ttlTimer = undefined
}

function startTtlClock() {
  stopTtlClock()
  refreshTtl()
  if (sessionActive.value) ttlTimer = window.setInterval(refreshTtl, 1000)
}

function clearLaunchCodeFromAddressBar() {
  const clean = new URL(window.location.href)
  clean.searchParams.delete('launchCode')
  window.history.replaceState({}, '', `${clean.pathname}${clean.search}${clean.hash}`)
}

async function exchangeLaunchSession() {
  if (!studioControlApiConfigured || !launchCode) return
  clearLaunchCodeFromAddressBar()
  try {
    const result = await controlApi.exchangeDebugSession({ launchCode })
    if (expectedSessionId && result.session.id !== expectedSessionId) throw new Error('launch code 与会话 ID 不匹配')
    relayToken.value = result.relayToken
    relayUrl.value = result.relayUrl
    debugSession.value = result.session
    sessionId.value = result.session.id
    sessionActive.value = result.session.status === 'ACTIVE'
    remoteNodes.value = []
    selectedNode.value = null
    startTtlClock()
    addLog('AUDIT', 'debug_session.exchanged', `${result.session.id} · ${result.session.deviceId} · token 仅保存在内存`)
    connectRelay(result.relayUrl, result.relayToken, result.session.id, result.session.capabilities)
    await reportHeartbeat('studio.connected', `relay=${result.relayUrl}`)
  } catch (value) {
    apiError.value = value instanceof Error ? value.message : 'launch code 交换失败'
    addLog('WARN', 'debug_session.exchange_failed', apiError.value)
  }
}

function connectRelay(url: string, token: string, id: string, capabilities: readonly string[]) {
  try {
    const client = new DebugRelayClient({
      url, token, sessionId: id, capabilities,
      onStatus: (status, detail) => {
        if (status === 'connected') {
          addLog('AUDIT', 'relay.connected', 'Edge relay 已完成首帧认证')
          try {
            if (capabilities.includes('view.layout')) client.requestLayout()
            if (capabilities.includes('view.frame')) client.requestFrame()
          } catch (value) {
            addLog('WARN', 'relay.initial_view_failed', value instanceof Error ? value.message : 'initial view request failed')
          }
        }
        if (status === 'disconnected') addLog('WARN', 'relay.disconnected', detail ?? '连接已断开')
        if (status === 'expired' || status === 'revoked') {
          sessionActive.value = false; relayToken.value = ''; stopTtlClock()
          addLog('WARN', `debug_session.${status}`, detail ?? status)
        }
        if (status === 'error') {
          apiError.value = detail ?? 'relay error'
          addLog('WARN', 'relay.error', apiError.value)
        }
      },
      onFrame: (frame) => { remoteFrame.value = `data:${frame.mimeType ?? 'image/jpeg'};base64,${frame.data}` },
      onLayout: (layout) => {
        remoteNodes.value = layout.nodes
        const selected = layout.nodes.find((node) => node.resourceId === selectedNode.value?.resourceId)
          ?? layout.nodes.find((node) => node.clickable)
          ?? layout.nodes[0]
        selectedNode.value = selected ?? null
        addLog('INFO', 'remote.layout', `${layout.nodes.length} 个节点已更新`)
      },
      onEvidence: (evidence) => { void recordRelayEvidence(evidence) },
    })
    relayClient.value = client
    client.connect()
  } catch (value) {
    addLog('WARN', 'relay.connect_failed', value instanceof Error ? value.message : 'relay 连接失败')
  }
}

async function reportHeartbeat(event: string, detail?: string, evidenceRefs?: string[]) {
  if (!liveSession.value || !debugSession.value) return
  try {
    debugSession.value = await controlApi.heartbeatDebugSession(debugSession.value.id, {
      stage: stage.value,
      event,
      ...(detail ? { detail } : {}),
      ...(evidenceRefs?.length ? { evidenceRefs } : {}),
    })
    refreshTtl()
  } catch (value) {
    const message = value instanceof Error ? value.message : '心跳回写失败'
    apiError.value = message
    addLog('WARN', 'debug_session.heartbeat_failed', message)
  }
}

async function captureEvidence() {
  if (!liveSession.value || !debugSession.value || !relayClient.value) {
    rejectUnavailable('证据采集', '仅真实受控会话可请求并登记证据')
    return
  }
  try {
    const requestId = relayClient.value.requestEvidence('SCREENSHOT')
    pendingEvidence.value.set(requestId, 'SCREENSHOT')
    addLog('AUDIT', 'evidence.requested', `${requestId} · 等待 Edge relay 回执`)
  } catch (value) {
    const message = value instanceof Error ? value.message : 'evidence request failed'
    apiError.value = message
    addLog('WARN', 'relay.evidence_failed', message)
  }
}

async function recordRelayEvidence(receipt: RelayEvidence) {
  const expectedKind = pendingEvidence.value.get(receipt.requestId)
  if (!expectedKind || expectedKind !== receipt.kind) {
    rejectUnavailable('证据登记', `拒绝未知或类型不匹配的 relay 回执：${receipt.commandId}`)
    return
  }
  pendingEvidence.value.delete(receipt.requestId)
  if (!liveSession.value || !debugSession.value) {
    rejectUnavailable('证据登记', '调试会话已失效')
    return
  }
  try {
    const evidence = await controlApi.recordDebugSessionEvidence(debugSession.value.id, {
      kind: expectedKind,
      sha256: receipt.sha256,
      objectRef: receipt.objectRef,
      metadata: {
        ...(receipt.metadata ?? {}),
        relayCommandId: receipt.commandId,
        ...(receipt.evidenceId ? { relayEvidenceId: receipt.evidenceId } : {}),
        ...(receipt.size !== undefined ? { size: receipt.size } : {}),
        source: 'edge.relay',
      },
    })
    recordedEvidence.value.unshift(evidence)
    addLog('AUDIT', 'evidence.recorded', `${evidence.kind} · ${evidence.sha256.slice(0, 12)}…`)
    await reportHeartbeat('evidence.recorded', evidence.id, [evidence.objectRef])
  } catch (value) {
    const message = value instanceof Error ? value.message : '证据回写失败'
    apiError.value = message
    addLog('WARN', 'evidence.record_failed', message)
  }
}

async function endSession() {
  if (!liveSession.value || !debugSession.value) return
  try {
    relayClient.value?.close('debug session revoked by studio')
    relayClient.value = null
    debugSession.value = await controlApi.revokeDebugSession(debugSession.value.id, { reason: 'Studio operator ended the debug session' })
    sessionActive.value = false
    relayToken.value = ''
    stopTtlClock()
    addLog('AUDIT', 'debug_session.revoked', debugSession.value.id)
  } catch (value) {
    apiError.value = value instanceof Error ? value.message : '会话撤销失败'
  }
}

function selectNode(node: UiNode) {
  selectedNode.value = node
  selectedInspector.value = 'Selector'
  addLog('INFO', 'selector.node_selected', node.resourceId ?? node.text ?? node.className)
}

function remoteInput(action: string, capability: string) {
  if (!sessionActive.value) return
  if (!grantedCapabilities.value.includes(capability)) {
    addLog('WARN', 'remote.input_denied', `${capability} 未获调试会话授权`)
    return
  }
  addLog('AUDIT', 'remote.input', liveSession.value ? `${capability} · ${action} · 受限 relay 请求已写审计` : `${capability} · ${action} · 显式模拟输入，不会发送到设备`)
  if (liveSession.value && capability === 'input.tap') {
    if (!selectedNode.value) {
      addLog('WARN', 'relay.input_failed', '尚未收到可用的实时 UI 节点')
      return
    }
    const coordinates = nodeCenter(selectedNode.value)
    if (!coordinates) {
      addLog('WARN', 'relay.input_failed', '选中节点没有有效 bounds')
      return
    }
    try { relayClient.value?.sendTap({ ...coordinates, locator: selectedNode.value.resourceId ?? selectedNode.value.id }) } catch (value) {
      addLog('WARN', 'relay.input_failed', value instanceof Error ? value.message : 'tap request failed')
    }
  }
  void reportHeartbeat('remote.input', `${capability} · ${action}`)
}

function nodeCenter(node: UiNode): { x: number; y: number } | null {
  if (Number.isInteger(node.centerX) && Number.isInteger(node.centerY)) {
    return { x: node.centerX!, y: node.centerY! }
  }
  const match = /^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$/.exec(node.bounds)
  if (!match) return null
  return {
    x: Math.floor((Number(match[1]) + Number(match[3])) / 2),
    y: Math.floor((Number(match[2]) + Number(match[4])) / 2),
  }
}

function insertDriverCall() {
  if (!selectedNode.value) return
  const call = selectedNode.value.clickable
    ? `        await driver.tap("${selectedNode.value.id}")\n`
    : `        await driver.observe("${selectedNode.value.id}")\n`
  const marker = '    async def before_commit('
  const index = source.value.indexOf(marker)
  if (index === -1) return
  source.value = `${source.value.slice(0, index)}${call}\n${source.value.slice(index)}`
  addLog('AUDIT', 'workspace.sdk_call_inserted', call.trim())
}

function rejectUnavailable(action: string, detail = `后端未提供 ${action} 控制能力，已拒绝浏览器本地推进`) {
  apiError.value = detail
  addLog('WARN', 'runner.control_unavailable', `${action} · ${detail}`)
}

function rejectRunnerControl(action: string) {
  rejectUnavailable(action)
}

onMounted(() => {
  if (fallbackMode.value) {
    addLog('AUDIT', 'mock_stream.declared', 'Control API 未配置；当前远控画面为显式模拟数据')
    return
  }
  void exchangeLaunchSession()
})
onUnmounted(() => {
  stopTtlClock()
  relayClient.value?.close('studio unmounted')
})
</script>

<template>
  <div class="studio-shell">
    <header class="studio-topbar">
      <div class="studio-brand"><span><Bug :size="17" /></span><div><strong>Automation Studio</strong><small>CloudCtl · 受限调试工作区</small></div></div>
      <a class="studio-button" :href="returnUrl"><ExternalLink :size="14" />返回 CloudCtl</a>
      <div class="session-toolbar">
        <label><span>Edge</span><select><option>edge-bj-lab</option><option>edge-hz-a</option></select><ChevronDown :size="13" /></label>
        <label><span>设备</span><select><option>北京-实验-008</option><option>杭州-内容-023（需维护）</option></select><ChevronDown :size="13" /></label>
        <button v-if="!sessionActive && !studioControlApiConfigured" class="studio-button primary" @click="startSession"><MonitorSmartphone :size="15" />创建 15 分钟会话</button>
        <a v-else-if="!sessionActive" class="studio-button primary" :href="returnUrl"><MonitorSmartphone :size="15" />从 CloudCtl 创建会话</a>
        <div v-else class="session-status"><span class="session-dot" /><div><b>{{ liveSession ? '受控会话已连接' : '模拟会话已连接' }}</b><small>{{ sessionId }} · {{ liveSession ? `剩余 ${ttlLabel}` : '剩余 14:42' }}</small></div></div>
        <button v-if="liveSession" class="studio-button danger-solid" @click="endSession">结束会话</button>
      </div>
      <div class="security-chip"><ShieldCheck :size="14" />PEM 留在 Edge</div>
    </header>

    <div v-if="apiError" class="studio-alert"><AlertTriangle :size="15" />{{ apiError }}</div>
    <div class="workspace-toolbar">
      <div class="file-tab"><Code2 :size="14" /><span>publish.py</span><i>●</i></div>
      <div class="runner-controls">
        <button class="tool-button" title="保存自动化包源" @click="addLog('AUDIT', 'workspace.saved', 'publish.py'); reportHeartbeat('workspace.saved', 'publish.py')"><Save :size="15" /></button>
        <span class="tool-divider" />
        <button class="tool-button" title="运行" :disabled="!sessionActive" @click="rejectRunnerControl('运行')"><Play :size="15" /></button>
        <button class="tool-button" title="暂停" :disabled="!sessionActive" @click="rejectRunnerControl('暂停')"><Pause :size="15" /></button>
        <button class="tool-button" title="单步" :disabled="!sessionActive" @click="rejectRunnerControl('单步')"><SkipForward :size="15" /></button>
        <button class="tool-button" title="回退重放" :disabled="!sessionActive || !replayAllowed" @click="rejectRunnerControl('回退重放')"><RotateCw :size="15" /></button>
        <button class="tool-button danger" title="安全取消" :disabled="!sessionActive || !cancelAllowed" @click="rejectRunnerControl('安全取消')"><CircleStop :size="15" /></button>
        <span class="stage-chip" :class="{ locked: !replayAllowed }">{{ stage }}</span>
      </div>
      <div class="mock-chip">{{ liveSession ? 'Control API 会话 · Edge relay 受限能力' : fallbackMode ? '显式模拟设备流 · 非真机证据' : '受控会话未连接 · 无设备流' }}</div>
    </div>

    <main class="studio-grid">
      <section class="remote-pane studio-pane">
        <div class="pane-title"><div><MonitorSmartphone :size="14" />远程画面</div><span>{{ liveSession ? `${relayUrl} · audited` : fallbackMode ? '720p · explicit mock · 28ms' : '等待受控会话' }}</span></div>
        <div class="remote-canvas" :class="remoteOrientation">
          <img v-if="remoteFrame" class="remote-frame" :src="remoteFrame" alt="Edge relay 实时画面">
          <div v-if="!liveSession && fallbackMode" class="phone-mock">
            <div class="phone-status"><span>10:48</span><span>Wi-Fi&nbsp;&nbsp;87%</span></div>
            <div class="app-toolbar">创建内容</div>
            <div class="content-image"><span>新品封面预览</span></div>
            <div class="content-copy">新品已经到店。这支短片展示包装细节、核心功能和适用场景。</div>
            <button class="publish-target" :class="{ highlighted: selectedNode?.id === 'publish' }" @click="selectNode(fallbackNodes[5]!); remoteInput('tap selected node', 'input.tap')">发布</button>
          </div>
          <div v-if="selectedNode?.clickable" class="node-highlight"><span>{{ selectedNode.resourceId ?? selectedNode.text }}</span></div>
        </div>
        <div class="remote-controls">
          <button title="受控 tap 输入" :disabled="!sessionActive" @click="remoteInput('tap signed locator publish', 'input.tap')"><MousePointer2 :size="15" /></button>
          <button title="旋转" @click="remoteOrientation = remoteOrientation === 'portrait' ? 'landscape' : 'portrait'"><RotateCw :size="15" /></button>
          <button title="手工截图" :disabled="!sessionActive" @click="captureEvidence"><Camera :size="15" /></button>
        </div>
      </section>

      <section class="editor-pane studio-pane">
        <div class="pane-title"><div><Code2 :size="14" />自动化包源</div><span>Python 3.12 · cloudctl_automation_sdk</span></div>
        <MonacoWorkspace v-model="source" />
      </section>

      <aside class="inspector-pane studio-pane">
        <div class="pane-tabs"><button v-for="tab in ['Selector', '变量', '证据'] as const" :key="tab" :class="{ active: selectedInspector === tab }" @click="selectedInspector = tab">{{ tab }}</button></div>
        <template v-if="selectedInspector === 'Selector'">
          <div class="inspector-section"><h3>UI 树</h3><div class="tree-list"><button v-for="node in uiNodes" :key="`${node.id}-${node.bounds}`" :class="{ selected: selectedNode?.id === node.id }" :style="{ paddingLeft: `${8 + node.depth * 13}px` }" @click="selectNode(node)"><span>{{ node.className.split('.').at(-1) }}</span><small>{{ node.resourceId ?? node.text ?? node.description ?? node.id }}</small></button><small v-if="uiNodes.length === 0" class="helper">尚未收到 Edge relay 的实时 layout。</small></div></div>
          <div class="inspector-section"><h3>节点属性</h3><dl class="property-grid"><dt>resourceId</dt><dd>{{ selectedNode?.resourceId ?? '—' }}</dd><dt>text</dt><dd>{{ selectedNode?.text ?? '—' }}</dd><dt>description</dt><dd>{{ selectedNode?.description ?? '—' }}</dd><dt>bounds</dt><dd>{{ selectedNode?.bounds ?? '—' }}</dd></dl></div>
          <div class="inspector-section"><h3>推荐 Locator</h3><code class="locator-code">{{ locator }}</code><button class="studio-button full" @click="insertDriverCall"><Crosshair :size="14" />插入 SDK 调用</button><small class="helper">优先 resourceId → text/description → 结构 → OCR/image；仅引用签名 registry，不生成坐标脚本。</small></div>
        </template>
        <template v-else-if="selectedInspector === '变量'"><div class="inspector-section"><h3>运行变量</h3><dl class="property-grid"><dt>session_id</dt><dd>{{ sessionId || '—' }}</dd><dt>device_id</dt><dd>{{ debugSession?.deviceId ?? (fallbackMode ? 'dev-bj-008（模拟）' : '—') }}</dd><dt>snapshot</dt><dd>—</dd><dt>relay_token</dt><dd>{{ liveSession ? '仅内存持有' : fallbackMode ? '显式模拟值' : '—' }}</dd><dt>capabilities</dt><dd>{{ grantedCapabilities.join(', ') || '—' }}</dd><dt>current_app</dt><dd>—</dd><dt>stage</dt><dd>{{ stage }}</dd></dl></div></template>
        <template v-else><div class="inspector-section"><h3>调试证据</h3><div class="evidence-list"><button v-for="evidence in recordedEvidence" :key="evidence.id"><Camera :size="14" /><span>{{ evidence.kind }}<small>sha256:{{ evidence.sha256.slice(0, 12) }}… · 已登记</small></span></button><button v-for="[requestId, kind] in pendingEvidence" :key="requestId" disabled><Camera :size="14" /><span>{{ kind }}<small>{{ requestId.slice(0, 12) }}… · 等待 relay 回执</small></span></button><small v-if="recordedEvidence.length === 0 && pendingEvidence.size === 0" class="helper">尚无已确认回执的证据。</small></div><button class="studio-button full" @click="rejectUnavailable('证据包导出')"><FileArchive :size="14" />导出受控调试包</button></div></template>
      </aside>
    </main>

    <section class="bottom-panel">
      <div class="bottom-tabs"><button v-for="tab in ['日志', '调用', '时间线'] as const" :key="tab" :class="{ active: lowerPanel === tab }" @click="lowerPanel = tab">{{ tab }}</button><span /><button title="收起面板"><ChevronDown :size="15" /></button></div>
      <div v-if="lowerPanel === '日志'" class="log-table"><div v-for="log in logs" :key="`${log.time}-${log.event}`"><time>{{ log.time }}</time><b :class="log.level.toLowerCase()">{{ log.level }}</b><code>{{ log.event }}</code><span>{{ log.detail }}</span></div></div>
      <div v-else-if="lowerPanel === '调用'" class="empty-panel"><TerminalSquare :size="18" />{{ liveSession ? '受限 relay' : fallbackMode ? '显式模拟 RPC' : '无活动 RPC' }}：app_start 118ms · input_text 204ms · tap 96ms · 不提供任意终端</div>
      <div v-else class="empty-panel"><Square :size="14" />{{ stage }} · 普通步骤可重放：{{ replayAllowed ? '是' : '否，commit intent 已写入' }}</div>
    </section>
  </div>
</template>
