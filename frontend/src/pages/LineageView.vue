<template>
  <div class="lineage">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="版本血缘"
      description="从发布版本回看来源：哪个文件、哪些 Sheet、谁确认了什么。下方「高级操作」仅供运维（重建 / 吊销 / 版本对比 / 行级修正）。"
    />

    <RowEvidence
      v-if="route.query.release_id && route.query.row_key"
      :release-id="String(route.query.release_id)"
      :row-key="String(route.query.row_key)"
      @close="clearRowEvidence"
    />

    <el-card shadow="never" v-loading="businessLoading">
      <template #header><span>业务血缘（结果 → 来源）</span></template>
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
          <el-table-column prop="action" label="动作" width="110" />
          <el-table-column prop="source" label="来源" width="120" show-overflow-tooltip />
          <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
        </el-table>
        <p v-else class="hint">暂无与当前上下文匹配的确认记录；可到「审计时间线」查看全部。</p>
      </template>
      <el-empty
        v-else
        description="从数据成果 / 阻塞数据的「追溯」进入即可看到来源；下方仍可查看最近发布版本。"
        :image-size="56"
      />
    </el-card>

    <el-collapse class="ops-fold">
      <el-collapse-item title="高级操作（运维：重建 / 吊销 / 版本对比 / 行级修正）" name="ops">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>流水统计</span>
          <el-space>
            <el-button :loading="statsLoading" @click="loadStats">刷新统计</el-button>
            <el-button :loading="auditLoading" @click="loadAudit">跑审计</el-button>
          </el-space>
        </div>
      </template>
      <el-space wrap style="margin-bottom: 12px">
        <el-tag>已发布 {{ stats?.published_total ?? '—' }}</el-tag>
        <el-tag type="info">规则直出占比 {{ stats?.l1_ratio ?? '—' }}</el-tag>
        <el-tag type="warning">待确认 {{ stats?.pending ?? '—' }}</el-tag>
        <el-tag :type="(audit?.suspicious_count || 0) > 0 ? 'danger' : 'success'">
          可疑行 {{ audit?.suspicious_count ?? '—' }} / {{ audit?.total_rows ?? '—' }}
        </el-tag>
      </el-space>
      <el-table v-if="audit?.suspicious?.length" :data="audit.suspicious" border size="small" max-height="240">
        <el-table-column prop="flow_id" label="流水编号" min-width="120" />
        <el-table-column prop="source_file" label="文件" min-width="120" />
        <el-table-column prop="parse_level" label="级别" width="70" />
        <el-table-column prop="quantity" label="数量" width="70" />
        <el-table-column label="原因" min-width="180">
          <template #default="{ row }">{{ (row.reasons || []).join(', ') }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header><span>发布版本重建 / 吊销</span></template>
      <div class="rebuild">
        <el-input v-model="rebuildId" placeholder="发布版本号" style="max-width: 360px" />
        <el-button type="primary" :loading="rebuildBusy" @click="doRebuild('rebuild')">重建</el-button>
        <el-button type="danger" plain :loading="rebuildBusy" @click="doRebuild('revoke')">吊销</el-button>
        <el-button link type="primary" :loading="releasesLoading" @click="loadReleases">最近发布</el-button>
      </div>
      <el-table
        v-if="filteredReleases.length"
        :data="filteredReleases"
        border size="small"
        max-height="220"
        style="margin-top: 12px"
        :row-class-name="releaseRowClass"
        @row-click="(row: { release_id: string }) => (rebuildId = row.release_id)"
      >
        <el-table-column prop="release_id" label="发布版本号" min-width="160" show-overflow-tooltip />
        <el-table-column prop="file_id" label="源文件" min-width="140" show-overflow-tooltip />
        <el-table-column prop="target_domain" label="域" width="110" />
        <el-table-column prop="clean_rows" label="行数" width="70" />
        <el-table-column prop="supersedes" label="取代" width="120" show-overflow-tooltip />
        <el-table-column prop="superseded_by" label="被取代" width="120" show-overflow-tooltip />
      </el-table>
      <p v-else-if="fileFilter && releases.length" class="hint">
        当前深链文件「{{ fileFilter }}」下暂无匹配发布版本；已显示全部时请清除筛选。
      </p>
      <div class="rebuild" style="margin-top: 10px">
        <el-input v-model="diffA" placeholder="版本A" style="max-width: 200px" />
        <el-input v-model="diffB" placeholder="版本B" style="max-width: 200px" />
        <el-button :loading="diffBusy" @click="runDiff">版本对比</el-button>
        <el-button type="warning" plain :loading="diffBusy" @click="runSupersede">标记取代</el-button>
      </div>
      <pre v-if="diffOut" class="mono">{{ diffOut }}</pre>
    </el-card>

    <el-card shadow="never">
      <template #header><span>行级修正提案</span></template>
      <div class="rebuild">
        <el-input v-model="corrRelease" placeholder="发布版本号" style="max-width: 180px" />
        <el-input v-model="corrRow" placeholder="行标识" style="max-width: 140px" />
        <el-input v-model="corrField" placeholder="字段" style="max-width: 120px" />
        <el-input v-model="corrValue" placeholder="新值" style="max-width: 120px" />
        <el-button type="primary" plain :loading="corrBusy" @click="proposeCorr">提案修正</el-button>
        <el-button :loading="corrBusy" @click="loadCorrs">刷新</el-button>
      </div>
      <el-table v-if="corrections.length" :data="corrections" border size="small" max-height="180" style="margin-top: 8px">
        <el-table-column prop="correction_id" label="编号" width="140" />
        <el-table-column prop="row_key" label="行标识" width="100" />
        <el-table-column prop="field" label="字段" width="90" />
        <el-table-column prop="value_new" label="新值" width="80" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">{{ corrStatusLabel(row.status) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button v-if="row.status === 'proposed'" link type="primary" @click="applyCorr(String(row.correction_id))">应用</el-button>
            <el-button v-if="row.status === 'proposed'" link type="danger" @click="declineCorr(String(row.correction_id))">拒绝</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import RowEvidence from '@/components/RowEvidence.vue'
