import { describe, expect, it } from 'vitest'
import { deviceLabel } from '@/data/listing-info-collect'

describe('listing info collect labels', () => {
  it('renders device name with bound account', () => {
    expect(deviceLabel({ id: '1', name: '11', account: 'xy920065163305', online: false })).toBe('11(xy920065163305)')
    expect(deviceLabel({ id: '2', name: 'LE2100', account: '', online: false })).toBe('LE2100')
  })
})
