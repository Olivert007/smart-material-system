<template>
  <div class="metrics">
    <el-card v-if="editable" shadow="never">
      <template #header>
        <div class="head">
          <span>流水指标激活门禁</span>
          <el-space>
            <el-button :loading="gateLoading" @click="loadGate">刷新门禁</el-button>
            <el-button :loading="fxLoading" @click="runFixtures">跑固定夹具</el-button>
            <el-button :loading="conflictLoading" @click="runConflictCheck">别名冲突检查</el-button>
            <el-button
              type="success"
              :disabled="!gate?.ready"
              :loading="activateBusy"
              @click="doActivate"
            >
              激活流水指标
            </el-button>
          </el-space>
        </div>
      </template>
      <el-space wrap>
        <el-tooltip
          v-if="gate?.missing?.length"
          :content="`缺失：${gate.missing.join('、')}`"
          placement="top"
        >
          <el-tag :type="gate?.ready ? 'success' : 'warning'">
            {{ gate?.ready ? '就绪' : '阻塞' }}
          </el-tag>
        </el-tooltip>
        <el-tag v-else :type="gate?.ready ? 'success' : 'warning'">
          {{ gate?.ready ? '就绪' : '阻塞' }}
        </el-tag>
        <el-tooltip
          v-for="(ok, key) in gate?.checks || {}"
          :key="key"
          :content="gateCheckHint(key)"
          placement="top"
        >
          <el-tag :type="ok ? 'success' : 'danger'" size="small">
            {{ gateCheckLabel(key) }}: {{ ok ? '✓' : '✗' }}
          </el-tag>
        </el-tooltip>
      </el-space>
      <p v-if="fxSummary" class="hint">夹具：{{ fxSummary }}</p>
      <p v-if="conflictHint" class="hint">{{ conflictHint }}</p>
      <el-table
        v-if="conflicts.length"
        :data="conflicts"
        border
        size="small"
        max-height="180"
        style="margin-top: 8px"
      >
        <el-table-column prop="alias" label="别名" min-width="160" />
        <el-table-column label="关联指标" min-width="220">
          <template #default="{ row }">{{ (row.metric_ids || []).join(', ') }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>指标列表</span>
          <el-space>
            <el-input
              v-model="q"
              clearable
              placeholder="搜索指标编码 / 名称"
              style="width: 220px"
            />
            <el-select v-model="statusFilter" clearable placeholder="状态" style="width: 120px">
              <el-option label="草稿" value="draft" />
              <el-option label="启用" value="active" />
              <el-option label="已废弃" value="deprecated" />
            </el-select>
            <el-select v-model="groupFilter" clearable placeholder="分组" style="width: 120px">
              <el-option label="业务" value="business" />
              <el-option label="质量" value="quality" />
              <el-option label="运维" value="ops" />
            </el-select>
            <el-button :loading="listLoading" @click="loadList">刷新</el-button>
            <el-button v-if="editable" type="primary" @click="openEdit()">新建</el-button>
          </el-space>
        </div>
      </template>

      <el-table :data="filtered" v-loading="listLoading" border size="small" style="width: 100%">
        <el-table-column prop="metric_id" label="指标编码" min-width="160" />
        <el-table-column prop="metric_name" label="名称" min-width="140" />
        <el-table-column prop="unit" label="单位" width="70" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.status === 'active' ? 'success' : row.status === 'draft' ? 'info' : 'warning'"
            >
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="60" />
        <el-table-column prop="engine" label="引擎" width="70" />
        <el-table-column label="求值" min-width="180">
          <template #default="{ row }">
            <span class="mono">{{ evalCache[row.metric_id]?.value ?? '—' }}</span>
            <span v-if="evalCache[row.metric_id]?.note" class="hint"> {{ evalCache[row.metric_id]?.note }}</span>
            <div v-if="evalCache[row.metric_id]?.history" class="hint">
              {{ evalCache[row.metric_id]?.history }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="runEval(row.metric_id)">试跑</el-button>
            <el-button link type="primary" @click="openTrend(row.metric_id)">趋势</el-button>
            <el-button v-if="editable" link @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="hint">共 {{ filtered.length }} / {{ items.length }} 条</div>
    </el-card>

    <el-dialog v-model="editVisible" :title="editForm.metric_id ? '编辑指标' : '新建指标'" width="640px" destroy-on-close>
      <el-form label-width="110px">
        <el-form-item label="指标编码" required>
          <el-input v-model="editForm.metric_id" :disabled="!!editingExisting" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="editForm.metric_name" />
        </el-form-item>
        <el-form-item label="单位">
          <el-input v-model="editForm.unit" />
        </el-form-item>
        <el-form-item label="引擎">
          <el-select v-model="editForm.engine" style="width: 140px">
            <el-option label="业务引擎" value="biz" />
            <el-option label="元数据引擎" value="meta" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.status" style="width: 140px">
            <el-option label="草稿" value="draft" />
            <el-option label="启用" value="active" />
            <el-option label="已废弃" value="deprecated" />
          </el-select>
        </el-form-item>
        <el-form-item label="口径说明">
          <el-input v-model="editForm.definition" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="口径 SQL" required>
          <el-input v-model="editForm.definition_sql" type="textarea" :rows="4" class="mono" />
          <p class="hint" style="margin: 4px 0 0">
            引擎为业务且状态为启用时，问答与报表按此 SQL 求值；元数据引擎走内部口径表。
            保存会新建版本，历史快照不回填。
          </p>
        </el-form-item>
        <el-form-item label="别名">
          <el-input v-model="aliasesText" placeholder="逗号分隔同义叫法" />
        </el-form-item>
        <el-alert
          v-if="editForm.metric_id.startsWith('FLOW_') && editForm.status === 'active'"
          type="warning"
          :closable="false"
          title="流水指标设为启用须门禁通过；否则接口返回无权限"
          style="margin-bottom: 8px"
        />
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saveBusy" @click="saveEdit">保存（版本号递增）</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="trendVisible" :title="`${trendMetricName} 快照趋势`" width="720px" destroy-on-close>
      <p v-if="trendNote" class="hint">{{ trendNote }}</p>
      <div ref="trendEl" class="trend-chart" />
      <template #footer>
        <el-button @click="trendVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import {
  activateFlowMetrics,
  checkMetricConflicts,
  evaluateMetric,
  flowGate,
  formatApiError,
  listMetrics,
  listMetricSnapshots,
  metricsFixtures,
  upsertMetric,
  type MetricItem,
} from '@/api/client'
import { gateLabel } from '@/utils/gateLabels'

