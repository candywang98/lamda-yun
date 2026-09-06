export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[]
export type JsonObject = { [key: string]: JsonValue }

export interface ProblemDetails {
  type: string
  title: string
  status: number
  code: string
  detail: string
  correlation_id: string
  retryable: boolean
  fields: Record<string, string>
}

export interface SessionInfo {
  tenantId: string
  userId: string
  roles: string[]
  mfa: boolean
  requestId: string
}

export interface TenantCreate {
  name: string
}

export interface UserCreate {
  oidcSubject: string
  roles: string[]
}

export interface RoleUpdate {
  roles: string[]
}

export interface EdgeCreate {
  logicalName: string
  certificateFingerprint: string
}

export interface DeviceCreate {
  edgeId: string
  logicalName: string
  androidVersion?: string | null
  lamdaVersion?: string | null
  targetAppVersions?: Record<string, string>
  capabilities?: JsonObject
  labels?: string[]
}

export interface MaintenanceRequest {
  enabled: boolean
  reason: string
  expectedVersion?: number | null
}

export interface LeaseRequest {
  ownerWorkflowId: string
  ttlSeconds?: number
}

export interface MediaCreate {
  sha256: string
  objectKey: string
  contentType: string
  sizeBytes: number
  sourceAssetId?: string | null
  metadata?: JsonObject
}

export interface ProductCreate {
  spuCode: string
  title: string
  description?: string
  category: string
  price: string
  stock: number
  mediaAssetIds?: string[]
  attributes?: JsonObject
}

export interface ProductUpdate extends ProductCreate {
  expectedRevision: number
}

export interface ProductArchiveRequest {
  reason: string
}

export interface ProductMediaUpdateItem {
  mediaAssetId: string
  sortOrder: number
  role: 'cover' | 'detail' | 'video'
}

export interface ProductMediaUpdate {
  expectedRevision: number
  items: ProductMediaUpdateItem[]
}

export interface ProductBatchUpdatePrice {
  productIds: string[]
  price: string
}

export interface ProductBatchUpdateGroup {
  productIds: string[]
  groupId: string
}

export interface ProductBatchDelete {
  productIds: string[]
  reason: string
}

export interface ProductImportItem {
  spuCode: string
  title: string
  description?: string
  category: string
  price: string
  stock: number
  imageUrls?: string[]
  groupId?: string | null
}

export interface ProductImportRequest {
  items: ProductImportItem[]
  groupId?: string | null
}

export interface ProductFilterRequest {
  search?: string | null
  category?: string | null
  groupId?: string | null
  minPrice?: string | null
  maxPrice?: string | null
  status?: 'ACTIVE' | 'ARCHIVED' | 'ALL' | null
}

export interface ProductMediaView extends ProductMediaUpdateItem {}

export interface ProductView {
  id: string
  spuCode: string
  title: string
  description: string
  category: string
  price: string
  stock: number
  status: string
  revision: number
  mediaAssetIds: string[]
  media: ProductMediaView[]
  attributes?: JsonObject
  createdAt: string
  updatedAt?: string
}

export interface ContentCreate {
  title: string
  payload: JsonObject
  groupId?: string | null
}

export interface RevisionCreate {
  payload: JsonObject
  groupId?: string | null
}

export interface ContentRevisionView {
  id: string
  revision_no: number
  payload: JsonObject
  payload_sha256: string
  created_at: string
}

export interface ContentView {
  id: string
  title: string
  status: string
  kind?: string | null
  archivedAt?: string | null
  groupIds: string[]
  revision: ContentRevisionView
}

export interface ContentSummary {
  id: string
  title: string
  status: string
  kind?: string | null
  draftState?: string | null
  latestRevision: number
  groupIds: string[]
  updatedAt?: string
}

export interface ContentGroupView {
  id: string
  name: string
  description?: string | null
  contentIds: string[]
  createdAt?: string
}

export interface ContentGroupCreate {
  name: string
  description?: string | null
}

export interface ContentXianyuDispatchRequest {
  deviceId: string
  listingPrice?: string | null
}

export interface ContentXianyuDispatchResult {
  contentId: string
  revisionId: string
  revisionNo: number
  deviceId: string
  mobileTask: JsonObject
  created: boolean
  tapsPublish: boolean
}

