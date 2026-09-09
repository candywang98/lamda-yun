<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import ScheduleEditor, { type ScheduleDraft } from '@/components/ScheduleEditor.vue'
import XianyuDevicePicker from '@/components/XianyuDevicePicker.vue'
import {
  emptySimpleConfig,
  loadSimpleConfig,
  recordSimpleTask,
  saveSimpleConfig,
  type XianyuSimpleKind,
} from '@/data/xianyu-simple-tasks'
import { fetchXianyuTaskDevices, type XianyuTaskDevice } from '@/data/xianyu-task-devices'

const props = defineProps<{ kind: XianyuSimpleKind }>()
const router = useRouter()
const form = reactive(emptySimpleConfig())
const devices = ref<XianyuTaskDevice[]>([])
const errorMessage = ref('')
const successMessage = ref('')
const schedule = ref<ScheduleDraft>({
  kind: 'IMMEDIATE',
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai',
  onceAt: '',
  rrule: 'FREQ=DAILY;INTERVAL=1',
  missPolicy: 'QUEUE_ONE',
  startDeadlineMinutes: 30,
})
const scheduleEditor = ref<{ validate: () => boolean } | null>(null)

const copy = computed(() => {
  if (props.kind === 'polish') {
    return {
      title: '某鱼擦亮商品',
      intervalLabel: '擦亮间隔',
      success: '已保存擦亮计划。不会登录闲鱼替你点擦亮。',
      help: [
        '每个闲鱼每天可擦亮一次（助手是模拟手动操作，是运行在闲鱼规则之下的）',
        '仅当设备在线时，才能创建定时执行任务和每天重复执行的任务',
      ],
    }
  }
  if (props.kind === 'shelf-up') {
    return {
      title: '闲鱼上架全部商品',
      intervalLabel: '上架间隔',
      success: '已保存上架计划。不会登录闲鱼替你点上架。',
      help: [
        '上架所有已下架商品，注意不要跟发布商品功能混淆',
        '仅当设备在线时，才能创建定时执行任务和每天重复执行的任务',
      ],
    }
  }
  if (props.kind === 'shelf-down') {
    return {
      title: '闲鱼下架商品',
      intervalLabel: '下架间隔',
      success: '已保存下架计划。不会登录闲鱼替你点下架。',
      help: [
        '曝光量、浏览量、想要数、关键词四项都开启时，满足其中一项即下架（或关系）。0 或不填表示该项不启用。',
        '仅当设备在线时，才能创建定时执行任务和每天重复执行的任务',
      ],
    }
  }
  if (props.kind === 'delete-goods') {
    return {
      title: '闲鱼删除下架商品',
      intervalLabel: '删除间隔',
      success: '已保存删除计划。不会登录闲鱼替你删商品。',
      help: [
        '该任务可删除已下架的闲鱼商品，删除时可能会从最底部删除，这样在删除过程中，顶部的商品将保持原位，耐心等待删除结束即可。',
        '仅当设备在线时，才能创建定时执行任务和每天重复执行的任务',
      ],
    }
  }
  return {
    title: '绑定闲鱼',
    intervalLabel: '',
    success: '已保存绑定计划。不会登录闲鱼抓取会员名。',
    help: [
      '该任务用来采集您的闲鱼名、圈子、宝贝数、卖出数、销售额、粉丝数、曝光量，屏幕是否可点击，输入法坐标等信息，采集后可在 设备列表 查看数据',
      '新设备会自动运行一次本任务，如果设备更换了闲鱼号或调整了手机屏幕分辨率或换了输入法版本、输入法设置，则需要重新运行本任务',
      "执行过绑定闲鱼任务的设备名后面会显示某鱼会员名，未执行过的会显示'未初始化'",
      '有极少数手机初始化闲鱼时无法打开宝贝列表、无法获取某鱼会员名，遇到此类问题您可手动填写会员名以跳过获取会员名 但跳过后该手机涉及到通过Activity打开页面的功能都无法操作，比如要打开宝贝列表的功能、鱼币抵扣功能',
      '仅当设备在线时，才能创建定时执行任务和每天重复执行的任务',
    ],
  }
})

function restore() {
  Object.assign(form, loadSimpleConfig(props.kind))
}

function saveConfig() {
  saveSimpleConfig(props.kind, form)
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
  saveSimpleConfig(props.kind, form)
  recordSimpleTask(props.kind, form)
  successMessage.value = copy.value.success
}

onMounted(async () => {
  restore()
  devices.value = await fetchXianyuTaskDevices()
  form.deviceIds = form.deviceIds.filter((id) => devices.value.some((item) => item.id === id))
})
</script>

