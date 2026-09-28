<script setup lang="ts">
import type { Component } from 'vue'
import type { Permission } from '@/types'
import { useSessionStore } from '@/stores/session'

defineProps<{ permission: Permission; label: string; icon?: Component; kind?: 'primary' | 'danger' | 'secondary'; title?: string; disabled?: boolean }>()
const emit = defineEmits<{ click: [] }>()
const session = useSessionStore()
</script>

<template>
  <button
    class="button"
    :class="`button-${kind ?? 'secondary'}`"
    :disabled="disabled || !session.can(permission)"
    :title="title ?? (!session.can(permission) ? '当前身份没有此操作权限' : undefined)"
    @click="!disabled && session.can(permission) && emit('click')"
  >
    <component :is="icon" v-if="icon" :size="16" />{{ label }}
  </button>
</template>