import {
  auditTimeline,
  decideCorrection,
  flowAudit,
  flowStats,
  formatApiError,
  getIntakeProfile,
  lineageRebuild,
  listCorrections,
  listFiles,
  listLineageReleases,
  proposeCorrection,
  releaseDiff,
  releaseSupersede,
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
const stats = ref<Awaited<ReturnType<typeof flowStats>> | null>(null)
const statsLoading = ref(false)
const audit = ref<Awaited<ReturnType<typeof flowAudit>> | null>(null)
const auditLoading = ref(false)
const rebuildId = ref(typeof route.query.release_id === 'string' ? route.query.release_id : '')
const rebuildBusy = ref(false)
const releases = ref<Array<Record<string, unknown>>>([])
const releasesLoading = ref(false)
const diffA = ref('')
const diffB = ref('')
const diffBusy = ref(false)
const diffOut = ref('')
const corrRelease = ref(typeof route.query.release_id === 'string' ? route.query.release_id : '')
const corrRow = ref('')
const corrField = ref('stock_qty')
const corrValue = ref('')
const corrBusy = ref(false)
const corrections = ref<Array<Record<string, unknown>>>([])

function releaseStatusLabel(s?: unknown): string {
  const v = String(s || '')
  if (!v || v === 'released') return '已发布'
  if (v === 'revoked') return '已吊销'
  return v
}

function corrStatusLabel(s?: unknown): string {
  const v = String(s || '')
  const map: Record<string, string> = { proposed: '待审核', applied: '已应用', declined: '已拒绝' }
  return map[v] || v || '—'
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

const filteredReleases = computed(() => {
  const f = fileFilter.value
  if (!f) return releases.value
  return releases.value.filter((r) => String(r.file_id || '') === f || String(r.file_id || '').includes(f))
})

function releaseRowClass({ row }: { row: Record<string, unknown> }) {
  if (rebuildId.value && row.release_id === rebuildId.value) return 'row-hl'
  if (fileFilter.value && String(row.file_id || '') === fileFilter.value) return 'row-hl'
  return ''
}

function needToken() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌（运维角色）')
    return false
  }
  if ((localStorage.getItem('ops_role') || 'ops') === 'viewer') {
    ElMessage.warning('当前角色无写权限')
    return false
  }
  return true
}

