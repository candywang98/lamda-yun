<script setup lang="ts">
import { computed, ref } from 'vue'
import { Ellipsis, RotateCcw, RefreshCw } from 'lucide-vue-next'
import type { ImCategory, ImMessage } from '@/api/im'
import { categoryLabel, classificationSource, classificationVersion, IM_CATEGORIES } from './classification'

const props = defineProps<{ message: ImMessage; canEdit: boolean; busy: boolean }>()
const emit = defineEmits<{
  classify: [category: ImCategory | null]
  reclassify: []
}>()
const menuOpen = ref(false)
const classification = computed(() => props.message.classification)
const validVersion = computed(() => classificationVersion(classification.value) !== null)
const rawScore = computed(() => {
  const score = classification.value?.confidence
  return typeof score === 'number' && Number.isFinite(score) ? String(score) : null
})

function choose(category: ImCategory | null) {
  menuOpen.value = false
  emit('classify', category)
}

function reclassify() {
  menuOpen.value = false
  emit('reclassify')
}
</script>

<template>
  <div v-if="message.direction === 'IN'" class="im-classification" :aria-busy="busy">
    <div class="im-classification-line">
      <span class="im-category" :data-category="classification?.category ?? 'UNKNOWN'">
        {{ categoryLabel(classification?.category) }}
      </span>
      <span>来源：{{ classificationSource(classification) }}</span>
      <span v-if="classification?.ruleCode">规则：{{ classification.ruleCode }}</span>
      <span v-if="classification?.predictedCategory">模型预测：{{ categoryLabel(classification.predictedCategory) }}</span>
      <span v-if="rawScore !== null" title="模型原始分数，非实测准确率">模型原始分数：{{ rawScore }}</span>
      <span v-if="classification?.modelStatus">模型状态：{{ classification.modelStatus }}</span>
      <span v-if="classification?.status">状态：{{ classification.status }}</span>
      <button
        v-if="canEdit"
        type="button"
        class="yy-btn im-classification-trigger"
        title="修改消息分类"
        aria-label="修改消息分类"
        :aria-expanded="menuOpen"
        :aria-controls="`classification-menu-${message.id}`"
        :disabled="busy || !validVersion"
        @click="menuOpen = !menuOpen"
      >
        <Ellipsis :size="16" aria-hidden="true" />
      </button>
      <span v-if="busy" role="status">分类更新中…</span>
    </div>
    <div
      v-if="menuOpen && canEdit"
      :id="`classification-menu-${message.id}`"
      class="im-classification-options"
      role="group"
      aria-label="消息分类操作"
      @keydown.esc.stop="menuOpen = false"
    >
      <button
        v-for="option in IM_CATEGORIES"
        :key="option.key"
        type="button"
        class="yy-btn"
        :disabled="busy || !validVersion"
        @click="choose(option.key)"
      >{{ option.label }}</button>
      <button type="button" class="yy-btn" :disabled="busy || !validVersion" @click="choose(null)">
        <RotateCcw :size="14" aria-hidden="true" />恢复自动
      </button>
      <button type="button" class="yy-btn" :disabled="busy || !validVersion" @click="reclassify">
        <RefreshCw :size="14" aria-hidden="true" />重新分类
      </button>
    </div>
  </div>
</template>

<style scoped>
.im-classification { font-size: 11px; color: #64748b; overflow-wrap: anywhere; }
.im-classification-line, .im-classification-options { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.im-category { border: 1px solid #cbd5e1; border-radius: 8px; padding: 1px 6px; color: #475569; }
.im-category[data-category='HUMAN_MESSAGE'] { border-color: #a7f3d0; color: #065f46; }
.im-category[data-category='SYSTEM_NOTICE'], .im-category[data-category='PROMOTION'] { border-color: #fecdd3; color: #9f1239; }
.im-category[data-category='UNKNOWN'] { border-color: #fde68a; color: #92400e; }
.im-classification-trigger { width: 28px; height: 28px; padding: 0; justify-content: center; }
.im-classification-options { margin-top: 6px; }
.im-classification-options .yy-btn { font-size: 12px; min-height: 28px; padding: 4px 8px; gap: 4px; }
</style>
