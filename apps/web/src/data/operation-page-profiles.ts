import type { CompetitorPageSpec } from './competitor-pages.generated'

export type OperationFieldControl = 'text' | 'textarea' | 'select' | 'number' | 'toggle' | 'datetime'

export interface OperationPageField {
  id: string
  label: string
  control: OperationFieldControl
  defaultValue: string | number | boolean
  options?: string[]
  placeholder?: string
  help?: string
}

export interface OperationPageProfile {
  key: string
  category: string
  purpose: string
  recordLabel: string
  fields: OperationPageField[]
  workflow: string[]
  sourcePage: number
  sourceRoute: string
}

interface ProfileSeed {
  category: string
  purpose: string
  recordLabel: string
  fields: OperationPageField[]
  workflow: string[]
}

const text = (id: string, label: string, defaultValue: string, help?: string): OperationPageField => ({ id, label, control: 'text', defaultValue, help })
const area = (id: string, label: string, defaultValue: string, placeholder?: string): OperationPageField => ({ id, label, control: 'textarea', defaultValue, placeholder })
const select = (id: string, label: string, options: string[], defaultValue = options[0] ?? ''): OperationPageField => ({ id, label, control: 'select', options, defaultValue })
const number = (id: string, label: string, defaultValue: number, help?: string): OperationPageField => ({ id, label, control: 'number', defaultValue, help })
const toggle = (id: string, label: string, defaultValue: boolean, help?: string): OperationPageField => ({ id, label, control: 'toggle', defaultValue, help })
const datetime = (id: string, label: string, defaultValue = '2026-08-31T09:00'): OperationPageField => ({ id, label, control: 'datetime', defaultValue })

function guideSeed(title: string, topic = title): ProfileSeed {
  return {
    category: '说明与教程',
    purpose: `按章节查看${topic}的页面说明、操作边界与检查清单。`,
    recordLabel: '章节',
    fields: [
      text('guideSearch', '教程内搜索', topic),
      select('lesson', '当前章节', ['功能概览', '准备工作', '页面操作', '风险与复核']),
      select('playbackRate', '播放速度', ['1.0x', '1.25x', '1.5x', '2.0x']),
      toggle('rememberProgress', '记住学习进度', true),
    ],
    workflow: ['定位主题', '查看准备条件', '跟随页面步骤', '完成边界检查'],
  }
}

function systemHomeProfile(title: string): ProfileSeed {
  if (title === '设备列表') return {
    category: '设备运营台', purpose: '复现设备体检、版本筛选、状态列与受控维护入口。', recordLabel: '设备',
    fields: [select('healthScope', '体检范围', ['全部授权设备', '仅异常设备', '仅在线设备']), select('clientVersion', '客户端版本', ['全部版本', '第七版', '第六版', '第五版']), text('groupNumber', '设备组号', '全部组'), toggle('includeOffline', '包含离线设备', true)],
    workflow: ['筛选设备', '查看体检异常', '选择受控维护动作', '记录处理结果'],
  }
  if (title === '系统授权') return {
    category: '授权管理', purpose: '展示可控设备额度、到期信息与卡密提交表面，不接入竞品授权服务。', recordLabel: '授权记录',
    fields: [text('licenseKey', '激活卡密', '', '仅作为本地页面规格，不会向竞品服务提交'), select('licenseAction', '授权动作', ['激活', '续费', '升级']), text('deviceQuota', '预期设备额度', '4 台'), toggle('confirmOwner', '确认由购买者本人操作', false)],
    workflow: ['核对账号主体', '检查授权状态', '录入卡密信息', '保留审计回执'],
  }
  if (title === '建议反馈') return {
    category: '反馈社区', purpose: '按类型、热度和处理状态浏览建议，并组织结构化反馈。', recordLabel: '反馈',
    fields: [select('feedbackType', '反馈类型', ['功能建议', '问题反馈', '使用咨询', '其他']), select('sortBy', '排序方式', ['最新', '最热', '只看我的']), text('feedbackTitle', '反馈标题', ''), area('feedbackDetail', '问题与期望', '', '说明出现位置、影响和期望结果')],
    workflow: ['搜索已有建议', '选择反馈类型', '补充复现信息', '跟踪处理进度'],
  }
  if (title === '公告通知') return {
    category: '消息中心', purpose: '呈现公告标题、发布时间和已读状态。', recordLabel: '公告',
    fields: [select('readState', '阅读状态', ['全部', '未读', '已读']), select('noticeType', '公告类型', ['全部公告', '版本升级', '功能上线', '服务通知']), text('noticeKeyword', '标题关键词', ''), toggle('markVisibleRead', '将当前筛选标记已读', false)],
    workflow: ['筛选公告', '查看公告详情', '确认影响范围', '更新阅读状态'],
  }
  if (title === '超级擦亮') return {
    category: '产品说明', purpose: '说明官方曝光工具的使用入口、计费提醒和合规边界，不提供代充或自动操作。', recordLabel: '说明项',
    fields: [select('contentSection', '说明主题', ['功能是什么', '官方使用入口', '费用提醒', '风险提示']), text('accountNote', '账号备注', ''), toggle('officialChannelOnly', '仅记录官方渠道', true)],
    workflow: ['阅读产品说明', '核对官方入口', '评估费用与风险', '记录人工决策'],
  }
  if (['产品介绍', '常见问题', '常用工具', '更新日志', '视频教程'].includes(title)) return guideSeed(title)
  return guideSeed(title)
}

