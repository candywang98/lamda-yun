import { createControlApiClient } from '@/api/control'
import { requireApiMode } from '@/api/runtime-mode'

export async function listAccounts() {
  requireApiMode('读取账号')
  return createControlApiClient().accounts()
}

export async function getAccountOwnership(accountId: string) {
  requireApiMode('读取账号历史归属')
  return createControlApiClient().accountOwnership(accountId)
}