export interface AutomationPackageCreate {
  artifactSha256: string
  manifest: JsonObject
  sbomRef: string
  sbomSha256: string
  signature: string
}

export interface RolloutEvidenceCreate {
  sampleSize: number
  successCount: number
  failureCount: number
  safetyViolations: number
  p95DurationMs: number
}

export interface AutomationPromotionRequest {
  targetPercentage: 5 | 25 | 100
  evidence: RolloutEvidenceCreate
}

export interface ApkFinding {
  ruleId: string
  severity: 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  title: string
}

export interface ApkAnalysisReport {
  keyId: string
  analyzer: string
  analyzerVersion: string
  analyzedAt: string
  artifactSha256: string
  packageName: string
  versionName: string
  versionCode: number
  signatureDigest: string
  minSdk: number
  targetSdk: number
  abis: string[]
  permissions: string[]
  sbomSha256: string
  debuggable: boolean
  usesCleartextTraffic: boolean
  verdict: 'CLEAN' | 'REJECTED' | 'PENDING'
  findings: ApkFinding[]
}

export interface ApkArtifactCreate {
  sha256: string
  packageName: string
  versionName: string
  versionCode: number
  signatureDigest: string
  minSdk: number
  targetSdk: number
  abis: string[]
  permissions: string[]
  sbomRef: string
  sbomSha256: string
  sourceRef: string
  analysisReport: ApkAnalysisReport
  analysisSignature: string
}

export interface PublishPlanCreate {
  contentRevisionId: string
  platform: string
  targets: JsonObject[]
  schedule: JsonObject
  execution: JsonObject
  approvalPolicy: 'NONE' | 'BEFORE_START' | 'BEFORE_COMMIT'
  automationPackageVersionId: string
}

export interface ApprovalRequest {
  decision: 'APPROVED' | 'REJECTED'
  reason?: string | null
}

export interface CommitIntentCreate {
  fencingToken: number
  beforeCommitEvidenceId: string
}

export interface TargetStateUpdate {
  state: string
  detail?: string | null
}

export interface EventView extends JsonObject {
  id: string
  tenantId: string
  type: string
  aggregateType: string
  aggregateId: string
  payload: JsonObject
  occurredAt: string
}

export type OperationTaskStatus = 'PENDING_APPROVAL' | 'REJECTED' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'PARTIAL' | 'FAILED' | 'CANCELED'
export type OperationItemStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'BLOCKED' | 'CANCELED'

export interface OperationCatalogEntry {
  key: string
  module: string
  resourceType: string
  batchAllowed: boolean
  requiredPermission: string
  authorized: boolean
  allowed: boolean
  executorAvailable: boolean
  executionState: 'implemented' | 'contract_only'
  allowedParameters: string[]
  description: string
  risk: 'standard' | 'approval'
  featureIds: string[]
}

export interface OperationFeatureEntry {
  featureId: string
  index: number
  module: string
  moduleLabel: string
  stage: string
  title: string
  mode: 'guide' | 'table' | 'form' | 'assets' | 'insight' | 'settings'
  operationKey: string | null
  policy: 'mapped' | 'unmapped' | 'blocked'
  executionState: 'implemented' | 'contract_only' | 'ui_only' | 'blocked'
  risk: 'standard' | 'approval' | 'blocked'
  authorized: boolean
  allowed: boolean
  executable: boolean
  reason: string
}

export interface OperationFeatureConfigDraft {
  featureId: string
  configuration: JsonObject
  version: number
  exists: boolean
  createdAt: string | null
  updatedAt: string | null
  updatedBy: string | null
}

export interface OperationFeatureConfigDraftUpdate {
  configuration: JsonObject
  expectedVersion: number
}

export interface OperationTaskCreate {
  operationKey: string
  featureId?: string
  resourceId: string
  parameters?: JsonObject
  context?: JsonObject
}

export interface BatchOperationCreate {
  operationKey: string
  featureId?: string
  resourceIds: string[]
  parameters?: JsonObject
  context?: JsonObject
}

export interface OperationTaskItem {
  id: string
  resourceId: string
  status: OperationItemStatus
  errorCode: string | null
  detail: string | null
  evidenceRefs: string[]
  updatedAt: string
}

