<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { resolveMediaPreviewUrl } from '@/api/media-assets'

const props = withDefaults(
  defineProps<{
    assetId: string
    alt?: string
    size?: number
  }>(),
  { size: 42 },
)

const src = ref('')
let requestId = 0
const boxSize = computed(() => `${props.size}px`)

watch(
  () => props.assetId,
  async (assetId) => {
    const current = ++requestId
    src.value = ''
    if (!assetId) return
    try {
      const next = await resolveMediaPreviewUrl(assetId)
      if (current === requestId) src.value = next
    } catch {
      if (current === requestId) src.value = ''
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  requestId += 1
})
</script>

<template>
  <img v-if="src" :src="src" :alt="alt ?? ''" />
  <span v-else class="placeholder" aria-hidden="true" />
</template>

<style scoped>
img,
.placeholder {
  width: v-bind(boxSize);
  height: v-bind(boxSize);
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
  display: block;
  background: #f8fafc;
}
.placeholder {
  background: #f1f5f9;
}
</style>
