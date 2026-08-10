<template>
  <div class="flow-analytics">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="流水分析（只读）"
      description="出入库按月趋势、Top 物资、L1/L2/L3 占比；口径与种子报表一致，可互验。"
    />
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>出入库按月趋势</span>
          <el-button link type="primary" @click="load">刷新</el-button>
        </div>
      </template>
      <div v-loading="loading" class="an-chart" ref="monthlyEl" />
      <p v-if="!monthly?.months?.length" class="hint">暂无流水数据</p>
    </el-card>
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>Top 物资流水（IN/OUT）</span>
          <el-input-number v-model="topN" :min="5" :max="50" size="small" @change="load" />
        </div>
      </template>
      <div v-loading="loading" class="an-chart" ref="topEl" />
    </el-card>
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>发布级别占比（共 {{ level?.total ?? 0 }} 条）</span>
        </div>
      </template>
      <div v-loading="loading" class="an-chart an-chart-sm" ref="levelEl" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { flowLevel, flowMonthly, flowTop, formatApiError, type FlowMonthly } from '@/api/client'

echarts.use([BarChart, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const loading = ref(false)
const topN = ref(10)
const monthly = ref<FlowMonthly | null>(null)
const level = ref<{ total?: number; items?: Array<{ name: string; value: number }> } | null>(null)
const monthlyEl = ref<HTMLDivElement | null>(null)
const topEl = ref<HTMLDivElement | null>(null)
const levelEl = ref<HTMLDivElement | null>(null)
const charts: echarts.ECharts[] = []

function disposeCharts() {
  for (const c of charts) c.dispose()
  charts.length = 0
}

function renderCharts(topItems: Array<{ material_id: string; inQty: number; outQty: number }>) {
  disposeCharts()
  const m = monthly.value
  if (m?.months?.length && monthlyEl.value) {
    const chart = echarts.init(monthlyEl.value)
    charts.push(chart)
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['入库', '出库'], bottom: 0 },
      grid: { left: 44, right: 12, top: 12, bottom: 28 },
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
    const ids = topItems.map((i) => i.material_id)
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['入库', '出库'], bottom: 0 },
      grid: { left: 80, right: 12, top: 12, bottom: 28 },
      xAxis: { type: 'category', data: ids, axisLabel: { rotate: 30, fontSize: 10 } },
      yAxis: { type: 'value' },
      series: [
        { name: '入库', type: 'bar', data: topItems.map((i) => i.inQty) },
        { name: '出库', type: 'bar', data: topItems.map((i) => i.outQty) },
      ],
    })
  }
  const lv = level.value
  if (lv?.items?.length && levelEl.value) {
    const chart = echarts.init(levelEl.value)
    charts.push(chart)
    chart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 0 },
      series: [{
        type: 'pie',
        radius: ['38%', '66%'],
        data: lv.items.map((i) => ({ name: i.name, value: i.value })),
        label: { formatter: '{b}: {c}' },
      }],
    })
  }
}

async function load() {
  loading.value = true
  try {
    const [m, top, lv] = await Promise.all([flowMonthly(), flowTop(topN.value), flowLevel()])
    monthly.value = m
    level.value = lv
    const byId = new Map<string, { material_id: string; inQty: number; outQty: number }>()
    for (const it of top.items || []) {
      const cur = byId.get(it.material_id) || { material_id: it.material_id, inQty: 0, outQty: 0 }
      if (it.flow_type === 'IN') cur.inQty += Number(it.qty) || 0
      else cur.outQty += Number(it.qty) || 0
      byId.set(it.material_id, cur)
    }
    const topItems = Array.from(byId.values()).sort((a, b) => b.inQty + b.outQty - a.inQty - b.outQty).slice(0, topN.value)
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
.head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.an-chart { width: 100%; height: 280px; }
.an-chart-sm { height: 220px; }
.hint { color: #909399; font-size: 13px; margin: 8px 0 0; }
</style>
