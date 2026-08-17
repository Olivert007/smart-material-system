<template>
  <div class="home">
    <el-alert
      :title="statusTitle"
      :type="statusType"
      :closable="false"
      show-icon
      :description="statusDesc"
    />

    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="head">
          <span>当前数据状态</span>
          <el-button size="small" :loading="loading" @click="load">刷新</el-button>
        </div>
      </template>
      <div class="cards">
        <div class="card">
          <div class="card-label">可用记录（候选）</div>
          <div class="card-value">{{ fmt(quality.clean_rows) }}</div>
          <div class="card-hint">通过门禁的规整结果，不等于正式发布</div>
        </div>
        <div class="card warn">
          <div class="card-label">阻塞记录</div>
          <div class="card-value">{{ fmt(quality.blocked_rows) }}</div>
          <div class="card-hint">未解决异常或未确认项</div>
        </div>
        <div class="card">
          <div class="card-label">可用率</div>
          <div class="card-value">{{ availabilityRate }}</div>
          <div class="card-hint">可用候选 ÷（可用 + 阻塞）；候选 ≠ 正式发布</div>
        </div>
        <div class="card clickable" @click="$router.push({ path: '/govern', query: { tab: 'map' } })">
          <div class="card-label">待确认字段</div>
          <div class="card-value">{{ fmt(todos.map_pending) }}</div>
        </div>
        <div class="card clickable" @click="$router.push({ path: '/govern', query: { tab: 'master' } })">
          <div class="card-label">待匹配物资</div>
          <div class="card-value">{{ fmt((todos.master_pending || 0) + (todos.material_align || 0)) }}</div>
        </div>
        <div class="card clickable warn" @click="$router.push({ path: '/govern', query: { tab: 'map' } })">
          <div class="card-label">待审核 AI 建议</div>
          <div class="card-value">{{ fmt(aiSuggestionPending) }}</div>
          <div class="card-hint">模型/候选建议，须人工确认</div>
        </div>
        <div class="card clickable" @click="$router.push({ path: '/govern', query: { tab: 'flow' } })">
          <div class="card-label">流水待确认</div>
          <div class="card-value">{{ fmt(todos.flow_pending) }}</div>
        </div>
        <div class="card clickable" @click="$router.push({ path: '/govern' })">
          <div class="card-label">待办合计</div>
          <div class="card-value">{{ fmt(todos.total) }}</div>
        </div>
        <div class="card ok clickable" @click="$router.push({ path: '/govern' })">
          <div class="card-label">处理后预计释放</div>
          <div class="card-value">{{ fmt(releasableRows) }}</div>
          <div class="card-hint">处理本批待办后约可进入可用的行数（估算）</div>
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
          <el-button @click="$router.push('/data')">查看数据成果</el-button>
          <el-button @click="$router.push('/ask')">问数助手</el-button>
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
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button
              v-if="row.file_id"
              link
              type="primary"
              @click="$router.push(`/stage/${row.file_id}`)"
            >
              规整确认
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="尚未接入文件，请先上传原始数据">
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
        <p class="hint">基于已入库可用候选数据；不等于正式发布报表。</p>
        <div class="cards compact" v-loading="loading">
          <el-tooltip v-for="c in bizCards" :key="c.key" :content="c.hint" placement="top">
            <div class="card biz-card" @click="goMetric(c.metric_id)">
              <div class="card-label">{{ c.label }}</div>
              <div class="card-value">{{ c.value }}</div>
            </div>
          </el-tooltip>
        </div>
        <div class="tops" v-if="overview?.business">
          <div>
            <div class="sub">按类别 Top</div>
            <el-table :data="overview.business.top_by_category || []" border size="small" empty-text="暂无可用分类数据">
              <el-table-column prop="name" label="类别" min-width="120" />
              <el-table-column prop="value" label="库存量" width="100" />
            </el-table>
          </div>
          <div>
            <div class="sub">按库位 Top</div>
            <el-table :data="overview.business.top_by_location || []" border size="small" empty-text="暂无可用库位数据">
              <el-table-column prop="name" label="库位" min-width="120" />
              <el-table-column prop="value" label="库存量" width="100" />
            </el-table>
          </div>
        </div>
        <div v-if="mini?.months?.length" class="spark">
          <div class="sub">近 6 月出入库趋势</div>
          <div ref="sparkEl" class="spark-chart" />
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
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { flowMonthly, formatApiError, statsOverview, type FlowMonthly, type StatsOverview } from '@/api/client'
import {
  dataStateLabel,
  dataStateTagType,
  mapIntakeStatusToDataState,
} from '@/utils/dataStates'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const router = useRouter()
const loading = ref(false)
const overview = ref<StatsOverview | null>(null)
const mini = ref<FlowMonthly | null>(null)
const sparkEl = ref<HTMLDivElement | null>(null)
let sparkChart: echarts.ECharts | null = null

const BIZ_METRICS: Record<string, { metric_id: string; hint: string }> = {
  sq: { metric_id: 'INV_QTY_TOTAL', hint: '米、个、包等计量单位不同，不能加总，故显示 —' },
  sv: { metric_id: 'INV_VALUE_TOTAL', hint: '库存金额（无有效单价时可能暂无数据）' },
  qf: { metric_id: 'INV_QUOTA_FILL_RATIO', hint: '定额利用率' },
  oq: { metric_id: 'INV_OVER_QUOTA_CNT', hint: '超定额物资行数' },
  st: { metric_id: 'INV_STALE_CNT', hint: '呆滞料行' },
  dq: { metric_id: 'DEMAND_QTY_TOTAL', hint: '需求总量' },
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

const aiSuggestionPending = computed(() => {
  const t = todos.value
  if (t.ai_suggestion_pending != null) return t.ai_suggestion_pending
  return (
    (t.map_pending || 0) +
    (t.master_pending || 0) +
    (t.material_align || 0) +
    (t.flow_pending || 0)
  )
})
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
    return '请先完成数据接入，形成可用候选数据后，这里会展示库存、需求、资产和流水概览。'
  }
  return '请先完成字段/单位/物资/流水治理，形成可用候选数据后，这里会展示库存、需求、资产和流水概览。'
})

