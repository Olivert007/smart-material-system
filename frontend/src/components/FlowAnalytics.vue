<template>
  <div class="flow-analytics" ref="rootEl">
    <el-card shadow="never" class="filter-card">
      <div class="filter-bar">
        <el-select
          v-model="categories"
          multiple
          collapse-tags
          collapse-tags-tooltip
          clearable
          placeholder="物资种类（默认全部）"
          class="filter-item"
        >
          <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="year" clearable placeholder="年份（默认全部）" class="filter-year">
          <el-option v-for="y in yearOptions" :key="y" :label="y" :value="y" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
        <el-button @click="onReset">重置</el-button>
      </div>
    </el-card>

    <!-- 流水概览 KPI（参考报告 .kpi 卡片） -->
    <el-card shadow="never" v-if="summary">
      <template #header>
        <div class="head">
          <span>流水概览</span>
          <span class="sub" v-if="summaryRange">{{ summaryRange }}</span>
        </div>
      </template>
      <div v-loading="loading" class="kpis">
        <div class="kpi"><div class="v">{{ fmtNum(summary.total) }}</div><div class="k">流水总条数</div></div>
        <div class="kpi"><div class="v">{{ fmtNum(summary.in.qty) }}</div><div class="k">入库数量（{{ fmtNum(summary.in.count) }} 条）</div></div>
        <div class="kpi"><div class="v">{{ fmtNum(summary.out.qty) }}</div><div class="k">出库数量（{{ fmtNum(summary.out.count) }} 条）</div></div>
        <div class="kpi" :class="netClass"><div class="v">{{ fmtNum(summary.net) }}</div><div class="k">净变化（入库-出库）</div></div>
        <div class="kpi"><div class="v">{{ fmtNum(summary.materials) }}</div><div class="k">涉及物资数</div></div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>出入库按月趋势</span>
          <el-button link type="primary" @click="load">刷新</el-button>
        </div>
      </template>
      <div v-loading="loading" class="an-chart" ref="monthlyEl" />
      <p v-if="!loading && !monthly?.months?.length" class="hint">当前筛选下暂无流水</p>
    </el-card>

    <div class="grid2">
      <el-card shadow="never">
        <template #header>
          <div class="head">
            <span>Top 物资流水（入库/出库）</span>
            <el-input-number v-model="topN" :min="5" :max="50" size="small" @change="load" />
          </div>
        </template>
        <div v-loading="loading" class="an-chart" ref="topEl" />
        <p v-if="!loading && topEmpty" class="hint">当前筛选下暂无流水</p>
      </el-card>
      <el-card shadow="never">
        <template #header>
          <div class="head">
            <span>流水解析可信级别占比<template v-if="level">（共 {{ level.total ?? 0 }} 条）</template></span>
          </div>
        </template>
        <div v-loading="loading" class="an-chart an-chart-sm" ref="levelEl" />
        <p v-if="levelNote" class="level-note">{{ levelNote }}</p>
      </el-card>
    </div>

    <!-- 库存健康（参考报告 §3 台账 305-B + §4 溪洛渡概览） -->
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>库存健康分析</span>
        </div>
      </template>
      <div v-loading="loading" class="kpis" v-if="inventory">
        <div class="kpi"><div class="v">{{ fmtNum(inventory.total) }}</div><div class="k">库存条目数</div></div>
        <div class="kpi"><div class="v">{{ fmtNum(inventory.stock_qty_total) }}</div><div class="k">库存数量合计</div></div>
        <div class="kpi kpi-warn"><div class="v">{{ fmtNum(inventory.low_stock.count) }}</div><div class="k">低库存项</div></div>
        <div class="kpi kpi-danger"><div class="v">{{ fmtNum(inventory.over_quota.count) }}</div><div class="k">超定额项</div></div>
      </div>
      <div v-loading="loading" class="grid2">
        <div class="mini">
          <div class="chart-title">库存类别分布（条目数）</div>
          <div class="an-chart an-chart-sm" ref="invCatEl" />
        </div>
        <div class="mini">
          <div class="chart-title">库存区域分布</div>
          <div class="an-chart an-chart-sm" ref="invRegionEl" />
        </div>
        <div class="mini">
          <div class="chart-title">低库存 TOP（库存 &lt; 最低库存）</div>
          <div class="an-chart an-chart-sm" ref="invLowEl" />
          <p class="hint">展示缺口最大的 {{ inventory?.low_stock.items.length ?? 0 }} 项，共 {{ inventory?.low_stock.count ?? 0 }} 项</p>
        </div>
        <div class="mini">
          <div class="chart-title">超定额 TOP（库存 &gt; 定额）</div>
          <div class="an-chart an-chart-sm" ref="invOverEl" />
          <p class="hint">展示超出最多的 {{ inventory?.over_quota.items.length ?? 0 }} 项，共 {{ inventory?.over_quota.count ?? 0 }} 项</p>
        </div>
      </div>
    </el-card>

    <!-- 资产清查（参考报告 §2 资产清查分析） -->
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>资产清查分析</span>
        </div>
      </template>
      <div v-loading="loading" class="kpis" v-if="asset">
        <div class="kpi"><div class="v">{{ fmtNum(asset.total) }}</div><div class="k">资产总条数</div></div>
        <div class="kpi"><div class="v">{{ fmtNum(asset.company_count) }}</div><div class="k">涉及公司数</div></div>
        <div class="kpi"><div class="v">{{ fmtNum(asset.domain_count) }}</div><div class="k">涉及区域（域）数</div></div>
      </div>
      <div v-loading="loading" class="grid2">
        <div class="mini">
          <div class="chart-title">资产公司分布</div>
          <div class="an-chart an-chart-sm" ref="assetCompanyEl" />
        </div>
        <div class="mini">
          <div class="chart-title">资产区域（域）分布</div>
          <div class="an-chart an-chart-sm" ref="assetDomainEl" />
        </div>
        <div class="mini full">
          <div class="chart-title">资产购买年份分布</div>
          <div class="an-chart an-chart-sm" ref="assetYearEl" />
        </div>
      </div>
    </el-card>

    <!-- 需求（参考报告 §3 维护材料需求统计） -->
    <el-card shadow="never" v-if="demand && demand.total > 0">
      <template #header>
        <div class="head">
          <span>需求分析</span>
        </div>
      </template>
      <div v-loading="loading" class="kpis" v-if="demand">
        <div class="kpi"><div class="v">{{ fmtNum(demand.total) }}</div><div class="k">需求条数</div></div>
        <div class="kpi"><div class="v">{{ fmtNum(demand.quantity) }}</div><div class="k">需求数量合计</div></div>
        <div class="kpi"><div class="v">{{ fmtNum(demand.materials) }}</div><div class="k">涉及物资数</div></div>
      </div>
      <div v-loading="loading" class="grid2">
        <div class="mini full">
          <div class="chart-title">需求物资 TOP（按需求数量）</div>
          <div class="an-chart an-chart-sm" ref="demandTopEl" />
        </div>
      </div>
    </el-card>

    <!-- 定额调整（参考报告 §6 备品备件定额调整清单） -->
    <el-card shadow="never" v-if="quota && quota.total > 0">
      <template #header>
        <div class="head">
          <span>定额调整分析</span>
        </div>
      </template>
      <div v-loading="loading" class="kpis" v-if="quota">
        <div class="kpi"><div class="v">{{ fmtNum(quota.total) }}</div><div class="k">调整记录数</div></div>
      </div>
      <div v-loading="loading" class="grid2">
        <div class="mini">
          <div class="chart-title">调整类型分布</div>
          <div class="an-chart an-chart-sm" ref="quotaTypeEl" />
        </div>
        <div class="mini">
          <div class="chart-title">调整物资 TOP</div>
          <div class="an-chart an-chart-sm" ref="quotaTopEl" />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { LegacyGridContainLabel } from 'echarts/features'
