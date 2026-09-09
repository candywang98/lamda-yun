import type {
  ApkArtifactCreate,
  ApprovalRequest,
  AutomationPackageCreate,
  AutomationPromotionRequest,
  BatchOperationCreate,
  CommitIntentCreate,
  ContentArchiveRequest,
  ContentCreate,
  ContentGroupCreate,
  ContentGroupView,
  ContentSummary,
  ContentView,
  ContentXianyuDispatchRequest,
  ContentXianyuDispatchResult,
  DeviceCreate,
  DevicePreviewSessionCreate,
  DevicePreviewStatus,
  DebugSession,
  DebugSessionCreate,
  DebugSessionCreateResult,
  DebugSessionDetail,
  DebugSessionEvidence,
  DebugSessionEvidenceCreate,
  DebugSessionExchange,
  DebugSessionExchangeResult,
  DebugSessionHeartbeat,
  DebugSessionRevoke,
  EdgeCreate,
  EventView,
  JsonObject,
  LeaseRequest,
  MaintenanceRequest,
  MediaAssetView,
  MediaCreate,
  MediaUploadCreate,
  MediaUploadGrant,
  PlatformTaskCreate,
  PlatformTaskPause,
  PlatformTaskReconcile,
  PlatformTaskResume,
  PlatformTaskView,
  ProductArchiveRequest,
  ProductBatchDelete,
  ProductBatchUpdateGroup,
  ProductBatchUpdatePrice,
  ProductCreate,
  ProductFilterRequest,
  ProductImportRequest,
  ProductMediaUpdate,
  ProductView,
  ProductUpdate,
  MobileEnrollmentCode,
  MobileEnrollmentCodeCreate,
  MobileTask,
  MobileTaskCreate,
  OperationAuditResult,
  OperationApprovalRequest,
  OperationCancelRequest,
  OperationCatalogEntry,
  OperationFeatureEntry,
  OperationFeatureConfigDraft,
  OperationFeatureConfigDraftUpdate,
  OperationTask,
  OperationTaskCreate,
  OperationTaskFilters,
  ProblemDetails,
  PublishPlanCreate,
  RevisionCreate,
  RoleUpdate,
  SessionInfo,
  SourceConnectionCreate,
  SourceConnectionResponse,
  SourcePreviewResponse,
  SyncErrorResponse,
  SyncRunRequest,
  SyncRunResponse,
  TargetStateUpdate,
  TenantCreate,
  UserCreate,
} from './types.js'

export interface CloudCtlClientOptions {
  baseUrl: string
  accessToken?: () => string | undefined | Promise<string | undefined>
  debugRelayToken?: () => string | undefined
  tenantId?: () => string | undefined
  devIdentity?: () => {
    tenantId: string
    userId: string
    roles: string[]
    mfa?: boolean
  } | undefined
  fetch?: typeof globalThis.fetch
}

export class CloudCtlApiError extends Error {
  constructor(
    readonly status: number,
    readonly problem: ProblemDetails,
  ) {
    super(problem.detail)
    this.name = 'CloudCtlApiError'
  }
}

function responseTextPreview(value: string): string {
  const normalized = value.replace(/\s+/g, ' ').trim()
  if (!normalized) return ''
  return normalized.length > 500 ? `${normalized.slice(0, 497)}...` : normalized
}

function responseProblem(response: Response, payload: unknown, rawBody: string): ProblemDetails {
  const object = payload && typeof payload === 'object' ? payload as Partial<ProblemDetails> : undefined
  const statusLabel = response.statusText.trim()
  const preview = responseTextPreview(rawBody)
  const fallbackDetail = preview
    ? `Request failed with HTTP ${response.status}: ${preview}`
    : `Request failed with HTTP ${response.status}${statusLabel ? ` ${statusLabel}` : ''}`

  return {
    type: typeof object?.type === 'string' ? object.type : 'about:blank',
    title: typeof object?.title === 'string' ? object.title : statusLabel || 'Request failed',
    status: typeof object?.status === 'number' ? object.status : response.status,
    code: typeof object?.code === 'string' ? object.code : `HTTP_${response.status}`,
    detail: typeof object?.detail === 'string' ? object.detail : fallbackDetail,
    correlation_id: typeof object?.correlation_id === 'string'
      ? object.correlation_id
      : response.headers.get('x-request-id') ?? '',
    retryable: typeof object?.retryable === 'boolean' ? object.retryable : response.status >= 500,
    fields: object?.fields && typeof object.fields === 'object' ? object.fields : {},
  }
}

