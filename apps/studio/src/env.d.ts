/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CONTROL_API_URL?: string
  readonly VITE_CONTROL_API_DEV_AUTH?: string
  readonly VITE_CONTROL_API_DEV_TENANT_ID?: string
  readonly VITE_CONTROL_API_DEV_USER_ID?: string
  readonly VITE_CLOUDCTL_WEB_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
