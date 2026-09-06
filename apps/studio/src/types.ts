export type RunnerStage = 'VALIDATE' | 'PREFLIGHT' | 'PREPARE' | 'BEFORE_COMMIT' | 'COMMIT_INTENT_WRITTEN' | 'COMMIT_ONCE' | 'RECONCILE' | 'CLEANUP'

export interface UiNode {
  id: string
  className: string
  resourceId?: string
  text?: string
  description?: string
  bounds: string
  depth: number
  clickable?: boolean
  centerX?: number
  centerY?: number
}

export interface StudioLog {
  time: string
  level: 'INFO' | 'WARN' | 'AUDIT'
  event: string
  detail: string
}
