import type { RunnerStage, UiNode } from '@/types'

const stageOrder: RunnerStage[] = ['VALIDATE', 'PREFLIGHT', 'PREPARE', 'BEFORE_COMMIT', 'COMMIT_INTENT_WRITTEN', 'COMMIT_ONCE', 'RECONCILE', 'CLEANUP']

export function generateLocator(node: UiNode) {
  if (node.resourceId) return `locator(resource_id="${node.resourceId}")`
  if (node.text) return `locator(text="${node.text}")`
  if (node.description) return `locator(description="${node.description}")`
  return `locator(name="${node.id}", review_required=True)  # fallback，不生成坐标脚本`
}

export function canReplay(stage: RunnerStage) {
  return stageOrder.indexOf(stage) < stageOrder.indexOf('COMMIT_INTENT_WRITTEN')
}

export function nextStage(stage: RunnerStage): RunnerStage {
  return stageOrder[Math.min(stageOrder.indexOf(stage) + 1, stageOrder.length - 1)]
}

export function canSafelyCancel(stage: RunnerStage) {
  return stage !== 'COMMIT_ONCE'
}
