<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createPostCatalog } from '@/api/post-catalog'
import { emptyPost } from '@/data/post-fields'
import { DEFAULT_POST_GROUP_NAME, resolvePostGroups } from '@/data/post-groups'

const router = useRouter()
const catalog = createPostCatalog()
const linksText = ref('')
const dedupe = ref(true)
const groupName = ref(DEFAULT_POST_GROUP_NAME)
const groups = ref<string[]>([])
const loadingGroups = ref(false)
const groupsError = ref('')
const busy = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const uncertainLinks = ref<string[]>([])

function parseLinks(raw: string): string[] {
  const lines = raw.split(/\r?\n/).map((line, index) => ({ value: line.trim(), number: index + 1 })).filter((line) => line.value)
  const invalid = lines.filter(({ value }) => {
    try {
      const url = new URL(value)
      return !['http:', 'https:'].includes(url.protocol) || !url.hostname || /\s/.test(value) || !!url.username || !!url.password
    } catch { return true }
  })
  if (invalid.length) throw new Error('第 ' + invalid.map((line) => line.number).join('、') + ' 行不是有效的 http/https 链接；请每行填写一条完整链接。未保存任何链接。')
  if (!lines.length) throw new Error('请填写至少一条 http/https 帖子链接')
  if (lines.length > 10) throw new Error('每次最多记录 10 条链接，请分批提交。')
  return lines.map((line) => line.value)
}

function titleFromLink(link: string): string {
  const url = new URL(link)
  const title = url.pathname.split('/').filter(Boolean).at(-1) ?? url.hostname
  try { return decodeURIComponent(title) } catch { return title }
}

async function loadGroups() {
  if (loadingGroups.value || busy.value) return
  loadingGroups.value = true
  groupsError.value = ''
  try {
    groups.value = resolvePostGroups(await catalog.list()).map((item) => item.name)
    if (!groups.value.includes(groupName.value)) groupName.value = groups.value[0] ?? DEFAULT_POST_GROUP_NAME
  } catch (error) {
    groupsError.value = '分组读取失败：' + (error instanceof Error ? error.message : String(error))
  } finally { loadingGroups.value = false }
}

async function recordLinks() {
  if (busy.value || loadingGroups.value || groupsError.value) return
  errorMessage.value = ''
  successMessage.value = ''
  let links: string[]
  try { links = parseLinks(linksText.value) } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
    return
  }
  const snapshot = { links, dedupe: dedupe.value }
  busy.value = true
  let imported = 0
  let skipped = 0
  let cursor = 0
  let saving = false
  try {
    const existing = snapshot.dedupe ? await catalog.list() : []
    const known = new Set(existing.flatMap((item) => [...item.sourceLinks, item.body.trim()]))
    for (const link of snapshot.links) {
      if (snapshot.dedupe && known.has(link)) { skipped += 1; cursor += 1; continue }
      saving = true
      await catalog.save({ post: emptyPost({ title: titleFromLink(link), body: link, sourceLinks: [link] }) })
      saving = false
      imported += 1
      cursor += 1
      known.add(link)
    }
    linksText.value = ''
    successMessage.value = '已记录 ' + imported + ' 条链接，跳过 ' + skipped + ' 条重复链接。未抓取正文或图片。'
  } catch (error) {
    // A rejected save may already have reached the server. Do not automatically replay it.
    if (saving) {
      const uncertain = snapshot.links[cursor]!
      uncertainLinks.value = [...new Set([...uncertainLinks.value, uncertain])]
      cursor += 1
    }
    linksText.value = snapshot.links.slice(cursor).join('\n')
    errorMessage.value = '记录中断：已确认保存 ' + imported + ' 条，跳过 ' + skipped + ' 条，尚未尝试 ' + (snapshot.links.length - cursor) + ' 条。' + (error instanceof Error ? error.message : String(error))
  } finally { busy.value = false }
}

onMounted(loadGroups)
</script>

<template>
  <section class="post-page">
    <div class="card">
      <h2>帖子链接记录 / 导入</h2>
      <p class="scope-note">仅将链接保存到帖子库，正文暂存为链接。不会抓取小红书或其他网站的正文、图片，也不处理图片；后续请在帖子编辑页补充内容。</p>
      <p v-if="loadingGroups" role="status">正在读取帖子分组…</p>
      <div v-if="groupsError" role="alert"><span>{{ groupsError }}</span><button class="link" type="button" :disabled="loadingGroups || busy" @click="loadGroups">重试读取分组</button></div>
      <fieldset :disabled="busy || loadingGroups || !!groupsError">
        <div class="row top"><label for="post-links">帖子链接</label><textarea id="post-links" v-model="linksText" rows="8" placeholder="每行一条完整的 http/https 链接，最多 10 条" /></div>
        <div class="row"><span class="label">重复链接</span><div><label class="radio"><input v-model="dedupe" type="radio" :value="true" /> 自动去重</label><label class="radio"><input v-model="dedupe" type="radio" :value="false" /> 允许重复记录</label></div></div>
        <div class="row"><label for="post-collect-group">帖子分组</label><div class="inline"><select id="post-collect-group" v-model="groupName" disabled><option v-for="item in groups" :key="item" :value="item">{{ item }}</option></select><button class="link" type="button" @click="router.push('/operations/post-management/post-management-04')">分组管理</button></div></div>
        <p class="scope-note">当前链接记录接口不写入分组，分组选择暂不可用。</p>
        <div class="footer"><button class="primary" type="button" @click="recordLinks">{{ busy ? '正在记录…' : '记录链接' }}</button></div>
      </fieldset>
      <p v-if="errorMessage" class="flash error" role="alert">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok" role="status">{{ successMessage }}</p>
      <div v-if="uncertainLinks.length" class="uncertain" role="alert"><strong>{{ uncertainLinks.length }} 条保存结果待核实</strong><p>以下请求未得到成功回执，可能已保存。已从输入框移出，不会自动重试。请先查看帖子库确认，仅在未保存时重新填写。</p><ul><li v-for="link in uncertainLinks" :key="link">{{ link }}</li></ul></div>
      <button class="link" type="button" @click="router.push('/operations/post-management/post-management-03')">查看帖子库</button>
    </div>
    <div class="help"><h3>使用说明</h3><ol><li>每行一条链接，任何无效行都会阻止本次保存。</li><li>自动去重会检查帖子库已有来源链接及本批次重复项。</li><li>中断后输入框只保留尚未尝试的链接；已成功及结果待核实的链接不会自动重复提交。</li></ol></div>
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
fieldset { border: 0; padding: 0; margin: 0; min-width: 0; display: grid; gap: 16px; }
.scope-note, .uncertain { margin: 0; font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }
.uncertain { padding: 12px; background: #fff7ed; }
button:disabled { opacity: .5; cursor: not-allowed; }
@media (max-width: 600px) { .row { grid-template-columns: 1fr; } .footer { padding-left: 0; } .inline { flex-wrap: wrap; } }
</style>
