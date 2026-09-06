<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
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
          <label class="radio" :for="`${kind}-app-sub`"><input :id="`${kind}-app-sub`" v-model="form.app" type="radio" value="sub" /> 副闲鱼</label>
          <label class="radio" :for="`${kind}-app-both`"><input :id="`${kind}-app-both`" v-model="form.app" type="radio" value="main-then-sub" /> 先主后副</label>
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
      <div class="row">
        <label class="label" for="xy-schedule">执行时间</label>
        <select id="xy-schedule" v-model="form.schedule">
          <option>立即执行</option>
        </select>
      </div>
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
            <button class="link" type="button" @click="router.push('/operations/system-home/system-home-02')">设备列表</button>
            查看数据
          </template>
          <template v-else>{{ item }}</template>
        </li>
      </ol>
    </div>
  </section>
</template>

<style scoped>
.page { display: grid; gap: 10px; color: #334155; }
.card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; gap: 16px; }
h2 { margin: 0; font-size: 15px; }
.banner { margin: 0; padding: 10px 12px; background: #f8fafc; border-left: 3px solid #0f766e; color: #334155; font-size: 13px; }
.banner.danger { color: #dc2626; border-left-color: #dc2626; background: #f8fafc; }
.row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: center; }
.label { color: #64748b; font-size: 13px; }
.radio { display: inline-flex; align-items: center; gap: 6px; margin: 0 12px 0 0; }
.inline { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
input, select { height: 34px; padding: 0 10px; border: 1px solid #d1d5db; border-radius: 4px; font: inherit; }
select, .inline input { width: min(280px, 100%); }
.hint { color: #94a3b8; font-size: 12px; }
.footer { padding-left: 100px; display: flex; gap: 10px; }
.primary { height: 34px; padding: 0 16px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; }
.flash { margin: 0; padding-left: 100px; font-size: 13px; }
.flash.error { color: #b91c1c; }
.flash.ok { color: #166534; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.link { border: 0; background: none; color: #0f766e; padding: 0; }
</style>
