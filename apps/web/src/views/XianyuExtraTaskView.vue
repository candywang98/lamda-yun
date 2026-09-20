<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import ScheduleEditor, { type ScheduleDraft } from '@/components/ScheduleEditor.vue'
import XianyuDevicePicker from '@/components/XianyuDevicePicker.vue'
import {
  ADDRESS_POOL_OPTIONS,
  DIKOU_TYPES,
  emptyExtraConfig,
  loadExtraConfig,
  PROMOTE_PACKAGES,
  recordExtraTask,
  saveExtraConfig,
  WUYOUMAI_TYPES,
  XIAODAO_OPTIONS,
  type XianyuExtraKind,
} from '@/data/xianyu-extra-tasks'
import { fetchXianyuTaskDevices, type XianyuTaskDevice } from '@/data/xianyu-task-devices'

const props = defineProps<{ kind: XianyuExtraKind }>()
const router = useRouter()
const form = reactive(emptyExtraConfig(props.kind))
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

const copy = computed(() => {
  const table: Record<XianyuExtraKind, { title: string; intervalLabel: string; success: string; help: string[] }> = {
    register: {
      title: '签到鱼币',
      intervalLabel: '',
      success: '已保存签到计划。不会登录闲鱼替你做鱼币任务。',
      help: [
        '能做的赚闲鱼币任务助手会尽量做，消耗大于收入的、容易出验证导致任务中断的、页面无法点击的、限时出现的任务、需要主动去买东西、改变宝贝状态、充话费、玩游戏等助手不会做（买或卖出一件宝贝、发布一件宝贝、去消消乐完成3次消除、去饿了么果园领水果等等）',
        '助手能做的任务有自动签到、自动领收益、自动升级小店、自动扔骰子、自动完成大部分闲鱼内赚鱼币任务（好物夺宝试试手气、去芭芭农场种水果、话费券限时限量抢、点击指定频道好物、搜一搜喜欢的商品、去借钱频道看一看、去看一看闲鱼直播）、去闲鱼空间拍照看价格、浏览鱼小铺工作台以及完成大部分需要跳转到第三方App的任务，比如去支付宝领积分、去支付宝农场领水果、去蚂蚁森林逛一逛、去蚂蚁庄园逛一逛（需要安装并登录支付宝），去淘宝签到领红包、去芭芭农场领水果、去逛一逛斗地主、逛短视频领现金（需要安装并登录淘宝），去快手极速版领红包（需要安装并登录快手），去淘特领好礼（需要安装并登录淘特），去中国移动签到领话费/去中国移动领话费（需要安装并登录中国移动），去百度逛一逛（需要安装并登录百度），去百度地图逛一逛（需要安装并登录百度地图），为了避免手机卡顿，建议配置较低的手机不要安装过多的第三方应用。',
      ],
    },
    dikou: {
      title: '鱼币抵扣',
      intervalLabel: '操作间隔',
      success: '已保存抵扣计划。不会登录闲鱼替你改抵扣。',
      help: [
        '该任务可一键设置闲鱼币抵扣，系统会加载全部宝贝后从顶部开始抵扣，这样在抵扣过程中，界面将保持原位不会滑动，耐心等待抵扣结束即可。',
        '卖家开启抵扣后，宝贝可以获得更多流量曝光',
        '买家购买闲鱼币抵扣宝贝时，可以消耗闲鱼币抵扣卖家设置价格的百分比，订单交易成功后卖家可获得买家支付的闲鱼币',
        '只有宝贝价格在1-100000元之间的非虚拟宝贝才可以开启交易抵扣',
      ],
    },
    promote: {
      title: '急速卖鱼币推广',
      intervalLabel: '',
      success: '已保存推广计划。不会登录闲鱼替你花鱼币推广。',
      help: [
        '极速卖每人每天最多推广1个宝贝，此为闲鱼的限制（助手是模拟手动操作，是运行在闲鱼规则之下的）',
        '宝贝开始推广后，闲鱼会在3天内推广至指定人数。若推广结束未达到指定人数，闲鱼会在48小时内按未达成比例返还闲鱼币',
        '涉及引流、低俗、低价、描述不符、非实际售卖等宝贝不允许推广',
      ],
    },
    xiaodao: {
      title: '闲鱼一键2人小刀',
      intervalLabel: '操作间隔',
      success: '已保存小刀计划。不会登录闲鱼替你开小刀。',
      help: [
        '该任务可一键开启闲鱼宝贝2人小刀，系统会加载全部宝贝后从顶部开始设置，在设置小刀过程中闲鱼界面会保持原位不动，耐心等待设置结束即可。',
        '这些情况不能开启小刀（闲鱼不支持）：1.宝贝库存数量<2 2.宝贝为多规格（规格设置>1）3.商品发货方式含买家自提 4.宝贝为闲鱼特色品类或特色交易方式',
        '刀固定数值时，如果小刀后价格小于等于0，则助手自动设置小刀价为0.01。比如宝贝价格为1元，设置小刀优惠2元，小刀后的价格为-1，助手会设置小刀价为0.01',
        '若宝贝已设置过粉丝价，小刀价需低于粉丝价',
      ],
    },
    'price-cut': {
      title: '闲鱼一键降价',
      intervalLabel: '执行间隔',
      success: '已保存降价计划。不会登录闲鱼替你改价。',
      help: [
        "请填写'比例降价'或'数值降价'，如都填写系统则使用'比例降价'",
        '商品价格100元，比例降价10%后价格为100-100*10%=90元\n商品价格100元，数值降价8元后的价格为100-8=92元',
        '价格过低宝贝、多规格宝贝、特殊宝贝（公益宝贝、免费送等等）无法降价（无降价按钮）',
        '当宝贝500+时，为了保证运行流畅，建议把操作对象设为前500个宝贝',
        '仅当设备在线时，才能创建定时执行任务和每天重复执行的任务',
      ],
    },
    review: {
      title: '闲鱼一键好评',
      intervalLabel: '评价间隔',
      success: '已保存好评计划。不会登录闲鱼替你发好评。',
      help: [
        '该任务可一键好评闲鱼订单，私信内容、好评内容可设置随机发送，参考消息回复格式',
        '仅当设备在线时，才能创建定时执行任务和每天重复执行的任务',
      ],
    },
    restart: {
      title: '重启闲鱼',
      intervalLabel: '',
      success: '已保存重启计划。不会远程强制关闭闲鱼。',
      help: [
        '该任务会重启闲鱼App，重启闲鱼后自己头像处会显示“刚刚来过”',
        '不同手机对双开应用的调度不同，双开后大部分手机只能重启主闲鱼',
      ],
    },
    'delete-feed': {
      title: '闲鱼删除动态',
      intervalLabel: '删除间隔',
      success: '已保存删除计划。不会登录闲鱼替你删动态。',
      help: ['因闲鱼近期的改版，无法删除卖出信息和交易评价信息'],
    },
    'delete-message': {
      title: '闲鱼删除消息',
      intervalLabel: '操作间隔',
      success: '已保存删除计划。不会登录闲鱼替你删消息。',
      help: [
        '该任务可删除闲鱼账号消息列表消息或点开聊天小红点',
        '实际删除间隔会以设置间隔为基准进行随机浮动',
        '删除后只是在消息列表消失，实际的聊天记录不会删除',
        '由于闲鱼的消息缓存机制，删除后的消息可能会再次出现，但消息数量会大大减少',
      ],
    },
    'delete-comment': {
      title: '闲鱼删除留言',
      intervalLabel: '删除间隔',
      success: '已保存删除计划。不会登录闲鱼替你删留言。',
      help: [
        '该任务可删除闲鱼宝贝的留言',
        '当宝贝500+时，为了保证运行流畅，建议把操作对象设为前500个宝贝',
      ],
    },
    'draft-up': {
      title: '闲鱼草稿上架',
      intervalLabel: '上架间隔',
      success: '已保存草稿上架计划。不会登录闲鱼替你点上架。',
      help: [
        '上架闲鱼草稿里所有的商品，注意不要跟发布商品功能混淆',
        '闲鱼的草稿最多可以保存50条，保存时长无限制',
        '仅当设备在线时，才能创建定时执行任务和每天重复执行的任务',
      ],
    },
    reedit: {
      title: '编辑重发任务',
      intervalLabel: '间隔',
      success: '已保存编辑重发计划。不会登录闲鱼替你重发。',
      help: [
        '间隔  编辑重发两个宝贝之间的间隔，单位秒，实际间隔会再加100-2000毫秒随机时间',
        '数量  编辑重发多少个宝贝后停止',
        '编辑重发期间关闭软件，重新开启功能时会接着上次的进度运行',
      ],
    },
    wuyoumai: {
      title: '托管无忧卖',
      intervalLabel: '',
      success: '已保存托管计划。不会登录闲鱼替你托管。',
      help: [
        '“全部托管”可批量将待托管商品加入无忧卖；“全部退出”可一键退出所有托管中的商品',
        '每退一个无忧卖，闲鱼的列表都会刷回顶部，所以每退一个，助手都要重新下滑，如果要退出很多宝贝会耗时很长',
        '如果某个宝贝提交托管后又出现在待托管列表，说明该宝贝不符合无忧卖的条件，可点击“审核中-审核不通过”查看',
      ],
    },
    'fast-reedit': {
      title: '快速编辑重发任务',
      intervalLabel: '间隔',
      success: '已保存快速重发计划。不会登录闲鱼替你重发。',
      help: [
        '编辑重发每个宝贝都需要完整加载一次宝贝列表，快速编辑重发只会加载一次列表，能节省大量时间',
        '间隔  编辑重发两个宝贝之间的间隔，单位秒，实际间隔会再加100-2000毫秒随机时间',
        '遍数  编辑重发多少遍后停止（编辑重发完宝贝列表所有宝贝算一遍）',
        '当宝贝500+时，为了保证运行流畅，建议把操作对象设为前500个宝贝',
      ],
    },
    'fast-down': {
      title: '下架全部闲鱼商品',
      intervalLabel: '删除间隔',
      success: '已保存快速下架计划。不会登录闲鱼替你下架。',
      help: [
        '普通下架商品需要加载完全部商品后才开始下架，遇到500+商品的号会消耗大量时间。',
        '快速下架商品会直接下架全部商品。',
        '间隔  下架两个商品之间的间隔，单位秒，实际间隔会再加100-2000毫秒随机时间',
      ],
    },
  }
  return table[props.kind]
})

