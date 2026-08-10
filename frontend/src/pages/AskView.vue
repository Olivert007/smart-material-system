<template>
  <div class="ask">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="自然语言查数（指标模板优先）"
      description="优先命中指标字典统一口径，无需大模型推算；未命中时自动生成查询并做语法校验。流水类指标草稿状态会提示质量门禁。"
    />

    <div class="composer">
      <el-input
        v-model="question"
        type="textarea"
        :rows="3"
        placeholder="例如：库存表有多少行 / 按库位统计库存记录数"
        @keydown.ctrl.enter="runAsk"
      />
      <div class="composer-actions">
        <el-button type="primary" :loading="busy" :disabled="!question.trim()" @click="runAsk">
          提问
        </el-button>
        <el-dropdown trigger="click" @command="(q: string) => (question = q)">
          <el-button>示例问题</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="ex in examples" :key="ex" :command="ex">{{ ex }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="hint">Ctrl+Enter 发送</span>
      </div>
    </div>

    <el-card v-if="result" class="result" shadow="never">
      <template #header>
        <div class="result-head">
          <span>结果</span>
          <div class="tags">
            <el-button
              v-if="result.data?.length"
              size="small"
              type="primary"
              plain
              @click="exportResult"
            >
              导出 CSV
            </el-button>
            <el-tag size="small" :type="result.ok ? 'success' : 'danger'">
              {{ result.ok ? '成功' : '失败' }}
            </el-tag>
            <el-tag v-if="result.source === 'metric_template'" size="small" type="success">
              指标模板 {{ result.metric_id || '' }}
            </el-tag>
            <el-tag size="small" type="info">{{ result.model_state || '-' }}</el-tag>
            <el-tag v-if="result.model" size="small">{{ result.model }}</el-tag>
            <el-tag v-if="result.model_invoked === false" size="small">未调用大模型：已命中指标字典口径</el-tag>
            <el-tag v-if="result.latency_ms != null" size="small" type="warning">
              {{ result.latency_ms }} ms
            </el-tag>
          </div>
        </div>
      </template>

      <el-alert
        v-if="result.hint"
        :title="result.hint"
        type="info"
        :closable="false"
        class="answer"
      />
      <el-alert
        v-if="result.answer"
        :title="result.answer"
        type="success"
        :closable="false"
        class="answer"
      />
      <el-alert
        v-if="result.error"
        :title="result.error"
        type="error"
        :closable="false"
        class="answer"
      />

      <div v-if="result.sql" class="sql-block">
        <div class="label">查询语句</div>
        <pre>{{ result.sql }}</pre>
      </div>

      <div v-if="chartable" class="chart-wrap">
        <div class="label">自动图表</div>
        <div ref="chartEl" class="chart" />
      </div>

      <el-table
        v-if="result.data?.length"
        :data="result.data"
        stripe
        border
        size="small"
        style="width: 100%"
        max-height="360"
      >
        <el-table-column
          v-for="col in displayCols"
          :key="col"
          :prop="col"
          :label="fieldZh(col)"
          min-width="120"
        />
      </el-table>
      <el-alert
        v-if="result.truncated"
        type="warning"
        :closable="false"
        show-icon
        class="truncate-hint"
        :title="`结果共 ${result.total_rows ?? result.rows ?? 0} 行，页面仅展示前 ${result.data?.length ?? 0} 行`"
        description="请缩小查询范围，或使用数据中心导出完整明细。"
      />
      <div v-if="result.ok && !result.data?.length" class="empty">无数据行（行数={{ result.rows ?? 0 }}）</div>
    </el-card>

    <el-card v-if="history.length" header="本会话历史" shadow="never">
      <el-timeline>
        <el-timeline-item
          v-for="(h, i) in history"
          :key="i"
          :type="h.ok ? 'success' : 'danger'"
          :timestamp="h.at"
        >
          <el-button link type="primary" @click="reuse(h.question)">{{ h.question }}</el-button>
          <span class="hist-meta">{{ h.ok ? `rows=${h.rows}` : h.error }}</span>
        </el-timeline-item>
      </el-timeline>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { askQuestion, downloadCsv, formatApiError, type AskResult } from '@/api/client'
import { fieldZh, visibleFields, zhColumns } from '@/utils/fields'

echarts.use([BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

type Hist = {
  question: string
  ok: boolean
  rows?: number | null
  error?: string | null
  at: string
}

const route = useRoute()
const router = useRouter()
const question = ref('')
const examples = [
  '库存表有多少行',
  '按库位统计库存记录数，取前10',
  '库存总量是多少',
  '按类别统计库存量',
  '资产台数有多少',
  '需求总量是多少',
  '入库合计是多少',
  '出库合计是多少',
  '超定额物资有多少',
  '呆滞料有多少行',
  '按单位统计库存（前5）',
]
const busy = ref(false)
const result = ref<AskResult | null>(null)
const history = ref<Hist[]>([])
const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function isNumeric(v: unknown): boolean {
  if (typeof v === 'number') return Number.isFinite(v)
  if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) return true
  return false
}

const chartable = computed(() => {
  const rows = result.value?.data || []
  if (rows.length < 2 || rows.length > 40) return false
  const cols = result.value?.columns || Object.keys(rows[0] || {})
  if (cols.length < 2) return false
  const labelCol = cols.find((c) => rows.every((r) => !isNumeric(r[c]))) || cols[0]
  const valueCol = cols.find((c) => c !== labelCol && rows.every((r) => isNumeric(r[c])))
  return !!(labelCol && valueCol)
})

/** 业务展示列：隐藏技术/溯源字段（仅影响展示与导出，不改原始结果）。 */
const displayCols = computed(() => {
  const res = result.value
  if (!res) return []
  return visibleFields(res.columns || Object.keys(res.data?.[0] || {}))
})

function renderChart() {
  if (!chartable.value || !chartEl.value || !result.value?.data?.length) {
    chart?.dispose()
    chart = null
    return
  }
  const rows = result.value.data
  const cols = result.value.columns || Object.keys(rows[0] || {})
  const labelCol = cols.find((c) => rows.every((r) => !isNumeric(r[c]))) || cols[0]
  const valueCol = cols.find((c) => c !== labelCol && rows.every((r) => isNumeric(r[c])))!
  const labels = rows.map((r) => String(r[labelCol] ?? ''))
  const values = rows.map((r) => Number(r[valueCol]))
  if (!chart) chart = echarts.init(chartEl.value)
  const usePie = rows.length <= 8
  chart.setOption(
    usePie
      ? {
          tooltip: { trigger: 'item' },
          series: [
            {
              type: 'pie',
              radius: ['28%', '62%'],
              data: labels.map((name, i) => ({ name, value: values[i] })),
            },
          ],
        }
      : {
          tooltip: { trigger: 'axis' },
          grid: { left: 48, right: 16, top: 24, bottom: 48 },
          xAxis: { type: 'category', data: labels, axisLabel: { rotate: 30 } },
          yAxis: { type: 'value' },
          series: [{ type: 'bar', data: values, name: valueCol }],
        },
    true,
  )
}

function loadHistory() {
  try {
    history.value = JSON.parse(sessionStorage.getItem('ask_history') || '[]')
  } catch {
    history.value = []
  }
}

function saveHistory() {
  sessionStorage.setItem('ask_history', JSON.stringify(history.value.slice(0, 20)))
}

function reuse(q: string) {
  question.value = q
  runAsk()
}

function exportResult() {
  const res = result.value
  if (!res?.data?.length) return
  const rawCols = res.columns || Object.keys(res.data[0] || {})
  const cols = visibleFields(rawCols)
  const headers = zhColumns(cols)
  const rows = res.data.map((r) =>
    Object.fromEntries(cols.map((c, i) => [headers[i], r[c]])),
  )
  downloadCsv(rows, headers, `ask_result_${Date.now()}.csv`, `已导出 ${rows.length} 行`)
  ElMessage.success(`已导出 ${rows.length} 行`)
}

async function runAsk() {
  const q = question.value.trim()
  if (!q) return
  busy.value = true
  result.value = null
  chart?.dispose()
  chart = null
  router.replace({ query: { ...route.query, q } })
  try {
    const res = await askQuestion(q)
    result.value = res
    history.value.unshift({
      question: q,
      ok: !!res.ok,
      rows: res.rows,
      error: res.error,
      at: new Date().toLocaleTimeString(),
    })
    saveHistory()
    if (!res.ok) ElMessage.error(res.error || '问答失败')
    await nextTick()
    renderChart()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  loadHistory()
  const q = typeof route.query.q === 'string' ? route.query.q : ''
  if (q) {
    question.value = q
    runAsk()
  }
})

onBeforeUnmount(() => {
  chart?.dispose()
  chart = null
})

watch(
  () => route.query.q,
  (q) => {
    if (typeof q === 'string' && q && q !== question.value) {
      question.value = q
    }
  },
)
</script>

<style scoped>
.ask { display: flex; flex-direction: column; gap: 16px; max-width: 960px; }
.composer { display: flex; flex-direction: column; gap: 10px; }
.composer-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; }
.result-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; }
.answer { margin-bottom: 12px; }
.sql-block { margin-bottom: 12px; }
.sql-block .label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.sql-block pre {
  margin: 0; padding: 10px 12px; background: #0f172a; color: #e2e8f0;
  border-radius: 8px; overflow: auto; font-size: 13px; line-height: 1.45;
}
.chart-wrap { margin-bottom: 12px; }
.chart-wrap .label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.chart { width: 100%; height: 280px; }
.empty { color: #909399; font-size: 13px; }
.truncate-hint { margin-top: 12px; }
.hist-meta { margin-left: 8px; color: #909399; font-size: 12px; }
</style>