const businessSnapshotTitle = computed(() =>
  shouldShowBusinessSnapshot.value ? '业务数据概览' : '业务数据概览（暂无可用数据）',
)

const snapshotEmptyAction = computed(() => {
  if (nextAction.value.label) return { label: nextAction.value.label, path: nextAction.value.path || '/intake' }
  if (hasRecentFiles.value || hasPendingWork.value) return { label: '处理待办事项', path: '/govern' }
  return { label: '去数据接入', path: '/intake' }
})

const availabilityRate = computed(() => {
  const clean = Number(quality.value.clean_rows) || 0
  const blocked = Number(quality.value.blocked_rows) || 0
  const denom = clean + blocked
  if (denom <= 0) return '—'
  return `${((clean / denom) * 100).toFixed(1)}%`
})

const releasableRows = computed(
  () => overview.value?.estimated_releasable_rows ?? 0,
)

const statusType = computed(() => {
  if ((todos.value.total || 0) > 0 || (quality.value.blocked_rows || 0) > 0) return 'warning'
  if ((quality.value.clean_rows || 0) > 0) return 'success'
  return 'info'
})

const statusTitle = computed(() => {
  if ((todos.value.total || 0) > 0) return '数据尚未全部可用：仍有待办需处理'
  if ((quality.value.blocked_rows || 0) > 0) return '部分数据被阻塞，暂不能全部进入可用结果'
  if ((quality.value.clean_rows || 0) > 0) return '当前有可用候选数据（不等于正式发布）'
  if (hasRecentFiles.value) return '数据正在接入或规整中，业务指标暂不可用'
  return '当前还没有可用业务数据'
})

const statusDesc = computed(() => {
  const gate = overview.value?.gate
  const parts = [
    `可用候选 ${fmt(quality.value.clean_rows)} 条`,
    `阻塞 ${fmt(quality.value.blocked_rows)} 条`,
    `可用率 ${availabilityRate.value}`,
    `待办 ${fmt(todos.value.total)} 项`,
  ]
  if ((releasableRows.value || 0) > 0) {
    parts.push(`处理后预计释放 ${fmt(releasableRows.value)} 条`)
  }
  if (gate && gate.ready === false && gate.missing?.length) {
    parts.push('门禁未就绪，需先完成数据接入与发布')
  }
  return parts.join(' · ')
})

const bizCards = computed(() => {
  const b = overview.value?.business
  const defs = [
    { key: 'sq', label: '库存总量', value: fmtBusinessMetric(b?.stock_qty_total) },
    { key: 'sv', label: '库存金额', value: fmtBusinessMetric(b?.stock_value_total) },
    { key: 'qf', label: '定额利用率', value: fmtBusinessMetric(b?.quota_fill_ratio) },
    { key: 'oq', label: '超定额物资', value: fmtBusinessMetric(b?.over_quota_count) },
    { key: 'st', label: '呆滞料行', value: fmtBusinessMetric(b?.stale_count) },
    { key: 'dq', label: '需求总量', value: fmtBusinessMetric(b?.demand_qty_total) },
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

function renderSpark() {
  const m = mini.value
  if (!m?.months?.length || !sparkEl.value) return
  if (!sparkChart) sparkChart = echarts.init(sparkEl.value)
  const n = 6
  sparkChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['入库', '出库'], bottom: 0 },
    grid: { left: 44, right: 12, top: 12, bottom: 28 },
    xAxis: { type: 'category', data: m.months.slice(-n), boundaryGap: false },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '入库', type: 'line', data: m.in.slice(-n), smooth: true, areaStyle: { opacity: 0.12 } },
      { name: '出库', type: 'line', data: m.out.slice(-n), smooth: true, areaStyle: { opacity: 0.12 } },
    ],
  })
}

async function loadSpark() {
  try {
    mini.value = await flowMonthly()
    await nextTick()
    renderSpark()
  } catch {
    /* optional */
  }
}

function onResize() {
  sparkChart?.resize()
}

onMounted(async () => {
  await load()
  await loadSpark()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  sparkChart?.dispose()
  sparkChart = null
})
</script>

<style scoped>
.home { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}
.cards.compact { grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); }
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
.card.ok { border-color: var(--el-color-success-light-5); }
.card-label { color: #909399; font-size: 12px; margin-bottom: 6px; }
.card-value { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
.card-hint { color: #a8abb2; font-size: 11px; margin-top: 6px; line-height: 1.3; }
.tops { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 12px; }
.sub { color: #606266; font-size: 13px; margin-bottom: 6px; }
.spark { margin-top: 14px; }
.spark-chart { width: 100%; height: 150px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.hint { color: #909399; font-size: 13px; margin: 0 0 12px; }
.next-block { display: flex; flex-direction: column; gap: 12px; }
.next-reason { color: #606266; font-size: 14px; line-height: 1.5; }
.cta { display: flex; gap: 12px; flex-wrap: wrap; }
.biz-empty { padding: 4px 0; display: flex; flex-direction: column; align-items: flex-start; gap: 10px; }
.biz-empty-title { font-size: 14px; font-weight: 600; color: #606266; }
.biz-empty-desc { color: #909399; font-size: 13px; line-height: 1.6; }
@media (max-width: 960px) { .tops { grid-template-columns: 1fr; } }
</style>