export class CloudCtlApiClient {
  private readonly baseUrl: string
  private readonly fetcher: typeof globalThis.fetch

  constructor(private readonly options: CloudCtlClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, '')
    this.fetcher = options.fetch ?? globalThis.fetch.bind(globalThis)
  }

  session(signal?: AbortSignal): Promise<SessionInfo> {
    return this.request('/api/v1/session', signal ? { signal } : {})
  }

  createTenant(body: TenantCreate): Promise<JsonObject> {
    return this.request('/api/v1/tenants', { method: 'POST', body })
  }

  createUser(body: UserCreate): Promise<JsonObject> {
    return this.request('/api/v1/users', { method: 'POST', body })
  }

  updateUserRoles(userId: string, body: RoleUpdate): Promise<JsonObject> {
    return this.request(`/api/v1/users/${segment(userId)}/roles`, { method: 'PUT', body })
  }

  securityPolicy(): Promise<JsonObject> {
    return this.request('/api/v1/settings/security-policy')
  }

  createEdge(body: EdgeCreate): Promise<JsonObject> {
    return this.request('/api/v1/edges', { method: 'POST', body })
  }

  createDevice(body: DeviceCreate): Promise<JsonObject> {
    return this.request('/api/v1/devices', { method: 'POST', body })
  }

  devices(): Promise<JsonObject[]> {
    return this.request('/api/v1/devices')
  }

  accounts(): Promise<JsonObject[]> {
    return this.request('/api/v1/accounts')
  }

  accountOwnership(accountId: string): Promise<JsonObject> {
    return this.request(`/api/v1/accounts/${segment(accountId)}/ownership`)
  }

  createTaskSchedule(body: JsonObject): Promise<JsonObject> {
    return this.request('/api/v1/task-schedules', { method: 'POST', body })
  }

  taskSchedules(): Promise<JsonObject[]> {
    return this.request('/api/v1/task-schedules')
  }

  fireTaskSchedule(scheduleId: string, body: JsonObject): Promise<JsonObject> {
    return this.request(`/api/v1/task-schedules/${segment(scheduleId)}:fire`, { method: 'POST', body })
  }

  setMaintenance(deviceId: string, body: MaintenanceRequest): Promise<JsonObject> {
    return this.request(`/api/v1/devices/${segment(deviceId)}:maintenance`, {
      method: 'POST',
      body,
    })
  }

  startDevicePreview(deviceId: string, body: DevicePreviewSessionCreate = {}): Promise<DevicePreviewStatus> {
    return this.request(`/api/v1/mobile/devices/${segment(deviceId)}/preview/sessions`, {
      method: 'POST',
      body: {
        ttlSeconds: body.ttlSeconds ?? 120,
        captureIntervalMs: body.captureIntervalMs ?? 2000,
      },
    })
  }

  devicePreview(deviceId: string, signal?: AbortSignal): Promise<DevicePreviewStatus> {
    return this.request(`/api/v1/mobile/devices/${segment(deviceId)}/preview`, signal ? { signal } : {})
  }

  async devicePreviewFrame(
    deviceId: string,
    etag?: string,
    signal?: AbortSignal,
  ): Promise<{ blob: Blob; etag: string | null } | null> {
    const headers = new Headers()
    headers.set('Accept', 'image/jpeg')
    const token = await this.options.accessToken?.()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const tenantId = this.options.tenantId?.()
    if (tenantId) headers.set('X-Tenant-Id', tenantId)
    const devIdentity = this.options.devIdentity?.()
    if (devIdentity) {
      headers.set('X-Tenant-Id', devIdentity.tenantId)
      headers.set('X-User-Id', devIdentity.userId)
      headers.set('X-Roles', devIdentity.roles.join(','))
      headers.set('X-MFA', String(devIdentity.mfa ?? true))
    }
    if (etag) headers.set('If-None-Match', etag)
    const requestInit: RequestInit = { method: 'GET', headers }
    if (signal) requestInit.signal = signal
    const response = await this.fetcher(
      `${this.baseUrl}/api/v1/mobile/devices/${segment(deviceId)}/preview/frame`,
      requestInit,
    )
    if (response.status === 404 || response.status === 304) return null
    if (!response.ok) {
      const payload: unknown = await response.json().catch(() => ({
        type: 'urn:cloudctl:problem:preview_frame',
        title: 'Preview frame failed',
        status: response.status,
        code: 'PREVIEW_FRAME_FAILED',
        detail: 'preview frame request failed',
        correlation_id: '',
        retryable: false,
        fields: {},
      }))
      throw new CloudCtlApiError(response.status, payload as ProblemDetails)
    }
    return { blob: await response.blob(), etag: response.headers.get('ETag') }
  }

  stopDevicePreview(deviceId: string, sessionId: string): Promise<DevicePreviewStatus> {
    return this.request(`/api/v1/mobile/devices/${segment(deviceId)}/preview/sessions/${segment(sessionId)}:stop`, {
      method: 'POST',
    })
  }

  acquireLease(deviceId: string, body: LeaseRequest): Promise<JsonObject> {
    return this.request(`/api/v1/devices/${segment(deviceId)}/leases`, { method: 'POST', body })
  }

  releaseLease(deviceId: string, leaseId: string): Promise<void> {
    return this.request(`/api/v1/devices/${segment(deviceId)}/leases/${segment(leaseId)}`, {
      method: 'DELETE',
    })
  }

  createMedia(body: MediaCreate): Promise<JsonObject> {
    return this.request('/api/v1/media/assets:register', { method: 'POST', body })
  }

  initiateMediaUpload(body: MediaUploadCreate): Promise<MediaUploadGrant> {
    return this.request('/api/v1/media/uploads', { method: 'POST', body })
  }

  completeMediaUpload(uploadId: string): Promise<MediaAssetView> {
    return this.request(`/api/v1/media/uploads/${segment(uploadId)}:complete`, { method: 'POST', body: {} })
  }

  products(): Promise<ProductView[]> {
    return this.request('/api/v1/products')
  }

  product(productId: string): Promise<ProductView> {
    return this.request(`/api/v1/products/${segment(productId)}`)
  }

  createProduct(body: ProductCreate): Promise<ProductView> {
    return this.request('/api/v1/products', { method: 'POST', body })
  }

  updateProduct(productId: string, body: ProductUpdate): Promise<ProductView> {
    return this.request(`/api/v1/products/${segment(productId)}`, { method: 'PUT', body })
  }

  updateProductMedia(productId: string, body: ProductMediaUpdate): Promise<ProductView> {
    return this.request(`/api/v1/products/${segment(productId)}/media`, { method: 'PUT', body })
  }

  archiveProduct(productId: string, body: ProductArchiveRequest): Promise<ProductView> {
    return this.request(`/api/v1/products/${segment(productId)}:archive`, { method: 'POST', body })
  }

  batchUpdateProductPrice(body: ProductBatchUpdatePrice): Promise<{ updated_count: number; product_ids: string[] }> {
    return this.request('/api/v1/products:batch-update-price', { method: 'POST', body })
  }

  batchUpdateProductGroup(body: ProductBatchUpdateGroup): Promise<{ updated_count: number; group_id: string }> {
    return this.request('/api/v1/products:batch-update-group', { method: 'POST', body })
  }

  batchDeleteProducts(body: ProductBatchDelete): Promise<{ archived_count: number; product_ids: string[] }> {
    return this.request('/api/v1/products:batch-delete', { method: 'POST', body })
  }

  importProducts(body: ProductImportRequest): Promise<{ imported_count: number; skipped_count: number; product_ids: string[] }> {
    return this.request('/api/v1/products:import', { method: 'POST', body })
  }

  filterProducts(body: ProductFilterRequest): Promise<ProductView[]> {
    return this.request('/api/v1/products:filter', { method: 'POST', body })
  }

  createContent(body: ContentCreate): Promise<ContentView> {
    return this.request('/api/v1/content', { method: 'POST', body })
  }

  contents(kind?: string): Promise<ContentSummary[]> {
    const query = kind ? `?kind=${encodeURIComponent(kind)}` : ''
    return this.request(`/api/v1/content${query}`)
  }

  content(contentId: string): Promise<ContentView> {
    return this.request(`/api/v1/content/${segment(contentId)}`)
  }

  createRevision(contentId: string, body: RevisionCreate): Promise<ContentView> {
    return this.request(`/api/v1/content/${segment(contentId)}/revisions`, { method: 'POST', body })
  }

  archiveContent(contentId: string, body: ContentArchiveRequest): Promise<ContentView> {
    return this.request(`/api/v1/content/${segment(contentId)}:archive`, { method: 'POST', body })
  }

  createContentGroup(body: ContentGroupCreate): Promise<ContentGroupView> {
    return this.request('/api/v1/content-groups', { method: 'POST', body })
  }

  contentGroups(): Promise<ContentGroupView[]> {
    return this.request('/api/v1/content-groups')
  }

  dispatchContentToXianyu(
    contentId: string,
    body: ContentXianyuDispatchRequest,
    idempotencyKey: string,
  ): Promise<ContentXianyuDispatchResult> {
    return this.request(`/api/v1/content/${segment(contentId)}:dispatch-xianyu`, {
      method: 'POST',
      body,
      headers: { 'Idempotency-Key': idempotencyKey },
    })
  }

  createAutomationPackage(body: AutomationPackageCreate): Promise<JsonObject> {
    return this.request('/api/v1/automation-packages', { method: 'POST', body })
  }

  promoteAutomationPackage(
    versionId: string,
    body: AutomationPromotionRequest,
  ): Promise<JsonObject> {
    return this.request(`/api/v1/automation-packages/${segment(versionId)}:promote`, {
      method: 'POST',
      body,
    })
  }

  createApkArtifact(body: ApkArtifactCreate): Promise<JsonObject> {
    return this.request('/api/v1/apk-artifacts', { method: 'POST', body })
  }

  createPublishPlan(body: PublishPlanCreate, idempotencyKey: string): Promise<JsonObject> {
    return this.request('/api/v1/publish-plans', {
      method: 'POST',
      body,
      headers: { 'Idempotency-Key': idempotencyKey },
    })
  }

  submitPublishPlan(planId: string): Promise<JsonObject> {
    return this.request(`/api/v1/publish-plans/${segment(planId)}:submit`, { method: 'POST' })
  }

  approvePublishPlan(planId: string, body: ApprovalRequest): Promise<JsonObject> {
    return this.request(`/api/v1/publish-plans/${segment(planId)}:approve`, { method: 'POST', body })
  }

  cancelPublishPlan(planId: string): Promise<JsonObject> {
    return this.request(`/api/v1/publish-plans/${segment(planId)}:cancel`, { method: 'POST' })
  }

  publishPlan(planId: string): Promise<JsonObject> {
    return this.request(`/api/v1/publish-plans/${segment(planId)}`)
  }

  createCommitIntent(targetId: string, body: CommitIntentCreate): Promise<JsonObject> {
    return this.request(`/api/v1/publish-targets/${segment(targetId)}/commit-intents`, {
      method: 'POST',
      body,
    })
  }

  updateTargetState(targetId: string, body: TargetStateUpdate): Promise<JsonObject> {
    return this.request(`/api/v1/publish-targets/${segment(targetId)}:state`, {
      method: 'POST',
      body,
    })
  }

  auditEvents(limit = 100): Promise<JsonObject[]> {
    return this.request(`/api/v1/audit-events?limit=${limit}`)
  }

  createMobileEnrollmentCode(body: MobileEnrollmentCodeCreate): Promise<MobileEnrollmentCode> {
    return this.request('/api/v1/mobile/enrollments', { method: 'POST', body })
  }

  mobileTasks(signal?: AbortSignal): Promise<MobileTask[]> {
    return this.request('/api/v1/mobile/tasks', signal ? { signal } : {})
  }

  createMobileTask(body: MobileTaskCreate, idempotencyKey: string): Promise<MobileTask> {
    return this.request('/api/v1/mobile/tasks', {
      method: 'POST',
      body,
      headers: { 'Idempotency-Key': idempotencyKey },
    })
  }

  mobileTask(taskId: string, signal?: AbortSignal): Promise<MobileTask> {
    return this.request(`/api/v1/mobile/tasks/${segment(taskId)}`, signal ? { signal } : {})
  }

  operationCatalog(signal?: AbortSignal): Promise<OperationCatalogEntry[]> {
    return this.request('/api/v1/operations/catalog', signal ? { signal } : {})
  }

  operationFeatures(signal?: AbortSignal): Promise<OperationFeatureEntry[]> {
    return this.request('/api/v1/operations/features', signal ? { signal } : {})
  }

  operationFeatureConfigDraft(featureId: string, signal?: AbortSignal): Promise<OperationFeatureConfigDraft> {
    return this.request(
      `/api/v1/operations/features/${segment(featureId)}/config-draft`,
      signal ? { signal } : {},
    )
  }

  updateOperationFeatureConfigDraft(
    featureId: string,
    body: OperationFeatureConfigDraftUpdate,
  ): Promise<OperationFeatureConfigDraft> {
    return this.request(`/api/v1/operations/features/${segment(featureId)}/config-draft`, {
      method: 'PUT',
      body,
    })
  }

  operationTasks(filters: OperationTaskFilters = {}, signal?: AbortSignal): Promise<OperationTask[]> {
    const query = new URLSearchParams()
    if (filters.module) query.set('module', filters.module)
    if (filters.status) query.set('status', filters.status)
    if (filters.afterId) query.set('afterId', filters.afterId)
    if (filters.limit !== undefined) query.set('limit', String(filters.limit))
    const suffix = query.size ? `?${query}` : ''
    return this.request(`/api/v1/operations/tasks${suffix}`, signal ? { signal } : {})
  }

  createOperationTask(body: OperationTaskCreate, idempotencyKey: string): Promise<OperationTask> {
    return this.request('/api/v1/operations/tasks', {
      method: 'POST',
      body,
      headers: { 'Idempotency-Key': idempotencyKey },
    })
  }

  createBatchOperation(body: BatchOperationCreate, idempotencyKey: string): Promise<OperationTask> {
    return this.request('/api/v1/operations:batch', {
      method: 'POST',
      body,
      headers: { 'Idempotency-Key': idempotencyKey },
    })
  }

  operationTask(taskId: string, signal?: AbortSignal): Promise<OperationTask> {
    return this.request(`/api/v1/operations/tasks/${segment(taskId)}`, signal ? { signal } : {})
  }

  cancelOperationTask(taskId: string, body: OperationCancelRequest): Promise<OperationTask> {
    return this.request(`/api/v1/operations/tasks/${segment(taskId)}:cancel`, { method: 'POST', body })
  }

  approveOperationTask(taskId: string, body: OperationApprovalRequest): Promise<OperationTask> {
    return this.request(`/api/v1/operations/tasks/${segment(taskId)}:approve`, { method: 'POST', body })
  }

  rejectOperationTask(taskId: string, body: OperationApprovalRequest): Promise<OperationTask> {
    return this.request(`/api/v1/operations/tasks/${segment(taskId)}:reject`, { method: 'POST', body })
  }

  operationAuditResult(taskId: string, signal?: AbortSignal): Promise<OperationAuditResult> {
    return this.request(`/api/v1/operations/tasks/${segment(taskId)}/audit-result`, signal ? { signal } : {})
  }

  createDebugSession(body: DebugSessionCreate): Promise<DebugSessionCreateResult> {
    return this.request('/api/v1/debug-sessions', { method: 'POST', body })
  }

  exchangeDebugSession(body: DebugSessionExchange): Promise<DebugSessionExchangeResult> {
    return this.request('/api/v1/debug-sessions:exchange', { method: 'POST', body })
  }

  debugSession(sessionId: string, signal?: AbortSignal): Promise<DebugSessionDetail> {
    return this.request(`/api/v1/debug-sessions/${segment(sessionId)}`, signal ? { signal } : {})
  }

  heartbeatDebugSession(sessionId: string, body: DebugSessionHeartbeat): Promise<DebugSession> {
    return this.request(`/api/v1/debug-sessions/${segment(sessionId)}:heartbeat`, {
      method: 'POST',
      body,
      headers: this.debugRelayHeaders(),
    })
  }

  recordDebugSessionEvidence(sessionId: string, body: DebugSessionEvidenceCreate): Promise<DebugSessionEvidence> {
    return this.request(`/api/v1/debug-sessions/${segment(sessionId)}/evidence`, {
      method: 'POST',
      body,
      headers: this.debugRelayHeaders(),
    })
  }

  revokeDebugSession(sessionId: string, body: DebugSessionRevoke): Promise<DebugSession> {
    return this.request(`/api/v1/debug-sessions/${segment(sessionId)}:revoke`, { method: 'POST', body })
  }

  pollEvents(afterId?: string, limit = 100): Promise<EventView[]> {
    const query = new URLSearchParams({ limit: String(limit) })
    if (afterId) query.set('afterId', afterId)
    return this.request(`/api/v1/events/poll?${query}`)
  }

  eventStreamUrl(): string {
    return `${this.baseUrl}/api/v1/events`
  }

  createSourceConnection(body: SourceConnectionCreate): Promise<SourceConnectionResponse> {
    return this.request('/api/v1/sources/connections', { method: 'POST', body })
  }

  listSourceConnections(signal?: AbortSignal): Promise<SourceConnectionResponse[]> {
    return this.request('/api/v1/sources/connections', signal ? { signal } : {})
  }

  getSourceConnection(connectionId: string, signal?: AbortSignal): Promise<SourceConnectionResponse> {
    return this.request(`/api/v1/sources/connections/${segment(connectionId)}`, signal ? { signal } : {})
  }

  previewSourceConnection(connectionId: string, signal?: AbortSignal): Promise<SourcePreviewResponse> {
    const init: { method: string; signal?: AbortSignal } = { method: 'POST' }
    if (signal) init.signal = signal
    return this.request(`/api/v1/sources/connections/${segment(connectionId)}/preview`, init)
  }

  startSyncRun(connectionId: string, body: SyncRunRequest): Promise<SyncRunResponse> {
    return this.request(`/api/v1/sources/connections/${segment(connectionId)}/sync`, {
      method: 'POST',
      body,
    })
  }

  listSyncRuns(connectionId: string, signal?: AbortSignal): Promise<SyncRunResponse[]> {
    return this.request(`/api/v1/sources/connections/${segment(connectionId)}/runs`, signal ? { signal } : {})
  }

  listSyncErrors(
    connectionId: string,
    options?: { resolved?: boolean; signal?: AbortSignal },
  ): Promise<SyncErrorResponse[]> {
    const query = new URLSearchParams()
    if (options?.resolved !== undefined) query.set('resolved', String(options.resolved))
    const queryString = query.toString()
    const path = `/api/v1/sources/connections/${segment(connectionId)}/errors${queryString ? `?${queryString}` : ''}`
    return this.request(path, options?.signal ? { signal: options.signal } : {})
  }

  listPlatformTasks(options?: {
    after?: string
    limit?: number
    deviceId?: string
    state?: string
    signal?: AbortSignal
  }): Promise<PlatformTaskView[]> {
    const query = new URLSearchParams()
    if (options?.after) query.set('after', options.after)
    if (options?.limit !== undefined) query.set('limit', String(options.limit))
    if (options?.deviceId) query.set('device_id', options.deviceId)
    if (options?.state) query.set('state', options.state)
    const queryString = query.toString()
    const path = `/api/v1/platform-tasks${queryString ? `?${queryString}` : ''}`
    return this.request(path, options?.signal ? { signal: options.signal } : {})
  }

  getPlatformTask(taskId: string, signal?: AbortSignal): Promise<PlatformTaskView> {
    return this.request(`/api/v1/platform-tasks/${segment(taskId)}`, signal ? { signal } : {})
  }

  createPlatformTask(body: PlatformTaskCreate): Promise<PlatformTaskView[]> {
    return this.request('/api/v1/platform-tasks', { method: 'POST', body })
  }

  pausePlatformTask(taskId: string, body: PlatformTaskPause): Promise<PlatformTaskView> {
    return this.request(`/api/v1/platform-tasks/${segment(taskId)}:pause`, { method: 'POST', body })
  }

  resumePlatformTask(taskId: string, body: PlatformTaskResume): Promise<PlatformTaskView> {
    return this.request(`/api/v1/platform-tasks/${segment(taskId)}:resume`, { method: 'POST', body })
  }

  reconcilePlatformTask(taskId: string, body: PlatformTaskReconcile): Promise<PlatformTaskView> {
    return this.request(`/api/v1/platform-tasks/${segment(taskId)}:reconcile`, { method: 'POST', body })
  }

  private debugRelayHeaders(): Record<string, string> {
    const relayToken = this.options.debugRelayToken?.()
    return relayToken ? { 'X-Debug-Relay-Token': relayToken } : {}
  }

  private async request<T>(
    path: string,
    init: {
      method?: string
      body?: unknown
      headers?: Record<string, string>
      signal?: AbortSignal
    } = {},
  ): Promise<T> {
    const headers = new Headers(init.headers)
    headers.set('Accept', 'application/json')
    const token = await this.options.accessToken?.()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const tenantId = this.options.tenantId?.()
    if (tenantId) headers.set('X-Tenant-Id', tenantId)
    const devIdentity = this.options.devIdentity?.()
    if (devIdentity) {
      headers.set('X-Tenant-Id', devIdentity.tenantId)
      headers.set('X-User-Id', devIdentity.userId)
      headers.set('X-Roles', devIdentity.roles.join(','))
      headers.set('X-MFA', String(devIdentity.mfa ?? true))
    }
    if (init.body !== undefined) headers.set('Content-Type', 'application/json')

    const requestInit: RequestInit = {
      method: init.method ?? 'GET',
      headers,
    }
    if (init.body !== undefined) requestInit.body = JSON.stringify(init.body)
    if (init.signal) requestInit.signal = init.signal
    const response = await this.fetcher(`${this.baseUrl}${path}`, requestInit)
    if (response.status === 204) return undefined as T
    const rawBody = await response.text()
    let payload: unknown
    try {
      payload = rawBody ? JSON.parse(rawBody) : undefined
    } catch {
      if (!response.ok) throw new CloudCtlApiError(response.status, responseProblem(response, undefined, rawBody))
      const preview = responseTextPreview(rawBody)
      throw new Error(`Invalid JSON response (HTTP ${response.status})${preview ? `: ${preview}` : ''}`)
    }
    if (!response.ok) throw new CloudCtlApiError(response.status, responseProblem(response, payload, rawBody))
    return payload as T
  }
}

const segment = (value: string): string => encodeURIComponent(value)
