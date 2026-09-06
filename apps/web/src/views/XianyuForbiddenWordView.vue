<script setup lang="ts">
import { computed, ref } from 'vue'
import { detectForbiddenWords, type ForbiddenHit } from '@/data/xianyu-material-pools'

const text = ref('')
const hits = ref<ForbiddenHit[] | null>(null)

const resultText = computed(() => {
  if (hits.value === null) return ''
  if (hits.value.length === 0) return '未命中高危或风险词。'
  return hits.value.map((item) => `【${item.level}】${item.word}（${item.reason}）`).join('\n')
})

function detect() {
  hits.value = detectForbiddenWords(text.value)
}
</script>

<template>
  <section class="page">
    <div class="card">
      <h2>商品违禁词检测</h2>
      <div class="row top">
        <label class="label" for="xy-foul-text">请输入文案</label>
        <textarea id="xy-foul-text" v-model="text" rows="6" placeholder="请输入文案" />
      </div>
      <div class="footer">
        <button class="primary" type="button" @click="detect">开始检测</button>
      </div>
      <div class="row top">
        <label class="label" for="xy-foul-result">检测结果</label>
        <textarea id="xy-foul-result" :value="resultText" rows="5" readonly />
      </div>
    </div>
    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>
          命中的词按风险等级标色，<span class="danger">高危</span>和<span class="warn">风险</span>的需要处理：
          <p><span class="danger">高危</span>＝闲鱼禁售或引流类（留微信、站外交易、管制刀具、毒品等），基本会被删除降权，建议必改</p>
          <p><span class="warn">风险</span>＝可证伪的虚假主张（国家级/最高级/全网最低/销量第一、国家免检、疾病治疗宣称、高仿假货、诱导中奖），建议改写</p>
        </li>
        <li>违禁词库数量：17136 条，分 22 类（引流联系方式、站外交易、管制刀具、毒品、色情、赌博金融、证件个人信息、野生动植物、烟酒、药品医疗器械、疾病治疗宣称、绝对化用语等）</li>
        <li>闲鱼官方词库不对外公开（发布后由闲鱼服务端校验），本词库按平台规则+广告法整理，检测结果仅供参考，请以闲鱼官方为准</li>
      </ol>
    </div>
  </section>
</template>

<style scoped>
.page { display: grid; gap: 10px; color: #334155; }
.card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; gap: 16px; }
h2 { margin: 0; font-size: 15px; }
.row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: start; }
.label { color: #64748b; font-size: 13px; padding-top: 8px; }
textarea { width: 100%; min-height: 96px; padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 4px; font: inherit; }
.footer { padding-left: 100px; }
.primary { height: 34px; padding: 0 16px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; }
.help { padding: 12px 14px 16px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.danger { color: #dc2626; }
.warn { color: #ea580c; }
</style>