import {
  flowFilters,
  flowLevel,
  flowMonthly,
  flowTop,
  flowSummary,
  inventoryHealth,
  assetOverview,
  demandOverview,
  quotaOverview,
  formatApiError,
  type FlowMonthly,
  type FlowSummary,
  type InventoryHealth,
  type AssetOverview,
  type DemandOverview,
  type QuotaOverview,
} from '@/api/client'

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
  LegacyGridContainLabel,
])

/** 发布级别业务含义（评审 §9）：可见内容只展示业务语义，不裸展示 L1/L2/L3。 */
const LEVEL_LABEL: Record<string, string> = {
  L1: '规则直接识别',
  L2: '规则校验后识别',
  L3: '需要人工确认',
}

const loading = ref(true)
const topN = ref(10)
const categories = ref<string[]>([])
const year = ref('')
const categoryOptions = ref<string[]>([])
const yearOptions = ref<string[]>([])
const topEmpty = ref(false)
const monthly = ref<FlowMonthly | null>(null)
const level = ref<{ total?: number; items?: Array<{ name: string; value: number }> } | null>(null)
const summary = ref<FlowSummary | null>(null)
const inventory = ref<InventoryHealth | null>(null)
const asset = ref<AssetOverview | null>(null)
const demand = ref<DemandOverview | null>(null)
const quota = ref<QuotaOverview | null>(null)
/** Top 物资聚合结果：由 load() 计算，供统一渲染（避免并发渲染互相清空）。 */
const topItems = ref<Array<{ key: string; displayName: string; inQty: number; outQty: number }>>([])

