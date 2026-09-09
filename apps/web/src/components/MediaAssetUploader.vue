<script setup lang="ts">
import { computed, ref } from 'vue'
import { uploadMediaFile } from '@/api/media-assets'

const props = withDefaults(defineProps<{
  accept?: string
  multiple?: boolean
  disabled?: boolean
  label?: string
}>(), {
  accept: 'image/*,video/mp4',
  multiple: true,
  disabled: false,
  label: '上传到媒体库',
})

const emit = defineEmits<{
  uploaded: [assets: Array<{ id: string; contentType: string; name: string }>]
  error: [message: string]
}>()

const input = ref<HTMLInputElement | null>(null)
const busy = ref(false)
const lastError = ref('')

const buttonLabel = computed(() => (busy.value ? '上传中…' : props.label))

async function onPick(event: Event) {
  const target = event.target as HTMLInputElement
  const files = [...(target.files ?? [])]
  target.value = ''
  if (files.length === 0) return
  busy.value = true
  lastError.value = ''
  try {
    const assets = []
    for (const file of files) {
      const asset = await uploadMediaFile(file, { originalName: file.name })
      assets.push({ id: asset.id, contentType: asset.contentType, name: file.name })
    }
    emit('uploaded', assets)
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    lastError.value = message
    emit('error', message)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="uploader">
    <button type="button" :disabled="disabled || busy" @click="input?.click()">{{ buttonLabel }}</button>
    <input ref="input" class="hidden" type="file" :accept="accept" :multiple="multiple" @change="onPick">
    <small v-if="lastError" class="error">{{ lastError }}</small>
  </div>
</template>

<style scoped>
.uploader { display: grid; gap: 6px; }
.hidden { display: none; }
.error { color: #b91c1c; }
</style>
