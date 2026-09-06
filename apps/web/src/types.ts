export type Role =
  | 'Viewer'
  | 'ContentEditor'
  | 'Publisher'
  | 'Approver'
  | 'AutomationDeveloper'
  | 'DeviceOperator'
  | 'SecurityAdmin'

export type Permission =
  | 'content:write'
  | 'publish:create'
  | 'publish:approve'
  | 'device:operate'
  | 'automation:develop'
  | 'security:admin'

export type Status =
  | 'ONLINE'
  | 'OFFLINE'
  | 'MAINTENANCE'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'QUEUED'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'PARTIAL'
  | 'FAILED'
  | 'UNKNOWN'
  | 'CANCELED'
  | 'PAUSED'
  | 'BLOCKED'
  | 'SUPPORTED'
  | 'CANDIDATE'

export interface Device {
  id: string
  name: string
  status: Status
  android: string
  lamda: string
  app: string
  edge: string
  battery: number | null
  temperature: number | null
  account: string
  capability: string
  lease?: string
  version?: number | null
  maintenance?: boolean
  lastSeenAt?: string | null
  presence?: 'ONLINE' | 'OFFLINE' | 'BOUND_UNSEEN'
  accessibilityEnabled?: boolean | null
  batteryOptimizationIgnored?: boolean | null
  runnerState?: string | null
}

export interface Work {
  id: string
  title: string
  revision: number
  group: string
  status: Status
  author: string
  updatedAt: string
  media: number
}

export interface PublishPlan {
  id: string
  title: string
  status: Status
  creator: string
  approver: string
  targets: number
  succeeded: number
  failed: number
  unknown: number
  schedule: string
  snapshot: string
  automation: string
}

export interface TaskRun {
  id: string
  plan: string
  status: Status
  adapter: string
  targetCount: number
  succeeded: number
  failed: number
  unknown: number
  startedAt: string
  duration: string
  creator: string
  version: string
  step: string
  cancellable: boolean
}

export interface ApkArtifact {
  id: string
  packageName: string
  version: string
  signer: string
  abi: string
  sdk: string
  hash: string
  scan: Status
  permissions: string
  channel: string
}
