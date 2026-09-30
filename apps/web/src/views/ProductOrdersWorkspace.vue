<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import ProductManagementView from '@/views/ProductManagementView.vue'
import OrdersView from '@/views/OrdersView.vue'

const route = useRoute()
const ordersActive = computed(() => route.query.tab === 'orders')
const productPath = '/operations/product-management/product-management-01'
</script>

<template>
  <div>
    <nav class="product-tabs" aria-label="商品管理视图">
      <RouterLink :to="productPath" :aria-current="!ordersActive ? 'page' : undefined" :class="{ active: !ordersActive }">商品列表</RouterLink>
      <RouterLink :to="{ path: productPath, query: { tab: 'orders' } }" :aria-current="ordersActive ? 'page' : undefined" :class="{ active: ordersActive }">已同步订单</RouterLink>
    </nav>
    <OrdersView v-if="ordersActive" />
    <ProductManagementView v-else />
  </div>
</template>

<style scoped>
.product-tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--yy-line, #d8dee6); margin-bottom: 16px; }
.product-tabs a { padding: 10px 16px; color: inherit; text-decoration: none; border-bottom: 2px solid transparent; }
.product-tabs a.active { color: #0f766e; border-bottom-color: #0f766e; font-weight: 600; }
</style>
