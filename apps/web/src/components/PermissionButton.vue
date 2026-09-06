<script setup lang="ts">
import type { Component } from 'vue'
import type { Permission } from '@/types'

defineProps<{ permission: Permission; label: string; icon?: Component; kind?: 'primary' | 'danger' | 'secondary'; title?: string; disabled?: boolean }>()
const emit = defineEmits<{ click: [] }>()
</script>

<template>
  <button
    class="button"
    :class="`button-${kind ?? 'secondary'}`"
    :disabled="disabled"
    :title="title"
    @click="emit('click')"
  >
    <component :is="icon" v-if="icon" :size="16" />{{ label }}
  </button>
</template>
