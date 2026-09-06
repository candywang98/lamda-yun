/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CONTROL_API_URL?: string
  readonly VITE_CONTROL_API_DEV_AUTH?: string
  readonly VITE_CONTROL_API_DEV_TENANT_ID?: string
  readonly VITE_OPERATIONS_MOCK_ENABLED?: string
  readonly VITE_STUDIO_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
