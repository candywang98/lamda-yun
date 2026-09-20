import type {
  BatchOperationCreate,
  JsonObject,
  OperationCatalogEntry,
  OperationFeatureEntry,
  OperationTask,
  OperationTaskCreate,
} from '@cloudctl/api-contracts'
import { createControlApiClient } from '@/api/control'
import type { OperationConnection } from './business-operation'

export interface OperationDirectory {
  connection: OperationConnection
  features: OperationFeatureEntry[]
  catalogs: OperationCatalogEntry[]
}

export class OperationsMintError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

const UNCONFIGURED = '未配置 Control API，业务表单不可用（不回退示例操作）'

export async function loadOperationDirectory(): Promise<OperationDirectory> {
  const client = createControlApiClient()
  const [features, catalogs] = await Promise.all([
    client.operationFeatures(),
    client.operationCatalog(),
  ])
  return { connection: 'live', features, catalogs }
}

export function unavailableDirectory(connection: OperationConnection): OperationDirectory {
  return { connection, features: [], catalogs: [] }
}

export async function mintBusinessOperation(input: {
  operationKey: string
  featureId: string
  resourceIds: string[]
  parameters: JsonObject
  context: JsonObject
  batch: boolean
  idempotencyKey: string
}): Promise<OperationTask> {
  const client = createControlApiClient()
  if (input.batch) {
    const body: BatchOperationCreate = {
      operationKey: input.operationKey,
      featureId: input.featureId,
      resourceIds: [...input.resourceIds],
      parameters: JSON.parse(JSON.stringify(input.parameters)),
      context: JSON.parse(JSON.stringify(input.context)),
    }
    return client.createBatchOperation(body, input.idempotencyKey)
  }
  const body: OperationTaskCreate = {
    operationKey: input.operationKey,
    featureId: input.featureId,
    resourceId: input.resourceIds[0]!,
    parameters: JSON.parse(JSON.stringify(input.parameters)),
    context: JSON.parse(JSON.stringify(input.context)),
  }
  return client.createOperationTask(body, input.idempotencyKey)
}

export async function fetchOperationTaskDetail(taskId: string): Promise<OperationTask> {
  return createControlApiClient().operationTask(taskId)
}

export function operationsUnconfiguredMessage(): string {
  return UNCONFIGURED
}
