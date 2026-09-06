<script setup lang="ts">
defineProps<{ title: string; description?: string; kicker?: string }>()
</script>

<template>
  <div class="page-header">
    <div>
      <span v-if="kicker" class="eyebrow">{{ kicker }}</span>
      <h2>{{ title }}</h2>
      <p v-if="description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-actions"><slot name="actions" /></div>
  </div>
</template>
