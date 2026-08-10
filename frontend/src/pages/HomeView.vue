<template>
  <div class="home">
    <el-alert
      v-if="todoText"
      :title="todoText"
      :type="overview?.flow?.pending ? 'warning' : 'info'"
      :closable="false"
      show-icon
    >
      <template v-if="overview?.flow?.pending" #default>
        <el-button link type="primary" @click="$router.push('/govern')">去治理中心</el-button>
      </template>
    </el-alert>

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>业务快照</span>
          <el-button size="small" :loading="loading" @click="load">刷新</el-button>
        </div>
      </template>
      <div class="cards" v-loading="loading">
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
          <el-table :data="overview.business.top_by_category || []" border size="small" empty-text="无">
            <el-table-column prop="name" label="类别" min-width="120" />
            <el-table-column prop="value" label="库存量" width="100" />
          </el-table>
        </div>
        <div>
          <div class="sub">按库位 Top</div>
          <el-table :data="overview.business.top_by_location || []" border size="small" empty-text="无">
            <el-table-column prop="name" label="库位" min-width="120" />
            <el-table-column prop="value" label="库存量" width="100" />
          </el-table>
        </div>
        <div>
          <div class="sub">按单位 Top（不同单位不能直接相加）</div>
          <el-table :data="overview.business.top_by_unit || []" border size="small" empty-text="无">
            <el-table-column prop="name" label="单位" min-width="120" />
            <el-table-column prop="value" label="库存量" width="100" />
          </el-table>
        </div>
      </div>
      <div v-if="mini?.months?.length" class="spark">
        <div class="sub">近 6 月出入库趋势</div>
        <div ref="sparkEl" class="spark-chart" />
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>数据规模（表行数）</span>
          <el-button size="small" type="primary" @click="$router.push('/data')">进入数据中心</el-button>
        </div>
      </template>
      <p class="hint">行数为物理表记录数，与上方业务指标口径不同；明细含物资名称请进数据中心浏览。</p>
      <div class="cards compact" v-loading="loading">
        <div
          v-for="c in tableCards"
          :key="c.key"
          class="card"
          @click="c.table && $router.push({ path: '/data', query: { tab: 'detail', table: c.table } })"
        >
          <div class="card-label">{{ c.label }}</div>
          <div class="card-value">{{ c.value }}</div>
        </div>
      </div>
    </el-card>

    <el-card v-if="recentFile" shadow="never">
      <template #header>最近接入</template>
      <div class="recent-line">
        <span>{{ recentFile.filename }} · {{ recentFile.status }} · {{ recentFile.rows }} 行 · {{ recentFile.created_at }}</span>
        <el-button link type="primary" @click="$router.push('/intake')">查看任务</el-button>
      </div>
    </el-card>

    <div class="cta">
      <el-button v-if="(overview?.flow?.pending ?? 0) > 0" type="warning" @click="$router.push('/govern')">
        处理 {{ overview?.flow?.pending }} 条流水待确认
      </el-button>
      <el-button v-else type="primary" @click="$router.push('/data')">浏览库存明细</el-button>
      <el-button @click="$router.push('/ask')">问一个问题</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { flowMonthly, formatApiError, statsOverview, type FlowMonthly, type StatsOverview } from '@/api/client'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const router = useRouter()
const loading = ref(false)
const overview = ref<StatsOverview | null>(null)
const mini = ref<FlowMonthly | null>(null)
const sparkEl = ref<HTMLDivElement | null>(null)
let sparkChart: echarts.ECharts | null = null

const BIZ_METRICS: Record<string, { metric_id: string; hint: string }> = {
  sq: { metric_id: 'INV_QTY_TOTAL', hint: '库存总量 = SUM(stock_qty)' },
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

const bizCards = computed(() => {
  const b = overview.value?.business
  const defs = [
    { key: 'sq', label: '库存总量', value: fmt(b?.stock_qty_total) },
    { key: 'sv', label: '库存金额', value: fmt(b?.stock_value_total) },
    { key: 'qf', label: '定额利用率', value: fmt(b?.quota_fill_ratio) },
    { key: 'oq', label: '超定额物资', value: fmt(b?.over_quota_count) },
    { key: 'st', label: '呆滞料行', value: fmt(b?.stale_count) },
    { key: 'dq', label: '需求总量', value: fmt(b?.demand_qty_total) },
    { key: 'ac', label: '资产台数', value: fmt(b?.asset_count) },
    { key: 'fi', label: '入库合计', value: fmt(b?.flow_in_qty) },
    { key: 'fo', label: '出库合计', value: fmt(b?.flow_out_qty) },
  ]
  return defs.map((d) => ({
    ...d,
    metric_id: BIZ_METRICS[d.key]?.metric_id || '',
    hint: BIZ_METRICS[d.key]?.hint || d.label,
  }))
})

const tableCards = computed(() => {
  const t = overview.value?.tables || {}
  return [
    { key: 'dim', label: '主数据', table: 'dim_material', value: t.dim_material ?? '—' },
    { key: 'inv', label: '库存', table: 'fact_inventory', value: t.fact_inventory ?? '—' },
    { key: 'asset', label: '资产', table: 'fact_asset', value: t.fact_asset ?? '—' },
    { key: 'demand', label: '需求', table: 'fact_demand', value: t.fact_demand ?? '—' },
    { key: 'flow', label: '流水', table: 'fact_stock_flow', value: t.fact_stock_flow ?? '—' },
  ]
})

const recentFile = computed(() => overview.value?.recent_files?.[0] ?? null)

const todoText = computed(() => {
  const pending = overview.value?.flow?.pending ?? 0
  const gate = overview.value?.gate?.ready
  if (pending > 0) return `流水待确认 ${pending} 条`
  if (!gate) return `数据门禁未就绪${overview.value?.gate?.missing?.length ? '：' + overview.value!.gate!.missing!.join('、') : ''}`
  return ''
})

function goMetric(metricId?: string) {
  if (!metricId) return
  router.push({ path: '/govern', query: { tab: 'metrics', id: metricId } })
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
.home { display: flex; flex-direction: column; gap: 16px; max-width: 1100px; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; }
.cards.compact { grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); }
.biz-card, .card {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 12px 14px;
  background: var(--el-bg-color);
  cursor: pointer;
  transition: border-color 0.15s;
}
.biz-card:hover, .card:hover { border-color: var(--el-color-primary); }
.card-label { color: #909399; font-size: 12px; margin-bottom: 6px; }
.card-value { font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums; }
.tops { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
.sub { color: #606266; font-size: 13px; margin-bottom: 6px; }
.spark { margin-top: 14px; }
.spark-chart { width: 100%; height: 150px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.hint { color: #909399; font-size: 13px; margin: 0 0 12px; }
.recent-line { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; font-size: 13px; }
.cta { display: flex; gap: 12px; flex-wrap: wrap; }
@media (max-width: 720px) { .tops { grid-template-columns: 1fr; } }
</style>
