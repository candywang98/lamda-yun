import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders } from '@/api/control'

// Local DTOs frozen at recipe-version/20260909.1. Shared generated clients are Root-owned.
export interface LocalRecipePackage {
  apiVersion: 'cloudctl.recipe/v1'
  kind: 'LocalRecipePackage'
  manifest: {
    id: string
    version: string
    hash: string
    signingKeyId: string
    minEngineVersion: number
    platform: string
    app: string
    commandTypes: string[]
  }
  graph: Record<string, unknown>
  signature: { algorithm: 'Ed25519'; keyId: string; digest: string }
}

export interface RecipeDeployment {
  id: string
  deviceId: string
  commandType: string
  status: 'PUBLISHED' | 'REVOKED'
  previousVersionId: string | null
  idempotencyKey: string
  publishedBy: string | null
  createdAt: string | null
  updatedAt: string | null
}

export interface RecipeVersion {
  id: string
  versionId: string
  name: string
  version: string
  artifactSha256: string
  signingKeyId: string
  createdAt: string | null
  package: LocalRecipePackage
  deployments: RecipeDeployment[]
}

export interface RecipePublishRequest {
  targetDeviceIds: string[]
  idempotencyKey: string
}

export interface RecipeRollbackRequest extends RecipePublishRequest {
  expectedCurrentVersionId: string
}

export class RecipeApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'RecipeApiError'
  }
}

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

// Only a format check for operator feedback. Trust, hash, signature and engine validation belong to the API.
export function parseRecipePackage(text: string): LocalRecipePackage {
  let value: unknown
  try { value = JSON.parse(text) } catch { throw new Error('文件不是有效的 JSON') }
  if (!object(value) || value.apiVersion !== 'cloudctl.recipe/v1' || value.kind !== 'LocalRecipePackage'
    || !object(value.manifest) || !object(value.graph) || !object(value.signature)) {
    throw new Error('请选择完整的已签名 LocalRecipePackage JSON 文件')
  }
  const manifest = value.manifest
  const signature = value.signature
  if (!['id', 'version', 'hash', 'signingKeyId', 'platform', 'app'].every((key) => typeof manifest[key] === 'string' && manifest[key])
    || !Number.isInteger(manifest.minEngineVersion) || Number(manifest.minEngineVersion) < 1
    || !Array.isArray(manifest.commandTypes) || !manifest.commandTypes.length
    || !manifest.commandTypes.every((command) => typeof command === 'string' && command.length > 0)
    || signature.algorithm !== 'Ed25519' || typeof signature.keyId !== 'string' || !signature.keyId
    || typeof signature.digest !== 'string' || !signature.digest) {
    throw new Error('签名包缺少有效的清单、引擎版本或 Ed25519 签名')
  }
  return value as unknown as LocalRecipePackage
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  if (!controlApiConfigured) throw new Error('未配置 Control API，无法管理 Recipe 版本')
  const headers = new Headers(controlApiHeaders())
  headers.set('Accept', 'application/json')
  if (body !== undefined) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${controlApiBaseUrl()}/api/v1/recipes${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers,
    credentials: 'same-origin',
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const text = await response.text()
  let payload: unknown
  try { payload = text ? JSON.parse(text) : null } catch {
    throw new RecipeApiError(response.status, `Recipe API 返回无效 JSON（HTTP ${response.status}）`)
  }
  if (!response.ok) {
    const detail = object(payload) && typeof payload.detail === 'string' ? payload.detail : '请求失败'
    const guidance = response.status === 409 ? '版本状态冲突，请刷新后重新确认。'
      : response.status === 401 || response.status === 403 ? '登录失效或缺少 recipe.publish 权限。' : ''
    throw new RecipeApiError(response.status, `${guidance}${detail}（HTTP ${response.status}）`)
  }
  return payload as T
}

function decodeVersion(value: unknown): RecipeVersion {
  if (!object(value)
    || !['id', 'versionId', 'name', 'version', 'artifactSha256', 'signingKeyId'].every((key) => typeof value[key] === 'string' && value[key])
    || !Array.isArray(value.deployments)
    || !value.deployments.every((row) => object(row)
      && ['id', 'deviceId', 'commandType', 'idempotencyKey'].every((key) => typeof row[key] === 'string' && row[key])
      && ['PUBLISHED', 'REVOKED'].includes(String(row.status))
      && (row.previousVersionId === null || typeof row.previousVersionId === 'string'))) {
    throw new Error('Recipe 版本响应格式错误，请刷新后重试')
  }
  parseRecipePackage(JSON.stringify(value.package))
  return value as unknown as RecipeVersion
}

export const recipeApi = {
  async catalog(): Promise<RecipeVersion[]> {
    const result = await request<{ items: RecipeVersion[] }>('')
    if (!result || !Array.isArray(result.items)) throw new Error('Recipe 目录响应格式错误')
    return result.items.map(decodeVersion)
  },
  detail: async (versionId: string) => decodeVersion(await request<unknown>(`/${encodeURIComponent(versionId)}`)),
  register: (signedPackage: LocalRecipePackage) => request<RecipeVersion>('', signedPackage),
  publish: (versionId: string, body: RecipePublishRequest) => request<RecipeVersion>(`/${encodeURIComponent(versionId)}:publish`, body),
  rollback: (versionId: string, body: RecipeRollbackRequest) => request<RecipeVersion>(`/${encodeURIComponent(versionId)}:rollback`, body),
}

export function deploymentHistory(catalog: RecipeVersion[], deviceId: string) {
  return catalog.flatMap((version) => version.deployments
    .filter((deployment) => deployment.deviceId === deviceId)
    .map((deployment) => ({ version, deployment })))
    .sort((a, b) => (b.deployment.createdAt ?? '').localeCompare(a.deployment.createdAt ?? ''))
}

// The rollback API has one expected version for all commands in a manifest.
// Offer a candidate only when every command has history and the same unambiguous active version.
export function rollbackExpectedVersion(catalog: RecipeVersion[], deviceId: string, target: RecipeVersion): string | null {
  if (!deviceId) return null
  const history = deploymentHistory(catalog, deviceId)
  const currentIds = new Set<string>()
  for (const command of target.package.manifest.commandTypes) {
    if (!history.some((row) => row.version.versionId === target.versionId && row.deployment.commandType === command)) return null
    const active = history.filter((row) => row.deployment.commandType === command && row.deployment.status === 'PUBLISHED')
    if (active.length !== 1 || active[0].version.versionId === target.versionId) return null
    currentIds.add(active[0].version.versionId)
  }
  return currentIds.size === 1 ? [...currentIds][0] : null
}
