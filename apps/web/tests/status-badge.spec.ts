import { render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'
import StatusBadge from '@/components/StatusBadge.vue'

describe('StatusBadge', () => {
  it('keeps UNKNOWN distinct from ordinary failures', () => {
    const { container } = render(StatusBadge, { props: { status: 'UNKNOWN' } })
    expect(screen.getByText('结果未知')).toBeTruthy()
    expect(container.querySelector('[data-status="UNKNOWN"]')?.classList.contains('status-unknown')).toBe(true)
  })

  it('uses the localized cancellation label', () => {
    render(StatusBadge, { props: { status: 'CANCELED' } })
    expect(screen.getByText('已取消')).toBeTruthy()
  })
})
