<template>
  <div class="ask">
    <el-alert
      v-if="modelDown"
      type="warning"
      :closable="false"
      show-icon
      title="复杂问数需本地模型"
      description="示例问题中的指标类问题仍可直接使用。"
    />
    <div v-if="modelDown" class="ask-degraded-actions">
      <el-button size="small" @click="$router.push('/system?tab=models')">查看模型状态</el-button>
    </div>

    <el-card v-if="recommendedQuestions.length || recommendHint" class="recommend" shadow="never">
      <template #header>
        <span>推荐问题</span>
      </template>
      <p v-if="recommendHint" class="recommend-hint">{{ recommendHint }}</p>
      <div class="recommend-chips">
        <el-button
          v-for="q in recommendedQuestions"
          :key="q"
          size="small"
          round
          @click="askFromChip(q)"
        >
          {{ q }}
        </el-button>
      </div>
    </el-card>

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
            <el-tag size="small" :type="result.ok ? 'success' : 'danger'">
              {{ result.ok ? '成功' : '失败' }}
            </el-tag>
            <el-tag v-if="sourceLabel" size="small" :type="sourceTagType || 'info'">
              {{ sourceLabel }}
            </el-tag>
            <el-tag v-if="result.engine_fallback" size="small" type="warning">
              已回退基础问数
            </el-tag>
            <el-tag v-if="result.metric_id" size="small" type="success">
              指标：{{ result.metric_name || result.metric_id }}
            </el-tag>
            <el-button
              v-if="result.data?.length"
              size="small"
              type="primary"
              plain
              @click="exportResult"
            >
              导出 CSV（问数结果快照）
            </el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="result.engine_fallback && result.ok && !isModelDegraded(result)"
        type="info"
        :closable="false"
        show-icon
        class="fallback-hint"
        title="已回退基础问数"
        description="Vanna 引擎未命中，已使用基础问数生成查询。"
      />
      <el-alert
        v-if="isModelDegraded(result) && !modelDown"
        type="warning"
        :closable="false"
        show-icon
        title="复杂问数需本地模型"
        :description="result.hint || result.error || '模型离线，未能生成查询'"
        class="answer"
      />
      <div v-if="isModelDegraded(result) && !modelDown" class="ask-degraded-actions">
        <el-button size="small" @click="$router.push('/system?tab=models')">查看模型状态</el-button>
      </div>
      <div
        v-if="isModelDegraded(result) && result.suggested_examples?.length"
        class="suggested-examples"
      >
        <div class="label">仍可尝试的指标类问题</div>
        <div class="recommend-chips">
          <el-button
            v-for="q in result.suggested_examples"
            :key="q"
            size="small"
            round
            @click="askFromChip(q)"
          >
            {{ q }}
          </el-button>
        </div>
      </div>
      <el-alert
        v-if="result.answer"
        :title="result.answer"
        type="success"
        :closable="false"
        class="answer"
      />
      <el-alert
        v-else-if="fallbackAnswer"
        :title="fallbackAnswer"
        type="success"
        :closable="false"
        class="answer"
      />
      <el-alert
        v-if="result.error && !isModelDegraded(result)"
        :title="result.error"
        type="error"
        :closable="false"
        class="answer"
      />

      <div v-if="chartable" class="chart-wrap">
        <div class="label">自动图表</div>
        <div ref="chartEl" class="chart" />
      </div>

      <el-descriptions
        v-if="singleMetric"
        :column="1"
        border
        size="small"
        class="metric-table"
      >
        <el-descriptions-item label="指标">{{ result.metric_name || result.metric_id }}</el-descriptions-item>
        <el-descriptions-item label="数值">{{ singleMetricValue }}</el-descriptions-item>
        <el-descriptions-item label="单位">{{ result.unit || '-' }}</el-descriptions-item>
        <el-descriptions-item label="来源">指标口径模板命中</el-descriptions-item>
      </el-descriptions>

      <el-table
        v-if="result.data?.length && displayCols.length"
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
        description="请缩小查询范围，或使用数据成果导出完整明细。"
      />
      <el-alert
        v-if="result.ok && result.empty_reason && (!result.data?.length || singleMetricValue == null)"
        type="info"
        :closable="false"
        show-icon
        class="empty-insight"
        title="未查到数据"
        :description="result.empty_reason"
      />
      <div
        v-if="result.ok && result.suggested_next?.length"
        class="suggested-next"
      >
        <div class="label">可以继续问</div>
        <div class="recommend-chips">
          <el-button
            v-for="q in result.suggested_next"
            :key="q"
            size="small"
            round
            @click="askFromChip(q)"
          >
            {{ q }}
          </el-button>
        </div>
      </div>
      <div v-else-if="result.ok && !result.data?.length && !result.empty_reason" class="empty">
        无数据行（行数={{ result.rows ?? 0 }}）
      </div>

      <el-collapse v-if="hasLocalToken" class="adv-fold">
        <el-collapse-item title="技术详情（模型状态 / 耗时）" name="adv">
          <div class="adv-meta">
            <el-tag v-if="result.engine_state" size="small" type="info">{{ result.engine_state }}</el-tag>
            <el-tag size="small" type="info">{{ result.model_state || '-' }}</el-tag>
            <el-tag v-if="result.latency_ms != null" size="small" type="warning">
              {{ result.latency_ms }} ms
            </el-tag>
          </div>
        </el-collapse-item>
      </el-collapse>
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
import { askQuestion, downloadCsv, fetchAskRecommendations, formatApiError, modelsStatus, type AskResult } from '@/api/client'
import { fieldZh, visibleFields, zhColumns } from '@/utils/fields'
import { ASK_RESULT_SCOPE } from '@/utils/copywriting'
import { askSourceLabel, askSourceTagType } from '@/utils/askSource'