function taskQueueProfile(): ProfileSeed {
  return {
    category: '任务运行队列', purpose: '按设备、任务类型、运行状态和计划时间查看受控任务。', recordLabel: '运行任务',
    fields: [text('taskKeyword', '任务或设备关键词', ''), select('runState', '运行状态', ['全部状态', '等待运行', '运行中', '运行成功', '运行失败']), select('executionApp', '执行应用', ['全部应用', '主应用', '副应用']), datetime('scheduledAfter', '计划时间起点')],
    workflow: ['筛选运行任务', '核对授权范围', '查看单项状态', '导出执行回执'],
  }
}

function productEditorProfile(title: string): ProfileSeed {
  if (title.includes('水印')) return {
    category: '图片水印编辑器', purpose: '按水印形式配置自定义文字、某鱼会员名/昵称或图片 logo，并保存到本机浏览器供发布时套用。', recordLabel: '水印配置',
    fields: [
      select('mode', '水印形式', ['自定义文字', '某鱼会员名', '某鱼昵称', '图片水印']),
      text('text', '水印文字', '水印文字', '如选了某鱼会员名/某鱼昵称但设备未绑定某鱼号，则默认使用该项'),
      select('fontFamily', '水印字体', ['simhei黑体.ttf', 'simsun宋体.ttf', 'msyh微软雅黑.ttf', 'arial.ttf']),
      number('fontSize', '文字大小', 50, '10-100磅'),
      text('color', '字体颜色', '#267cde'),
      number('opacity', '透明度', 90, '取值1-100，默认100（完全不透明）'),
      select('position', '水印位置', ['右上', '右下', '左上', '左下', '居中']),
      number('marginX', '水平边距', 20, '水平（横轴）边距，单位为像素，默认20'),
      number('marginY', '垂直边距', 20, '垂直（纵轴）边距，单位为像素，默认20'),
      number('shadow', '文字阴影', 0, '取值1-100，默认为0（表示无阴影）'),
      toggle('tile', '铺满全图', false),
      number('rotation', '旋转角度', 45, '取值范围为0-360，铺满与非铺满均生效'),
      select('applyTo', '应用图片', ['全部', '首张', '尾张']),
    ],
    workflow: ['选择水印形式', '配置文字或上传 logo', '预览并调整位置透明度', '保存配置到本机浏览器'],
  }
  if (title.includes('地址池')) return {
    category: '地址池编辑器', purpose: `维护${title}，支持分组、随机策略和回退地址。`, recordLabel: '地址',
    fields: [text('poolName', '地址池名称', title), select('addressSource', '地址来源', title.includes('设备') ? ['设备上报地址', '人工录入'] : ['人工录入', '授权地址簿']), select('allocation', '分配策略', ['按设备固定', '池内随机', '按地区轮换']), area('addresses', '地址清单', '', '每行一条授权地址')],
    workflow: ['创建地址池', '录入并校验地址', '设置分配策略', '保存版本'],
  }
  if (title.includes('描述池') || title.includes('标签池')) return {
    category: title.includes('描述') ? '描述池编辑器' : '标签池编辑器', purpose: `维护发布时可引用的${title}内容和抽取规则。`, recordLabel: title.includes('描述') ? '描述' : '标签',
    fields: [text('poolName', '内容池名称', title), area('poolItems', '内容条目', '', title.includes('标签') ? '输入标签，以换行分隔' : '输入描述，每段一条'), select('selectionMode', '引用方式', ['固定使用', '随机抽取', '按顺序轮换']), number('maxItems', '单次最多引用', title.includes('标签') ? 10 : 1)],
    workflow: ['选择内容池', '编辑内容条目', '设置引用规则', '预览并保存'],
  }
  if (title.includes('教程')) return guideSeed(title, '商品编辑')
  if (title === '普通宝贝') return {
    category: '闲鱼商品编辑器', purpose: '把闲鱼商品标题、描述和价格写入内容库，再下发给已绑定 Companion 的手机填写发布表。', recordLabel: '商品草稿',
    fields: [
      text('spuCode', 'SPU 编码', ''),
      text('productTitle', '商品标题', ''),
      area('description', '商品描述', '', '填写真实成色、规格和交付说明'),
      text('listingPrice', '闲鱼价格', '128', '数字价格，下发到手机后写入闲鱼价格键盘'),
      select('category', '商品分类', ['数码', '家居', '服饰', '其他']),
      number('stock', '库存', 1),
      text('mediaAssetIds', '媒体资产 ID', '', '可选；当前下发闲鱼只支持纯文字和价格'),
      select('contentGroup', '内容分组', ['默认分组', '待复核']),
      select('draftState', '保存状态', ['草稿', '待复核']),
    ],
    workflow: ['填写标题描述价格', '保存到内容库', '选择绑定设备', '下发闲鱼填表'],
  }
  const productType = title.includes('拍卖') ? '拍卖商品' : title.includes('房屋') ? '房屋出租' : title.includes('免费送') ? '免费赠送' : '普通商品'
  return {
    category: `${productType}编辑器`, purpose: `按${productType}页面结构维护标题、分类、价格、库存和交付信息。`, recordLabel: '商品草稿',
    fields: [text('productTitle', '商品标题', `${title}草稿`), select('category', '商品分类', ['数码', '家居', '服饰', '其他']), number('price', title.includes('免费送') ? '运费（元）' : title.includes('拍卖') ? '起拍价（元）' : '售价（元）', title.includes('免费送') ? 0 : 99), number('stock', '库存', 1), area('description', '商品描述', '', '填写真实成色、规格和交付说明')],
    workflow: ['选择商品类型', '填写核心信息', '配置图片与交付', '检查预览并保存'],
  }
}

