import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DebugSession, DebugSessionEvidence } from '@cloudctl/api-contracts'

const { api, activeSession, revokedSession, screenshotEvidence, relayState } = vi.hoisted(() => {
  const active: DebugSession = {
    id: '01993d2a-6127-7b5d-9f34-c87c146138aa',
    tenantId: '00000000-0000-7000-8000-000000001111',
    edgeId: 'edge-bj-001',
    deviceId: 'dev-bj-008',
    leaseId: '00000000-0000-7000-8000-000000003301',
    fencingToken: 42,
    capabilities: ['view.frame', 'view.layout', 'input.tap', 'input.swipe', 'input.text', 'debug.steps', 'debug.variables', 'evidence.capture'],
    purpose: 'Automation Studio 受限调试与证据采集',
    status: 'ACTIVE',
    createdBy: '00000000-0000-7000-8000-000000002206',
    createdAt: '2026-08-31T01:00:00Z',
    expiresAt: '2036-08-31T01:15:00Z',
    exchangedAt: '2026-08-31T01:00:02Z',
    lastHeartbeatAt: null,
    stage: null,
    event: null,
    detail: null,
    returnUrl: 'http://127.0.0.1:5173/studio',
    revokedAt: null,
    revokedBy: null,
    revokeReason: null,
  }
  const revoked: DebugSession = {
    ...active,
    status: 'REVOKED',
    revokedAt: '2026-08-31T01:01:00Z',
    revokedBy: active.createdBy,
    revokeReason: 'Studio operator ended the debug session',
  }
  const evidence: DebugSessionEvidence = {
    id: 'evidence-001',
    sessionId: active.id,
    kind: 'SCREENSHOT',
    sha256: '88a16e2000000000000000000000000000000000000000000000000000000000',
    objectRef: `s3://cloudctl-evidence/${active.id}/manual-shot-004.png`,
    metadata: { redacted: true, source: 'studio.manual' },
    createdAt: '2026-08-31T01:00:30Z',
  }
  return {
    activeSession: active,
    revokedSession: revoked,
    screenshotEvidence: evidence,
    relayState: { options: null as null | { onEvidence?: (value: unknown) => void; onLayout?: (value: unknown) => void }, requestId: 'request-evidence-001' },
    api: {
      exchangeDebugSession: vi.fn().mockResolvedValue({ session: active, relayToken: 'relay-token-memory-only-1234567890', relayUrl: 'wss://127.0.0.1:7443/debug' }),
      heartbeatDebugSession: vi.fn().mockResolvedValue(active),
      recordDebugSessionEvidence: vi.fn().mockResolvedValue(evidence),
      revokeDebugSession: vi.fn().mockResolvedValue(revoked),
    },
  }
})

vi.mock('@/api/relay', () => ({
  DebugRelayClient: class {
    constructor(options: { onEvidence?: (value: unknown) => void; onLayout?: (value: unknown) => void }) { relayState.options = options }
    connect() {}
    close() {}
    requestLayout() { return 'request-layout' }
    requestFrame() { return 'request-frame' }
    requestEvidence() { return relayState.requestId }
    sendTap() { return 'request-tap' }
  },
}))

vi.mock('@/api/control', () => ({
  studioControlApiConfigured: true,
  createStudioControlApiClient: () => api,
}))

describe('Studio live debug session', () => {
  let App: typeof import('@/App.vue').default

  beforeAll(async () => {
    window.history.replaceState({}, '', `/?sessionId=${activeSession.id}&launchCode=launch-code-one-time-1234567890&returnUrl=${encodeURIComponent('http://127.0.0.1:5173/studio')}`)
    App = (await import('@/App.vue')).default
  })

  beforeEach(() => {
    vi.clearAllMocks()
    window.history.replaceState({}, '', `/?sessionId=${activeSession.id}&launchCode=launch-code-one-time-1234567890&returnUrl=${encodeURIComponent('http://127.0.0.1:5173/studio')}`)
  })

  it('exchanges and erases the launch code, then audits evidence and revocation', async () => {
    render(App, { global: { stubs: { MonacoWorkspace: true } } })

    await screen.findByText('受控会话已连接')
    expect(screen.queryByText(/显式模拟设备流|explicit mock/)).toBeNull()
    expect(api.exchangeDebugSession).toHaveBeenCalledWith({ launchCode: 'launch-code-one-time-1234567890' })
    expect(new URL(window.location.href).searchParams.has('launchCode')).toBe(false)
    expect(new URL(window.location.href).searchParams.get('sessionId')).toBe(activeSession.id)
    await waitFor(() => expect(api.heartbeatDebugSession).toHaveBeenCalledWith(activeSession.id, expect.objectContaining({ event: 'studio.connected' })))

    await fireEvent.click(screen.getByRole('button', { name: '手工截图' }))
    expect(api.recordDebugSessionEvidence).not.toHaveBeenCalled()
    relayState.options?.onEvidence?.({
      type: 'evidence', commandId: 'command-001', requestId: relayState.requestId, evidenceId: screenshotEvidence.id,
      kind: 'SCREENSHOT', sha256: screenshotEvidence.sha256, objectRef: screenshotEvidence.objectRef, size: 1234,
      metadata: { redacted: true },
    })
    await waitFor(() => expect(api.recordDebugSessionEvidence).toHaveBeenCalledWith(activeSession.id, {
      kind: 'SCREENSHOT',
      sha256: screenshotEvidence.sha256,
      objectRef: screenshotEvidence.objectRef,
      metadata: { redacted: true, relayCommandId: 'command-001', relayEvidenceId: screenshotEvidence.id, size: 1234, source: 'edge.relay' },
    }))
    await waitFor(() => expect(api.heartbeatDebugSession).toHaveBeenCalledWith(activeSession.id, expect.objectContaining({
      event: 'evidence.recorded',
      evidenceRefs: [screenshotEvidence.objectRef],
    })))

    await fireEvent.click(screen.getByRole('button', { name: '结束会话' }))
    await waitFor(() => expect(api.revokeDebugSession).toHaveBeenCalledWith(activeSession.id, {
      reason: 'Studio operator ended the debug session',
    }))
    expect(revokedSession.status).toBe('REVOKED')
  })

  it('keeps runner stage durable and fails closed when backend controls do not exist', async () => {
    render(App, { global: { stubs: { MonacoWorkspace: true } } })
    await screen.findByText('受控会话已连接')
    expect(screen.getAllByText('VALIDATE').length).toBeGreaterThan(0)
    api.heartbeatDebugSession.mockClear()
    await fireEvent.click(screen.getByRole('button', { name: '单步' }))
    expect(screen.getAllByText('VALIDATE').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/后端未提供 单步 控制能力/).length).toBeGreaterThan(0)
    expect(api.heartbeatDebugSession).not.toHaveBeenCalled()
  })

  it('erases the launch code before a rejected exchange can leave it in browser history', async () => {
    api.exchangeDebugSession.mockRejectedValueOnce(new Error('launch code already consumed'))

    render(App, { global: { stubs: { MonacoWorkspace: true } } })

    await waitFor(() => expect(api.exchangeDebugSession).toHaveBeenCalled())
    expect(new URL(window.location.href).searchParams.has('launchCode')).toBe(false)
    expect(new URL(window.location.href).searchParams.get('sessionId')).toBe(activeSession.id)
  })
})
