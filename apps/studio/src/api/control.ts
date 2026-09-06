import { CloudCtlApiClient } from '@cloudctl/api-contracts'

const apiUrl = import.meta.env.VITE_CONTROL_API_URL?.trim() ?? ''
const devAuthEnabled = import.meta.env.VITE_CONTROL_API_DEV_AUTH === 'true'
const tenantId = import.meta.env.VITE_CONTROL_API_DEV_TENANT_ID ?? '00000000-0000-7000-8000-000000001111'
const userId = import.meta.env.VITE_CONTROL_API_DEV_USER_ID ?? '00000000-0000-7000-8000-000000002206'

export const studioControlApiConfigured = apiUrl.length > 0

export function createStudioControlApiClient(relayToken: () => string | undefined) {
  return new CloudCtlApiClient({
    baseUrl: apiUrl,
    debugRelayToken: relayToken,
    devIdentity: devAuthEnabled
      ? () => ({ tenantId, userId, roles: ['device_operator'], mfa: true })
      : undefined,
  })
}
