<script setup lang="ts">
import type { Component } from 'vue'
defineProps<{ label: string; value: string; detail: string; tone?: 'good' | 'warn' | 'bad' | 'neutral'; icon: Component }>()
</script>

<template>
  <article class="metric-card" :class="`metric-${tone ?? 'neutral'}`">
    <div class="metric-top"><span>{{ label }}</span><component :is="icon" :size="17" /></div>
    <strong>{{ value }}</strong>
    <small>{{ detail }}</small>
  </article>
</template>
