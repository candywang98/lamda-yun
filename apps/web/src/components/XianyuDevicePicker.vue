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
      <label v-for="device in devices" :key="device.id" class="chip" :class="{ selected: modelValue.includes(device.id), offline: !device.online }">
        <input type="checkbox" :checked="modelValue.includes(device.id)" @change="setIds(toggleId(modelValue, device.id))" />
        <span class="chip-name">{{ deviceLabel(device, showAccount) }}</span>
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
.row { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 14px; align-items: center; }
.row.top { align-items: start; }
.label { color: #0f172a; font-size: 14px; font-weight: 600; padding-top: 8px; }

.chip {
  display: inline-flex; align-items: center; gap: 8px;
  margin: 0 10px 10px 0; padding: 9px 12px;
  border: 1px solid #e2e8f0; border-radius: 10px; background: #fff;
  font-size: 14px; color: #1e293b; cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
}
.chip:hover { border-color: #5eead4; background: #f8fdfc; }
.chip.selected { border-color: #0f766e; background: #f0fdfa; box-shadow: 0 0 0 1px #0f766e inset; }
.chip.offline { color: #64748b; }
.chip input { accent-color: #0f766e; width: 16px; height: 16px; margin: 0; flex: none; }
.chip-name { line-height: 1.4; }
.chip small { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: 999px; font-size: 12px; background: #f1f5f9; color: #64748b; }
.chip small::before { content: ""; width: 6px; height: 6px; border-radius: 999px; background: #94a3b8; }
.chip small.on { background: #dcfce7; color: #15803d; }
.chip small.on::before { background: #22c55e; }

.links { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; margin-top: 2px; color: #0f766e; font-size: 13px; }
.links button { border: 0; background: none; color: #0f766e; padding: 0; font-size: 13px; font-weight: 600; cursor: pointer; }
.links button:hover { text-decoration: underline; }
.count {
  min-width: 24px; height: 24px; padding: 0 8px; border-radius: 999px;
  background: #0f766e; color: #fff; font-size: 12px; font-weight: 700;
  display: inline-grid; place-items: center;
}
.hint { color: #94a3b8; font-size: 13px; padding: 10px 14px; border: 1px dashed #cbd5e1; border-radius: 10px; background: #f8fafc; }

@media (max-width: 720px) {
  .row { grid-template-columns: 1fr; row-gap: 8px; }
  .label { padding-top: 0; }
}
</style>