function collectionProfile(title: string): ProfileSeed {
  if (title.includes('任务列表')) return {
    category: '采集任务记录', purpose: '查看已提交的采集请求、解析进度、积分变化与失败原因。', recordLabel: '采集任务',
    fields: [text('collectorKeyword', '任务关键词', ''), select('collectorState', '解析状态', ['全部状态', '排队中', '解析中', '已完成', '失败']), select('sourcePlatform', '来源平台', ['全部平台', '闲鱼', '淘宝', '转转', '其他']), toggle('showRefunded', '显示已退回积分任务', true)],
    workflow: ['筛选采集任务', '查看解析进度', '检查失败原因', '导出结果索引'],
  }
  if (title.includes('教程')) return guideSeed(title, '合规采集与导入')
  const isSearch = title.includes('搜索')
  const isDetail = title.includes('详情') || title.includes('视频')
  const isArticle = title.includes('文章')
  return {
    category: isSearch ? '关键词检索导入' : isDetail ? '详情资源解析' : isArticle ? '文章链接解析' : '来源链接解析',
    purpose: `复现${title}的来源输入、去重、字段映射和目标分组；策略层保持阻断，不调用第三方私有接口。`, recordLabel: '解析结果',
    fields: [select('sourcePlatform', '来源平台', [title.replace(/链接采集|店铺解析|宝贝采集|解析/g, '') || '指定来源', '其他公开来源']), ...(isSearch ? [text('sourceInput', '搜索关键词', '')] : [area('sourceInput', '公开链接', '', '每行一个公开页面地址')]), select('duplicatePolicy', '重复处理', ['跳过已有内容', '创建新修订', '仅更新价格库存']), select('destinationGroup', '导入目标分组', ['待复核', '采集草稿', '不自动入库']), toggle('downloadMedia', '登记公开媒体引用', isDetail)],
    workflow: ['输入公开来源', '检查授权与可访问性', '预览字段映射', '人工确认导入'],
  }
}

