<script setup lang="ts">
import PageHeader from '@/components/PageHeader.vue'
import { displaySettingItems } from '@/data/display-settings'
import { isRetiredOperation, operationModules } from '@/data/operations-catalog'
import { useDisplaySettings } from '@/stores/display-settings'

const display = useDisplaySettings()
</script>

<template>
  <PageHeader title="显示设置" description="关掉大模块或其中的小入口后，侧栏和功能目录不再显示它们，方便精简和逐个调试。选择保存在当前浏览器。" />

  <section class="panel yy-workbench">
    <div class="yy-workbench-head">
      <h3>模块与入口</h3>
      <div class="page-actions">
        <span class="cell-sub">显示 {{ display.visibleModuleCount }} / {{ operationModules.length }} 个模块 · {{ display.visibleOperationCount }} 个入口</span>
        <button class="button" type="button" @click="display.showAllModules()">全部显示</button>
      </div>
    </div>
    <div class="yy-module-settings">
      <section v-for="module in operationModules" :key="module.id" class="yy-module-setting">
        <label class="yy-module-setting-head">
          <input :aria-label="module.label" type="checkbox" :checked="display.moduleVisible(module.id)" @change="display.setModuleVisible(module.id, ($event.target as HTMLInputElement).checked)" />
          <strong>{{ module.label }}</strong>
          <small>{{ module.operations.filter((item) => !isRetiredOperation(item.id)).length }} 个入口</small>
        </label>
        <div class="yy-operation-settings">
          <label v-for="operation in module.operations.filter((item) => !isRetiredOperation(item.id))" :key="operation.id">
            <input :aria-label="`${module.label} / ${operation.title}`" type="checkbox" :checked="display.operationVisible(operation.id, module.id)" @change="display.setOperationVisible(operation.id, module.id, ($event.target as HTMLInputElement).checked)" />
            {{ operation.title }}
          </label>
        </div>
      </section>
    </div>
  </section>

  <section class="panel yy-workbench">
    <div class="yy-workbench-head">
      <h3>功能页额外展示</h3>
      <div class="page-actions">
        <button class="button" type="button" @click="display.showAll()">全部显示</button>
        <button class="button" type="button" @click="display.hideAll()">全部隐藏</button>
      </div>
    </div>
    <ul class="yy-display-list">
      <li v-for="item in displaySettingItems" :key="item.id">
        <label class="operation-toggle">
          <input :aria-label="item.label" type="checkbox" :checked="display.visible(item.id)" @change="display.setVisible(item.id, ($event.target as HTMLInputElement).checked)" />
          <span>{{ display.visible(item.id) ? '显示' : '不显示' }}</span>
        </label>
        <div>
          <strong>{{ item.label }}</strong>
          <small>{{ item.detail }}</small>
        </div>
      </li>
    </ul>
  </section>
</template>