<template>
  <section class="page">
    <div class="card">
      <header class="card-head">
        <span class="card-mark" aria-hidden="true"></span>
        <div>
          <h2>{{ copy.title }}</h2>
          <p class="card-sub">配置任务参数并选择执行设备，创建后按队列顺序执行</p>
        </div>
      </header>
      <div v-if="kind === 'shelf-down'" class="banner">请先阅读页面底部的使用说明，符合条件的商品才会被下架，0表示不启用！</div>
      <div v-if="kind === 'bind'" class="banner danger">注意：新设备首次使用会自动“绑定闲鱼”。若更换账号、修改分辨率或更换输入法（含版本/设置变更），需重新运行绑定任务，否则可能导致输入文字异常。</div>
      <XianyuDevicePicker v-model="form.deviceIds" :devices="devices" :show-account="kind === 'bind'" />
      <div class="row">
        <span class="label">执行应用</span>
        <div>
          <label class="radio" :for="`${kind}-app-main`"><input :id="`${kind}-app-main`" v-model="form.app" type="radio" value="main" /> 主闲鱼</label>
          <p class="hint">一期每设备仅绑定一个闲鱼账号，副闲鱼/先主后副已禁用。</p>
        </div>
      </div>
      <template v-if="kind === 'shelf-down'">
        <div class="row">
          <label class="label" for="xy-exposure">曝光量</label>
          <div class="inline">
            <input id="xy-exposure" v-model.number="form.exposure" type="number" min="0" />
            <span class="hint">下架小于此数值的，0表示不启用</span>
          </div>
        </div>
        <div class="row">
          <label class="label" for="xy-views">浏览量</label>
          <div class="inline">
            <input id="xy-views" v-model.number="form.views" type="number" min="0" />
            <span class="hint">下架小于此数值的，0表示不启用</span>
          </div>
        </div>
        <div class="row">
          <label class="label" for="xy-wants">想要数</label>
          <div class="inline">
            <input id="xy-wants" v-model.number="form.wants" type="number" min="0" />
            <span class="hint">下架小于此数值的，0表示不启用</span>
          </div>
        </div>
        <div class="row">
          <label class="label" for="xy-keyword">关键词</label>
          <div class="inline">
            <input id="xy-keyword" v-model="form.keyword" />
            <span class="hint">下架标题包含此关键词的，不填则不启用</span>
          </div>
        </div>
        <div class="row">
          <label class="label" for="xy-target">操作对象</label>
          <select id="xy-target" v-model="form.target">
            <option>全部宝贝</option>
            <option>指定分组</option>
            <option>选中宝贝</option>
          </select>
        </div>
      </template>
      <div v-if="kind === 'bind'" class="row">
        <label class="label" for="xy-member">会员名</label>
        <div class="inline">
          <input id="xy-member" v-model="form.memberName" />
          <span class="hint">如果没有遇到绑定异常，此项无需填写，详情请阅读页面底部第4条</span>
        </div>
      </div>
      <div v-if="kind !== 'bind'" class="row">
        <label class="label" for="xy-interval">{{ copy.intervalLabel }}</label>
        <div class="inline">
          <input id="xy-interval" v-model.number="form.intervalSeconds" type="number" min="1" />
          <span>秒</span>
        </div>
      </div>
      <ScheduleEditor
        ref="scheduleEditor"
        v-model="schedule"
        :device-count="form.deviceIds.length"
        :offline-queued="true"
      />
      <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok">{{ successMessage }}</p>
      <div class="footer">
        <button class="primary" type="button" @click="createTask">创建任务</button>
        <button class="ghost" type="button" @click="saveConfig">保存配置</button>
      </div>
    </div>
    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li v-for="(item, index) in copy.help" :key="index" :style="{ '--i': index + 1 }">
          <template v-if="kind === 'bind' && index === 0">
            该任务用来采集您的闲鱼名、圈子、宝贝数、卖出数、销售额、粉丝数、曝光量，屏幕是否可点击，输入法坐标等信息，采集后可在
            <button class="link" type="button" @click="router.push('/operations/system-home/system-home-02')">设备列表</button><span class="nowrap">查看数据</span>
          </template>
          <template v-else>{{ item }}</template>
        </li>
      </ol>
    </div>
  </section>
</template>

