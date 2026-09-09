import type { RecipeVersion } from '@/api/recipes'

// Software-only HTTP/UI fixture: recipe-version/20260909.1. Not a trusted production signature.
export function recipeFixture(version = '2.0.0', status: 'PUBLISHED' | 'REVOKED' = 'PUBLISHED'): RecipeVersion {
  const id = `version-${version}`
  return {
    id, versionId: id, name: '设备探测', version, artifactSha256: 'a'.repeat(64), signingKeyId: 'test-signing-key', createdAt: '2026-09-09T10:00:00Z',
    package: {
      apiVersion: 'cloudctl.recipe/v1', kind: 'LocalRecipePackage',
      manifest: { id: 'device-probe', version, hash: 'a'.repeat(64), signingKeyId: 'test-signing-key', minEngineVersion: 2, platform: 'companion', app: 'com.company.cloudctl.companion', commandTypes: ['device.probe_capabilities.v1'] },
      graph: { startStateId: 'probe', maxIterations: 8, maxDurationMs: 30000, states: [{ stateId: 'probe', action: 'log', onSuccess: 'SUCCEEDED', terminal: true }] },
      signature: { algorithm: 'Ed25519', keyId: 'test-signing-key', digest: 'software-test-only' },
    },
    deployments: [{ id: `deployment-${version}`, deviceId: 'device-1', commandType: 'device.probe_capabilities.v1', status, previousVersionId: version === '2.0.0' ? 'version-1.0.0' : null, idempotencyKey: `key-${version}`, publishedBy: 'operator-persisted', createdAt: '2026-09-09T10:05:00Z', updatedAt: '2026-09-09T10:06:00Z' }],
  }
}