const rootEl = ref<HTMLDivElement | null>(null)

const monthlyEl = ref<HTMLDivElement | null>(null)
const topEl = ref<HTMLDivElement | null>(null)
const levelEl = ref<HTMLDivElement | null>(null)
const invCatEl = ref<HTMLDivElement | null>(null)
const invRegionEl = ref<HTMLDivElement | null>(null)
const invLowEl = ref<HTMLDivElement | null>(null)
const invOverEl = ref<HTMLDivElement | null>(null)
const assetCompanyEl = ref<HTMLDivElement | null>(null)
const assetDomainEl = ref<HTMLDivElement | null>(null)
const assetYearEl = ref<HTMLDivElement | null>(null)
const demandTopEl = ref<HTMLDivElement | null>(null)
const quotaTypeEl = ref<HTMLDivElement | null>(null)
const quotaTopEl = ref<HTMLDivElement | null>(null)
const charts: echarts.ECharts[] = []
let chartObserver: ResizeObserver | null = null

const summaryRange = computed(() => {
  const s = summary.value
  if (!s?.min_date && !s?.max_date) return ''
  return `${s.min_date || '?'} ~ ${s.max_date || '?'}`
})

const netClass = computed(() => (summary.value && summary.value.net >= 0 ? 'kpi-up' : 'kpi-down'))

const levelNote = computed(() => {
  const lv = level.value
  if (!lv?.items?.length) return ''
  const base = '识别方式：规则直接识别、规则校验后识别、需要人工确认。'
  if (lv.items.length === 1 && lv.total) {
    return `${base} 当前全部为 ${lv.items[0].name}，因此占比图只有一个扇区。`
  }
  return base
})