echarts.use([BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const route = useRoute()
const router = useRouter()
const question = ref('')
/** 模型离线时也可回答的单值指标示例。 */
const SINGLE_VALUE_EXAMPLES = [
  '库存表有多少行',
  '库存总量是多少',
  '资产台数有多少',
  '需求总量是多少',
  '入库合计是多少',
  '出库合计是多少',
  '超定额物资有多少',
  '呆滞料有多少行',
  '零库存物资有多少',
  '缺少库位的库存有多少',
]
/** 需本地模型的分组/前N 类复杂问数，仅模型可用时展示。 */
const COMPLEX_EXAMPLES = [
  '按库位统计库存记录数，取前10',
  '按类别统计库存量',
  '按单位统计库存（前5）',
]
const examples = computed(() =>
  modelDown.value ? SINGLE_VALUE_EXAMPLES : [...SINGLE_VALUE_EXAMPLES, ...COMPLEX_EXAMPLES],
)
const busy = ref(false)
const result = ref<AskResult | null>(null)
const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
const modelDown = ref(false)
const hasLocalToken = computed(() => Boolean(localStorage.getItem('ops_token')))
const recommendedQuestions = ref<string[]>([])
const recommendHint = ref<string | null>(null)

const sourceLabel = computed(() => askSourceLabel(result.value?.source))
const sourceTagType = computed(() => askSourceTagType(result.value?.source))

function askFromChip(q: string) {
  question.value = q
  runAsk()
}

/** 单值指标命中：指标模板 + 单行单列结果，以业务结果表呈现而非 v 列表格。 */
const singleMetric = computed(() => {
  const res = result.value
  return !!res && res.source === 'metric_template' && !!res.metric_id && res.data?.length === 1
})

const singleMetricValue = computed(() => {
  const res = result.value
  if (!res?.data?.length) return null
  const row = res.data[0]
  const key = Object.keys(row)[0]
  return key != null ? row[key] : null
})

/** 无 answer 但返回单行单列时，用列名与值拼出摘要。 */
const fallbackAnswer = computed(() => {
  const res = result.value
  if (res?.answer || !res?.data?.length) return null
  const row = res.data[0]
  const cols = Object.keys(row)
  if (cols.length !== 1) return null
  return `${fieldZh(cols[0])} = ${row[cols[0]]}`
})

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

function exportResult() {
  const res = result.value
  if (!res?.data?.length) return
  // 单值指标：v 列已隐藏，导出业务口径表而非空表头
  if (singleMetric.value) {
    const row = res.data[0]
    const valKey = Object.keys(row)[0]
    const headers = ['指标', '数值', '单位', '数据范围']
    const rows = [
      {
        指标: res.metric_name || res.metric_id || '-',
        数值: valKey != null ? row[valKey] : '',
        单位: res.unit || '-',
        数据范围: ASK_RESULT_SCOPE,
      },
    ]
    downloadCsv(rows, headers, `ask_result_${Date.now()}.csv`, '已导出 1 行')
    ElMessage.success('已导出 1 行')
    return
  }
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
    if (isModelDegraded(res)) modelDown.value = true
    if (!res.ok && !isModelDegraded(res)) ElMessage.error(res.error || '问答失败')
    await nextTick()
    renderChart()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    busy.value = false
  }
}

function isModelDegraded(res: AskResult | null) {
  if (!res) return false
  if (res.degraded) return true
  return [
    'local_model_unavailable',
    'circuit_open',
    'llm_invocation_failed',
    'model_unavailable',
  ].includes(String(res.model_state || ''))
}

onMounted(async () => {
  try {
    const ms = await modelsStatus()
    modelDown.value = !ms.big?.ok
  } catch {
    modelDown.value = false
  }
  try {
    const rec = await fetchAskRecommendations(!modelDown.value)
    recommendedQuestions.value = rec.questions?.length
      ? rec.questions
      : (modelDown.value ? SINGLE_VALUE_EXAMPLES : examples.value)
    recommendHint.value = rec.hint || null
  } catch {
    recommendedQuestions.value = modelDown.value ? SINGLE_VALUE_EXAMPLES : examples.value
  }
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
.ask { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.recommend { margin-bottom: 0; }
.recommend-hint { margin: 0 0 10px; color: #606266; font-size: 13px; }
.recommend-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.suggested-examples, .suggested-next { margin-bottom: 12px; }
.suggested-examples .label, .suggested-next .label { font-size: 12px; color: #909399; margin-bottom: 6px; }
.empty-insight { margin-bottom: 12px; }
.composer { display: flex; flex-direction: column; gap: 10px; }
.composer-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.ask-degraded-actions { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
.hint { color: #909399; font-size: 12px; }
.result-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; }
.fallback-hint { margin-bottom: 12px; }
.answer { margin-bottom: 12px; }
.chart-wrap { margin-bottom: 12px; }
.chart-wrap .label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.chart { width: 100%; height: 280px; }
.empty { color: #909399; font-size: 13px; }
.truncate-hint { margin-top: 12px; }
.adv-fold { margin-top: 12px; }
.adv-meta { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.metric-table { margin-bottom: 12px; }
</style>
