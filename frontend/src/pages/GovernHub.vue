<template>
  <div class="govern-hub">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      :title="hubTitle"
      :description="hubDescription"
    />

    <!-- Empty: no files — only CTA -->
    <template v-if="isNoData">
      <el-empty description="当前没有可规整数据">
        <template #default>
          <ol class="empty-steps">
            <li>在「数据接入」上传原始需求表或台账</li>
            <li>完成字段识别与暂存确认</li>
            <li>回到本页处理待办，使数据进入可用</li>
          </ol>
          <el-button type="primary" @click="$router.push('/intake')">去数据接入</el-button>
        </template>
      </el-empty>
    </template>

    <!-- Main workbench when files exist -->
    <template v-else-if="summary">
      <el-alert
        :type="stateAlertType"
        :closable="false"
        show-icon
        :title="stateTitle"
        :description="summary.state_message"
      />

      <div class="summary-row" v-loading="summaryLoading">
        <div class="scard">
          <div class="slabel">待确认字段</div>
          <div class="svalue">{{ summary.map_pending_count }}</div>
        </div>
        <div class="scard">
          <div class="slabel">待匹配物资</div>
          <div class="svalue">{{ summary.material_pending_count }}</div>
        </div>
        <div class="scard">
          <div class="slabel">单位相关</div>
          <div class="svalue">{{ summary.unit_pending_count ?? 0 }}</div>
        </div>
        <div class="scard">
          <div class="slabel">流水待确认</div>
          <div class="svalue">{{ summary.flow_pending_count }}</div>
        </div>
        <div class="scard warn clickable" @click="$router.push('/ai-review')">
          <div class="slabel">待审核 AI 建议</div>
          <div class="svalue">{{ summary.ai_suggestion_pending_count ?? 0 }}</div>
        </div>
        <div class="scard warn">
          <div class="slabel">阻塞行</div>
          <div class="svalue">{{ summary.blocked_rows }}</div>
        </div>
        <div class="scard">
          <div class="slabel">发布阻断</div>
          <div class="svalue">{{ summary.release_blocker_count }}</div>
        </div>
        <div class="scard ok">
          <div class="slabel">预计可释放</div>
          <div class="svalue">{{ summary.estimated_releasable_rows ?? 0 }}</div>
        </div>
      </div>

      <div v-if="summary.next_actions?.length" class="next-actions">
        <el-button
          v-for="a in summary.next_actions"
          :key="a.code"
          type="primary"
          plain
          @click="$router.push(a.path)"
        >
          {{ a.label }}
        </el-button>
      </div>

      <el-alert
        v-if="summary.empty_reason && summary.total <= 0"
        type="success"
        :closable="false"
        show-icon
        :title="summary.empty_reason"
      />

      <section ref="todosSectionEl" class="todos-section">
        <div class="section-head">
          <h3>{{ isTodosHub ? '治理待办队列' : '当前待处理事项' }}</h3>
          <el-button size="small" :loading="todoLoading" @click="refreshAll">刷新</el-button>
        </div>
        <div class="todo-toolbar">
          <el-radio-group v-model="todoFilter" size="small" @change="onFilterChange">
            <el-radio-button label="">全部</el-radio-button>
            <el-radio-button label="map">字段</el-radio-button>
            <el-radio-button label="unit">单位</el-radio-button>
            <el-radio-button label="master">物资</el-radio-button>
            <el-radio-button label="material_align">对齐</el-radio-button>
            <el-radio-button label="exception">异常</el-radio-button>
            <el-radio-button label="flow">出入库</el-radio-button>
            <el-radio-button label="release_blocker">发布阻断</el-radio-button>
          </el-radio-group>
        </div>
        <el-table
          :data="todoItems"
          v-loading="todoLoading"
          border
          size="small"
          empty-text="暂无待办"
          highlight-current-row
          @row-click="(row: GovernTodoItem) => openTodo(row)"
        >
          <el-table-column label="类型" width="100">
            <template #default="{ row }">{{ typeLabel(row.todo_type) }}</template>
          </el-table-column>
          <el-table-column prop="title" label="问题" min-width="200" show-overflow-tooltip />
          <el-table-column prop="affected_rows" label="影响行数" width="90" />
          <el-table-column label="来源文件" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.source_file || '—' }}</template>
          </el-table-column>
          <el-table-column label="来源 Sheet" width="110" show-overflow-tooltip>
            <template #default="{ row }">{{ row.source_sheet || '—' }}</template>
          </el-table-column>
          <el-table-column label="置信度" width="80">
            <template #default="{ row }">
              {{ row.confidence != null ? Number(row.confidence).toFixed(2) : '—' }}
            </template>
          </el-table-column>
          <el-table-column prop="suggestion" label="系统建议" min-width="160" show-overflow-tooltip />
          <el-table-column label="处理后" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ afterEffect(row) }}</template>
          </el-table-column>
          <el-table-column label="会形成规则" width="100">
            <template #default="{ row }">{{ row.forms_rule ? '是' : '否' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click.stop="openTodo(row)">去处理</el-button>
              <el-button
                v-if="row.todo_type === 'map' || row.todo_type === 'unit'"
                link
                type="success"
                @click.stop="quickMap(row, 'accept')"
              >
                采纳建议
              </el-button>
              <el-button
                v-if="row.todo_type === 'map' || row.todo_type === 'unit' || row.todo_type === 'flow'"
                link
                type="info"
                @click.stop="quickIgnore(row)"
              >
                忽略（不修复）
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <p class="hint">批量或单项处理前请确认影响范围；忽略只会跳过待办，不会修复数据。</p>
      </section>

      <!-- Detail expands on demand -->
      <section v-if="detailOpen" class="detail-section">
        <div class="section-head">
          <h3>处理详情：{{ detailTitle }}</h3>
          <el-button size="small" text @click="closeDetail">收起</el-button>
        </div>

        <div class="compare-panel">
          <div class="compare-title">规整前后对比</div>
          <el-table
            v-if="compareRows.length"
            :data="compareRows"
            border
            size="small"
            empty-text="暂无可对比样本"
          >
            <el-table-column prop="from" label="规整前" min-width="160" show-overflow-tooltip />
            <el-table-column prop="to" label="规整后（建议）" min-width="160" show-overflow-tooltip />
            <el-table-column prop="source" label="来源" width="100" />
            <el-table-column prop="confidence" label="置信度" width="90" />
          </el-table>
          <el-empty v-else description="暂无可对比样本" :image-size="48" />
        </div>

        <GovernView
          v-if="detailInnerTab"
          :key="'detail-' + detailInnerTab + '-' + (activeTodo?.todo_id || '')"
          :initial-tab="detailInnerTab"
          :hide-outer-tabs="true"
        />
        <el-alert
          v-else-if="activeTodo?.todo_type === 'release_blocker'"
          type="warning"
          :closable="false"
          show-icon
          :title="activeTodo.title"
          :description="activeTodo.suggestion || '请先完成相关规整后再启用指标'"
        />
        <el-alert
          v-else-if="activeTodo?.todo_type === 'exception'"
          type="warning"
          :closable="false"
          show-icon
          :title="activeTodo.title"
          description="请到「数据成果 → 阻塞数据」查看明细并回到字段/物资规整修复；忽略不等于修复。"
        >
          <el-button type="primary" link @click="$router.push('/data?tab=blocked')">查看阻塞数据</el-button>
        </el-alert>
        <p class="hint">处理完成后请点「刷新」更新待办列表。</p>
      </section>

      <el-collapse v-model="advancedOpen" class="advanced-fold">
        <el-collapse-item title="高级能力（规则沉淀 / 出入库 / 规则资产 / 指标口径）" name="adv">
          <template v-if="advancedOpen.includes('adv')">
            <el-alert
              type="warning"
              :closable="false"
              show-icon
              title="面向治理人员"
              description="规则变更前请先看影响预演；日常请优先处理上方待办。"
              style="margin-bottom: 10px"
            />
            <el-tabs v-model="advInner">
              <el-tab-pane label="规则沉淀" name="rulelearn" />
              <el-tab-pane label="出入库记录处理" name="flow" />
              <el-tab-pane label="规则资产" name="assets" />
              <el-tab-pane label="指标口径" name="metrics" />
            </el-tabs>
            <GovernView
              v-if="advInner === 'rulelearn' || advInner === 'flow'"
              :key="'adv-' + advInner"
              :initial-tab="advInner"
              :hide-outer-tabs="true"
            />
            <AssetsView v-else-if="advInner === 'assets'" />
            <MetricsView v-else :editable="metricsEditable" />
          </template>
        </el-collapse-item>
      </el-collapse>
    </template>

    <div v-else v-loading="summaryLoading" class="loading-box" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import GovernView from '@/pages/GovernView.vue'