function contentManagementProfile(title: string, contentName: '商品' | '帖子'): ProfileSeed {
  if (title.includes('教程')) return guideSeed(title, `${contentName}管理`)
  if (title.includes('列表')) return {
    category: `${contentName}内容库`, purpose: `按分组、状态、来源和更新时间管理${contentName}。`, recordLabel: contentName,
    fields: [text('contentKeyword', `${contentName}标题或 ID`, ''), select('contentState', '内容状态', ['全部状态', '草稿', '待复核', '可发布', '已归档']), select('contentGroup', '内容分组', ['全部分组', '默认分组', '待复核']), toggle('includeArchived', '包含归档内容', false)],
    workflow: ['筛选内容', '打开详情', '批量变更分组', '导出当前视图'],
  }
  if (title.includes('分组')) return {
    category: `${contentName}分组管理`, purpose: `维护${contentName}分组、排序和批量归属。`, recordLabel: '分组',
    fields: [text('groupName', '分组名称', `${contentName}默认分组`), text('groupCode', '分组编码', `${contentName === '商品' ? 'product' : 'post'}-default`), number('sortOrder', '显示顺序', 10), toggle('defaultGroup', '设为默认分组', false)],
    workflow: ['新建或选择分组', '设置名称与排序', '调整内容归属', '保存并记录变更'],
  }
  if (title.includes('水印')) return productEditorProfile('宝贝水印')
  if (title.includes('数据包') || title.includes('导入') || title.includes('采集')) return {
    category: `${contentName}导入工作台`, purpose: `校验${title}文件或公开来源，预览字段后写入待复核内容库。`, recordLabel: '导入批次',
    fields: [select('importFormat', '导入格式', title.includes('淘宝') ? ['淘宝数据包', 'CSV'] : title.includes('多多') ? ['多多数据包', 'CSV'] : ['CSV', 'JSON', '公开链接']), text('fileReference', '文件或来源引用', ''), select('duplicatePolicy', '重复处理', ['跳过', '更新草稿', '创建副本']), select('destinationGroup', '目标分组', ['待复核', '默认分组'])],
    workflow: ['选择导入来源', '校验字段与媒体', '处理重复项', '确认写入草稿库'],
  }
  if (title.includes('违禁词')) return {
    category: '内容合规检查', purpose: `扫描${contentName}标题与描述，标记命中词和需要人工复核的位置。`, recordLabel: '检查结果',
    fields: [select('contentScope', '检查范围', [`全部${contentName}`, '当前分组', '选中内容']), select('ruleSet', '规则集', ['平台基础规则', '租户补充规则']), toggle('includeMediaOcr', '检查图片 OCR 文本', true), select('onMatch', '命中后处理', ['仅标记', '转入待复核', '阻止提交'])],
    workflow: ['选择内容范围', '加载规则版本', '查看命中上下文', '人工确认处置'],
  }
  if (title.includes('发布') || title.includes('共享')) return {
    category: title.includes('共享') ? '货源共享计划' : '发布计划', purpose: `${title}页面用于选择内容、授权账号、分配方式和审批快照。`, recordLabel: '计划项',
    fields: [select('contentScope', `${contentName}范围`, ['选中内容', '当前分组', '待发布内容']), select('accountScope', '授权账号范围', ['选择授权账号', '按账号组分配']), select('distributionMode', '分配方式', ['均匀分配', '逐账号复制', '人工指定']), datetime('publishAt', '计划时间')],
    workflow: ['选择内容', '选择授权账号', '预览分配与风险', '提交审批或保存计划'],
  }
  if (title.includes('删除')) return {
    category: `${contentName}回收站`, purpose: `筛选待删除${contentName}，预览引用关系并执行可审计的回收站操作。`, recordLabel: contentName,
    fields: [select('deleteScope', '删除范围', ['选中内容', '指定分组']), toggle('keepRecycleBin', '保留在回收站', true), text('deleteReason', '删除原因', ''), toggle('confirmReferences', '已检查引用关系', false)],
    workflow: ['筛选待删除内容', '检查计划与素材引用', '填写原因', '提交审批'],
  }
  return {
    category: `${contentName}编辑器`, purpose: `维护${contentName}正文、图片、分组和发布前状态。`, recordLabel: `${contentName}草稿`,
    fields: [
      text('contentTitle', `${contentName}标题`, ''),
      area('contentBody', `${contentName}正文`, '', '填写真实、可核验的内容'),
      text('mediaAssetIds', '媒体资产 ID', '', '可选，逗号分隔；须已在系统素材完成校验入库'),
      select('targetApp', '目标平台', ['小红书', '抖音', '未指定']),
      select('contentGroup', '内容分组', ['默认分组', '待复核']),
      select('draftState', '保存状态', ['草稿', '待复核']),
    ],
    workflow: ['编辑正文', '配置素材', '选择分组', '预览并保存草稿'],
  }
}

