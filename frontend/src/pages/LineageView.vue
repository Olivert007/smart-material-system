<template>
  <div class="lineage">
    <RowEvidence
      v-if="route.query.release_id && route.query.row_key"
      :release-id="String(route.query.release_id)"
      :row-key="String(route.query.row_key)"
      @close="clearRowEvidence"
    />

    <el-card shadow="never" v-loading="businessLoading">
      <template #header><span>来源概览</span></template>
      <template v-if="business.releases.length || business.file">
        <div v-if="business.releases.length" class="release-cards">
          <div v-for="r in business.releases" :key="String(r.release_id)" class="release-card">
            <div class="rc-top">
              <div>
                <div class="rc-id">{{ releaseCardTitle(r) }}</div>
                <div class="rc-sub">版本 {{ shortReleaseId(r.release_id) }}</div>
              </div>
              <el-tag size="small" :type="String(r.status) === 'revoked' ? 'danger' : 'success'">
                {{ releaseStatusLabel(r.status) }}
              </el-tag>
            </div>
            <div class="rc-meta">
              已入库 {{ r.clean_rows ?? '—' }} 行 / 阻塞 {{ r.blocked_rows ?? 0 }}
            </div>
            <div class="rc-meta">确认人 {{ actorZhLabel(r.released_by) }} · {{ r.released_at || '—' }}</div>
            <div v-if="r.supersedes || r.superseded_by" class="rc-meta">
              取代 {{ r.supersedes || '—' }} / 被取代 {{ r.superseded_by || '—' }}
            </div>
          </div>
        </div>
        <el-descriptions v-if="business.file" :column="2" border size="small" style="margin-top: 10px">
          <el-descriptions-item label="来源文件">{{ business.file.filename }}</el-descriptions-item>
          <el-descriptions-item label="格式">{{ business.file.format || '—' }}</el-descriptions-item>
          <el-descriptions-item label="工作表数">{{ business.file.sheets ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="行数">{{ business.file.rows ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="接入时间">{{ business.file.created_at || '—' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="business.sheets.length" class="sub">工作表清单</div>
        <el-table
          v-if="business.sheets.length"
          :data="business.sheets"
          border
          size="small"
          style="margin-top: 6px"
        >
          <el-table-column prop="sheet" label="工作表" min-width="140" />
          <el-table-column label="角色" width="120" :formatter="(r: Record<string, unknown>) => roleZh(r.role_hint)" />
          <el-table-column label="结构" width="130" :formatter="(r: Record<string, unknown>) => structureZh(r.structure_hint)" />
          <el-table-column prop="rows" label="行" width="70" />
          <el-table-column prop="cols" label="列" width="70" />
        </el-table>
        <div class="audit-link">
          <el-button link type="primary" @click="goAuditTab">查看操作记录 →</el-button>
        </div>
      </template>
      <el-empty
        v-else
        description="从数据成果 / 阻塞数据的「追溯」进入即可看到来源。"
        :image-size="56"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import RowEvidence from '@/components/RowEvidence.vue'
import {
  formatApiError,
  getIntakeProfile,
  listFiles,
  listLineageReleases,
  type FileItem,
} from '@/api/client'
import {
  ACTOR_ZH,
  DOMAIN_ZH,
  ROLE_ZH,
  STRUCTURE_ZH,
  mapZh,
} from '@/utils/auditLabels'

const route = useRoute()
const router = useRouter()
const business = ref<{
  releases: Array<Record<string, unknown>>
  file: FileItem | null
  sheets: Array<Record<string, unknown>>
}>({ releases: [], file: null, sheets: [] })
const businessLoading = ref(false)
const fileNameById = ref<Record<string, string>>({})

function releaseFileLabel(r: Record<string, unknown>) {
  const fid = String(r.file_id || '')
  return fileNameById.value[fid] || business.value.file?.filename || fid
}

function releaseCardTitle(r: Record<string, unknown>) {
  const domain = domainZh(r.target_domain)
  const file = releaseFileLabel(r)
  if (domain && domain !== '—' && file) return `${domain} · ${file}`
  return file || domain || String(r.release_id || '—')
}

function shortReleaseId(id: unknown): string {
  const s = String(id || '')
  if (!s) return '—'
  return s.length > 8 ? s.slice(-8) : s
}

function releaseStatusLabel(s?: unknown): string {
  const v = String(s || '')
  if (!v || v === 'released') return '已发布'
  if (v === 'revoked') return '已吊销'
  return v
}

function domainZh(v: unknown): string {
  return mapZh(DOMAIN_ZH, v) || '—'
}

function actorZhLabel(v: unknown): string {
  return mapZh(ACTOR_ZH, v)
}

function roleZh(v: unknown): string {
  return mapZh(ROLE_ZH, v)
}

function structureZh(v: unknown): string {
  return mapZh(STRUCTURE_ZH, v)
}

function clearRowEvidence() {
  const q = { ...route.query }
  delete q.row_key
  router.replace({ path: '/trace', query: q })
}

function goAuditTab() {
  router.replace({
    path: '/trace',
    query: { ...route.query, tab: 'audit', scope: 'govern' },
  })
}

const fileFilter = computed(() => {
  if (typeof route.query.file_id === 'string' && route.query.file_id) return route.query.file_id
  if (typeof route.query.source_file === 'string' && route.query.source_file) return route.query.source_file
  return ''
})

async function loadBusiness() {
  businessLoading.value = true
  try {
    const relId =
      typeof route.query.release_id === 'string' && route.query.release_id
        ? route.query.release_id
        : ''
    const rawFid = fileFilter.value || ''
    const [releases, files] = await Promise.all([
      listLineageReleases({ limit: 30 }),
      listFiles(50, 0),
    ])
    const fileItems = files.items || []
    fileNameById.value = Object.fromEntries(
      fileItems.map((f) => [f.file_id, f.filename || f.file_id]),
    )
    const allRels = releases.items || []
    // 先按 release_id 定位发布版本，再解析源文件哈希：优先取该发布版本绑定的文件；
    // 其次把文件名解析为哈希；兜底按原值（哈希，来自阻塞数据等入口）使用。
    const rel = relId ? allRels.find((r) => String(r.release_id) === relId) : undefined
    let fid = rawFid
    if (rel?.file_id) {
      fid = String(rel.file_id)
    } else {
      const hit =
        fileItems.find((f) => f.filename === rawFid) ||
        fileItems.find((f) => f.file_id === rawFid)
      if (hit) fid = hit.file_id
    }
    // 过滤发布版本：release_id 精确匹配；file 上下文用解析后的哈希匹配（兼容哈希/文件名）
    const rels = relId
      ? allRels.filter((r) => String(r.release_id) === relId)
      : allRels.filter((r) => !fid || String(r.file_id || '').includes(fid))
    const fileRow = fid ? fileItems.find((f) => f.file_id === fid) || null : null
    let sheets: Array<Record<string, unknown>> = []
    if (fid) {
      try {
        const profile = await getIntakeProfile(fid)
        sheets = (profile?.profile?.sheets || []) as Array<Record<string, unknown>>
      } catch {
        /* profile 可能未生成，忽略 */
      }
    }
    business.value = {
      releases: rels,
      file: fileRow,
      sheets,
    }
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    businessLoading.value = false
  }
}

onMounted(() => {
  void loadBusiness()
})

watch(
  () => [route.query.release_id, route.query.file_id, route.query.source_file],
  () => {
    void loadBusiness()
  },
)
</script>

<style scoped>
.lineage { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.release-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.release-card {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 12px 14px;
  background: var(--el-fill-color-blank);
}
.rc-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.rc-id { font-weight: 600; font-size: 14px; word-break: break-all; }
.rc-sub { color: #909399; font-size: 12px; margin-top: 4px; }
.rc-meta { color: #606266; font-size: 12px; margin-top: 6px; line-height: 1.5; }
.sub { color: #606266; font-size: 13px; margin: 12px 0 6px; font-weight: 600; }
.audit-link { margin-top: 10px; }
</style>
