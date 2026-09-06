<script setup lang="ts">
import { reactive, ref } from 'vue'
import { loadTagPools, MAX_TAGS_PER_POOL, saveTagPools } from '@/data/xianyu-material-pools'

const pools = reactive<string[][]>(loadTagPools())
const drafts = reactive<string[]>(Array.from({ length: pools.length }, () => ''))
const errorMessage = ref('')
const successMessage = ref('')
const titles = ['一', '二', '三', '四', '五', '六']

function addTag(index: number) {
  const value = drafts[index]!.trim()
  errorMessage.value = ''
  if (!value) return
  if (pools[index]!.includes(value)) {
    errorMessage.value = '该标签已存在'
    return
  }
  if (pools[index]!.length >= MAX_TAGS_PER_POOL) {
    errorMessage.value = '标签数量建议不要超过10个'
    return
  }
  pools[index]!.push(value)
  drafts[index] = ''
}

function removeTag(poolIndex: number, tag: string) {
  pools[poolIndex] = pools[poolIndex]!.filter((item) => item !== tag)
}

function saveAll() {
  saveTagPools(pools.map((pool) => [...pool]))
  successMessage.value = '全部标签池已保存到当前浏览器'
  errorMessage.value = ''
}
</script>

<template>
  <section class="page">
    <div class="card">
      <h2>标签池</h2>
      <div class="grid">
        <div v-for="(pool, index) in pools" :key="index" class="pool">
          <strong>标签池{{ titles[index] }}</strong>
          <div class="box">
            <span v-for="tag in pool" :key="tag" class="tag">
              {{ tag }}
              <button type="button" @click="removeTag(index, tag)">x</button>
            </span>
            <input :id="`tag-draft-${index}`" v-model="drafts[index]" :aria-label="`标签池${titles[index]}`" @keydown.enter.prevent="addTag(index)" />
          </div>
        </div>
      </div>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="ok">{{ successMessage }}</p>
      <button class="primary" type="button" @click="saveAll">保存全部标签池</button>
    </div>
    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>您可在此设置标签池，编辑宝贝的时候可以批量设置图片标签</li>
        <li>输入文字后按回车键生成新标签，标签数量建议不要超过10个</li>
      </ol>
    </div>
  </section>
</template>

<style scoped>
.page { display: grid; gap: 10px; color: #334155; }
.card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; gap: 16px; }
h2 { margin: 0; font-size: 15px; }
.grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; }
.pool { display: grid; gap: 8px; }
.pool strong { font-size: 13px; color: #64748b; font-weight: 600; }
.box { min-height: 92px; border: 1px solid #d1d5db; border-radius: 6px; padding: 8px; display: flex; flex-wrap: wrap; gap: 6px; align-content: flex-start; }
.tag { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 4px; background: #0f766e; color: #fff; font-size: 12px; }
.tag button { border: 0; background: none; color: #fff; padding: 0; }
.box input { flex: 1; min-width: 64px; border: 0; outline: none; font: inherit; }
.primary { width: fit-content; height: 34px; padding: 0 16px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; }
.error { margin: 0; color: #b91c1c; font-size: 13px; }
.ok { margin: 0; color: #166534; font-size: 13px; }
.help { padding: 12px 14px 16px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
@media (max-width: 1100px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
