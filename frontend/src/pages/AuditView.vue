<template>
  <div class="audit">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <el-space wrap>
            <el-radio-group v-model="auditScope" size="small" @change="onScopeChange">
              <el-radio-button value="govern">发布与治理</el-radio-button>
              <el-radio-button value="report">报表运行</el-radio-button>
              <el-radio-button value="all">全部</el-radio-button>
            </el-radio-group>
            <el-input v-model="filterRelease" clearable placeholder="发布版本" style="width: 160px" />
            <el-input v-model="filterFile" clearable placeholder="源文件" style="width: 180px" />
            <el-input v-model="filterQ" clearable placeholder="关键词（规则/物资等）" style="width: 180px" />
            <el-select v-model="filterSource" clearable placeholder="记录来源" style="width: 140px">
              <el-option v-for="(zh, key) in SOURCE_ZH" :key="key" :label="zh" :value="key" />
            </el-select>
            <el-input v-model="filterActor" clearable placeholder="操作者" style="width: 120px" />
            <el-button type="primary" :loading="loading" @click="onSearch">查询</el-button>
          </el-space>
        </div>
      </template>
      <RetryBanner :message="errorMsg" @retry="load" />
      <el-table :data="rows" v-loading="loading" border size="small" empty-text="暂无记录">
        <el-table-column prop="ts" label="时间" width="170" />
        <el-table-column prop="kind_zh" label="类型" width="100" />
        <el-table-column prop="source_zh" label="记录来源" width="130" show-overflow-tooltip />
        <el-table-column prop="action_zh" label="操作内容" width="110" show-overflow-tooltip />
        <el-table-column prop="actor_zh" label="操作者" width="120" show-overflow-tooltip />
        <el-table-column label="发布" width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ releaseLabel(row.release_id) }}</template>
        </el-table-column>
        <el-table-column label="源文件" width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ fileLabel(row.file_id) }}</template>
        </el-table-column>
        <el-table-column prop="detail_zh" label="详情" min-width="220" show-overflow-tooltip />
      </el-table>
      <div class="pager">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          :page-sizes="[20, 50, 100, 200]"
          @current-change="onPage"
          @size-change="onSize"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auditTimeline, formatApiError, listFiles, listLineageReleases } from '@/api/client'
import RetryBanner from '@/components/RetryBanner.vue'
import {
  ACTOR_ZH,
  DOMAIN_ZH,
  KIND_ZH,
  SOURCE_ZH,
  actionZh,
  mapZh,
  renderAuditDetail,
  zhToKey,
} from '@/utils/auditLabels'

const SCOPES = ['govern', 'report', 'all'] as const
type AuditScope = (typeof SCOPES)[number]

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const errorMsg = ref('')
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filterSource = ref('')
const filterActor = ref('')
const filterRelease = ref('')
const filterFile = ref('')
const filterQ = ref('')
const auditScope = ref<AuditScope>('govern')
const rows = ref<Array<Record<string, string>>>([])
const cachedRows = ref<Array<Record<string, string>>>([])
const fileNameById = ref<Record<string, string>>({})
const releaseById = ref<
  Record<string, { file_id: string; target_domain?: string }>
>({})

function shortId(id: string): string {
  return id.length > 8 ? id.slice(-8) : id
}

function shortFilename(name: string): string {
  return name.length > 18 ? `${name.slice(0, 16)}…` : name
}

function releaseLabel(id?: string | null): string {
  const rid = String(id || '')
  if (!rid) return '—'
  const rel = releaseById.value[rid]
  if (rel) {
    const domain = mapZh(DOMAIN_ZH, rel.target_domain)
    const fname = fileNameById.value[rel.file_id] || ''
    const title = [domain, fname ? shortFilename(fname) : ''].filter(Boolean).join(' · ')
    if (title) return title
  }
  return `版本 …${shortId(rid)}`
}

function fileLabel(id?: string | null): string {
  const fid = String(id || '')
  if (!fid) return '—'
  return fileNameById.value[fid] || fid
}

function mapItems(items: Array<Record<string, string>>) {
  return items.map((it) => ({
    ...it,
    kind_zh: mapZh(KIND_ZH, it.kind),
    source_zh: mapZh(SOURCE_ZH, it.source),
    action_zh: actionZh(it.action),
    actor_zh: mapZh(ACTOR_ZH, it.actor),
    detail_zh: renderAuditDetail(it.detail || ''),
  }))
}

