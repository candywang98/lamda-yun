import { describe, expect, it, vi } from 'vitest'
import { DebugRelayClient } from '@/api/relay'

class FakeSocket {
  static instances: FakeSocket[] = []
  static OPEN = 1
  readyState = 0
  sent: string[] = []
  onopen?: () => void
  onmessage?: (event: { data: string }) => void
  onerror?: () => void
  onclose?: () => void
  constructor(public readonly url: string) { FakeSocket.instances.push(this) }
  send(value: string) { this.sent.push(value) }
  close() { this.readyState = 3; this.onclose?.() }
  open() { this.readyState = 1; this.onopen?.() }
  message(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) }) }
}

describe('DebugRelayClient', () => {
  it('authenticates in the first frame without leaking token into URL', () => {
    const client = new DebugRelayClient({ url: 'ws://127.0.0.1:7443/debug', token: 'secret-token', sessionId: 'session-1', capabilities: ['input.tap'], WebSocket: FakeSocket as unknown as typeof WebSocket })
    client.connect()
    const socket = FakeSocket.instances.at(-1)!
    expect(socket.url).not.toContain('secret-token')
    socket.open()
    expect(JSON.parse(socket.sent[0])).toEqual({ type: 'debug.auth', sessionId: 'session-1', token: 'secret-token' })
    socket.message({ type: 'auth.ok' })
    expect(client.status).toBe('connected')
  })

  it('consumes frame/layout and gates tap/evidence by capability', () => {
    const onFrame = vi.fn(); const onLayout = vi.fn()
    const client = new DebugRelayClient({ url: 'ws://localhost/relay', token: 'token', sessionId: 's', capabilities: ['input.tap'], WebSocket: FakeSocket as unknown as typeof WebSocket, onFrame, onLayout })
    client.connect(); const socket = FakeSocket.instances.at(-1)!; socket.open(); socket.message({ type: 'ready' })
    socket.message({ type: 'frame', data: 'abc', mimeType: 'image/jpeg' }); socket.message({ type: 'layout', nodes: [{ id: 'root', className: 'android.view.View', bounds: '[0,0][10,10]', depth: 0, centerX: 5, centerY: 5 }] })
    expect(onFrame).toHaveBeenCalledWith(expect.objectContaining({ data: 'abc' })); expect(onLayout).toHaveBeenCalled()
    client.sendTap({ x: 1, y: 2 }); expect(JSON.parse(socket.sent.at(-1)!)).toMatchObject({ type: 'input.tap', x: 1, y: 2 })
    expect(() => client.requestEvidence()).toThrow('evidence.capture')
  })

  it('correlates a real evidence receipt to the request before delivering it', () => {
    const onEvidence = vi.fn()
    const client = new DebugRelayClient({ url: 'ws://localhost/relay', token: 'token', sessionId: 's', capabilities: ['evidence.capture'], WebSocket: FakeSocket as unknown as typeof WebSocket, onEvidence })
    client.connect(); const socket = FakeSocket.instances.at(-1)!; socket.open(); socket.message({ type: 'ready' })
    const requestId = client.requestEvidence('SCREENSHOT')
    expect(JSON.parse(socket.sent.at(-1)!)).toMatchObject({ type: 'evidence.capture', kind: 'SCREENSHOT', requestId })
    socket.message({ type: 'debug.accepted', commandId: 'command-1' })
    socket.message({ type: 'evidence', commandId: 'command-1', evidenceId: 'evidence-1', kind: 'SCREENSHOT', sha256: 'a'.repeat(64), objectRef: 's3://bucket/shot.png' })
    expect(onEvidence).toHaveBeenCalledWith(expect.objectContaining({ commandId: 'command-1', requestId, sha256: 'a'.repeat(64) }))
  })

  it('fails closed for malformed or uncorrelated evidence receipts', () => {
    const onEvidence = vi.fn(); const onStatus = vi.fn()
    const client = new DebugRelayClient({ url: 'ws://localhost/relay', token: 'token', sessionId: 's', capabilities: ['evidence.capture'], WebSocket: FakeSocket as unknown as typeof WebSocket, onEvidence, onStatus })
    client.connect(); const socket = FakeSocket.instances.at(-1)!; socket.open(); socket.message({ type: 'ready' })
    socket.message({ type: 'evidence', commandId: 'unknown', kind: 'SCREENSHOT', sha256: 'a'.repeat(64) })
    expect(onEvidence).not.toHaveBeenCalled()
    expect(onStatus).toHaveBeenLastCalledWith('error', 'invalid relay evidence receipt')
    socket.message({ type: 'evidence', commandId: 'unknown', kind: 'SCREENSHOT', sha256: 'a'.repeat(64), objectRef: 's3://bucket/shot.png' })
    expect(onEvidence).not.toHaveBeenCalled()
    expect(onStatus).toHaveBeenLastCalledWith('error', 'uncorrelated relay evidence receipt')
  })

  it('stops sending after relay expiry or revocation', () => {
    const onStatus = vi.fn()
    const client = new DebugRelayClient({ url: 'ws://127.0.0.1/relay', token: 'token', sessionId: 's', capabilities: ['input.tap'], WebSocket: FakeSocket as unknown as typeof WebSocket, onStatus })
    client.connect(); const socket = FakeSocket.instances.at(-1)!; socket.open(); socket.message({ type: 'ready' }); socket.message({ type: 'revoked' })
    expect(client.status).toBe('revoked'); expect(onStatus).toHaveBeenCalledWith('revoked', expect.any(String)); expect(() => client.sendTap({ x: 1, y: 2 })).toThrow('not connected')
  })

  it('rejects insecure non-loopback relay URLs', () => {
    expect(() => new DebugRelayClient({ url: 'ws://relay.example/debug', token: 't', sessionId: 's', capabilities: [] })).toThrow('loopback')
    expect(() => new DebugRelayClient({ url: 'https://relay.example/debug', token: 't', sessionId: 's', capabilities: [] })).toThrow('ws or wss')
  })
})