export interface OperationTask {
  id: string
  tenantId: string
  operationKey: string
  featureId: string | null
  module: string
  requestSha256: string
  requestedBy: string
  status: OperationTaskStatus
  parameters: JsonObject
  context: JsonObject
  risk: 'standard' | 'approval'
  executionState: 'implemented' | 'contract_only'
  executorAvailable: boolean
  totalCount: number
  succeededCount: number
  failedCount: number
  blockedCount: number
  canceledCount: number
  cancelRequested: boolean
  resultSummary: JsonObject
  createdAt: string
  startedAt: string | null
  completedAt: string | null
  approvalDecision: 'APPROVED' | 'REJECTED' | null
  approvalReason: string | null
  approvedBy: string | null
  decidedAt: string | null
  items?: OperationTaskItem[]
}

export interface OperationTaskFilters {
  module?: string
  status?: OperationTaskStatus
  afterId?: string
  limit?: number
}

export interface OperationCancelRequest {
  reason: string
}

export interface OperationApprovalRequest {
  reason: string
}

export interface OperationAuditEvent {
  id: string
  actorType: string
  actorId: string
  action: string
  resourceType: string
  resourceId: string
  requestId: string
  workflowId: string | null
  deviceId: string | null
  edgeId: string | null
  result: string
  beforeHash: string | null
  afterHash: string | null
  metadata: JsonObject
  occurredAt: string
}

export interface OperationAuditResult {
  task: OperationTask
  auditEvents: OperationAuditEvent[]
}

export type DebugSessionStatus = 'PENDING_EXCHANGE' | 'ACTIVE' | 'EXPIRED' | 'REVOKED'
export type DebugCapability =
  | 'view.frame'
  | 'view.layout'
  | 'input.tap'
  | 'input.swipe'
  | 'input.text'
  | 'debug.steps'
  | 'debug.variables'
  | 'evidence.capture'
export type DebugEvidenceKind = 'SCREENSHOT' | 'UI_TREE' | 'STEP' | 'RESULT' | 'DIAGNOSTIC'

export interface DebugSession {
  id: string
  tenantId: string
  edgeId: string
  deviceId: string
  leaseId: string | null
  fencingToken: number | null
  capabilities: DebugCapability[]
  purpose: string
  status: DebugSessionStatus
  createdBy: string
  createdAt: string
  expiresAt: string
  exchangedAt: string | null
  lastHeartbeatAt: string | null
  stage: string | null
  event: string | null
  detail: string | null
  returnUrl: string | null
  revokedAt: string | null
  revokedBy: string | null
  revokeReason: string | null
}

export interface DebugSessionCreate {
  deviceId: string
  capabilities: DebugCapability[]
  ttlSeconds: number
  purpose: string
  returnUrl?: string
}

export interface DebugSessionCreateResult {
  session: DebugSession
  launchCode: string
}

export interface DebugSessionExchange {
  launchCode: string
}

export interface DebugSessionExchangeResult {
  session: DebugSession
  relayToken: string
  relayUrl: string
}

export interface DebugSessionHeartbeat {
  stage: string
  event: string
  detail?: string
  evidenceRefs?: string[]
}

export interface DebugSessionEvidenceCreate {
  kind: DebugEvidenceKind
  sha256: string
  objectRef: string
  metadata?: JsonObject
}

export interface DebugSessionEvidence {
  id: string
  sessionId: string
  kind: DebugEvidenceKind
  sha256: string
  objectRef: string
  metadata: JsonObject
  createdAt: string
}

export interface DebugSessionDetail extends DebugSession {
  evidence: DebugSessionEvidence[]
}

export interface DebugSessionRevoke {
  reason: string
}

export interface DevicePreviewSessionCreate {
  ttlSeconds?: number
  captureIntervalMs?: number
}

export interface DevicePreviewStatus {
  deviceId: string
  sessionId: string | null
  active: boolean
  expiresAt: string | null
  captureIntervalMs: number
  waitingForFrame: boolean
  capturedAt: string | null
  sha256: string | null
  width: number | null
  height: number | null
  contentType: string | null
  hasFrame: boolean
}

export type MobileAutomationAction = 'ui.find' | 'ui.tap' | 'ui.input' | 'ui.wait' | 'ui.screenshot' | 'ui.assert' | 'run.log'
export type MobileLocatorPredicate = 'EXISTS' | 'NOT_EXISTS' | 'ENABLED'

