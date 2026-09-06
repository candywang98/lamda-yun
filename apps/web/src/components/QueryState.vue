<script setup lang="ts">
import { AlertCircle, LoaderCircle } from 'lucide-vue-next'
defineProps<{ loading: boolean; error?: Error | null; empty?: boolean; emptyText?: string }>()
</script>

<template>
  <div v-if="loading" class="query-state"><LoaderCircle class="spin" :size="22" /><span>正在加载最新状态…</span></div>
  <div v-else-if="error" class="query-state query-error"><AlertCircle :size="22" /><span>{{ error.message }}</span></div>
  <div v-else-if="empty" class="query-state"><span>{{ emptyText ?? '暂无数据' }}</span></div>
  <slot v-else />
</template>
