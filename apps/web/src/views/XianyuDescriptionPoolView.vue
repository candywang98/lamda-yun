<script setup lang="ts">
import { reactive, ref } from 'vue'
import {
  downloadCsv,
  loadDescriptionPools,
  saveDescriptionPools,
  type DescriptionItem,
} from '@/data/xianyu-material-pools'

const pools = reactive<DescriptionItem[][]>(loadDescriptionPools())
const adding = ref<number | null>(null)
const draft = ref('')
const successMessage = ref('')

const titles = ['一', '二', '三', '四', '五', '六']

function persist() {
  saveDescriptionPools(pools.map((pool) => [...pool]))
}

function addItem(index: number) {
  adding.value = index
  draft.value = ''
}

function confirmAdd() {
  if (adding.value === null) return
  const text = draft.value.trim()
  if (!text) return
  pools[adding.value]!.push({ id: String(pools[adding.value]!.length + 1).padStart(3, '0'), text })
  persist()
  adding.value = null
  successMessage.value = '描述已添加到当前浏览器'
}

function removeItem(poolIndex: number, itemId: string) {
  pools[poolIndex] = pools[poolIndex]!.filter((item) => item.id !== itemId)
  persist()
}

function exportPool(index: number) {
  downloadCsv(`描述池${titles[index]}.csv`, [['ID', '描述'], ...pools[index]!.map((item) => [item.id, item.text])])
}
</script>

<template>
  <section class="page">
    <div class="card">
      <h2>描述池</h2>
      <p v-if="successMessage" class="ok">{{ successMessage }}</p>
      <div class="grid">
        <div v-for="(pool, index) in pools" :key="index" class="pool">
          <div class="toolbar">
            <button class="primary" type="button" @click="addItem(index)">添加描述池{{ titles[index] }}</button>
            <span class="spacer" />
            <button class="outline" type="button">筛选</button>
            <button class="outline" type="button">还原</button>
            <button class="outline" type="button" @click="exportPool(index)">导出</button>
            <button class="outline" type="button" @click="window.print()">打印</button>
          </div>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>描述</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="pool.length === 0"><td colspan="3" class="empty">暂无描述</td></tr>
              <tr v-for="item in pool" :key="item.id">
                <td>{{ item.id }}</td>
                <td>{{ item.text }}</td>
                <td><button class="link" type="button" @click="removeItem(index, item.id)">✕</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>您可在此设置描述池，发布某鱼宝贝的时候可追加随机描述。若想追加固定描述，可在某描述池中只添加一个描述</li>
      </ol>
    </div>
    <div v-if="adding !== null" class="mask" @click.self="adding = null">
      <div class="modal">
        <h3>添加描述池{{ titles[adding] }}</h3>
        <textarea v-model="draft" rows="5" placeholder="输入描述内容" />
        <div class="modal-actions">
          <button type="button" @click="adding = null">取消</button>
          <button class="primary" type="button" @click="confirmAdd">确定</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page { display: grid; gap: 10px; color: #334155; }
.card, .help, .pool { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; gap: 12px; }
h2 { margin: 0; font-size: 15px; }
.ok { margin: 0; color: #166534; font-size: 13px; }
.grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.pool { padding: 10px; display: grid; gap: 8px; }
.toolbar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.spacer { flex: 1; }
.primary { height: 32px; padding: 0 10px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; }
.outline { height: 28px; padding: 0 8px; border-radius: 4px; border: 1px solid #0f766e; background: #fff; color: #0f766e; font-size: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { padding: 8px 6px; border-bottom: 1px solid #f1f5f9; text-align: left; }
th { color: #64748b; background: #f8fafc; }
.empty { color: #94a3b8; }
.link { border: 0; background: none; color: #0f766e; }
.help { padding: 12px 14px 16px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.mask { position: fixed; inset: 0; background: rgb(15 23 42 / 0.35); display: grid; place-items: center; }
.modal { width: min(420px, 92vw); background: #fff; border-radius: 8px; padding: 16px; display: grid; gap: 10px; }
textarea { width: 100%; min-height: 100px; padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 4px; font: inherit; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
@media (max-width: 1100px) { .grid { grid-template-columns: 1fr; } }
</style>
