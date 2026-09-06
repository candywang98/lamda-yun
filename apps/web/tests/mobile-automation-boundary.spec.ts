import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const viewPath = resolve(process.cwd(), 'src/views/OperationsView.vue')
const clientPath = resolve(process.cwd(), '../../packages/api-contracts/typescript/src/client.ts')
const typesPath = resolve(process.cwd(), '../../packages/api-contracts/typescript/src/types.ts')

describe('mobile automation production boundary', () => {
  it('enrolls devices from the operations workbench via Control API only', () => {
    const view = readFileSync(viewPath, 'utf8')
    const client = readFileSync(clientPath, 'utf8')

    expect(view).toContain("from '@/api/control'")
    expect(view).toContain('createMobileEnrollmentCode')
    expect(view).not.toContain("from '@/api/client'")
    expect(view).not.toMatch(/EdgeClient|EDGE_API_PATH|localhost:65000|127\.0\.0\.1:65000|usb:/i)
    expect(client).toContain("'/api/v1/mobile/enrollments'")
    expect(client).toContain("'/api/v1/mobile/tasks'")
    expect(client).toContain('`/api/v1/mobile/tasks/${segment(taskId)}`')
  })

  it('keeps the task action list closed and excludes arbitrary execution primitives', () => {
    const types = readFileSync(typesPath, 'utf8')
    expect(types).toContain("action: 'ui.find'")
    expect(types).toContain("action: 'ui.tap'")
    expect(types).toContain("action: 'ui.input'")
    expect(types).toContain("action: 'ui.wait'")
    expect(types).toContain("action: 'ui.screenshot'")
    expect(types).toContain("action: 'ui.assert'")
    expect(types).toContain("action: 'run.log'")
    expect(types).not.toMatch(/action:\s*['"](?:shell|adb|exec|command|coordinate|swipe)['"]/i)
  })
})
