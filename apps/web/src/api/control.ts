import { CloudCtlApiClient } from '@cloudctl/api-contracts'
import { controlApiBaseUrl, controlApiConfigured, operationsMockEnabled } from '@/api/runtime-mode'

export { controlApiBaseUrl, controlApiConfigured, operationsMockEnabled }

const apiUrl = controlApiBaseUrl()
const devAuthEnabled = import.meta.env.VITE_CONTROL_API_DEV_AUTH === 'true'
const tenantId = import.meta.env.VITE_CONTROL_API_DEV_TENANT_ID ?? '00000000-0000-7000-8000-000000001111'

export function controlApiHeaders(): HeadersInit {
  if (!devAuthEnabled) return {}
  return {
    'X-Tenant-Id': tenantId,
    'X-User-Id': '00000000-0000-7000-8000-000000002207',
    'X-Roles': 'security_admin',
    'X-MFA': 'true',
  }
}

export function createControlApiClient() {
  return new CloudCtlApiClient({
    baseUrl: apiUrl,
    devIdentity: devAuthEnabled
      ? () => ({
          tenantId,
          userId: '00000000-0000-7000-8000-000000002207',
          roles: ['security_admin'],
          mfa: true,
        })
      : undefined,
  })
}
