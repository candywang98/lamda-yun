<script setup lang="ts">
import { computed } from 'vue'
import { deviceLabel, invertSelection, toggleId, type XianyuTaskDevice } from '@/data/xianyu-task-devices'

const props = withDefaults(defineProps<{
  devices: XianyuTaskDevice[]
  modelValue: string[]
  showAccount?: boolean
}>(), { showAccount: false })

const emit = defineEmits<{ 'update:modelValue': [string[]] }>()

const selectedCount = computed(() => props.modelValue.filter((id) => props.devices.some((item) => item.id === id)).length)

function setIds(ids: string[]) {
  emit('update:modelValue', ids)
}
</script>

<template>
  <div class="row top">
    <span class="label">执行设备</span>
    <div>
      <div v-if="devices.length === 0" class="hint">当前没有已接入设备。接入 Companion 后会出现在这里。</div>
      <label v-for="device in devices" :key="device.id" class="chip">
        <input type="checkbox" :checked="modelValue.includes(device.id)" @change="setIds(toggleId(modelValue, device.id))" />
        {{ deviceLabel(device, showAccount) }}
        <small :class="device.online ? 'on' : 'off'">{{ device.online ? '在线' : '离线' }}</small>
      </label>
      <div class="links">
        <button type="button" @click="setIds(invertSelection(modelValue, devices.map((item) => item.id)))">全选/反选设备</button>
        <button type="button" @click="setIds(devices.filter((item) => item.online).map((item) => item.id))">全选在线设备</button>
        <button type="button" @click="setIds([])">全部取消选择</button>
        <span class="count">{{ selectedCount }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: center; }
.row.top { align-items: start; }
.label { color: #64748b; font-size: 13px; padding-top: 6px; }
.chip { display: inline-flex; align-items: center; gap: 6px; margin: 0 12px 8px 0; padding: 4px 8px; border: 1px solid #e5e7eb; border-radius: 6px; }
.chip small { padding: 0 6px; border-radius: 4px; font-size: 11px; background: #f1f5f9; }
.chip small.on { background: #dcfce7; color: #166534; }
.chip small.off { color: #64748b; }
.links { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 6px; color: #0f766e; font-size: 13px; }
.links button { border: 0; background: none; color: #0f766e; padding: 0; }
.count { min-width: 22px; height: 22px; padding: 0 6px; border-radius: 4px; background: #f1f5f9; color: #334155; text-align: center; }
.hint { color: #94a3b8; font-size: 12px; }
</style>
