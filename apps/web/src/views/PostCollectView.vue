<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createPostCatalog } from '@/api/post-catalog'
import { emptyPost } from '@/data/post-fields'
import { DEFAULT_POST_GROUP_NAME, resolvePostGroups } from '@/data/post-groups'

const router = useRouter()
const catalog = createPostCatalog()
const linksText = ref('')
const collectAs = ref('帖子')
const dedupe = ref(true)
const plugin = ref('md5')
const groupName = ref(DEFAULT_POST_GROUP_NAME)
const groups = ref<string[]>([DEFAULT_POST_GROUP_NAME])
const busy = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

function parseLinks(raw: string): string[] {
  return [...new Set(raw.split(/\s+/).map((item) => item.trim()).filter((item) => /^https?:\/\//i.test(item)))]
}

function titleFromLink(link: string): string {
  try {
    const url = new URL(link)
    return decodeURIComponent(url.pathname.split('/').filter(Boolean).at(-1) ?? url.hostname)
  } catch {
    return link
  }
}

async function startCollect() {
  const links = parseLinks(linksText.value)
  if (links.length === 0) {
    errorMessage.value = '请填写至少一条 http/https 帖子链接'
    return
  }
  if (links.length > 10) {
    errorMessage.value = '为保证采集成功率，单次最多可采集 10 条链接'
    return
  }
  busy.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const existing = dedupe.value ? await catalog.list() : []
    let imported = 0
    let skipped = 0
    for (const link of links) {
      if (dedupe.value && existing.some((item) => item.sourceLinks.includes(link))) {
        skipped += 1
        continue
      }
      await catalog.save({
        post: emptyPost({
          title: titleFromLink(link),
          body: link,
          groupName: groupName.value,
          sourceLinks: [link],
          notes: plugin.value === 'md5' ? '图片MD5处理' : '',
        }),
      })
      imported += 1
    }
    successMessage.value = `已记录 ${imported} 条链接到帖子库${skipped ? `，跳过 ${skipped} 条重复链接` : ''}。不会登录第三方平台抓取正文。`
  } catch (error) {
    errorMessage.value = `采集失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    groups.value = resolvePostGroups(await catalog.list()).map((item) => item.name)
  } catch {
    groups.value = [DEFAULT_POST_GROUP_NAME]
  }
})
</script>

<template>
  <section class="post-page">
    <div class="card">
      <h2>帖子/笔记/文章 链接采集</h2>
      <div class="row top">
        <label for="post-links">帖子链接</label>
        <textarea id="post-links" v-model="linksText" rows="8" placeholder="第一条帖子链接&#10;第二条帖子链接&#10;第三条帖子链接" />
      </div>
      <div class="row"><span class="label">采集为</span><label class="radio"><input v-model="collectAs" type="radio" value="帖子" /> 帖子</label></div>
      <div class="row">
        <span class="label">是否去重</span>
        <label class="radio"><input v-model="dedupe" type="radio" :value="true" /> 自动去重</label>
        <label class="radio"><input v-model="dedupe" type="radio" :value="false" /> 相同链接重复采集</label>
      </div>
      <div class="row"><span class="label">采集插件</span><label class="radio"><input v-model="plugin" type="radio" value="md5" /> 图片MD5处理</label></div>
      <div class="row">
        <label for="post-collect-group">帖子分组</label>
        <div class="inline">
          <select id="post-collect-group" v-model="groupName">
            <option v-for="item in groups" :key="item" :value="item">{{ item }}</option>
          </select>
          <button class="link" type="button" @click="router.push('/operations/post-management/post-management-04')">分组管理</button>
        </div>
      </div>
      <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok">{{ successMessage }}</p>
      <div class="footer"><button class="primary" type="button" :disabled="busy" @click="startCollect">开始采集</button></div>
    </div>
    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>已支持采集小红书笔记。（采集后可发布到闲鱼或小红书）</li>
        <li>为保证小红书采集的成功率，单次最多可采集10条链接，每个链接一行。</li>
        <li>遇到采集错误请重试，如多次尝试后依然错误可能是平台规则改变。</li>
        <li>勾选自动去重后，会忽略有成功采集记录的重复提交的链接。</li>
        <li>当前会把链接保存到帖子库，不会登录第三方私有接口抓取正文。</li>
      </ol>
    </div>
  </section>
</template>

<style scoped>
.post-page { display: grid; gap: 10px; color: #334155; }
.card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; gap: 16px; }
h2 { margin: 0; font-size: 15px; }
.row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: center; }
.row.top { align-items: start; }
.label, label { color: #64748b; font-size: 13px; }
textarea, select { width: 100%; padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 4px; font: inherit; }
.radio, .inline { display: inline-flex; align-items: center; gap: 6px; margin-right: 16px; color: #334155; }
.inline { width: 100%; margin-right: 0; }
.link { height: 32px; padding: 0 10px; border: 0; background: none; color: #0f766e; cursor: pointer; }
.footer { padding-left: 100px; }
.primary { height: 32px; padding: 0 16px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; }
.flash { margin: 0; font-size: 13px; }
.flash.error { color: #b91c1c; }
.flash.ok { color: #166534; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
</style>