import AssetsView from '@/pages/AssetsView.vue'
import MetricsView from '@/pages/MetricsView.vue'
import { gateLabel } from '@/utils/gateLabels'
import {
  formatApiError,
  governTodoDecision,
  governTodoList,
  governTodoSummary,
  type GovernTodoItem,
  type GovernTodoSummary,
} from '@/api/client'

const route = useRoute()
const router = useRouter()
const todosSectionEl = ref<HTMLElement | null>(null)

/** 主导航双入口：/todos=治理待办，/govern=数据规整 */
const isTodosHub = computed(() => route.path === '/todos' || route.path.startsWith('/todos'))

const hubTitle = computed(() =>
  isTodosHub.value ? '治理待办' : '数据规整工作台',
)
const hubDescription = computed(() =>
  isTodosHub.value
    ? '按影响范围处理待确认字段、异常、AI 建议与发布阻断。采纳或忽略前会预演影响；忽略不等于修复。可前往「AI建议审核」集中处理模型候选。'
    : '先看当前能不能用、下一步做什么；字段/物资/单位规整与低置信待办在此处理。AI 建议须人工确认后才会进入可用数据。',
)

const DETAIL_TAB_MAP: Record<string, string> = {
  map: 'map',
  unit: 'map',
  master: 'master',
  material_align: 'master',
  flow: 'flow',
  reconcile: 'reconcile',
  exception: 'reconcile',
}