<style scoped>
.page { display: grid; gap: 16px; color: #334155; max-width: 920px; }

.card, .help {
  background: #fff;
  border: 1px solid #e6eaf2;
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 12px 32px -20px rgba(15, 23, 42, 0.18);
}
.card { padding: 24px 28px 26px; display: grid; gap: 16px; }

.card-head { display: flex; align-items: center; gap: 14px; }
.card-mark {
  width: 42px; height: 42px; flex: none; border-radius: 12px;
  background: linear-gradient(135deg, #0f766e 0%, #14b8a6 100%);
  box-shadow: 0 6px 14px -6px rgba(15, 118, 110, 0.55);
  display: grid; place-items: center;
}
.card-mark::before {
  content: ""; width: 20px; height: 20px; background: #fff;
  -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 17H7A5 5 0 0 1 7 7h2'/%3E%3Cpath d='M15 7h2a5 5 0 1 1 0 10h-2'/%3E%3Cline x1='8' y1='12' x2='16' y2='12'/%3E%3C/svg%3E") center / contain no-repeat;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 17H7A5 5 0 0 1 7 7h2'/%3E%3Cpath d='M15 7h2a5 5 0 1 1 0 10h-2'/%3E%3Cline x1='8' y1='12' x2='16' y2='12'/%3E%3C/svg%3E") center / contain no-repeat;
}
h2 { margin: 0; font-size: 19px; font-weight: 650; color: #0f172a; letter-spacing: 0.01em; }
.card-sub { margin: 3px 0 0; font-size: 13px; color: #64748b; }

.banner {
  margin: 0; display: flex; align-items: flex-start; gap: 10px;
  border: 1px solid #99f6e4; background: #f0fdfa; color: #0f766e;
  padding: 12px 16px; border-radius: 10px; font-size: 14px; line-height: 1.75;
}
.banner::before {
  content: "i"; flex: none; width: 20px; height: 20px; margin-top: 2px;
  border-radius: 999px; background: #0f766e; color: #fff;
  font-size: 13px; font-weight: 700; font-style: italic; font-family: Georgia, serif;
  display: grid; place-items: center;
}
.banner.danger { border-color: #fecaca; background: #fef5f5; color: #b91c1c; }
.banner.danger::before { content: "!"; background: #dc2626; font-style: normal; font-family: inherit; }

.row { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 14px; align-items: center; }
.label { color: #0f172a; font-size: 14px; font-weight: 600; }
.radio { display: inline-flex; align-items: center; gap: 7px; margin: 0 16px 0 0; font-size: 14px; color: #334155; cursor: pointer; }
.radio input { accent-color: #0f766e; width: 16px; height: 16px; margin: 0; }
.inline { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-size: 14px; color: #334155; }

input, select {
  height: 38px; padding: 0 12px; box-sizing: border-box;
  border: 1px solid #cbd5e1; border-radius: 8px;
  font: inherit; font-size: 14px; color: #0f172a; background: #fff;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
input:focus, select:focus {
  outline: none; border-color: #0f766e;
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.15);
}
select, .inline input { width: min(300px, 100%); }

.hint { color: #94a3b8; font-size: 12.5px; }

.footer { padding-left: 110px; display: flex; gap: 12px; }
.primary, .ghost {
  height: 40px; padding: 0 22px; border-radius: 8px;
  font-size: 14px; font-weight: 600; cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}
.primary {
  border: 0; background: #0f766e; color: #fff;
  box-shadow: 0 6px 14px -8px rgba(15, 118, 110, 0.8);
}
.primary:hover { background: #115e59; }
.ghost { border: 1px solid #cbd5e1; background: #fff; color: #334155; }
.ghost:hover { background: #f8fafc; border-color: #94a3b8; }

.flash { margin: 0; margin-left: 110px; padding: 10px 14px; border-radius: 8px; font-size: 13.5px; }
.flash.error { background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c; }
.flash.ok { background: #f0fdf4; border: 1px solid #bbf7d0; color: #15803d; }

.help { padding: 20px 24px 22px; }
.help h3 { margin: 0 0 14px; font-size: 15px; font-weight: 650; color: #0f172a; }
.help ol { margin: 0; padding: 0; list-style: none; counter-reset: step; display: grid; gap: 10px; }
.help li { counter-increment: step; display: flex; gap: 12px; align-items: flex-start; font-size: 14px; line-height: 1.9; color: #334155; overflow-wrap: break-word; }
.help li::before {
  content: counter(step); flex: none; margin-top: 3px;
  width: 20px; height: 20px; border-radius: 999px;
  background: #ccfbf1; color: #0f766e;
  font-size: 12px; font-weight: 700; display: grid; place-items: center;
}
.link { display: inline-block; white-space: nowrap; border: 0; background: none; color: #0f766e; padding: 0 1px; font-size: inherit; font-weight: 600; cursor: pointer; border-bottom: 1px solid rgba(15, 118, 110, 0.35); line-height: 1.4; }
.link:hover { color: #115e59; border-bottom-color: #115e59; }
.nowrap { white-space: nowrap; }

@media (max-width: 720px) {
  .row { grid-template-columns: 1fr; row-gap: 8px; }
  .footer { padding-left: 0; }
  .flash { margin-left: 0; }
}
</style>
