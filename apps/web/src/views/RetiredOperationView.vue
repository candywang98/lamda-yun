<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<template>
  <section class="page">
    <div class="card">
      <h2>{{ title }}</h2>
      <p>该入口保留在一期目录中，等待真机可用性验证（T102），不得静默删除。</p>
      <p>当前状态：<strong>AVAILABILITY_PENDING</strong>。平台若不提供对应页面，将记录 NOT_SUPPORTED + reason，而不是当作已下线永久剔除。</p>
    </div>
  </section>
</template>

<style scoped>
.page { display: grid; gap: 10px; color: #334155; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px 18px 20px; }
h2 { margin: 0 0 8px; font-size: 15px; }
p { margin: 0 0 8px; color: #64748b; font-size: 13px; }
</style>