const summary = ref<GovernTodoSummary | null>(null)
const summaryLoading = ref(false)
const todoItems = ref<GovernTodoItem[]>([])
const todoLoading = ref(false)
const todoFilter = ref(typeof route.query.type === 'string' ? route.query.type : '')
const detailOpen = ref(false)
const detailType = ref('')
const activeTodo = ref<GovernTodoItem | null>(null)
const advInner = ref('rulelearn')
const advancedOpen = ref<string[]>([])

const isNoData = computed(
  () => summary.value != null && (summary.value.file_count ?? 0) <= 0,
)

const metricsEditable = computed(() => {
  const role = localStorage.getItem('ops_role') || 'ops'
  return role === 'ops' || role === 'govern'
})

function afterEffect(row: GovernTodoItem) {
  const n = row.affected_rows
  const rowsPart = n != null && n > 0 ? `确认后约影响 ${n} 行` : '确认后按建议更新'
  if (row.todo_type === 'exception' || row.todo_type === 'release_blocker') {
    return `${rowsPart}；忽略≠修复，需回到规整处理`
  }
  if (row.forms_rule) return `${rowsPart}；将沉淀为规则`
  return `${rowsPart}；不会自动写入未确认事实`
}

const stateTitle = computed(() => {
  const s = summary.value?.state
  if (s === 'no_data') return '当前没有可规整数据'
  if (s === 'parsing') return '正在识别结构'
  if (s === 'blocked') return '当前数据暂不可用'
  if (s === 'needs_standardization') return '当前需要规整'
  if (s === 'published') return '当前已有发布版本（可用候选）'
  if (s === 'ready') return '当前数据可用'
  return '数据规整状态'
})

const stateAlertType = computed(() => {
  const s = summary.value?.state
  if (s === 'ready' || s === 'published') return 'success' as const
  if (s === 'blocked') return 'error' as const
  if (s === 'needs_standardization') return 'warning' as const
  return 'info' as const
})

const detailTitle = computed(() => {
  const t = detailType.value
  const map: Record<string, string> = {
    map: '字段规整',
    unit: '单位规整',
    master: '物资规整',
    material_align: '物资对齐',
    flow: '出入库记录',
    exception: '异常与阻塞',
    release_blocker: '发布阻断',
    reconcile: '库存对账',
  }
  return map[t] || typeLabel(t)
})