function fmtNum(v: unknown): string {
  const n = Number(v ?? 0)
  if (!Number.isFinite(n)) return '-'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function disposeCharts() {
  for (const c of charts) c.dispose()
  charts.length = 0
}

function makeChart(el: HTMLDivElement | null): echarts.ECharts | null {
  if (!el) return null
  const chart = echarts.init(el)
  charts.push(chart)
  // 容器布局可能尚未稳定（KPI 卡插入导致重排），初始化后强制对齐容器宽度
  requestAnimationFrame(() => chart.resize())
  return chart
}

/** 横向条形图（参考报告 barh_plot：TopN 名称反序 + 数值标注） */
function setBarh(
  el: HTMLDivElement | null,
  rows: Array<{ name: string; value: number }>,
  opts: { color?: string; valueLabel?: string } = {},
) {
  if (!el || !rows.length) return
  const names = rows.map((r) => r.name)
  const values = rows.map((r) => r.value)
  const chart = makeChart(el)
  if (!chart) return
  chart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 16, right: 60, top: 12, bottom: 8, containLabel: true },
    xAxis: { type: 'value' },
    yAxis: {
      type: 'category',
      data: [...names].reverse(),
      axisLabel: { fontSize: 11, width: 140, overflow: 'truncate', tooltip: { show: true } },
    },
    series: [
      {
        type: 'bar',
        data: [...values].reverse(),
        itemStyle: { color: opts.color || '#2f6fb2', borderRadius: [0, 3, 3, 0] },
        barMaxWidth: 16,
        label: { show: true, position: 'right', fontSize: 10, formatter: (p: any) => `${p.value}` },
      },
    ],
  })
}

/** 饼图（参考报告 pie_plot：占比标注） */
function setPie(
  el: HTMLDivElement | null,
  rows: Array<{ name: string; value: number }>,
  color?: string[],
) {
  if (!el || !rows.length) return
  const chart = makeChart(el)
  if (!chart) return
  chart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, type: 'scroll', fontSize: 11 },
    series: [
      {
        type: 'pie',
        radius: ['32%', '58%'],
        center: ['50%', '42%'],
        data: rows.map((r) => ({ name: r.name, value: r.value })),
        color,
        label: { show: true, position: 'outside', fontSize: 10, formatter: '{b}\n{d}%' },
        labelLine: { length: 8, length2: 6 },
        emphasis: { label: { fontWeight: 'bold' } },
      },
    ],
  })
}