export interface MobileFindStep {
  stepId: string
  action: 'ui.find'
  locatorRef: string
  timeoutMs: number
}

export interface MobileTapStep {
  stepId: string
  action: 'ui.tap'
  locatorRef: string
  postconditionLocatorRef: string
  timeoutMs: number
}

export interface MobileInputStep {
  stepId: string
  action: 'ui.input'
  locatorRef: string
  value: string
  replace: boolean
  sensitive: boolean
  timeoutMs: number
}

export interface MobileWaitStep {
  stepId: string
  action: 'ui.wait'
  locatorRef: string
  condition: MobileLocatorPredicate
  pollMs: number
  timeoutMs: number
}

export interface MobileScreenshotStep {
  stepId: string
  action: 'ui.screenshot'
  label: string
  timeoutMs: number
}

export interface MobileAssertStep {
  stepId: string
  action: 'ui.assert'
  locatorRef: string
  predicate: MobileLocatorPredicate
  timeoutMs: number
}

export interface MobileLogStep {
  stepId: string
  action: 'run.log'
  level: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'
  messageCode: string
  attributes: Record<string, string | number | boolean>
  timeoutMs: number
}

export type MobileAutomationStep =
  | MobileFindStep
  | MobileTapStep
  | MobileInputStep
  | MobileWaitStep
  | MobileScreenshotStep
  | MobileAssertStep
  | MobileLogStep

export interface MobileEnrollmentCodeCreate {
  deviceId: string
  ttlSeconds: number
}

export interface MobileEnrollmentCode {
  enrollmentId: string
  deviceId: string
  code: string
  expiresAt: string
}

export interface MobileTaskCreate {
  deviceId: string
  targetPackage: string
  totalTimeoutMs: number
  steps: MobileAutomationStep[]
}

export type MobileTaskStatus = 'QUEUED' | 'CLAIMED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELED' | 'EXPIRED'

export interface MobileTaskEventView {
  id: string
  taskId: string
  sequence: number
  eventType: 'STEP_STARTED' | 'STEP_SUCCEEDED' | 'STEP_FAILED' | 'EVIDENCE' | 'LOG'
  stepIndex: number | null
  payload: Record<string, string | number | boolean | null>
  occurredAt: string
}

export interface MobileTask {
  id: string
  deviceId: string
  targetPackage: string
  totalTimeoutMs: number
  steps: MobileAutomationStep[]
  status: MobileTaskStatus
  leaseId: string | null
  leaseExpiresAt: string | null
  attempt: number
  lastSequence: number
  currentStep: number | null
  result: Record<string, string | number | boolean | null>
  errorCode: string | null
  detail: string | null
  createdAt?: string
  startedAt?: string | null
  completedAt?: string | null
  events?: MobileTaskEventView[]
}

// Source connection types
export interface SourceConnectionCreate {
  connection_name: string
  source_kind: string
  entity_kind: string
  config: JsonObject
  secret_ref?: string | null
  mapping_version: string
}

export interface SourceConnectionResponse {
  id: string
  tenant_id: string
  connection_name: string
  source_kind: string
  entity_kind: string
  config: JsonObject
  secret_ref?: string | null
  mapping_version: string
  status: string
  last_test_at?: string | null
  last_test_result?: string | null
  created_at: string
  created_by: string
}

export interface SourcePreviewResponse {
  valid_records: number
  invalid_records: number
  total_read: number
  sample_valid: JsonObject[]
  sample_invalid: Array<{
    raw: JsonObject
    errors: string[]
  }>
}

export interface SyncRunRequest {
  run_mode: 'full' | 'incremental'
}

export interface SyncRunResponse {
  id: string
  tenant_id: string
  connection_id: string
  run_mode: string
  status: string
  started_at: string
  completed_at?: string | null
  cursor_before?: string | null
  cursor_after?: string | null
  records_read: number
  records_created: number
  records_updated: number
  records_failed: number
  error_summary?: string | null
}

export interface SyncErrorResponse {
  id: string
  sync_run_id: string
  connection_id: string
  external_id: string
  error_code?: string | null
  error_message: string
  field_name?: string | null
  record_snapshot: JsonObject
  retry_count: number
  created_at: string
  resolved_at?: string | null
}