const detailInnerTab = computed(() => {
  const t = detailType.value
  if (t === 'release_blocker' || t === 'exception') return ''
  return DETAIL_TAB_MAP[t] || ''
})

type CompareRow = { from: string; to: string; source: string; confidence: string }

const compareRows = computed<CompareRow[]>(() => {
  const row = activeTodo.value
  if (!row?.raw_ref) return []
  const ref = row.raw_ref
  const from =
    String(ref.from_value ?? ref.header ?? ref.material_name ?? ref.from_name ?? '') || ''
  const to =
    String(
      ref.to_value ?? ref.suggested_field ?? ref.material_code ?? ref.to_name ?? '',
    ) || ''
  if (!from && !to) return []
  const conf =
    row.confidence != null
      ? String(row.confidence)
      : ref.score != null
        ? String(ref.score)
        : '-'
  return [
    {
      from: from || '-',
      to: to || '-',
      source: typeLabel(row.todo_type),
      confidence: conf,
    },
  ]
})

function typeLabel(t: string) {
  const map: Record<string, string> = {
    map: '字段',
    unit: '单位',
    master: '物资',
    material_align: '物资对齐',
    flow: '出入库',
    exception: '异常',
    release_blocker: '发布阻断',
    correction: '修正',
    blocked: '阻塞',
  }
  return map[t] || gateLabel(t)
}

function hubPath() {
  return isTodosHub.value ? '/todos' : '/govern'
}

function syncQuery() {
  const q: Record<string, string> = {}
  if (todoFilter.value) q.type = todoFilter.value
  if (detailOpen.value && detailType.value) q.detail = detailType.value
  router.replace({ path: hubPath(), query: q })
}

function onFilterChange() {
  syncQuery()
  loadTodos()
}

async function loadSummary() {
  summaryLoading.value = true
  try {
    summary.value = await governTodoSummary()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    summaryLoading.value = false
  }
}

async function loadTodos() {
  todoLoading.value = true
  try {
    const res = await governTodoList({
      limit: 100,
      todo_type: todoFilter.value || undefined,
      sort: 'impact',
    })
    todoItems.value = res.items
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    todoLoading.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadSummary(), loadTodos()])
}

function openTodo(row: GovernTodoItem) {
  activeTodo.value = row
  detailType.value = row.todo_type
  detailOpen.value = true
  if (row.todo_type === 'flow') {
    // also allow advanced fold for flow tools; detail embeds GovernView flow
  }
  syncQuery()
}

function closeDetail() {
  detailOpen.value = false
  detailType.value = ''
  activeTodo.value = null
  syncQuery()
}

function openDetailByType(t: string) {
  detailType.value = t
  detailOpen.value = true
  const found = todoItems.value.find((i) => i.todo_type === t)
  activeTodo.value = found || null
  syncQuery()
}

