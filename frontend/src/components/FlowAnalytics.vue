<template>
  <div class="flow-analytics">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="流水分析（只读）"
      description="出入库按月趋势、Top 物资、L1/L2/L3 占比；基于可用候选数据，非正式发布报表。"
    />
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="数据范围：可用 · 非正式发布"
      description="状态：可用。下载或截图不等于正式发布；请核对口径与来源版本。"
      style="margin-bottom: 8px"
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

function renderCharts(topItems: Array<{ key: string; displayName: string; code: string; inQty: number; outQty: number }>) {
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
          const lines = [it?.displayName || '']
          if (it?.code) lines.push(`编码：${it.code}`)
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
  const lv = level.value
  if (lv?.items?.length && levelEl.value) {
    const chart = echarts.init(levelEl.value)
    charts.push(chart)
    chart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 0 },
      series: [{
        type: 'pie',
        radius: ['38%', '62%'],
        center: ['50%', '44%'],
        data: lv.items.map((i) => ({ name: i.name, value: i.value })),
        label: { show: true, position: 'inside', fontSize: 11, color: '#fff' },
        labelLine: { show: false },
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
    // 聚合 key 用 asset_code||material_id，内部按编码对齐，不以中文名合并
    const byKey = new Map<string, { key: string; displayName: string; code: string; inQty: number; outQty: number }>()
    for (const it of top.items || []) {
      const code = (it.asset_code || '').trim() || it.material_id
      const name = it.display_name || it.material_name || code
      const cur = byKey.get(code) || { key: code, displayName: name, code, inQty: 0, outQty: 0 }
      if (name) cur.displayName = name
      if (it.flow_type === 'IN') cur.inQty += Number(it.qty) || 0
      else cur.outQty += Number(it.qty) || 0
      byKey.set(code, cur)
    }
    const topItems = Array.from(byKey.values()).sort((a, b) => b.inQty + b.outQty - a.inQty - a.outQty).slice(0, topN.value)
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
.an-chart { width: 100%; height: 320px; }
.an-chart-sm { height: 240px; }
.hint { color: #909399; font-size: 13px; margin: 8px 0 0; }
</style>