function ordersProfile(title: string): ProfileSeed {
  if (title.includes('教程')) return guideSeed(title, '订单管理')
  if (title.includes('同步')) return {
    category: '订单同步', purpose: '从已授权账号读取订单同步状态，并按时间窗生成本地索引。', recordLabel: '同步批次',
    fields: [select('accountScope', '授权账号', ['选择授权账号', '全部健康账号']), select('timeWindow', '订单时间窗', ['最近 24 小时', '最近 7 天', '自定义时间']), select('syncMode', '同步模式', ['增量同步', '校验已有订单']), toggle('includeAfterSales', '包含售后状态', true)],
    workflow: ['选择授权账号', '设置时间范围', '预览同步数量', '创建同步任务'],
  }
  if (title.includes('采购') || title.includes('单号')) return {
    category: title.includes('采购') ? '采购辅助清单' : '物流单号核对', purpose: `${title}仅呈现订单匹配、采购或物流核对字段，生产策略保持阻断。`, recordLabel: '订单',
    fields: [text('orderKeyword', '订单号或商品关键词', ''), select('orderState', '订单状态', ['待处理', '待采购', '待发货', '已完成']), select('supplierReference', '供应来源', ['人工选择', '已登记供应来源']), toggle('manualReview', '要求人工逐单确认', true)],
    workflow: ['筛选订单', '核对买家与商品', '人工处理外部环节', '登记结果与凭证'],
  }
  return {
    category: '订单总览', purpose: '按账号、订单状态、采购状态和物流状态查看全部订单。', recordLabel: '订单',
    fields: [text('orderKeyword', '订单号或买家关键词', ''), select('accountScope', '账号范围', ['全部授权账号', '指定账号组']), select('orderState', '订单状态', ['全部状态', '待付款', '待发货', '运输中', '已完成', '售后中']), select('logisticsState', '物流状态', ['全部物流', '无单号', '已揽收', '运输中', '已签收'])],
    workflow: ['组合筛选订单', '查看订单详情', '核对履约信息', '导出当前清单'],
  }
}

function analyticsProfile(title: string): ProfileSeed {
  if (title.includes('教程')) return guideSeed(title, '统计分析')
  if (title.includes('流量')) return {
    category: '流量趋势分析', purpose: '比较商品曝光、浏览、咨询等指标在选定周期内的变化。', recordLabel: '指标记录',
    fields: [select('accountScope', '账号范围', ['全部授权账号', '指定账号组']), select('dateRange', '统计周期', ['最近 7 天', '最近 30 天', '自定义']), select('metric', '主指标', ['曝光量', '浏览量', '咨询量', '转化率']), select('comparison', '对比方式', ['环比上一周期', '按账号对比', '按分组对比'])],
    workflow: ['选择统计范围', '选择指标与周期', '定位异常变化', '导出分析摘要'],
  }
  return {
    category: '商品指标采集', purpose: '对授权账号内商品建立指标快照，用于后续趋势比较。', recordLabel: '商品指标',
    fields: [select('accountScope', '授权账号', ['选择授权账号', '全部健康账号']), select('productScope', '商品范围', ['全部上架商品', '指定分组', '选中商品']), select('metricSet', '指标集合', ['基础曝光与浏览', '曝光浏览咨询收藏']), datetime('snapshotAt', '快照时间')],
    workflow: ['选择授权账号', '确定商品范围', '预览指标集合', '创建快照任务'],
  }
}

