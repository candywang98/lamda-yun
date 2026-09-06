import { CloudCtlApiClient } from '@cloudctl/api-contracts'

const apiUrl = import.meta.env.VITE_CONTROL_API_URL?.trim() ?? ''
const devAuthEnabled = import.meta.env.VITE_CONTROL_API_DEV_AUTH === 'true'
const tenantId = import.meta.env.VITE_CONTROL_API_DEV_TENANT_ID ?? '00000000-0000-7000-8000-000000001111'

export const controlApiConfigured = apiUrl.length > 0
export const operationsMockEnabled = import.meta.env.DEV && import.meta.env.VITE_OPERATIONS_MOCK_ENABLED === 'true'

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
