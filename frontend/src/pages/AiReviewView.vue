<template>
  <div class="ai-review">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="AI建议审核"
      description="系统根据字段名、样例值和上下文给出候选建议；请确认后再用于规整。模型不会自动写入业务事实、创建主数据或发布。"
    />

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="如何区分建议与事实"
      class="legend"
    >
      <ul class="legend-list">
        <li><strong>系统规则判断</strong>：门禁、阻塞码、发布阻断等，不以模型输出为准。</li>
        <li><strong>模型建议 / 规则+模型候选</strong>：仅预填，须人工采纳、修改或拒绝。</li>
        <li><strong>待审核</strong>：仍在本页队列，确认前不会进入可用数据。</li>
        <li><strong>已人工确认</strong>：离开本队列；可在下方「最近确认」或「追溯审计」查看。</li>
      </ul>
    </el-alert>

    <div class="summary-row" v-loading="summaryLoading">
      <div class="scard warn">
        <div class="slabel">待审核 AI 建议</div>
        <div class="svalue">{{ summary?.ai_suggestion_pending_count ?? 0 }}</div>
      </div>
      <div class="scard">
        <div class="slabel">字段 / 单位</div>
        <div class="svalue">{{ (summary?.map_pending_count ?? 0) }}</div>
      </div>
      <div class="scard">
        <div class="slabel">物资匹配</div>
        <div class="svalue">{{ summary?.material_pending_count ?? 0 }}</div>
      </div>
      <div class="scard">
        <div class="slabel">出入库</div>
        <div class="svalue">{{ summary?.flow_pending_count ?? 0 }}</div>
      </div>
      <div class="scard">
        <div class="slabel">本页列表</div>
        <div class="svalue">{{ items.length }}</div>
      </div>
    </div>

    <div class="toolbar">
      <el-radio-group v-model="kindFilter" size="small" @change="onFilterChange">
        <el-radio-button label="">全部建议</el-radio-button>
        <el-radio-button label="field">字段</el-radio-button>
        <el-radio-button label="material">物资</el-radio-button>
        <el-radio-button label="classify">分类/对齐</el-radio-button>
        <el-radio-button label="flow">出入库</el-radio-button>
      </el-radio-group>
      <el-button size="small" :loading="loading" @click="refreshAll">刷新</el-button>
      <el-button size="small" @click="$router.push('/system?tab=models')">本地模型状态</el-button>
      <el-button size="small" @click="$router.push('/todos')">治理待办</el-button>
    </div>

    <el-table
      :data="filteredItems"
      v-loading="loading"
      border
      size="small"
      empty-text="当前没有待审核的 AI 建议"
      highlight-current-row
    >
      <el-table-column label="建议类型" width="110">
        <template #default="{ row }">{{ row.kind_label || typeLabel(row.todo_type) }}</template>
      </el-table-column>
      <el-table-column label="来源" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="sourceTagType(row.suggestion_source)">
            {{ row.source_label || '候选建议' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default>
          <el-tag size="small" type="warning">待审核</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="问题" min-width="200" show-overflow-tooltip />
      <el-table-column prop="suggestion" label="系统建议" min-width="180" show-overflow-tooltip />
      <el-table-column label="置信度" width="80">
        <template #default="{ row }">
          {{ row.confidence != null ? Number(row.confidence).toFixed(2) : '—' }}
        </template>
      </el-table-column>
      <el-table-column prop="affected_rows" label="影响行数" width="90" />
      <el-table-column label="来源文件" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.source_file || '—' }}</template>
      </el-table-column>
      <el-table-column label="采纳后" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ afterEffect(row) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="canAccept(row)"
            link
            type="success"
            @click="decide(row, 'accept')"
          >
            采纳
          </el-button>
          <el-button
            v-if="canAccept(row)"
            link
            type="primary"
            @click="decide(row, 'amend')"
          >
            修改后采纳
          </el-button>
          <el-button link type="info" @click="decide(row, 'reject')">拒绝</el-button>
          <el-button link type="primary" @click="goDetail(row)">去处理</el-button>
        </template>
      </el-table-column>
    </el-table>
    <p class="hint">
      字段建议：系统根据字段名和样例值给出候选映射，请确认后再用于规整数据。物资建议：系统不会自动合并主数据，请人工确认。拒绝或忽略不会自动放行异常。
    </p>

    <el-card shadow="never" class="recent">
      <template #header>
        <div class="head">
          <span>最近已人工确认</span>
          <el-button link type="primary" @click="$router.push('/trace?tab=audit')">追溯审计</el-button>
        </div>
      </template>
      <el-table
        :data="history"
        v-loading="historyLoading"
        border
        size="small"
        empty-text="暂无确认记录"
      >
        <el-table-column prop="source" label="来源" width="120" />
        <el-table-column prop="decision" label="决定" width="100" />
        <el-table-column prop="actor" label="操作人" width="120" />
        <el-table-column prop="created_at" label="时间" width="180" />
        <el-table-column label="摘要" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ historySummary(row) }}</template>
        </el-table-column>
      </el-table>
      <p class="hint">已确认项离开「待审核」队列；本表仅展示近期人工确认痕迹。</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  formatApiError,
  governTodoDecision,
  governTodoList,
  governTodoSummary,
  listAssetHistory,
  type GovernTodoItem,
  type GovernTodoSummary,
} from '@/api/client'
import { gateLabel } from '@/utils/gateLabels'