function platformTaskProfile(title: string, platform: string): ProfileSeed {
  if (title.includes('教程')) return guideSeed(title, `${platform}授权任务`)
  if (title.includes('养号') || title.includes('流量模式') || title.includes('鱼币') || title.includes('一键好评')) return {
    category: '策略阻断说明', purpose: `${title}保留页面字段与风险说明，但不提供自动执行或绕过平台机制的能力。`, recordLabel: '审计项',
    fields: [select('accountScope', `${platform}账号范围`, ['不选择账号', '查看已授权账号状态']), select('policyReason', '阻断原因', ['高风险自动化', '平台权益或互动行为', '缺少可验证授权']), text('reviewTicket', '人工复核单号', ''), toggle('acknowledged', '已阅读策略说明', false)],
    workflow: ['查看原页面意图', '识别高风险行为', '记录人工处理方式', '保留审计说明'],
  }
  if (title.includes('地址池') || title.includes('描述池') || title.includes('标签池') || title.includes('水印')) return productEditorProfile(title.includes('水印') ? '宝贝水印' : title)
  if (title.includes('违禁词')) return contentManagementProfile('违禁词检测', '商品')
  if (title.includes('绑定')) return {
    category: `${platform}账号绑定`, purpose: '建立设备与已授权平台账号的显式对应关系，并检查授权健康状态。', recordLabel: '账号绑定',
    fields: [select('deviceScope', '授权设备', ['选择在线设备', '选择设备组']), text('accountAlias', '账号备注名', ''), select('authorizationWindow', '授权有效期检查', ['立即检查', '仅保存绑定草稿']), toggle('confirmOwnership', '确认拥有账号操作授权', false)],
    workflow: ['选择设备', '确认账号主体', '检查授权健康', '保存绑定关系'],
  }
  if (title === '发布商品' && platform === '闲鱼') return {
    category: '闲鱼发布任务', purpose: '把商品信息（标题/描述/价格/图片视频）下发给已绑定 Companion，由手机自动填写并发布到闲鱼。', recordLabel: '发布任务',
    fields: [
      area('listingBody', '商品描述', '自用闲置，功能正常，支持当面交易', '将写入闲鱼发布页描述框'),
      text('listingPrice', '价格', '128', '仅数字，对应闲鱼价格键盘'),
      text('mediaAssetIds', '媒体资产ID', '', '可选；多个ID用逗号分隔，最多50个，需先上传到媒体库'),
      select('contentScope', '内容范围', ['选中内容', '指定分组', '待发布内容']),
      select('accountScope', '闲鱼账号范围', ['选择授权账号', '指定账号组']),
      select('distributionMode', '分配方式', ['均匀分配', '人工指定']),
      datetime('schedule', '计划时间'),
      toggle('autoPublish', '自动点击发布按钮', true, '关闭后仅填表不发布'),
    ],
    workflow: ['填写描述和价格', '上传图片视频获取资产ID', '下发 Companion 任务', '手机自动填表并发布'],
  }
  if (title.includes('发布')) return {
    category: `${platform}发布任务`, purpose: `选择内容与${platform}授权账号，预览分配、地址、时间和审批快照。`, recordLabel: '发布计划项',
    fields: [select('contentScope', '内容范围', ['选中内容', '指定分组', '待发布内容']), select('accountScope', `${platform}账号范围`, ['选择授权账号', '指定账号组']), select('distributionMode', '分配方式', ['均匀分配', '人工指定']), datetime('schedule', '计划时间'), toggle('dryRun', '先执行配置校验', true)],
    workflow: ['选择内容', '选择授权账号', '预览分配和风险', '提交审批'],
  }
  if (title.includes('降价') || title.includes('小刀')) return {
    category: `${platform}价格调整`, purpose: `${title}在授权商品范围内生成价格变更预览，必须设置价格下限并审批。`, recordLabel: '价格变更',
    fields: [select('accountScope', '账号范围', ['选择授权账号', '指定账号组']), select('productScope', '商品范围', ['选中商品', '指定分组']), select('priceStrategy', '调价方式', ['固定金额', '百分比']), number('priceDelta', '调整值', 5), number('minimumPrice', '最低允许价格', 10)],
    workflow: ['选择商品范围', '设置调价规则', '检查最低价保护', '提交审批'],
  }
  if (title.includes('重启')) return {
    category: '应用维护任务', purpose: `对授权设备上的${platform}应用创建受控重启计划，不暴露任意设备命令。`, recordLabel: '维护任务',
    fields: [select('deviceScope', '设备范围', ['选择在线设备', '指定设备组']), datetime('maintenanceAt', '维护时间'), number('reconnectTimeout', '重连等待（秒）', 60), toggle('healthCheckAfter', '重启后执行健康检查', true)],
    workflow: ['选择授权设备', '设置维护窗口', '预览影响范围', '提交审批'],
  }
  const action = title.includes('删除') ? '删除' : title.includes('下架') ? '下架' : title.includes('上架') ? '上架' : title.includes('擦亮') ? '擦亮' : '状态处理'
  return {
    category: `${platform}${action}任务`, purpose: `在已授权账号和内容范围内创建${title}计划，逐项保留状态与审计。`, recordLabel: '任务目标',
    fields: [select('accountScope', `${platform}账号范围`, ['选择授权账号', '指定账号组']), select('targetScope', '目标范围', ['选中内容', '指定分组', '按状态筛选']), select('interval', '任务间隔', ['30 秒', '60 秒', '120 秒']), datetime('schedule', '计划时间'), toggle('stopOnError', '单项失败时暂停批次', true)],
    workflow: ['选择账号与目标', '检查当前状态', '预览节奏和风险', '提交审批'],
  }
}

function creativeProfile(title: string): ProfileSeed {
  if (title.includes('教程')) return guideSeed(title, '创意中心')
  if (title.includes('分析')) return {
    category: '爆款分析', purpose: '按类目、价格带和统计周期查看公开内容特征与本地运营指标。', recordLabel: '分析样本',
    fields: [select('category', '商品类目', ['数码', '家居', '服饰', '其他']), select('priceBand', '价格带', ['0-50', '50-200', '200-1000', '1000+']), select('dateRange', '统计周期', ['最近 7 天', '最近 30 天']), select('metric', '排序指标', ['曝光增长', '咨询率', '收藏率'])],
    workflow: ['选择分析范围', '查看指标排行', '拆解内容特征', '保存分析摘要'],
  }
  if (title.includes('蓝海词')) return {
    category: '关键词分析', purpose: '按类目筛选关键词，比较热度、竞争度和内容适配性。', recordLabel: '关键词',
    fields: [text('keywordSeed', '种子关键词', ''), select('category', '所属类目', ['全类目', '数码', '家居', '服饰']), select('sortMetric', '排序指标', ['机会指数', '搜索热度', '竞争度']), number('resultLimit', '结果数量', 100)],
    workflow: ['输入种子词', '选择类目与指标', '查看候选词', '导出选中词'],
  }
  return {
    category: 'AI 文案工作台', purpose: '基于真实商品信息选择语气和模型生成文案草稿，结果必须人工复核。', recordLabel: '文案变体',
    fields: [text('productReference', '商品引用', ''), select('tone', '文案语气', ['简洁可信', '生活化', '参数导向']), select('model', '模型', ['租户默认模型', '高质量模型']), text('keywords', '必须包含的关键词', ''), toggle('humanReview', '生成后进入人工复核', true)],
    workflow: ['选择真实商品信息', '设置语气与关键词', '生成多个草稿', '人工编辑并保存'],
  }
}

