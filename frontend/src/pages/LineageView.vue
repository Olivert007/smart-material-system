<template>
  <div class="lineage">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="版本血缘（高级操作）"
      description="按域删除重建、版本对比与行级修正；需运维角色。禁止直接修改业务表（按域删除重建）。"
    />

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
        v-if="releases.length"
        :data="releases"
        border size="small"
        max-height="220"
        style="margin-top: 12px"
        @row-click="(row: { release_id: string }) => (rebuildId = row.release_id)"
      >
        <el-table-column prop="release_id" label="发布版本号" min-width="160" show-overflow-tooltip />
        <el-table-column prop="target_domain" label="域" width="110" />
        <el-table-column prop="clean_rows" label="行数" width="70" />
        <el-table-column prop="supersedes" label="取代" width="120" show-overflow-tooltip />
        <el-table-column prop="superseded_by" label="被取代" width="120" show-overflow-tooltip />
      </el-table>
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
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button v-if="row.status === 'proposed'" link type="primary" @click="applyCorr(String(row.correction_id))">应用</el-button>
            <el-button v-if="row.status === 'proposed'" link type="danger" @click="declineCorr(String(row.correction_id))">拒绝</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  decideCorrection,
  flowAudit,
  flowStats,
  formatApiError,
  lineageRebuild,
  listCorrections,
  listLineageReleases,
  proposeCorrection,
  releaseDiff,
  releaseSupersede,
} from '@/api/client'

const stats = ref<Awaited<ReturnType<typeof flowStats>> | null>(null)
const statsLoading = ref(false)
const audit = ref<Awaited<ReturnType<typeof flowAudit>> | null>(null)
const auditLoading = ref(false)
const rebuildId = ref('')
const rebuildBusy = ref(false)
const releases = ref<Array<Record<string, unknown>>>([])
const releasesLoading = ref(false)
const diffA = ref('')
const diffB = ref('')
const diffBusy = ref(false)
const diffOut = ref('')
const corrRelease = ref('')
const corrRow = ref('')
const corrField = ref('stock_qty')
const corrValue = ref('')
const corrBusy = ref(false)
const corrections = ref<Array<Record<string, unknown>>>([])

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

onMounted(() => { void loadStats() })
</script>

<style scoped>
.lineage { display: flex; flex-direction: column; gap: 16px; max-width: 1100px; }
.head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.rebuild { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; white-space: pre-wrap; }
@media (max-width: 720px) { .rebuild { flex-direction: column; align-items: stretch; } }
</style>
