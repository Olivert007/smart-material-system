<template>
  <div class="trace-hub">
    <p v-if="!hasTraceContext" class="intro-hint">
      从「数据成果」或「阻塞数据」点「追溯」可查看来源与行级证据；此处可浏览全部发布版本与操作记录。
    </p>
    <el-alert
      v-if="contextLine"
      type="warning"
      :closable="false"
      show-icon
      :title="contextLine"
      style="margin-top: -4px"
    />
    <el-tabs v-model="tab" @tab-change="onTab">
      <el-tab-pane label="数据来源" name="lineage" />
      <el-tab-pane label="操作记录" name="audit" />
    </el-tabs>
    <LineageView v-if="tab === 'lineage'" />
    <AuditView v-else />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listFiles, listLineageReleases } from '@/api/client'
import { DOMAIN_ZH, mapZh } from '@/utils/auditLabels'
import LineageView from '@/pages/LineageView.vue'
import AuditView from '@/pages/AuditView.vue'

const route = useRoute()
const router = useRouter()

const TAB_NAMES = ['lineage', 'audit'] as const
const TRACE_QUERY_KEYS = ['release_id', 'file_id', 'source_file', 'row_key', 'q', 'blocked_row'] as const

const tab = ref(
  TAB_NAMES.includes(route.query.tab as (typeof TAB_NAMES)[number])
    ? String(route.query.tab)
    : 'lineage',
)

const fileNameById = ref<Record<string, string>>({})
const releaseById = ref<Record<string, { file_id: string; target_domain?: string }>>({})

const hasTraceContext = computed(() =>
  TRACE_QUERY_KEYS.some((k) => {
    const v = route.query[k]
    return typeof v === 'string' ? v.length > 0 : Array.isArray(v) && v.some(Boolean)
  }),
)

function shortId(id: string): string {
  return id.length > 8 ? id.slice(-8) : id
}

const contextLine = computed(() => {
  const parts: string[] = []
  const releaseId = typeof route.query.release_id === 'string' ? route.query.release_id : ''
  if (releaseId) {
    const rel = releaseById.value[releaseId]
    const domain = rel ? mapZh(DOMAIN_ZH, rel.target_domain) : ''
    const fname = rel ? fileNameById.value[rel.file_id] || '' : ''
    const title = [domain, fname].filter(Boolean).join(' · ')
    parts.push(title ? `发布 ${title}` : `发布版本 …${shortId(releaseId)}`)
  }
  const sourceFile = typeof route.query.source_file === 'string' ? route.query.source_file : ''
  const fileId = typeof route.query.file_id === 'string' ? route.query.file_id : ''
  if (sourceFile) {
    parts.push(`源文件 ${sourceFile}`)
  } else if (fileId) {
    const name = fileNameById.value[fileId]
    if (name) parts.push(`源文件 ${name}`)
  }
  if (route.query.q) parts.push(`关键词 ${route.query.q}`)
  if (route.query.blocked_row) parts.push(`阻塞行 ${route.query.blocked_row}`)
  return parts.length ? `当前追溯上下文：${parts.join(' · ')}` : ''
})

function onTab(name: string | number) {
  router.replace({
    path: '/trace',
    query: { ...route.query, tab: String(name) },
  })
}

onMounted(async () => {
  try {
    const [files, releases] = await Promise.all([
      listFiles(50),
      listLineageReleases({ limit: 50 }),
    ])
    fileNameById.value = Object.fromEntries(
      (files.items || []).map((f) => [f.file_id, f.filename || f.file_id]),
    )
    releaseById.value = Object.fromEntries(
      (releases.items || []).map((r) => [r.release_id, r]),
    )
  } catch {
    /* 文件名解析失败时回退显示短号 */
  }
})

watch(
  () => route.query.tab,
  (v) => {
    if (v && TAB_NAMES.includes(v as (typeof TAB_NAMES)[number])) tab.value = String(v)
  },
)
</script>

<style scoped>
.trace-hub { display: flex; flex-direction: column; gap: 12px; width: 100%; }
.intro-hint { color: #909399; font-size: 13px; margin: 0; line-height: 1.5; }
</style>