function chatProfile(title: string): ProfileSeed {
  if (title.includes('素材')) return {
    category: `${title}库`, purpose: `维护聊天可引用的${title}、版本和适用场景。`, recordLabel: '回复素材',
    fields: [text('assetName', '素材名称', ''), select('scene', '适用场景', ['售前咨询', '价格沟通', '发货说明', '售后说明']), text('assetReference', '素材文件引用', ''), toggle('enabled', '允许在回复中使用', true)],
    workflow: ['上传或选择素材', '设置适用场景', '预览回复效果', '保存素材版本'],
  }
  if (title.includes('关键词')) return {
    category: '关键词回复规则', purpose: '设置触发词、匹配方式、回复内容和人工接管条件。', recordLabel: '关键词规则',
    fields: [text('triggerWords', '触发关键词', ''), select('matchMode', '匹配方式', ['包含任一关键词', '完全匹配', '正则规则（受限）']), area('responseText', '回复内容', '', '不得包含误导性承诺'), select('handoffRule', '转人工条件', ['买家继续追问', '命中敏感词', '不自动转人工'])],
    workflow: ['设置触发条件', '编辑回复内容', '预览多段回复', '测试并启用规则'],
  }
  if (title.includes('场景回复组')) return {
    category: '场景回复组', purpose: '按咨询场景组织多条回复，并设置随机、顺序或多段发送方式。', recordLabel: '回复组',
    fields: [text('groupName', '回复组名称', '售前咨询'), select('scene', '咨询场景', ['商品状态', '价格沟通', '发货时效', '售后问题']), select('sendMode', '发送方式', ['随机一条', '顺序轮换', '多段发送']), number('messageInterval', '多段间隔（秒）', 2)],
    workflow: ['创建场景组', '添加回复内容', '设置发送方式', '测试后启用'],
  }
  if (title.includes('格式')) return {
    category: '消息格式设置', purpose: '配置多段消息、署名、素材顺序和人工接管提示。', recordLabel: '格式模板',
    fields: [select('segmentMode', '多段方式', ['保持原段落', '按句号拆分', '整段发送']), toggle('includeSignature', '添加客服署名', false), text('signature', '客服署名', ''), toggle('showHandoffNotice', '转人工时发送提示', true)],
    workflow: ['选择消息拆分方式', '配置署名和提示', '预览消息序列', '保存设置'],
  }
  if (title.includes('开启') || title.includes('关闭') || title.includes('手机端')) return {
    category: '回复服务状态', purpose: `${title}页面管理授权账号的回复开关、在线时段和人工接管。`, recordLabel: '账号回复状态',
    fields: [select('accountScope', '授权账号范围', ['选择授权账号', '指定账号组']), select('serviceState', '目标状态', title.includes('关闭') ? ['关闭自动回复'] : ['开启自动回复', '仅手机端人工回复']), text('activeHours', '服务时段', '09:00-22:00'), toggle('handoffEnabled', '允许人工接管', true)],
    workflow: ['选择授权账号', '设置服务状态与时段', '检查规则冲突', '保存并记录变更'],
  }
  return {
    category: '快捷回复管理', purpose: '维护人工聊天可快速插入的短语、分类和快捷检索词。', recordLabel: '快捷回复',
    fields: [text('shortcutTitle', '快捷回复名称', ''), area('shortcutBody', '回复内容', ''), select('shortcutGroup', '回复分类', ['售前', '发货', '售后', '其他']), text('searchAliases', '检索别名', '')],
    workflow: ['创建快捷回复', '编辑内容与分类', '预览插入效果', '保存并排序'],
  }
}

function assetsProfile(title: string): ProfileSeed {
  if (title.includes('水印')) return productEditorProfile('宝贝水印')
  if (title.includes('地址池') || title.includes('描述池') || title.includes('标签池')) return productEditorProfile(title)
  const assetType = title.replace('素材', '') || '文件'
  return {
    category: `${title}库`, purpose: `管理${assetType}文件的来源、版本、适用范围和引用状态。`, recordLabel: title,
    fields: [text('assetName', '素材名称', ''), select('assetScope', '适用范围', ['全部内容', '指定分组', '聊天回复']), text('fileReference', '文件引用', ''), text('versionNote', '版本说明', '初始版本'), toggle('active', '允许新内容引用', true)],
    workflow: ['上传或登记素材', '校验格式与哈希', '设置适用范围', '保存资产版本'],
  }
}

