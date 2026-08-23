<template>
  <div class="home">
    <el-alert
      v-if="runtimeHint"
      :title="runtimeHint.title"
      :type="runtimeHint.type"
      :closable="false"
      show-icon
      :description="runtimeHint.desc"
      class="runtime-alert"
    />
    <el-alert
      :title="statusTitle"
      :type="statusType"
      :closable="false"
      show-icon
      :description="alertDesc"
    />

    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="head">
          <span>当前数据状态</span>
          <el-button size="small" :loading="loading" @click="load">刷新</el-button>
        </div>
      </template>
      <div class="cards">
        <div class="card clickable" @click="$router.push('/govern')">
          <div class="card-label">待办合计</div>
          <div class="card-value">{{ fmt(todos.total) }}</div>
        </div>
        <div class="card">
          <div class="card-label">可用行数</div>
          <div class="card-value">{{ fmt(quality.clean_rows) }}</div>
        </div>
        <div class="card warn">
          <div class="card-label">阻塞行数</div>
          <div class="card-value">{{ fmt(quality.blocked_rows) }}</div>
          <div class="card-hint">未解决异常或未确认项</div>
        </div>
        <div class="card clickable" @click="$router.push({ path: '/govern', query: { tab: 'flow' } })">
          <div class="card-label">流水待确认</div>
          <div class="card-value">{{ fmt(todos.flow_pending) }}</div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>最优先下一步</template>
      <div class="next-block">
        <div class="next-reason">{{ nextAction.reason || '加载中…' }}</div>
        <div class="cta">
          <el-button type="primary" @click="$router.push(nextAction.path || '/intake')">
            {{ nextAction.label || '继续' }}
          </el-button>
          <el-button v-if="(todos.total || 0) > 0 && nextAction.path !== '/govern'" @click="$router.push('/govern')">去数据规整</el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>最近接入</span>
          <el-button link type="primary" @click="$router.push('/intake')">全部</el-button>
        </div>
      </template>
      <el-table
        v-if="recentFiles.length"
        :data="recentFiles"
        border
        size="small"
        empty-text="暂无接入文件"
      >
        <el-table-column prop="filename" label="文件" min-width="180" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="fileStateTag(row.status)">
              {{ fileStateLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="rows" label="行数" width="90" />
        <el-table-column prop="created_at" label="接入时间" width="180" />
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button
              v-if="row.file_id"
              link
              type="primary"
              :disabled="row.status === 'failed'"
              @click="goStage(row)"
            >
              规整确认
            </el-button>
            <el-button
              v-if="row.file_id"
              link
              type="danger"
              @click="onDeleteFile(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="尚未接入文件">
        <p class="first-use-hint">{{ FIRST_USE_INTAKE_HINT }}</p>
        <el-button type="primary" @click="$router.push('/intake')">去数据接入</el-button>
      </el-empty>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>{{ businessSnapshotTitle }}</span>
          <el-button size="small" type="primary" plain @click="$router.push('/data')">进入数据成果</el-button>
        </div>
      </template>
      <template v-if="shouldShowBusinessSnapshot">
        <div class="cards compact" v-loading="loading">
          <el-tooltip v-for="c in bizCards" :key="c.key" :content="c.hint" placement="top">
            <div class="card biz-card" @click="goMetric(c.metric_id)">
              <div class="card-label">{{ c.label }}</div>
              <div class="card-value">{{ c.value }}</div>
            </div>
          </el-tooltip>
        </div>
      </template>
      <div v-else class="biz-empty">
        <div class="biz-empty-title">{{ businessSnapshotEmptyReason }}</div>
        <div class="biz-empty-desc">{{ businessSnapshotDescription }}</div>
        <el-button type="primary" plain @click="$router.push(snapshotEmptyAction.path)">
          {{ snapshotEmptyAction.label }}
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteFile, formatApiError, modelsStatus, statsOverview, type StatsOverview } from '@/api/client'
import {
  dataStateLabel,
  dataStateTagType,
  mapIntakeStatusToDataState,
} from '@/utils/dataStates'
import { DATA_SCOPE_DISCLAIMER, runtimeLevelTitle } from '@/utils/copywriting'
import { FIRST_USE_INTAKE_HINT } from '@/utils/modelRuntime'

const router = useRouter()
const loading = ref(false)
const overview = ref<StatsOverview | null>(null)
const runtimeLevel = ref<string>('')
const runtimeBlocking = ref<string[]>([])

const runtimeHint = computed(() => {
  const level = runtimeLevel.value
  if (!level || level === 'full') return null
  if (level === 'none') {
    return {
      title: runtimeLevelTitle('none'),
      type: 'error' as const,
      desc: '后端或 worker 未启动，上传解析与模型能力均不可用。请运行 ./scripts/start_dev_stack.sh 查看启动顺序。',
    }
  }
  if (level === 'dev_ok') {
    return {
      title: runtimeLevelTitle('dev_ok'),
      type: 'info' as const,
      desc: 'API 与前端已就绪，但本地模型服务未启动；规则路径可演示，智能建议与复杂问数不可用。',
    }
  }
  const impact =
    runtimeBlocking.value.length > 0
      ? runtimeBlocking.value.join('、')
      : '部分模型不可用或名称不匹配'
  return {
    title: runtimeLevelTitle('stage1_degraded'),
    type: 'warning' as const,
    desc: `影响：${impact}。复杂生成与语义召回可能降级；规则路径与数据接入仍可运行。可在「系统设置 → 本地模型」查看详情。`,
  }
})

function canEnterStage(status?: string): boolean {
  return ['evidence_done', 'staged', 'released'].includes(String(status || ''))
}

async function goStage(row: { file_id?: string; filename?: string; status?: string }) {
  if (!row.file_id) return
  if (row.status === 'failed') {
    ElMessage.warning('该文件解析失败，请先到「数据接入」页重试解析或重新上传')
    return
  }
  if (!canEnterStage(row.status)) {
    try {
      await ElMessageBox.confirm(
        `文件「${row.filename || row.file_id}」尚未完成解析（当前：${fileStateLabel(row.status)}）。\n进入规整页可能无法继续，是否仍要查看？`,
        '规整确认',
        { type: 'warning', confirmButtonText: '仍要查看', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  router.push(`/stage/${row.file_id}`)
}

const BIZ_METRICS: Record<string, { metric_id: string; hint: string }> = {
  sq: { metric_id: 'INV_QTY_TOTAL', hint: '米、个、包等计量单位不同，不能加总，故显示 —' },
  ac: { metric_id: 'ASSET_COUNT_TOTAL', hint: '资产台数' },
  fi: { metric_id: 'FLOW_IN_QTY_TOTAL', hint: '入库合计' },
  fo: { metric_id: 'FLOW_OUT_QTY_TOTAL', hint: '出库合计' },
}

function fmt(v: unknown) {
  if (v == null || v === '') return '—'
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) return '—'
    if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 1 })
    return String(Number(v.toFixed(2)))
  }
  return String(v)
}

function fmtBusinessMetric(v: unknown) {
  if (!shouldShowBusinessSnapshot.value) return '暂无'
  return fmt(v)
}

function fileStateLabel(status?: string) {
  const code = mapIntakeStatusToDataState(status)
  if (code) return dataStateLabel(code)
  return status || '—'
}

function fileStateTag(status?: string) {
  const code = mapIntakeStatusToDataState(status)
  return dataStateTagType(code)
}

const quality = computed(() => overview.value?.quality ?? { clean_rows: 0, blocked_rows: 0 })
const todos = computed(
  () =>
    overview.value?.todos ?? {
      map_pending: 0,
      master_pending: 0,
      flow_pending: 0,
      material_align: 0,
      ai_suggestion_pending: 0,
      total: 0,
    },
)

const nextAction = computed(
  () =>
    overview.value?.next_action ?? {
      code: 'intake',
      label: '上传物资文件',
      path: '/intake',
      reason: '',
    },
)
const recentFiles = computed(() => overview.value?.recent_files ?? [])

const hasRecentFiles = computed(() => recentFiles.value.length > 0)

const hasQualityRows = computed(() => {
  return ((quality.value.clean_rows ?? 0) > 0) || ((quality.value.blocked_rows ?? 0) > 0)
})

const hasPendingWork = computed(() => {
  return (todos.value.total ?? 0) > 0
})

const hasAnyBusinessMetric = computed(() => {
  const b = overview.value?.business
  if (!b) return false
  return [
    b.stock_qty_total,
    b.stock_value_total,
    b.quota_fill_ratio,
    b.stale_count,
    b.over_quota_count,
    b.asset_count,
    b.demand_qty_total,
    b.flow_in_qty,
    b.flow_out_qty,
  ].some((v) => v !== null && Number.isFinite(Number(v)) && Number(v) !== 0)
})

const shouldShowBusinessSnapshot = computed(() => {
  return (quality.value.clean_rows ?? 0) > 0 || hasAnyBusinessMetric.value
})

const businessSnapshotEmptyReason = computed(() => {
  if (!hasRecentFiles.value && !hasPendingWork.value && !hasQualityRows.value) {
    return '当前还没有可用业务数据'
  }
  return '数据正在接入或规整中，业务指标暂不可用'
})

const businessSnapshotDescription = computed(() => {
  if (hasPendingWork.value || (quality.value.blocked_rows ?? 0) > 0) {
    return '完成数据规整并形成可用数据后，这里会展示库存、需求、资产和流水概览。'
  }
  if (!hasRecentFiles.value) {
    return '请先完成数据接入，形成可用数据后，这里会展示库存、需求、资产和流水概览。'
  }
  return '请先完成字段/单位/物资/流水治理，形成可用数据后，这里会展示库存、需求、资产和流水概览。'
})

const businessSnapshotTitle = computed(() =>
  shouldShowBusinessSnapshot.value ? '业务数据概览' : '业务数据概览（暂无可用数据）',
)

const snapshotEmptyAction = computed(() => {
  if (nextAction.value.label) return { label: nextAction.value.label, path: nextAction.value.path || '/intake' }
  if (hasRecentFiles.value || hasPendingWork.value) return { label: '处理待办事项', path: '/govern' }
  return { label: '去数据接入', path: '/intake' }
})

const statusType = computed(() => {
  if ((todos.value.total || 0) > 0 || (quality.value.blocked_rows || 0) > 0) return 'warning'
  if ((quality.value.clean_rows || 0) > 0) return 'success'
  return 'info'
})

const statusTitle = computed(() => {
  if ((todos.value.total || 0) > 0) return '数据尚未全部可用：仍有待办需处理'
  if ((quality.value.blocked_rows || 0) > 0) return '部分数据被阻塞，暂不能全部进入可用结果'
  if ((quality.value.clean_rows || 0) > 0) return '当前有可用数据'
  if (hasRecentFiles.value) return '数据正在接入或规整中，业务指标暂不可用'
  return '当前还没有可用业务数据'
})

const statusDesc = computed(() => {
  return [
    `可用 ${fmt(quality.value.clean_rows)} 条`,
    `阻塞 ${fmt(quality.value.blocked_rows)} 条`,
    `待办 ${fmt(todos.value.total)} 项`,
  ].join(' · ')
})

const alertDesc = computed(() => {
  if ((quality.value.clean_rows || 0) > 0 && (todos.value.total || 0) === 0) {
    return DATA_SCOPE_DISCLAIMER
  }
  return statusDesc.value
})

const bizCards = computed(() => {
  const b = overview.value?.business
  const defs = [
    { key: 'sq', label: '库存总量', value: fmtBusinessMetric(b?.stock_qty_total) },
    { key: 'ac', label: '资产台数', value: fmtBusinessMetric(b?.asset_count) },
    { key: 'fi', label: '入库合计', value: fmtBusinessMetric(b?.flow_in_qty) },
    { key: 'fo', label: '出库合计', value: fmtBusinessMetric(b?.flow_out_qty) },
  ]
  return defs.map((d) => ({
    ...d,
    metric_id: BIZ_METRICS[d.key]?.metric_id || '',
    hint: BIZ_METRICS[d.key]?.hint || d.label,
  }))
})

function goMetric(metricId?: string) {
  if (!metricId) return
  router.push({ path: '/govern', query: { tab: 'advanced', id: metricId } })
}

async function onDeleteFile(row: { file_id?: string; filename?: string }) {
  if (!row.file_id) return
  const name = row.filename || row.file_id
  try {
    await ElMessageBox.confirm(
      `确定删除「${name}」吗？该文件及其规整记录、已发布业务数据将一并清除，且不可恢复。`,
      '删除文件',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }
  try {
    const res = await deleteFile(row.file_id)
    ElMessage.success(
      `已删除「${res.filename || name}」${res.releases_removed.length ? `（含 ${res.releases_removed.length} 次发布数据）` : ''}`,
    )
    await load()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

async function loadRuntime() {
  try {
    const ms = await modelsStatus()
    runtimeBlocking.value = Array.isArray(ms.blocking) ? ms.blocking : []
    if (ms.model_runtime) {
      runtimeLevel.value = ms.model_runtime
      return
    }
    const allOk = ms.big?.ok && ms.fast?.ok && ms.embed?.ok
    runtimeLevel.value = allOk ? 'full' : 'stage1_degraded'
  } catch {
    runtimeLevel.value = 'none'
    runtimeBlocking.value = ['api_not_ready']
  }
}

async function load() {
  loading.value = true
  try {
    overview.value = await statsOverview(5)
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadRuntime()
  void load()
})
</script>

<style scoped>
.home { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.cards.compact { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.biz-card, .card {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 12px 14px;
  background: var(--el-bg-color);
  transition: border-color 0.15s;
}
.biz-card, .card.clickable { cursor: pointer; }
.biz-card:hover, .card.clickable:hover { border-color: var(--el-color-primary); }
.card.warn { border-color: var(--el-color-warning-light-5); }
.card-label { color: #909399; font-size: 12px; margin-bottom: 6px; }
.card-value { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
.card-hint { color: #a8abb2; font-size: 11px; margin-top: 6px; line-height: 1.3; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.next-block { display: flex; flex-direction: column; gap: 12px; }
.next-reason { color: #606266; font-size: 14px; line-height: 1.5; }
.cta { display: flex; gap: 12px; flex-wrap: wrap; }
.biz-empty { padding: 4px 0; display: flex; flex-direction: column; align-items: flex-start; gap: 10px; }
.biz-empty-title { font-size: 14px; font-weight: 600; color: #606266; }
.biz-empty-desc { color: #909399; font-size: 13px; line-height: 1.6; }
.first-use-hint { max-width: 520px; margin: 0 0 12px; color: #909399; font-size: 13px; line-height: 1.6; text-align: center; }
@media (max-width: 720px) {
  .cards,
  .cards.compact { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
