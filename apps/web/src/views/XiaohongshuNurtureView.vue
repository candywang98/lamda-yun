<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import XianyuDevicePicker from '@/components/XianyuDevicePicker.vue'
import {
  CHANNEL_OPTIONS,
  emptyNurtureConfig,
  loadNurtureConfig,
  recordNurtureTask,
  saveNurtureConfig,
} from '@/data/xiaohongshu-nurture'
import { fetchXianyuTaskDevices, type XianyuTaskDevice } from '@/data/xianyu-task-devices'

const form = reactive(emptyNurtureConfig())
const devices = ref<XianyuTaskDevice[]>([])
const errorMessage = ref('')
const successMessage = ref('')

function saveConfig() {
  saveNurtureConfig(form)
  errorMessage.value = ''
  successMessage.value = '配置已保存到当前浏览器'
}

function createTask() {
  errorMessage.value = ''
  successMessage.value = ''
  if (form.deviceIds.length === 0) {
    errorMessage.value = '请先选择执行设备'
    return
  }
  saveNurtureConfig(form)
  recordNurtureTask(form)
  successMessage.value = '已保存养号计划。不会登录小红书，也不会下发到手机。'
}

onMounted(async () => {
  Object.assign(form, loadNurtureConfig())
  devices.value = await fetchXianyuTaskDevices()
  form.deviceIds = form.deviceIds.filter((id) => devices.value.some((item) => item.id === id))
})
</script>

<template>
  <section class="page">
    <div class="card">
      <h2>红薯养号</h2>
      <XianyuDevicePicker v-model="form.deviceIds" :devices="devices" />
      <div class="row">
        <span class="label">浏览类型</span>
        <div>
          <label class="radio" for="xhs-browse-discover"><input id="xhs-browse-discover" v-model="form.browseType" type="radio" value="discover" /> 发现</label>
          <label class="radio" for="xhs-browse-follow"><input id="xhs-browse-follow" v-model="form.browseType" type="radio" value="follow" /> 关注</label>
          <label class="radio" for="xhs-browse-local"><input id="xhs-browse-local" v-model="form.browseType" type="radio" value="local" /> 本地</label>
        </div>
      </div>
      <div class="row">
        <label class="label" for="xhs-channel">频道类型</label>
        <div class="inline">
          <select id="xhs-channel" v-model="form.channel">
            <option v-for="item in CHANNEL_OPTIONS" :key="item" :value="item">{{ item }}</option>
          </select>
          <span class="hint">选择发现后再选择的频道</span>
        </div>
      </div>
      <div class="row">
        <span class="label">适配多开</span>
        <div>
          <label class="radio" for="xhs-multi-off"><input id="xhs-multi-off" v-model="form.multiOpen" type="radio" value="off" /> 关闭</label>
          <label class="radio" for="xhs-multi-on"><input id="xhs-multi-on" v-model="form.multiOpen" type="radio" value="clone" /> 红薯多开</label>
        </div>
      </div>
      <div class="row">
        <label class="label" for="xhs-flip">翻屏次数</label>
        <div class="inline">
          <input id="xhs-flip" v-model.number="form.flipCount" type="number" min="1" />
          <span class="hint">浏览帖子时翻动屏幕的次数</span>
        </div>
      </div>
      <div class="row">
        <label class="label" for="xhs-click">点击概率</label>
        <div class="inline">
          <input id="xhs-click" v-model.number="form.clickRate" type="number" min="0" max="100" />
          <span>%</span>
        </div>
      </div>
      <div class="row">
        <label class="label" for="xhs-like">点赞概率</label>
        <div class="inline">
          <input id="xhs-like" v-model.number="form.likeRate" type="number" min="0" max="100" />
          <span>%</span>
        </div>
      </div>
      <div class="row">
        <label class="label" for="xhs-collect">收藏概率</label>
        <div class="inline">
          <input id="xhs-collect" v-model.number="form.collectRate" type="number" min="0" max="100" />
          <span>%</span>
        </div>
      </div>
      <div class="row">
        <label class="label" for="xhs-comment-rate">评论概率</label>
        <div class="inline">
          <input id="xhs-comment-rate" v-model.number="form.commentRate" type="number" min="0" max="100" />
          <span>%</span>
        </div>
      </div>
      <div class="row top">
        <label class="label" for="xhs-comments">评论内容</label>
        <textarea id="xhs-comments" v-model="form.comments" rows="6" />
      </div>
      <div class="row">
        <label class="label" for="xhs-schedule">执行时间</label>
        <select id="xhs-schedule" v-model="form.schedule">
          <option>立即执行</option>
        </select>
      </div>
      <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok">{{ successMessage }}</p>
      <div class="footer">
        <button class="primary" type="button" @click="createTask">创建任务</button>
        <button class="primary" type="button" @click="saveConfig">保存配置</button>
      </div>
    </div>
    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li><span class="tag">翻屏次数</span> 浏览帖子时翻动屏幕的次数</li>
        <li><span class="tag">点击概率</span> 翻屏后点击帖子的概率（随机点击）</li>
        <li>点赞概率、收藏概率、评论概率 即进入帖子详情页后进行相应操作的概率</li>
        <li><span class="tag">评论内容</span> 支持随机评论，随机内容之间用 # 分割</li>
        <li>如不使用某功能，可将其概率设置为 0</li>
        <li><span class="tag">适配多开</span> 红薯多开运行任务前，请手动切换红薯分身到前屏，暂无法像闲鱼那样选择主副应用</li>
      </ol>
    </div>
  </section>
</template>

<style scoped>
.page { display: grid; gap: 10px; color: #334155; }
.card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; gap: 14px; }
h2 { margin: 0; font-size: 15px; }
.row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: center; }
.row.top { align-items: start; }
.label { color: #64748b; font-size: 13px; padding-top: 6px; }
.radio { display: inline-flex; align-items: center; gap: 6px; margin: 0 12px 8px 0; }
.inline { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
input, select, textarea { height: 34px; padding: 0 10px; border: 1px solid #d1d5db; border-radius: 4px; font: inherit; }
select, input[type='number'] { width: min(280px, 100%); }
textarea { width: min(720px, 100%); height: auto; padding: 10px; resize: vertical; line-height: 1.7; }
.hint { color: #94a3b8; font-size: 12px; }
.footer { padding-left: 100px; display: flex; gap: 10px; }
.primary { height: 34px; padding: 0 16px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; }
.flash { margin: 0; padding-left: 100px; font-size: 13px; }
.flash.error { color: #b91c1c; }
.flash.ok { color: #166534; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.tag { display: inline-block; margin-right: 6px; padding: 0 6px; border-radius: 4px; background: #f1f5f9; color: #475569; }
</style>
