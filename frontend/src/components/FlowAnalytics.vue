<template>
  <div class="flow-analytics">
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
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>Top 物资流水（入库/出库）</span>
        </div>
      </template>
      <div v-loading="loading" class="an-chart" ref="topEl" />
      <p v-if="!loading && topEmpty" class="hint">当前筛选下暂无流水</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { LegacyGridContainLabel } from 'echarts/features'
import { flowFilters, flowMonthly, flowTop, formatApiError, type FlowMonthly } from '@/api/client'

echarts.use([
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
  LegacyGridContainLabel,
])

const loading = ref(true)
const topN = ref(10)
const categories = ref<string[]>([])
const year = ref('')
const categoryOptions = ref<string[]>([])
const yearOptions = ref<string[]>([])
const topEmpty = ref(false)
const monthly = ref<FlowMonthly | null>(null)
const monthlyEl = ref<HTMLDivElement | null>(null)
const topEl = ref<HTMLDivElement | null>(null)
const charts: echarts.ECharts[] = []

function disposeCharts() {
  for (const c of charts) c.dispose()
  charts.length = 0
}

function renderCharts(topItems: Array<{ key: string; displayName: string; inQty: number; outQty: number }>) {
  disposeCharts()
  const m = monthly.value
  if (m?.months?.length && monthlyEl.value) {
    const chart = echarts.init(monthlyEl.value)
    charts.push(chart)
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['入库', '出库'], bottom: 0 },
      grid: { left: 44, right: 12, top: 16, bottom: 36, containLabel: true },
      xAxis: { type: 'category', data: m.months, boundaryGap: false },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        { name: '入库', type: 'line', data: m.in, smooth: true },
        { name: '出库', type: 'line', data: m.out, smooth: true },
      ],
    })
  }
  if (topItems.length && topEl.value) {
    const chart = echarts.init(topEl.value)
    charts.push(chart)
    const fmtAxis = (v: string) => (v.length > 10 ? `${v.slice(0, 10)}…` : v)
    chart.setOption({
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const arr = Array.isArray(params) ? params : [params]
          const it = topItems[arr[0]?.dataIndex ?? 0]
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
        data: topItems.map((i) => i.displayName),
        axisLabel: { interval: 0, hideOverlap: true, rotate: 20, fontSize: 10, width: 90, overflow: 'truncate', formatter: fmtAxis },
      },
      yAxis: { type: 'value' },
      series: [
        { name: '入库', type: 'bar', data: topItems.map((i) => i.inQty) },
        { name: '出库', type: 'bar', data: topItems.map((i) => i.outQty) },
      ],
    })
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
    const [m, top] = await Promise.all([flowMonthly(q), flowTop(topN.value, q)])
    monthly.value = m
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
    const topItems = Array.from(byKey.values()).sort((a, b) => b.inQty + b.outQty - a.inQty - a.outQty).slice(0, topN.value)
    topEmpty.value = topItems.length === 0
    requestAnimationFrame(() => renderCharts(topItems))
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
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  disposeCharts()
})

defineExpose({ load })
</script>

<style scoped>
.flow-analytics { display: flex; flex-direction: column; gap: 16px; }
.filter-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.filter-item { width: 240px; max-width: 100%; }
.filter-year { width: 160px; max-width: 100%; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.an-chart { width: 100%; height: 320px; }
.hint { color: #909399; font-size: 13px; margin: 8px 0 0; }
</style>
