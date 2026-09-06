<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<template>
  <section class="page">
    <div class="card">
      <h2>{{ title }}</h2>
      <p>闲鱼已下线帖子相关能力，本入口不再使用。</p>
    </div>
  </section>
</template>

<style scoped>
.page { display: grid; gap: 10px; color: #334155; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px 18px 20px; }
h2 { margin: 0 0 8px; font-size: 15px; }
p { margin: 0; color: #64748b; font-size: 13px; }
</style>
