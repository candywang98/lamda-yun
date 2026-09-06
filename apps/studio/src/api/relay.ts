import type { DebugCapability } from '@cloudctl/api-contracts'
import type { UiNode } from '@/types'
export type RelayStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'expired' | 'revoked' | 'error'
export interface RelayFrame { type: 'frame'; data: string; mimeType?: string; width?: number; height?: number; sequence?: number }
export interface RelayLayout { type: 'layout'; nodes: UiNode[]; sequence?: number }
export interface RelayEvidence { type: 'evidence'; commandId: string; requestId: string; evidenceId?: string; kind: string; sha256: string; objectRef: string; size?: number; metadata?: Record<string, unknown> }
export interface RelayClientOptions { url: string; token: string; sessionId: string; capabilities: readonly DebugCapability[] | readonly string[]; WebSocket?: typeof WebSocket; onStatus?: (status: RelayStatus, detail?: string) => void; onFrame?: (frame: RelayFrame) => void; onLayout?: (layout: RelayLayout) => void; onEvidence?: (evidence: RelayEvidence) => void; onMessage?: (message: Record<string, unknown>) => void }
type RelayMessage = Record<string, unknown> & { type?: string }
function isLoopback(hostname: string) { return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1' || hostname === '[::1]' }
export class DebugRelayClient {
  private readonly options: RelayClientOptions; private readonly WebSocketCtor: typeof WebSocket; private socket: WebSocket | null = null; private statusValue: RelayStatus = 'idle'; private closedByCaller = false; private readonly awaitingAcceptance: string[] = []; private readonly commandRequests = new Map<string, string>()
  constructor(options: RelayClientOptions) { this.options = options; this.WebSocketCtor = options.WebSocket ?? globalThis.WebSocket; this.validateUrl(options.url); if (!options.token.trim()) throw new Error('relay token is required'); if (!options.sessionId.trim()) throw new Error('relay session is required') }
  get status() { return this.statusValue }
  connect() { if (this.statusValue === 'connecting' || this.statusValue === 'connected') return; if (!this.WebSocketCtor) throw new Error('WebSocket is not available in this environment'); this.closedByCaller = false; this.setStatus('connecting'); const socket = new this.WebSocketCtor(this.options.url); this.socket = socket; socket.onopen = () => { socket.send(JSON.stringify({ type: 'debug.auth', sessionId: this.options.sessionId, token: this.options.token })) }; socket.onmessage = (event) => this.handleMessage(event.data); socket.onerror = () => this.setStatus('error', 'relay transport error'); socket.onclose = () => { this.socket = null; if (!this.closedByCaller && this.statusValue !== 'expired' && this.statusValue !== 'revoked') this.setStatus('disconnected') } }
  close(reason = 'studio closed relay') { this.closedByCaller = true; this.statusValue = 'disconnected'; this.options.onStatus?.('disconnected', reason); const socket = this.socket; this.socket = null; if (socket && socket.readyState < 2) socket.close(1000, reason.slice(0, 120)) }
  sendTap(input: { x: number; y: number; locator?: string }) { this.sendCapability('input.tap', { type: 'input.tap', ...input }) }
  requestFrame() { this.sendCapability('view.frame', { type: 'view.frame' }) }
  requestLayout() { this.sendCapability('view.layout', { type: 'view.layout' }) }
  requestEvidence(kind: 'SCREENSHOT' | 'UI_TREE' = 'SCREENSHOT') { return this.sendCapability('evidence.capture', { type: 'evidence.capture', kind }) }
  private sendCapability(capability: string, message: RelayMessage) { if (!(this.options.capabilities as readonly string[]).includes(capability)) throw new Error(`${capability} is not granted for this debug session`); if (this.statusValue !== 'connected' || !this.socket || this.socket.readyState !== 1) throw new Error('relay is not connected'); const requestId = crypto.randomUUID(); this.awaitingAcceptance.push(requestId); this.socket.send(JSON.stringify({ ...message, sessionId: this.options.sessionId, requestId })); return requestId }
  private handleMessage(raw: unknown) { let message: RelayMessage; try { message = typeof raw === 'string' ? JSON.parse(raw) as RelayMessage : JSON.parse(new TextDecoder().decode(raw as ArrayBuffer)) as RelayMessage } catch { this.setStatus('error', 'invalid relay message'); return }; this.options.onMessage?.(message); switch (message.type) { case 'auth.ok': case 'ready': this.setStatus('connected'); break; case 'debug.accepted': this.acceptCommand(message); break; case 'frame': if (typeof message.data === 'string') this.options.onFrame?.(message as unknown as RelayFrame); break; case 'layout': if (Array.isArray(message.nodes) && message.nodes.every(isUiNode)) this.options.onLayout?.(message as unknown as RelayLayout); else this.setStatus('error', 'invalid relay layout'); break; case 'evidence': this.receiveEvidence(message); break; case 'expired': this.terminate('expired', 'debug session expired'); break; case 'revoked': this.terminate('revoked', 'debug session revoked'); break; case 'auth.error': this.terminate('error', typeof message.detail === 'string' ? message.detail : 'relay authentication rejected'); break } }
  private acceptCommand(message: RelayMessage) { if (typeof message.commandId !== 'string' || !message.commandId) { this.setStatus('error', 'invalid relay command acceptance'); return }; const requestId = this.awaitingAcceptance.shift(); if (!requestId) { this.setStatus('error', 'uncorrelated relay command acceptance'); return }; this.commandRequests.set(message.commandId, requestId) }
  private receiveEvidence(message: RelayMessage) { if (!isRelayEvidence(message)) { this.setStatus('error', 'invalid relay evidence receipt'); return }; const requestId = this.commandRequests.get(message.commandId); if (!requestId) { this.setStatus('error', 'uncorrelated relay evidence receipt'); return }; this.commandRequests.delete(message.commandId); this.options.onEvidence?.({ ...message, requestId }) }
  private terminate(status: 'expired' | 'revoked' | 'error', detail: string) { this.closedByCaller = true; this.statusValue = status; this.options.onStatus?.(status, detail); const socket = this.socket; this.socket = null; if (socket && socket.readyState < 2) socket.close(1000, status) }
  private setStatus(status: RelayStatus, detail?: string) { this.statusValue = status; this.options.onStatus?.(status, detail) }
  private validateUrl(value: string) { let parsed: URL; try { parsed = new URL(value) } catch { throw new Error('relay URL is invalid') }; const dev = import.meta.env?.DEV ?? false; if (parsed.protocol !== 'wss:' && parsed.protocol !== 'ws:') throw new Error('relay URL must use ws or wss'); if (parsed.protocol === 'ws:' && !(dev && isLoopback(parsed.hostname))) throw new Error('insecure ws relay is permitted only on loopback during development'); if (parsed.search || parsed.hash) throw new Error('relay URL must not contain query or fragment') }
}

function isRelayEvidence(value: RelayMessage): value is RelayMessage & Omit<RelayEvidence, 'requestId'> {
  return value.type === 'evidence'
    && typeof value.commandId === 'string'
    && typeof value.kind === 'string'
    && typeof value.sha256 === 'string'
    && /^[a-f0-9]{64}$/i.test(value.sha256)
    && typeof value.objectRef === 'string'
    && value.objectRef.length > 0
}

function isUiNode(value: unknown): value is UiNode {
  if (!value || typeof value !== 'object') return false
  const node = value as Record<string, unknown>
  return typeof node.id === 'string'
    && typeof node.className === 'string'
    && typeof node.bounds === 'string'
    && Number.isInteger(node.depth)
    && (node.centerX === undefined || Number.isInteger(node.centerX))
    && (node.centerY === undefined || Number.isInteger(node.centerY))
}
