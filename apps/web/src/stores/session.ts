import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { Permission, Role } from '@/types'

export const useSessionStore = defineStore('session', () => {
  const role = ref<Role>('SecurityAdmin')
  const user = ref({ id: 'user-local', name: '本机', tenant: '个人' })
  const sidebarOpen = ref(false)

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function can(_permission: Permission) {
    // Development stub: all permissions granted
    return true
  }

  function setRole(nextRole: Role) {
    role.value = nextRole
  }

  return { role, user, sidebarOpen, can, setRole }
})