const props = withDefaults(defineProps<{ editable?: boolean }>(), { editable: true })

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const route = useRoute()

const items = ref<MetricItem[]>([])
const listLoading = ref(false)
const q = ref('')
const statusFilter = ref<string | undefined>()
const groupFilter = ref<string | undefined>()
const evalCache = reactive<Record<string, { value: unknown; note?: string | null; history?: string }>>({})

const gate = ref<{
  ready: boolean
  checks: Record<string, boolean>
  missing: string[]
} | null>(null)
const gateLoading = ref(false)
const fxLoading = ref(false)
const fxSummary = ref('')
const activateBusy = ref(false)
const conflictLoading = ref(false)
const conflictHint = ref('')
const conflicts = ref<Array<{ alias: string; metric_ids: string[] }>>([])

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  active: '启用',
  deprecated: '已废弃',
}

function statusLabel(s: string) {
  return STATUS_LABELS[s] || s
}

const GATE_CHECK_LABELS: Record<string, string> = {
  rule_path_has_published_rows: '已发布出入库流水',
  l1_l2_l3_stats_available: '出入库分级统计可用',
  no_year_as_quantity: '无年份脏数据',
  reconcile_runnable: '库存对账可运行',
  fixture_tests_passed: '夹具测试',
  lineage_rebuild_clean: '血缘重建干净',
}

function gateCheckLabel(key: string) {
  return GATE_CHECK_LABELS[key] || gateLabel(key)
}

function gateCheckHint(key: string) {
  const hints: Record<string, string> = {
    rule_path_has_published_rows: '当前没有已发布的出入库流水，库存对账相关指标暂不可用',
    l1_l2_l3_stats_available: '已发布流水按分级统计可用',
    no_year_as_quantity: '无"年份当数量"脏数据',
    reconcile_runnable: '库存对账可运行',
    fixture_tests_passed: '内置夹具测试全部通过',
    lineage_rebuild_clean: '血缘审计后重建干净',
  }
  return hints[key] || gateLabel(key)
}

const editVisible = ref(false)
const editingExisting = ref(false)
const saveBusy = ref(false)
const aliasesText = ref('')
const editForm = reactive({
  metric_id: '',
  metric_name: '',
  definition_sql: '',
  unit: '',
  definition: '',
  engine: 'biz',
  status: 'draft',
  source_tables: '',
})

// —— 快照趋势 ——
const trendVisible = ref(false)
const trendMetricId = ref('')
const trendNote = ref('')
const trendEl = ref<HTMLDivElement | null>(null)
let trendChart: echarts.ECharts | null = null

const trendMetricName = computed(() => {
  const hit = items.value.find((m) => m.metric_id === trendMetricId.value)
  return hit?.metric_name || trendMetricId.value
})

async function openTrend(metricId: string) {
  trendMetricId.value = metricId
  trendNote.value = ''
  trendVisible.value = true
  try {
    const snaps = await listMetricSnapshots(metricId, 50)
    await nextTick()
    trendChart?.dispose()
    trendChart = null
    const items = (snaps.items || []).slice().reverse() // 接口按时间倒序，转正序
    if (!items.length) {
      trendNote.value = '暂无快照：后台任务每 30 分钟自动记录业务指标；可先「试跑」写入一条。'
      return
    }
    if (!trendEl.value) return
    trendChart = echarts.init(trendEl.value)
    trendChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: [metricId], top: 0 },
      grid: { left: 44, right: 16, top: 32, bottom: 28 },
      xAxis: {
        type: 'category',
        data: items.map((s) => String(s.evaluated_at || '').slice(0, 16).replace('T', ' ')),
        boundaryGap: false,
      },
      yAxis: { type: 'value' },
      series: [
        {
          name: metricId,
          type: 'line',
          smooth: true,
          connectNulls: true,
          data: items.map((s) => (s.value == null ? null : Number(s.value))),
        },
      ],
    })
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