const showInterval = computed(() => Boolean(copy.value.intervalLabel))

function restore() {
  Object.assign(form, loadExtraConfig(props.kind))
  errorMessage.value = ''
  successMessage.value = ''
}

function saveConfig() {
  saveExtraConfig(props.kind, form)
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
  if (props.kind === 'xiaodao' && !form.xiaodaoType) {
    errorMessage.value = '请选择小刀操作方式'
    return
  }
  if (props.kind === 'price-cut' && !form.percentCut.trim() && !form.amountCut.trim()) {
    errorMessage.value = '请填写比例降价或数值降价'
    return
  }
  saveExtraConfig(props.kind, form)
  recordExtraTask(props.kind, form)
  successMessage.value = copy.value.success
}

watch(() => props.kind, restore)

onMounted(async () => {
  restore()
  devices.value = await fetchXianyuTaskDevices()
  form.deviceIds = form.deviceIds.filter((id) => devices.value.some((item) => item.id === id))
})
</script>

<template>
  <section class="page">
    <div class="card">
      <h2>{{ copy.title }}</h2>
      <div v-if="kind === 'register'" class="banner danger">想了解能做哪些任务，不能做哪些任务，请阅读页面底部的说明</div>
      <XianyuDevicePicker v-model="form.deviceIds" :devices="devices" />
      <div class="row">
        <span class="label">执行应用</span>
        <div>
          <label class="radio" :for="`${kind}-app-main`"><input :id="`${kind}-app-main`" v-model="form.app" type="radio" value="main" /> 主闲鱼</label>
          <p class="hint">一期每设备仅绑定一个闲鱼账号，副闲鱼/先主后副已禁用。</p>
        </div>
      </div>

      <div v-if="kind === 'register'" class="row">
        <span id="xy-jump-label" class="label">跳转任务</span>
        <div>
          <label class="radio" for="xy-jump-on"><input id="xy-jump-on" v-model="form.jumpTask" type="radio" value="on" aria-describedby="xy-jump-label" /> 开启</label>
          <label class="radio" for="xy-jump-off"><input id="xy-jump-off" v-model="form.jumpTask" type="radio" value="off" aria-describedby="xy-jump-label" /> 关闭</label>
          <p class="hint">是否做跳转到其他App的任务，如跳转支付宝、淘宝...</p>
        </div>
      </div>

      <template v-if="kind === 'dikou'">
        <div class="row">
          <span class="label">操作类型</span>
          <div>
            <label v-for="item in DIKOU_TYPES" :key="item" class="radio" :for="`xy-dikou-${item}`">
              <input :id="`xy-dikou-${item}`" v-model="form.dikouType" type="radio" :value="item" /> {{ item }}
            </label>
          </div>
        </div>
        <div class="row">
          <span class="label">操作对象</span>
          <div>
            <label class="radio" for="xy-dikou-off"><input id="xy-dikou-off" v-model="form.dikouTarget" type="radio" value="未开启抵扣宝贝" /> 未开启抵扣宝贝</label>
            <label class="radio" for="xy-dikou-on"><input id="xy-dikou-on" v-model="form.dikouTarget" type="radio" value="已开启抵扣宝贝" /> 已开启抵扣宝贝</label>
          </div>
        </div>
      </template>

      <template v-if="kind === 'promote'">
        <div class="row">
          <span class="label">选择宝贝</span>
          <div>
            <label class="radio" for="xy-item-exp"><input id="xy-item-exp" v-model="form.promoteItem" type="radio" value="曝光最高宝贝" /> 曝光最高宝贝</label>
            <label class="radio" for="xy-item-view"><input id="xy-item-view" v-model="form.promoteItem" type="radio" value="浏览最高宝贝" /> 浏览最高宝贝</label>
            <label class="radio" for="xy-item-want"><input id="xy-item-want" v-model="form.promoteItem" type="radio" value="想要最高宝贝" /> 想要最高宝贝</label>
          </div>
        </div>
        <div class="row">
          <span class="label">选择套餐</span>
          <div>
            <label v-for="item in PROMOTE_PACKAGES" :key="item" class="radio" :for="`xy-pkg-${item}`">
              <input :id="`xy-pkg-${item}`" v-model="form.promotePackage" type="radio" :value="item" /> {{ item }}
            </label>
          </div>
        </div>
      </template>

      <div v-if="kind === 'xiaodao'" class="row">
        <label class="label" for="xy-xiaodao">操作类型</label>
        <select id="xy-xiaodao" v-model="form.xiaodaoType">
          <option value="">选择小刀操作方式</option>
          <option v-for="item in XIAODAO_OPTIONS" :key="item" :value="item">{{ item }}</option>
        </select>
      </div>

      <template v-if="kind === 'price-cut'">
        <div class="row">
          <label class="label" for="xy-percent">比例降价</label>
          <div class="inline">
            <input id="xy-percent" v-model="form.percentCut" type="number" min="0" placeholder="请输入降价百分比" />
            <span>%</span>
          </div>
        </div>
        <div class="row">
          <label class="label" for="xy-amount">数值降价</label>
          <div class="inline">
            <input id="xy-amount" v-model="form.amountCut" type="number" min="0" step="0.01" />
            <span>元</span>
          </div>
        </div>
        <div class="row">
          <label class="label" for="xy-cut-target">操作对象</label>
          <select id="xy-cut-target" v-model="form.target">
            <option>全部宝贝</option>
            <option>前500个宝贝</option>
            <option>指定分组</option>
          </select>
        </div>
      </template>

      <template v-if="kind === 'review'">
        <div class="row top">
          <label class="label" for="xy-private">私信内容</label>
          <div>
            <textarea id="xy-private" v-model="form.privateMessage" rows="4" placeholder="可以互相好评一下吗~" />
            <p class="hint">设置好评前私信内容，留空则为不私信直接好评</p>
          </div>
        </div>
        <div class="row top">
          <label class="label" for="xy-review">好评内容</label>
          <div>
            <textarea id="xy-review" v-model="form.reviewBody" rows="5" />
            <p class="hint">符号#为随机发送的分隔符</p>
          </div>
        </div>
        <div class="row">
          <span class="label">好评对象</span>
          <div>
            <label class="radio" for="xy-sold"><input id="xy-sold" v-model="form.reviewTarget" type="radio" value="我卖出的" /> 我卖出的</label>
            <label class="radio" for="xy-bought"><input id="xy-bought" v-model="form.reviewTarget" type="radio" value="我买到的" /> 我买到的</label>
            <p class="hint">默认的「我卖出的」为给买家好评</p>
          </div>
        </div>
      </template>

      <div v-if="kind === 'delete-message'" class="row">
        <span class="label">操作类型</span>
        <div>
          <label class="radio" for="xy-msg-del"><input id="xy-msg-del" v-model="form.messageAction" type="radio" value="删除对话框" /> 删除对话框</label>
          <label class="radio" for="xy-msg-dot"><input id="xy-msg-dot" v-model="form.messageAction" type="radio" value="点开小红点" /> 点开小红点</label>
        </div>
      </div>

      <div v-if="kind === 'delete-comment'" class="row">
        <label class="label" for="xy-comment-target">操作对象</label>
        <select id="xy-comment-target" v-model="form.target">
          <option>全部宝贝</option>
          <option>前500个宝贝</option>
          <option>指定分组</option>
        </select>
      </div>

      <div v-if="kind === 'wuyoumai'" class="row">
        <span class="label">操作类型</span>
        <div>
          <label v-for="item in WUYOUMAI_TYPES" :key="item" class="radio" :for="`xy-wuyou-${item}`">
            <input :id="`xy-wuyou-${item}`" v-model="form.wuyoumaiType" type="radio" :value="item" /> {{ item }}
          </label>
        </div>
      </div>

      <template v-if="kind === 'reedit'">
        <div class="row">
          <label class="label" for="xy-extra-interval">间隔</label>
          <div class="inline">
            <input id="xy-extra-interval" v-model.number="form.intervalSeconds" type="number" min="1" />
            <span>秒</span>
          </div>
        </div>
        <div class="row">
          <label class="label" for="xy-quantity">数量</label>
          <input id="xy-quantity" v-model.number="form.quantity" type="number" min="1" />
        </div>
        <div class="row">
          <span class="label">更换地址</span>
          <div>
            <label v-for="item in ADDRESS_POOL_OPTIONS" :key="item" class="radio" :for="`reedit-addr-${item}`">
              <input :id="`reedit-addr-${item}`" v-model="form.addressPool" type="radio" :value="item" /> {{ item }}
            </label>
            <div class="links"><button class="link" type="button" @click="router.push('/operations/xy-tasks/xy-tasks-25')">地址池设置</button></div>
          </div>
        </div>
        <div class="row">
          <span class="label">自动短标题</span>
          <div>
            <label class="radio" for="reedit-short-on"><input id="reedit-short-on" v-model="form.autoShortTitle" type="radio" value="on" /> 开启</label>
            <label class="radio" for="reedit-short-off"><input id="reedit-short-off" v-model="form.autoShortTitle" type="radio" value="off" /> 关闭</label>
            <p class="hint">新版闲鱼（7.23.20及以上）会给部分宝贝自动生成短标题，不想要的话勾选「关闭」就行了</p>
          </div>
        </div>
      </template>

      <template v-if="kind === 'fast-reedit'">
        <div class="row">
          <label class="label" for="xy-rounds">遍数</label>
          <input id="xy-rounds" v-model.number="form.rounds" type="number" min="1" />
        </div>
        <div class="row">
          <label class="label" for="xy-fast-target">操作对象</label>
          <select id="xy-fast-target" v-model="form.target">
            <option>全部宝贝</option>
            <option>前500个宝贝</option>
            <option>指定分组</option>
          </select>
        </div>
        <div class="row">
          <label class="label" for="xy-extra-interval">间隔</label>
          <div class="inline">
            <input id="xy-extra-interval" v-model.number="form.intervalSeconds" type="number" min="1" />
            <span>秒</span>
          </div>
        </div>
        <div class="row">
          <span class="label">自动短标题</span>
          <div>
            <label class="radio" for="fast-short-on"><input id="fast-short-on" v-model="form.autoShortTitle" type="radio" value="on" /> 开启</label>
            <label class="radio" for="fast-short-off"><input id="fast-short-off" v-model="form.autoShortTitle" type="radio" value="off" /> 关闭</label>
            <p class="hint">新版闲鱼（7.23.20及以上）会给部分宝贝自动生成短标题，不想要的话勾选「关闭」就行了</p>
          </div>
        </div>
        <div class="row">
          <span class="label">更换地址</span>
          <div>
            <label v-for="item in ADDRESS_POOL_OPTIONS" :key="item" class="radio" :for="`fast-addr-${item}`">
              <input :id="`fast-addr-${item}`" v-model="form.addressPool" type="radio" :value="item" /> {{ item }}
            </label>
            <div class="links"><button class="link" type="button" @click="router.push('/operations/xy-tasks/xy-tasks-25')">地址池设置</button></div>
          </div>
        </div>
      </template>

      <div v-if="showInterval && kind !== 'reedit' && kind !== 'fast-reedit'" class="row">
        <label class="label" for="xy-extra-interval">{{ copy.intervalLabel }}</label>
        <div class="inline">
          <input id="xy-extra-interval" v-model.number="form.intervalSeconds" type="number" min="1" />
          <span>秒</span>
        </div>
      </div>
      <ScheduleEditor v-model="schedule" :device-count="form.deviceIds.length" :offline-queued="true" />
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
        <li v-for="(item, index) in copy.help" :key="index">
          <template v-if="kind === 'review' && index === 0">
            该任务可一键好评闲鱼订单，私信内容、好评内容可设置随机发送，参考
            <button class="link" type="button" @click="router.push('/operations/chat/chat-06')">消息回复格式</button>
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
.banner.danger { color: #dc2626; border-left-color: #dc2626; }
.row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: center; }
.row.top { align-items: start; }
.label { color: #64748b; font-size: 13px; padding-top: 4px; }
.radio { display: inline-flex; align-items: center; gap: 6px; margin: 0 12px 8px 0; }
.inline { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
input, select, textarea { padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 4px; font: inherit; }
input, select { height: 34px; }
select, .inline input { width: min(280px, 100%); }
textarea { width: 100%; min-height: 88px; resize: vertical; }
.hint { margin: 6px 0 0; color: #94a3b8; font-size: 12px; }
.footer { padding-left: 100px; display: flex; gap: 10px; }
.primary { height: 34px; padding: 0 16px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; }
.flash { margin: 0; padding-left: 100px; font-size: 13px; }
.flash.error { color: #b91c1c; }
.flash.ok { color: #166534; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; white-space: pre-line; }
.links { margin-top: 6px; }
.link { border: 0; background: none; color: #0f766e; padding: 0; }
</style>