function profileSettings(title: string): ProfileSeed {
  if (title === '基本资料') return {
    category: '个人资料', purpose: '维护用于账号识别和辅助找回的联系方式。', recordLabel: '资料项',
    fields: [text('username', '用户名', 'demo-operator', '用户名不可修改'), select('gender', '性别', ['未设置', '男', '女']), text('qq', 'QQ', ''), text('wechat', '微信', ''), text('email', '邮箱', '')],
    workflow: ['核对用户名', '补充联系方式', '检查找回信息', '保存资料'],
  }
  if (title === '修改密码') return {
    category: '密码安全', purpose: '修改当前账号密码并给出强度与登录会话提示。', recordLabel: '安全事件',
    fields: [text('currentPassword', '当前密码', ''), text('newPassword', '新密码', ''), text('confirmPassword', '确认新密码', ''), toggle('signOutOthers', '退出其他登录会话', true)],
    workflow: ['验证当前密码', '输入强密码', '确认会话处理', '提交修改'],
  }
  if (title === '邀请好友') return {
    category: '邀请关系', purpose: '展示邀请链接、注册与会员状态及奖励记录，不自动传播邀请内容。', recordLabel: '邀请记录',
    fields: [select('inviteView', '记录范围', ['全部好友', '已注册', '已开通会员']), text('inviteKeyword', '好友或状态关键词', ''), toggle('showRewardOnly', '仅显示有奖励记录', false)],
    workflow: ['查看邀请说明', '复制个人邀请链接', '查看绑定记录', '核对奖励明细'],
  }
  if (title === '积分明细') return {
    category: '积分账本', purpose: '按积分池、收支类型和时间查看余额变化。', recordLabel: '积分流水',
    fields: [select('pointPool', '积分池', ['全部积分', '月积分', '永久积分']), select('transactionType', '收支类型', ['全部类型', '采集扣分', '解析扣分', 'AI 扣分', '发放与奖励']), select('dateRange', '时间范围', ['本月', '最近 90 天', '全部']), toggle('showRefunds', '显示失败退回', true)],
    workflow: ['查看当前余额', '筛选积分流水', '核对功能消耗', '导出账本'],
  }
  return {
    category: 'AI 功能设置', purpose: '分别设置 AI 改写、标题、分词和规格修正使用的模型与自定义提示词。', recordLabel: 'AI 功能配置',
    fields: [select('aiFeature', 'AI 功能', ['AI 改写', 'AI 标题', 'AI 分词', 'AI 修正规格']), select('model', '使用模型', ['租户默认模型', '快速模型', '高质量模型']), area('customPrompt', '自定义提示词', '', '留空时使用官方或租户默认提示词'), toggle('confirmPointCost', '显示积分消耗确认', true)],
    workflow: ['选择 AI 功能', '选择模型', '编辑并预览提示词', '保存功能配置'],
  }
}

function seedFor(moduleId: string, title: string): ProfileSeed {
  switch (moduleId) {
    case 'system-home': return systemHomeProfile(title)
    case 'task-queue': return taskQueueProfile()
    case 'product-editor': return productEditorProfile(title)
    case 'collection': return collectionProfile(title)
    case 'product-management': return contentManagementProfile(title, '商品')
    case 'post-management': return contentManagementProfile(title, '帖子')
    case 'orders': return ordersProfile(title)
    case 'analytics': return analyticsProfile(title)
    case 'xy-tasks': return platformTaskProfile(title, '闲鱼')
    case 'zz-tasks': return platformTaskProfile(title, '转转')
    case 'red-tasks': return platformTaskProfile(title, '小红书')
    case 'creative': return creativeProfile(title)
    case 'chat': return chatProfile(title)
    case 'assets': return assetsProfile(title)
    case 'profile': return profileSettings(title)
    default: return guideSeed(title)
  }
}

export function buildOperationPageProfile(moduleId: string, title: string, source: CompetitorPageSpec): OperationPageProfile {
  const seed = seedFor(moduleId, title)
  return {
    ...seed,
    key: `${moduleId}:${source.index}:${source.route}`,
    purpose: `${seed.purpose} 原页面要点：${source.summary.slice(0, 120)}${source.summary.length > 120 ? '…' : ''}`,
    sourcePage: source.page,
    sourceRoute: source.route,
  }
}

export function initialPageParameters(profile: OperationPageProfile) {
  return Object.fromEntries(profile.fields.map((field) => [field.id, field.defaultValue])) as Record<string, string | number | boolean>
}