function onTrendResize() {
  trendChart?.resize()
}

const filtered = computed(() => {
  const needle = q.value.trim().toLowerCase()
  return items.value.filter((m) => {
    if (statusFilter.value && m.status !== statusFilter.value) return false
    if (groupFilter.value && (m.metric_group || 'business') !== groupFilter.value) return false
    if (!needle) return true
    return (
      m.metric_id.toLowerCase().includes(needle) ||
      (m.metric_name || '').toLowerCase().includes(needle)
    )
  })
})

async function loadList() {
  listLoading.value = true
  try {
    const res = await listMetrics()
    items.value = res.items
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    listLoading.value = false
  }
}

async function loadGate() {
  gateLoading.value = true
  try {
    gate.value = await flowGate()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    gateLoading.value = false
  }
}

async function runFixtures() {
  fxLoading.value = true
  try {
    const res = await metricsFixtures()
    fxSummary.value = `${res.passed}/${res.total} ${res.ok ? 'OK' : 'FAIL'}`
    ElMessage[res.ok ? 'success' : 'error'](fxSummary.value)
    await loadGate()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    fxLoading.value = false
  }
}

async function runConflictCheck() {
  conflictLoading.value = true
  try {
    const res = await checkMetricConflicts()
    conflicts.value = res.conflicts || []
    conflictHint.value = res.ok
      ? '无别名冲突'
      : `发现 ${res.conflict_count} 组冲突（须人工改别名）`
    ElMessage[res.ok ? 'success' : 'warning'](conflictHint.value)
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    conflictLoading.value = false
  }
}

async function doActivate() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  try {
    await ElMessageBox.confirm(
      '确认将流水指标设为启用？\n影响预演：启用后问数/报表将按新口径求值；须门禁全绿；不会自动改业务库历史数据。',
      '指标口径变更预演',
      { type: 'warning' },
    )
  } catch {
    return
  }
  activateBusy.value = true
  try {
    const res = await activateFlowMetrics()
    ElMessage.success(`已激活 ${res.activated?.length || 0} 项`)
    await Promise.all([loadList(), loadGate()])
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    activateBusy.value = false
  }
}

async function runEval(metricId: string) {
  try {
    const ev = await evaluateMetric(metricId)
    let history = ''
    try {
      const snaps = await listMetricSnapshots(metricId, 5)
      if (snaps.items?.length) {
        history = snaps.items
          .map((s) => `${s.evaluated_at?.slice(0, 19) || '?'}=${s.value ?? 'null'}`)
          .join(' · ')
      }
    } catch {
      /* snapshot optional */
    }
    evalCache[metricId] = {
      value: ev.value,
      note: ev.note,
      history: history || (ev.snapshot_written ? 'snapshot ok' : undefined),
    }
    ElMessage.success(`${metricId} = ${ev.value ?? 'null'} (${ev.status})`)
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

function openEdit(row?: MetricItem) {
  editingExisting.value = !!row
  editForm.metric_id = row?.metric_id || ''
  editForm.metric_name = row?.metric_name || ''
  editForm.definition_sql = row?.definition_sql || 'SELECT 1 AS v'
  editForm.unit = row?.unit || ''
  editForm.definition = row?.definition || ''
  editForm.engine = row?.engine || 'biz'
  editForm.status = row?.status || 'draft'
  editForm.source_tables = row?.source_tables || ''
  aliasesText.value = (row?.aliases || []).join(',')
  editVisible.value = true
}

async function saveEdit() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  if (!editForm.metric_id.trim() || !editForm.metric_name.trim() || !editForm.definition_sql.trim()) {
    ElMessage.warning('指标编码 / 名称 / 查询语句必填')
    return
  }
  saveBusy.value = true
  try {
    await upsertMetric({
      metric_id: editForm.metric_id.trim(),
      metric_name: editForm.metric_name.trim(),
      definition_sql: editForm.definition_sql.trim(),
      unit: editForm.unit,
      definition: editForm.definition,
      engine: editForm.engine,
      status: editForm.status,
      source_tables: editForm.source_tables,
      aliases: aliasesText.value
        .split(/[,，;；]/)
        .map((s) => s.trim())
        .filter(Boolean),
    })
    ElMessage.success('已保存')
    editVisible.value = false
    await loadList()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    saveBusy.value = false
  }
}

onMounted(async () => {
  const id = route.query.id
  if (typeof id === 'string' && id) {
    q.value = id
  }
  await Promise.all([loadList(), props.editable ? loadGate() : Promise.resolve()])
  if (typeof id === 'string' && id) {
    await openTrend(id)
  }
  window.addEventListener('resize', onTrendResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onTrendResize)
  trendChart?.dispose()
  trendChart = null
})
</script>

<style scoped>
.metrics { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 13px; margin: 8px 0 0; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; }
.trend-chart { width: 100%; height: 300px; margin-top: 4px; }
</style>
