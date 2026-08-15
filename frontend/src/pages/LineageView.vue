<template>
  <div class="lineage">
    <h2 class="page-title">数据来源</h2>

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
              <span class="rc-id">{{ r.release_id }}</span>
              <el-tag size="small" :type="String(r.status) === 'revoked' ? 'danger' : 'success'">
                {{ releaseStatusLabel(r.status) }}
              </el-tag>
            </div>
            <div class="rc-meta">
              来源文件 {{ r.file_id }} · 域 {{ r.target_domain || '—' }} · 可用候选
              {{ r.clean_rows ?? '—' }} 行 / 阻塞 {{ r.blocked_rows ?? '—' }}
            </div>
            <div class="rc-meta">确认人 {{ r.released_by || '—' }} · {{ r.released_at || '—' }}</div>
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
          <el-descriptions-item label="文件编号">{{ business.file.file_id }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="business.sheets.length" class="sub">Sheet 清单</div>
        <el-table
          v-if="business.sheets.length"
          :data="business.sheets"
          border
          size="small"
          style="margin-top: 6px"
        >
          <el-table-column prop="sheet" label="工作表" min-width="140" />
          <el-table-column prop="role_hint" label="角色" width="120" />
          <el-table-column prop="structure_hint" label="结构" width="130" />
          <el-table-column prop="rows" label="行" width="70" />
          <el-table-column prop="cols" label="列" width="70" />
        </el-table>
        <div v-if="business.confirms.length" class="sub">谁确认了什么（审计记录）</div>
        <el-table
          v-if="business.confirms.length"
          :data="business.confirms"
          border
          size="small"
          max-height="240"
          style="margin-top: 6px"
        >
          <el-table-column prop="ts" label="时间" width="160" />
          <el-table-column prop="actor" label="确认人" width="90" />
          <el-table-column prop="action" label="操作内容" width="110" />
          <el-table-column prop="source" label="记录来源" width="120" show-overflow-tooltip />
          <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
        </el-table>
        <p v-else class="hint">暂无与当前上下文匹配的确认记录；可到「操作记录」查看全部。</p>
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
  auditTimeline,
  formatApiError,
  getIntakeProfile,
  listFiles,
  listLineageReleases,
  type FileItem,
} from '@/api/client'

const route = useRoute()
const router = useRouter()
const business = ref<{
  releases: Array<Record<string, unknown>>
  file: FileItem | null
  sheets: Array<Record<string, unknown>>
  confirms: Array<Record<string, unknown>>
}>({ releases: [], file: null, sheets: [], confirms: [] })
const businessLoading = ref(false)

function releaseStatusLabel(s?: unknown): string {
  const v = String(s || '')
  if (!v || v === 'released') return '已发布'
  if (v === 'revoked') return '已吊销'
  return v
}

function clearRowEvidence() {
  const q = { ...route.query }
  delete q.row_key
  router.replace({ path: '/trace', query: q })
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
    const fid = fileFilter.value || ''
    const [releases, files, confirms] = await Promise.all([
      listLineageReleases({ limit: 30 }),
      listFiles(50, 0),
      auditTimeline({
        limit: 50,
        release_id: relId || undefined,
        file_id: fid || undefined,
      }),
    ])
    const rels = (releases.items || []).filter(
      (r) =>
        (!relId || String(r.release_id) === relId) &&
        (!fid || String(r.file_id || '').includes(fid)),
    )
    const fileRow = fid ? (files.items || []).find((f) => f.file_id === fid) || null : null
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
      confirms: (confirms.items || []) as Array<Record<string, unknown>>,
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
.page-title { font-size: 16px; font-weight: 600; color: var(--el-text-color-primary); margin: 0; }
.hint { color: #909399; font-size: 13px; margin: 8px 0 0; }
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
.rc-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.rc-id { font-weight: 600; font-size: 14px; word-break: break-all; }
.rc-meta { color: #606266; font-size: 12px; margin-top: 6px; line-height: 1.5; }
.sub { color: #606266; font-size: 13px; margin: 12px 0 6px; font-weight: 600; }
</style>
