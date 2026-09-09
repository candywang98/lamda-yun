import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { SessionInfo } from '@cloudctl/api-contracts'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { operationsMockEnabled } from '@/api/runtime-mode'
import type { Permission, Role } from '@/types'

const ROLE_PERMISSIONS: Record<string, Permission[]> = {
  viewer: ['content.read', 'device.read'],
  content_editor: ['content.read', 'content.write', 'content:write', 'data.delete'],
  publisher: ['content.read', 'publish.create', 'publish:create', 'task.create'],
  approver: ['publish.approve', 'publish:approve', 'device.read'],
  automation_developer: ['automation.manage', 'automation:develop', 'recipe.publish', 'device.read'],
  device_operator: ['device.read', 'device.control', 'device:operate', 'task.create'],
  security_admin: [
    'content.read',
    'content.write',
    'content:write',
    'publish.create',
    'publish:create',
    'publish.approve',
    'publish:approve',
    'device.read',
    'device.control',
    'device:operate',
    'task.create',
    'recipe.publish',
    'data.delete',
    'automation.manage',
    'automation:develop',
    'security:admin',
  ],
}

const FRONTEND_TO_API_ROLE: Record<Role, string> = {
  Viewer: 'viewer',
  ContentEditor: 'content_editor',
  Publisher: 'publisher',
  Approver: 'approver',
  AutomationDeveloper: 'automation_developer',
  DeviceOperator: 'device_operator',
  SecurityAdmin: 'security_admin',
}

function displayRole(apiRole: string): Role {
  const mapping: Record<string, Role> = {
    viewer: 'Viewer',
    content_editor: 'ContentEditor',
    publisher: 'Publisher',
    approver: 'Approver',
    automation_developer: 'AutomationDeveloper',
    device_operator: 'DeviceOperator',
    security_admin: 'SecurityAdmin',
  }
  return mapping[apiRole] ?? 'Viewer'
}

export const useSessionStore = defineStore('session', () => {
  const role = ref<Role>('Viewer')
  const user = ref({ id: '', name: '未登录', tenant: '' })
  const permissions = ref<Permission[]>([])
  const session = ref<SessionInfo | null>(null)
  const loaded = ref(false)
  const loadError = ref('')
  const sidebarOpen = ref(false)

  const permissionSet = computed(() => new Set(permissions.value))

  function can(permission: Permission) {
    if (!loaded.value && operationsMockEnabled && !controlApiConfigured) {
      return true
    }
    return permissionSet.value.has(permission)
  }

  function applySession(info: SessionInfo) {
    session.value = info
    user.value = { id: info.userId, name: info.userId.slice(0, 8), tenant: info.tenantId }
    const merged = new Set<Permission>()
    for (const apiRole of info.roles) {
      for (const item of ROLE_PERMISSIONS[apiRole] ?? []) merged.add(item)
    }
    permissions.value = [...merged]
    role.value = displayRole(info.roles[0] ?? 'viewer')
    loaded.value = true
    loadError.value = ''
  }

  async function loadSession() {
    if (!controlApiConfigured) {
      if (operationsMockEnabled) {
        role.value = 'SecurityAdmin'
        permissions.value = ROLE_PERMISSIONS.security_admin
        user.value = { id: 'user-local', name: '本机', tenant: '个人' }
        loaded.value = true
        return
      }
      loadError.value = '未配置 Control API，无法加载真实登录态'
      loaded.value = true
      permissions.value = []
      return
    }
    const info = await createControlApiClient().session()
    applySession(info)
  }

  function setRole(nextRole: Role) {
    if (!operationsMockEnabled) return
    role.value = nextRole
    permissions.value = ROLE_PERMISSIONS[FRONTEND_TO_API_ROLE[nextRole]] ?? []
  }

  return { role, user, sidebarOpen, can, setRole, loadSession, applySession, loaded, loadError, permissions, session }
})