type ReviewItem = GovernTodoItem & {
  suggestion_source?: string
  suggestion_kind?: string
  source_label?: string
  kind_label?: string
  review_label?: string
}

const router = useRouter()
const summary = ref<GovernTodoSummary | null>(null)
const summaryLoading = ref(false)
const items = ref<ReviewItem[]>([])
const loading = ref(false)
const kindFilter = ref('')
const history = ref<Array<Record<string, unknown>>>([])
const historyLoading = ref(false)

const filteredItems = computed(() => {
  if (!kindFilter.value) return items.value
  return items.value.filter((i) => i.suggestion_kind === kindFilter.value)
})

function typeLabel(t: string) {
  const map: Record<string, string> = {
    map: '字段',
    unit: '单位',
    master: '物资',
    material_align: '分类/对齐',
    flow: '出入库',
  }
  return map[t] || gateLabel(t)
}

function sourceTagType(src?: string) {
  if (src === 'model') return 'warning' as const
  if (src === 'hybrid') return 'info' as const
  if (src === 'system') return '' as const
  return 'info' as const
}

function afterEffect(row: ReviewItem) {
  const n = row.affected_rows
  const rowsPart = n != null && n > 0 ? `确认后约影响 ${n} 行` : '确认后按建议更新'
  if (row.forms_rule) return `${rowsPart}；将沉淀为规则（仍非自动发布）`
  return `${rowsPart}；不会自动写入未确认事实`
}

function canAccept(row: ReviewItem) {
  return ['map', 'unit', 'master', 'material_align', 'flow'].includes(row.todo_type)
}

function historySummary(row: Record<string, unknown>) {
  const detail = row.detail ?? row.note
  if (detail == null) return '—'
  if (typeof detail === 'string') return detail.slice(0, 120)
  try {
    return JSON.stringify(detail).slice(0, 120)
  } catch {
    return String(detail).slice(0, 120)
  }
}

function onFilterChange() {
  /* client-side filter only */
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

async function loadItems() {
  loading.value = true
  try {
    const res = await governTodoList({
      limit: 200,
      todo_type: 'ai',
      sort: 'impact',
    })
    items.value = res.items as ReviewItem[]
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const res = await listAssetHistory({ limit: 15, offset: 0 })
    history.value = (res.items || []).filter((h) => {
      const d = String(h.decision || '')
      return d && d !== 'proposed'
    })
  } catch {
    history.value = []
  } finally {
    historyLoading.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadSummary(), loadItems(), loadHistory()])
}

function goDetail(row: ReviewItem) {
  const type = row.todo_type === 'unit' ? 'unit' : row.todo_type
  router.push({ path: '/todos', query: { type, detail: type } })
}

async function decide(row: ReviewItem, decision: 'accept' | 'amend' | 'reject') {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在系统设置填写操作令牌')
    return
  }

  let amended: Record<string, unknown> | undefined
  if (decision === 'amend') {
    const current = String(row.suggestion || row.raw_ref?.to_value || '')
    try {
      const { value } = await ElMessageBox.prompt('修改后的建议值', '修改后采纳', {
        inputValue: current,
        confirmButtonText: '采纳修改',
        cancelButtonText: '取消',
      })
      if (row.todo_type === 'map' || row.todo_type === 'unit') {
        amended = { std_field: value }
      } else {
        amended = { value }
      }
    } catch {
      return
    }
  }

  let previewNote = ''
  const mappedDecision = decision === 'reject' ? 'reject' : decision === 'amend' ? 'amend' : 'accept'
  try {
    const preview = await governTodoDecision(row.todo_id, {
      decision: mappedDecision === 'reject' ? 'ignore' : mappedDecision,
      dry_run: true,
      amended_value: amended,
    })
    previewNote = [
      `影响约 ${preview.affected_rows ?? row.affected_rows ?? 0} 行`,
      preview.forms_rule ? '将沉淀为规则' : '不自动写入未确认事实',
      preview.warning || '',
    ]
      .filter(Boolean)
      .join('；')
  } catch {
    previewNote = `约影响 ${row.affected_rows ?? 0} 行`
  }

  const title =
    decision === 'reject'
      ? '拒绝该建议？'
      : decision === 'amend'
        ? '按修改后的值采纳？'
        : '采纳该 AI 建议？'
  try {
    await ElMessageBox.confirm(
      `${row.title}\n建议：${row.suggestion || '—'}\n${previewNote}\n拒绝后该项仍可能阻塞，不会静默放行。`,
      title,
      { type: 'warning' },
    )
  } catch {
    return
  }

  try {
    const key =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `ai_${Date.now()}`
    await governTodoDecision(row.todo_id, {
      decision: mappedDecision === 'reject' ? 'ignore' : mappedDecision,
      amended_value: amended,
      idempotency_key: key,
    })
    ElMessage.success(
      decision === 'reject' ? '已拒绝（未自动放行）' : '已确认建议',
    )
    await refreshAll()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

onMounted(() => {
  refreshAll()
})
</script>

<style scoped>
.ai-review { display: flex; flex-direction: column; gap: 12px; width: 100%; }
.legend :deep(.el-alert__content) { width: 100%; }
.legend-list {
  margin: 4px 0 0;
  padding-left: 1.2em;
  line-height: 1.7;
  color: #606266;
  font-size: 13px;
}
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
.slabel { color: #909399; font-size: 12px; margin-bottom: 4px; }
.svalue { font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums; }
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}
.hint { color: #909399; font-size: 12px; margin: 4px 0 0; }
.recent .head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