async function loadStats() {
  statsLoading.value = true
  try { stats.value = await flowStats() } catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { statsLoading.value = false }
}

async function loadAudit() {
  auditLoading.value = true
  try {
    audit.value = await flowAudit()
    ElMessage.success(`审计完成：可疑 ${audit.value.suspicious_count}`)
  } catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { auditLoading.value = false }
}

async function doRebuild(mode: 'rebuild' | 'revoke') {
  if (!needToken() || !rebuildId.value.trim()) return
  try {
    await ElMessageBox.confirm(`${mode === 'revoke' ? '吊销' : '重建'} ${rebuildId.value}？`, '确认', { type: 'warning' })
  } catch { return }
  rebuildBusy.value = true
  try {
    await lineageRebuild({ release_id: rebuildId.value.trim(), revoke_only: mode === 'revoke' })
    ElMessage.success('完成')
    await Promise.all([loadStats(), loadAudit(), loadReleases()])
  } catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { rebuildBusy.value = false }
}

async function loadReleases() {
  releasesLoading.value = true
  try { releases.value = (await listLineageReleases({ limit: 30 })).items || [] }
  catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { releasesLoading.value = false }
}

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

async function runDiff() {
  if (!diffA.value.trim() || !diffB.value.trim()) return
  diffBusy.value = true
  try {
    diffOut.value = JSON.stringify(await releaseDiff(diffA.value.trim(), diffB.value.trim()), null, 2)
  } catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { diffBusy.value = false }
}

async function runSupersede() {
  if (!needToken()) return
  const newer = diffB.value.trim() || rebuildId.value.trim()
  const older = diffA.value.trim()
  if (!newer || !older) return
  diffBusy.value = true
  try {
    await releaseSupersede(newer, older)
    ElMessage.success('已标记取代')
    await loadReleases()
  } catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { diffBusy.value = false }
}

async function loadCorrs() {
  try { corrections.value = (await listCorrections()).items || [] }
  catch (e: unknown) { ElMessage.error(formatApiError(e)) }
}

async function proposeCorr() {
  if (!needToken()) return
  corrBusy.value = true
  try {
    await proposeCorrection({
      release_id: corrRelease.value.trim() || rebuildId.value.trim(),
      row_key: corrRow.value.trim(),
      field: corrField.value.trim(),
      value_new: corrValue.value,
      reason: 'lineage ui',
    })
    ElMessage.success('已提案')
    await loadCorrs()
  } catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { corrBusy.value = false }
}

async function applyCorr(id: string) {
  corrBusy.value = true
  try {
    await decideCorrection(id, 'apply')
    ElMessage.success('已应用')
    await loadCorrs()
  } catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { corrBusy.value = false }
}

async function declineCorr(id: string) {
  corrBusy.value = true
  try {
    await decideCorrection(id, 'decline')
    await loadCorrs()
  } catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { corrBusy.value = false }
}

onMounted(() => {
  void loadStats()
  void loadBusiness()
  void loadReleases().then(() => {
    if (!rebuildId.value && filteredReleases.value.length === 1) {
      rebuildId.value = String(filteredReleases.value[0].release_id || '')
      corrRelease.value = rebuildId.value
    }
  })
})

watch(
  () => [route.query.release_id, route.query.file_id, route.query.source_file],
  () => {
    if (typeof route.query.release_id === 'string' && route.query.release_id) {
      rebuildId.value = route.query.release_id
      corrRelease.value = route.query.release_id
    }
    void loadBusiness()
  },
)
</script>

<style scoped>
.lineage { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.rebuild { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; white-space: pre-wrap; }
.hint { color: #909399; font-size: 13px; margin: 8px 0 0; }
.lineage :deep(.row-hl) { background: var(--el-color-primary-light-9); }
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
.ops-fold { background: #fff; border: 1px solid #ebeef5; border-radius: 4px; padding: 0 12px; }
.ops-fold :deep(.el-collapse-item__content) { padding-bottom: 12px; }
.ops-fold :deep(.el-card) { border: none; box-shadow: none; }
@media (max-width: 720px) { .rebuild { flex-direction: column; align-items: stretch; } }
</style>