function renderCharts() {
  disposeCharts()
  const t = topItems.value
  const m = monthly.value
  if (m?.months?.length && monthlyEl.value) {
    const chart = makeChart(monthlyEl.value)
    if (chart) {
      chart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { data: ['入库', '出库'], bottom: 0 },
        grid: { left: 44, right: 12, top: 16, bottom: 36, containLabel: true },
        xAxis: { type: 'category', data: m.months, boundaryGap: false },
        yAxis: { type: 'value', minInterval: 1 },
        series: [
          { name: '入库', type: 'line', data: m.in, smooth: true, itemStyle: { color: '#2f6fb2' } },
          { name: '出库', type: 'line', data: m.out, smooth: true, itemStyle: { color: '#d97706' } },
        ],
      })
    }
  }
  if (t.length && topEl.value) {
    const chart = makeChart(topEl.value)
    if (chart) {
      const fmtAxis = (v: string) => (v.length > 10 ? `${v.slice(0, 10)}…` : v)
      chart.setOption({
        tooltip: {
          trigger: 'axis',
          formatter: (params: any) => {
            const arr = Array.isArray(params) ? params : [params]
            const it = t[arr[0]?.dataIndex ?? 0]
            // 评审 §8.3：tooltip 只展示中文业务名称，不展示「编码：M-…」
            const lines = [it?.displayName || '']
            for (const p of arr) lines.push(`${p.marker}${p.seriesName}：${p.value}`)
            return lines.join('<br/>')
          },
        },
        legend: { data: ['入库', '出库'], bottom: 0 },
        grid: { left: 80, right: 16, top: 16, bottom: 40, containLabel: true },
        xAxis: {
          type: 'category',
          data: t.map((i) => i.displayName),
          axisLabel: { interval: 0, hideOverlap: true, rotate: 20, fontSize: 10, width: 90, overflow: 'truncate', formatter: fmtAxis },
        },
        yAxis: { type: 'value' },
        series: [
          { name: '入库', type: 'bar', data: t.map((i) => i.inQty), itemStyle: { color: '#2f6fb2' } },
          { name: '出库', type: 'bar', data: t.map((i) => i.outQty), itemStyle: { color: '#d97706' } },
        ],
      })
    }
  }
  const lv = level.value
  if (lv?.items?.length && levelEl.value) {
    const chart = makeChart(levelEl.value)
    if (chart) {
      const data = lv.items.map((i) => ({ name: LEVEL_LABEL[i.name] || i.name, value: i.value }))
      chart.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        legend: { bottom: 0 },
        series: [{
          type: 'pie',
          radius: ['38%', '62%'],
          center: ['50%', '44%'],
          data,
          label: { show: true, position: 'inside', fontSize: 10, color: '#fff', formatter: (p: any) => p.name },
          labelLine: { show: false },
        }],
      })
    }
  }

  // ---- 库存健康 ----
  const inv = inventory.value
  if (inv) {
    setBarh(invCatEl.value, inv.by_category.map((r) => ({ name: r.name, value: r.count })), { color: '#2f6fb2' })
    setPie(invRegionEl.value, inv.by_region.map((r) => ({ name: r.name, value: r.count })))
    setBarh(
      invLowEl.value,
      inv.low_stock.items.map((r) => ({ name: r.display_name, value: r.stock_qty })),
      { color: '#c0392b' },
    )
    setBarh(
      invOverEl.value,
      inv.over_quota.items.map((r) => ({ name: r.display_name, value: r.stock_qty })),
      { color: '#7d3c98' },
    )
  }

  // ---- 资产清查 ----
  const as = asset.value
  if (as) {
    setPie(assetCompanyEl.value, as.by_company.map((r) => ({ name: r.name, value: r.count })))
    setPie(assetDomainEl.value, as.by_domain.map((r) => ({ name: r.name, value: r.count })))
    if (assetYearEl.value && as.by_year.length) {
      const chart = makeChart(assetYearEl.value)
      if (chart) {
        chart.setOption({
          tooltip: { trigger: 'axis' },
          grid: { left: 44, right: 12, top: 16, bottom: 30, containLabel: true },
          xAxis: { type: 'category', data: as.by_year.map((r) => r.name) },
          yAxis: { type: 'value', minInterval: 1 },
          series: [
            {
              type: 'bar',
              data: as.by_year.map((r) => r.count),
              itemStyle: { color: '#16a085' },
              label: { show: true, position: 'top', fontSize: 9 },
            },
          ],
        })
      }
    }
  }

  // ---- 需求 ----
  if (demand.value) {
    setBarh(
      demandTopEl.value,
      demand.value.top.map((r) => ({ name: r.display_name, value: r.qty })),
      { color: '#d97706' },
    )
  }

  // ---- 定额调整 ----
  if (quota.value) {
    setPie(quotaTypeEl.value, quota.value.by_type.map((r) => ({ name: r.name, value: r.count })))
    setBarh(
      quotaTopEl.value,
      quota.value.top.map((r) => ({ name: r.display_name, value: r.count })),
      { color: '#2f6fb2' },
    )
  }
}

function query() {
  return {
    categories: categories.value,
    year: year.value || undefined,
  }
}