function applyGovernPage() {
  const start = (page.value - 1) * pageSize.value
  rows.value = cachedRows.value.slice(start, start + pageSize.value)
}

function seedFromRoute() {
  if (typeof route.query.release_id === 'string') filterRelease.value = route.query.release_id
  if (typeof route.query.file_id === 'string') filterFile.value = route.query.file_id
  if (typeof route.query.q === 'string') filterQ.value = route.query.q
  if (typeof route.query.source === 'string') {
    filterSource.value = zhToKey(SOURCE_ZH, route.query.source) || route.query.source
  }
  if (typeof route.query.actor === 'string') filterActor.value = route.query.actor
  if (typeof route.query.scope === 'string' && (SCOPES as readonly string[]).includes(route.query.scope)) {
    auditScope.value = route.query.scope as AuditScope
  }
}

function onSearch() {
  page.value = 1
  load()
}

function onScopeChange() {
  page.value = 1
  load()
}

function onPage(p: number) {
  page.value = p
  if (auditScope.value === 'govern') {
    applyGovernPage()
    return
  }
  load()
}

function onSize(s: number) {
  pageSize.value = s
  page.value = 1
  if (auditScope.value === 'govern') {
    applyGovernPage()
    return
  }
  load()
}

async function loadCaches() {
  try {
    const [releases, files] = await Promise.all([
      listLineageReleases({ limit: 50 }),
      listFiles(50),
    ])
    fileNameById.value = Object.fromEntries(
      (files.items || []).map((f) => [f.file_id, f.filename || f.file_id]),
    )
    releaseById.value = Object.fromEntries(
      (releases.items || []).map((r) => [r.release_id, r]),
    )
  } catch {
    /* 标签缓存失败时回退显示短 id */
  }
}

async function load() {
  loading.value = true
  errorMsg.value = ''
  router.replace({
    path: '/trace',
    query: {
      ...route.query,
      tab: 'audit',
      scope: auditScope.value,
      ...(filterRelease.value.trim() ? { release_id: filterRelease.value.trim() } : { release_id: undefined }),
      ...(filterFile.value.trim() ? { file_id: filterFile.value.trim() } : { file_id: undefined }),
      ...(filterQ.value.trim() ? { q: filterQ.value.trim() } : { q: undefined }),
    },
  })
  try {
    const sourceParam =
      auditScope.value === 'report'
        ? 'report_run'
        : filterSource.value.trim() &&
            !(auditScope.value === 'govern' && filterSource.value.trim() === 'report_run')
          ? filterSource.value.trim()
          : undefined
    const res = await auditTimeline({
      limit: auditScope.value === 'govern' ? 500 : pageSize.value,
      offset: auditScope.value === 'govern' ? 0 : (page.value - 1) * pageSize.value,
      source: sourceParam,
      actor: zhToKey(ACTOR_ZH, filterActor.value.trim()) || undefined,
      release_id: filterRelease.value.trim() || undefined,
      file_id: filterFile.value.trim() || undefined,
      q: filterQ.value.trim() || undefined,
    })
    let items = (res.items || []) as Array<Record<string, string>>
    if (auditScope.value === 'govern') {
      items = items.filter((it) => it.source !== 'report_run')
      cachedRows.value = mapItems(items)
      total.value = cachedRows.value.length
      applyGovernPage()
    } else {
      cachedRows.value = []
      total.value = res.total ?? 0
      rows.value = mapItems(items)
    }
  } catch (e: unknown) {
    errorMsg.value = formatApiError(e)
  } finally {
    loading.value = false
  }
}

watch(
  () => [route.query.release_id, route.query.file_id, route.query.source_file, route.query.q, route.query.scope],
  () => {
    seedFromRoute()
  },
)

onMounted(() => {
  seedFromRoute()
  void loadCaches()
  load()
})
</script>

<style scoped>
.audit { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.head { display: flex; justify-content: space-between; align-items: center; }
.pager { display: flex; justify-content: flex-end; margin-top: 12px; }
@media (max-width: 720px) { .head :deep(.el-space) { flex-wrap: wrap; } }
</style>
