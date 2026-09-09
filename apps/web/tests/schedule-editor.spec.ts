import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ScheduleEditor, { type ScheduleDraft } from '@/components/ScheduleEditor.vue'

describe('ScheduleEditor', () => {
  it('rejects empty and past onceAt', async () => {
    const wrapper = mount(ScheduleEditor, {
      props: {
        modelValue: {
          kind: 'ONCE',
          timezone: 'Asia/Shanghai',
          onceAt: '',
          rrule: 'FREQ=DAILY;INTERVAL=1',
          missPolicy: 'QUEUE_ONE',
          startDeadlineMinutes: 30,
        } satisfies ScheduleDraft,
      },
    })
    expect((wrapper.vm as { validate: () => boolean }).validate()).toBe(false)
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[role="alert"]').text()).toContain('预约时间不能为空')
    await wrapper.setProps({
      modelValue: {
        kind: 'ONCE',
        timezone: 'Asia/Shanghai',
        onceAt: '2000-01-01T00:00',
        rrule: 'FREQ=DAILY;INTERVAL=1',
        missPolicy: 'QUEUE_ONE',
        startDeadlineMinutes: 30,
      },
    })
    expect((wrapper.vm as { validate: () => boolean }).validate()).toBe(false)
  })

  it('shows next three recurring times and batch is independent tasks', () => {
    const wrapper = mount(ScheduleEditor, {
      props: {
        deviceCount: 10,
        accountLabel: '闲鱼甲',
        modelValue: {
          kind: 'RECURRING',
          timezone: 'Asia/Shanghai',
          onceAt: '',
          rrule: 'FREQ=DAILY;INTERVAL=1',
          missPolicy: 'QUEUE_ONE',
          startDeadlineMinutes: 30,
        },
      },
    })
    expect(wrapper.get('[data-testid="schedule-next"]').text()).toMatch(/T/)
    expect(wrapper.text()).toContain('设备数：10')
    expect(wrapper.text()).toContain('没有优先级')
  })
})