async function quickMap(row: GovernTodoItem, decision: 'accept' | 'ignore') {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在系统设置填写操作令牌')
    return
  }
  let previewNote = ''
  try {
    const preview = await governTodoDecision(row.todo_id, {
      decision,
      dry_run: true,
      expected_version: row.version,
    })
    previewNote = [
      `影响约 ${preview.affected_rows ?? row.affected_rows ?? 0} 行`,
      preview.forms_rule ? '将沉淀为规则' : '不自动写入未确认事实',
      preview.warning || (decision === 'ignore' ? '忽略不等于修复' : ''),
    ]
      .filter(Boolean)
      .join('；')
  } catch {
    previewNote =
      decision === 'ignore'
        ? '忽略不会修复数据，仅跳过确认'
        : `约影响 ${row.affected_rows ?? 0} 行`
  }
  try {
    await ElMessageBox.confirm(
      decision === 'ignore'
        ? `忽略该字段待办？\n${row.title}\n${previewNote}`
        : `采纳系统建议？\n${row.title}\n建议：${row.suggestion}\n${previewNote}`,
      decision === 'ignore' ? '忽略（不修复）' : '采纳建议',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const key =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `todo_${Date.now()}`
    await governTodoDecision(row.todo_id, {
      decision,
      idempotency_key: key,
      expected_version: row.version,
    })
    ElMessage.success(decision === 'ignore' ? '已忽略（未修复）' : '已确认映射')
    await refreshAll()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

async function quickIgnore(row: GovernTodoItem) {
  if (row.todo_type === 'map' || row.todo_type === 'unit') {
    await quickMap(row, 'ignore')
    return
  }
  if (row.todo_type === 'flow') {
    if (!localStorage.getItem('ops_token')) {
      ElMessage.warning('请先在系统设置填写操作令牌')
      return
    }
    let previewNote = '忽略不等于修复'
    try {
      const preview = await governTodoDecision(row.todo_id, {
        decision: 'ignore',
        dry_run: true,
        expected_version: row.version,
      })
      previewNote = `影响约 ${preview.affected_rows ?? row.affected_rows ?? 0} 行；${
        preview.warning || '忽略不等于修复'
      }`
    } catch {
      /* keep default */
    }
    try {
      await ElMessageBox.confirm(
        `忽略该出入库待办？\n${row.title}\n${previewNote}`,
        '忽略（不修复）',
        { type: 'warning' },
      )
    } catch {
      return
    }
    try {
      const key =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID()
          : `todo_${Date.now()}`
      await governTodoDecision(row.todo_id, {
        decision: 'ignore',
        idempotency_key: key,
        expected_version: row.version,
      })
      ElMessage.success('已忽略（未修复）')
      await refreshAll()
    } catch (e: unknown) {
      ElMessage.error(formatApiError(e))
    }
  }
}

watch(
  () => route.query.type,
  (v) => {
    if (typeof v === 'string') todoFilter.value = v
    else todoFilter.value = ''
  },
)

onMounted(async () => {
  const qTab = String(route.query.tab || '')
  const qDetail = typeof route.query.detail === 'string' ? route.query.detail : ''

  // Legacy ?tab=map|master|... → expand detail
  if (qTab === 'map' || qTab === 'master' || qTab === 'reconcile' || qTab === 'units') {
    const t = qTab === 'units' ? 'unit' : qTab
    detailType.value = t
    detailOpen.value = true
  } else if (qTab === 'assets' || qTab === 'metrics' || qTab === 'rulelearn' || qTab === 'flow') {
    advInner.value = qTab === 'flow' || qTab === 'rulelearn' ? qTab : qTab
    advancedOpen.value = ['adv']
    if (qTab === 'flow') {
      detailType.value = 'flow'
      detailOpen.value = true
    }
  } else if (qTab === 'advanced') {
    advancedOpen.value = ['adv']
  } else if (qDetail) {
    openDetailByType(qDetail)
  }

  // 数据规整入口默认展开高级能力中的规则/口径入口提示；治理待办聚焦队列
  if (!isTodosHub.value && qTab === 'advanced') {
    advancedOpen.value = ['adv']
  }

  await refreshAll()

  if (detailOpen.value && !activeTodo.value) {
    const found = todoItems.value.find((i) => i.todo_type === detailType.value)
    activeTodo.value = found || null
  }

  if (isTodosHub.value) {
    requestAnimationFrame(() => {
      todosSectionEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }
})
</script>

<style scoped>
.govern-hub { display: flex; flex-direction: column; gap: 12px; width: 100%; }
.empty-steps { text-align: left; margin: 0 0 16px; padding-left: 1.2em; color: #606266; line-height: 1.8; }
.summary-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}
.scard {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 10px 12px;
  background: var(--el-bg-color);
}
.scard.warn { border-color: var(--el-color-warning-light-5); }
.scard.ok { border-color: var(--el-color-success-light-5); }
.scard.clickable { cursor: pointer; }
.scard.clickable:hover { border-color: var(--el-color-primary-light-5); }
.slabel { color: #909399; font-size: 12px; margin-bottom: 4px; }
.svalue { font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums; }
.next-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.section-head h3 { margin: 0; font-size: 16px; font-weight: 600; }
.todo-toolbar { margin-bottom: 8px; }
.hint { color: #909399; font-size: 12px; margin-top: 8px; }
.detail-section {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 12px;
  background: var(--el-fill-color-blank);
}
.compare-panel {
  margin-bottom: 12px;
  padding: 10px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}
.compare-title { font-weight: 600; margin-bottom: 8px; font-size: 13px; }
.advanced-fold { margin-top: 4px; }
.loading-box { min-height: 120px; }
</style>