async function loadFilters() {
  try {
    const f = await flowFilters()
    categoryOptions.value = f.categories || []
    yearOptions.value = f.years || []
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

function onReset() {
  categories.value = []
  year.value = ''
  void load()
}

async function load() {
  loading.value = true
  try {
    const q = query()
    // 流水与概览板块一次性并行加载，最后统一渲染一次，避免多次 renderCharts 竞态
    const [m, top, lv, sm, inv, as, dm, qt] = await Promise.all([
      flowMonthly(q),
      flowTop(topN.value, q),
      flowLevel(),
      flowSummary(q),
      inventoryHealth(10),
      assetOverview(12),
      demandOverview(10),
      quotaOverview(10),
    ])
    monthly.value = m
    level.value = lv
    summary.value = sm
    inventory.value = inv
    asset.value = as
    demand.value = dm
    quota.value = qt
    // 聚合 key 用 asset_code||material_id，内部按编码对齐，不以中文名合并
    const byKey = new Map<string, { key: string; displayName: string; inQty: number; outQty: number }>()
    for (const it of top.items || []) {
      const code = (it.asset_code || '').trim() || it.material_id
      // 评审 §8.2：坐标轴只展示中文业务名称；无中文名时不暴露内部编号
      let name = it.display_name || it.material_name || ''
      if (!name || name === code) name = '未命名物资'
      const cur = byKey.get(code) || { key: code, displayName: name, inQty: 0, outQty: 0 }
      if (name) cur.displayName = name
      if (it.flow_type === 'IN') cur.inQty += Number(it.qty) || 0
      else cur.outQty += Number(it.qty) || 0
      byKey.set(code, cur)
    }
    // 同名不同编码的物资用中性序号区分（如「光纤适配器（2）」），不暴露内部编号
    const nameCount = new Map<string, number>()
    const marked = new Set<string>()
    for (const v of byKey.values()) {
      const n = v.displayName
      const seen = nameCount.get(n) || 0
      if (seen > 0 && !marked.has(n)) {
        marked.add(n)
        v.displayName = `${n}（${seen + 1}）`
      }
      nameCount.set(n, seen + 1)
    }
    const topItemsArr = Array.from(byKey.values()).sort((a, b) => b.inQty + b.outQty - a.inQty - a.outQty).slice(0, topN.value)
    topItems.value = topItemsArr
    topEmpty.value = topItemsArr.length === 0
    requestAnimationFrame(() => renderCharts())
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    loading.value = false
  }
}

function onResize() {
  for (const c of charts) c.resize()
}

onMounted(() => {
  void loadFilters()
  void load()
  window.addEventListener('resize', onResize)
  // 布局随视口变化重排（如 grid 列数变化）时，同步缩放所有图表
  if (rootEl.value && typeof ResizeObserver !== 'undefined') {
    chartObserver = new ResizeObserver(() => {
      for (const c of charts) c.resize()
    })
    chartObserver.observe(rootEl.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chartObserver?.disconnect()
  disposeCharts()
})

defineExpose({ load })
</script>

<style scoped>
.flow-analytics { display: flex; flex-direction: column; gap: 16px; }
.filter-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.filter-item { width: 240px; max-width: 100%; }
.filter-year { width: 160px; max-width: 100%; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.head .sub { color: #909399; font-size: 12px; font-weight: 400; }
.an-chart { width: 100%; height: 320px; }
.an-chart-sm { height: 220px; }
.hint { color: #909399; font-size: 13px; margin: 8px 0 0; }
.level-note { color: #606266; font-size: 13px; margin: 10px 0 0; line-height: 1.6; }

/* KPI 指标卡（参考报告 .kpis/.kpi 展示）：自适应网格，自动均分行宽、按宽度换行 */
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; }
.kpi {
  background: #fff;
  border-radius: 10px;
  padding: 14px 20px;
  min-width: 0;
  border-left: 5px solid #2f6fb2;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}
.kpi .v { font-size: 24px; font-weight: 700; color: #1e3a5f; line-height: 1.2; }
.kpi .k { font-size: 12px; color: #666; margin-top: 4px; }
.kpi-up { border-left-color: #2f6fb2; }
.kpi-down { border-left-color: #c0392b; }
.kpi-down .v { color: #c0392b; }
.kpi-warn { border-left-color: #d97706; }
.kpi-warn .v { color: #d97706; }
.kpi-danger { border-left-color: #c0392b; }
.kpi-danger .v { color: #c0392b; }

/* 图表网格（参考报告 .grid2 布局）：流体自适应列数，无需固定断点 */
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 18px; }
.mini .chart-title { color: #555; font-size: 13px; margin: 2px 0 6px; }
.mini.full { grid-column: 1 / -1; }
</style>
