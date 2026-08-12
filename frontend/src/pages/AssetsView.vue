<template>
  <div class="assets">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="自学习资产"
      description="每次确认都让系统更准：表头映射 / 流水拆解 / SQL 修正确认后回写，下次同输入自动命中、不耗本地模型。本页只读浏览这些资产。"
    />

    <el-tabs v-model="tab" @tab-change="onTab">
      <el-tab-pane label="规则字典" name="rules" />
      <el-tab-pane label="流水示例" name="flow" />
      <el-tab-pane label="确认历史" name="history" />
      <el-tab-pane label="问答 SQL 示例" name="fewshot" />
    </el-tabs>

    <template v-if="tab === 'rules'">
      <el-card shadow="never">
        <template #header>
          <div class="head">
            <span>表头映射规则</span>
            <el-space>
              <el-input v-model="q" clearable placeholder="筛选表头 / 字段" style="width: 220px" />
              <el-button :loading="conflictLoading" @click="checkConflicts">冲突检查</el-button>
              <el-button :loading="loading" @click="loadRules">刷新</el-button>
            </el-space>
          </div>
        </template>
        <p class="hint" style="margin: 0 0 10px">
          命中 = 该表头被自动命中的次数，命中一次即省一次本地模型调用。
        </p>
        <PagedTable
          v-model:page="rulesPage"
          v-model:page-size="rulesPageSize"
          :total="rulesTotal"
          @change="loadRules"
        >
          <el-table :data="filteredRules" v-loading="loading" border size="small">
            <el-table-column prop="header" label="表头" min-width="140" />
            <el-table-column prop="std_field" label="标准字段" width="140" />
            <el-table-column prop="business_domain" label="域" width="100" />
            <el-table-column prop="hits" label="命中" width="70" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'disabled' ? 'info' : 'success'">
                  {{ row.status === 'disabled' ? '停用' : '启用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="待处理命中" width="100">
              <template #default="{ row }">
                {{ (Number(row.pending_map_hits) || 0) + (Number(row.pending_blocked_hits) || 0) }}
              </template>
            </el-table-column>
            <el-table-column prop="source" label="来源" width="120" />
            <el-table-column prop="confirmed_by" label="确认人" width="100" />
            <el-table-column prop="created_at" label="时间" width="160" />
            <el-table-column label="操作" width="170" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openPreview(row)">
                  预演
                </el-button>
                <el-button
                  v-if="row.status !== 'disabled'"
                  link
                  type="warning"
                  @click="openPreview(row, 'disable')"
                >
                  停用
                </el-button>
                <el-button v-else link type="success" @click="openPreview(row, 'enable')">
                  启用
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </PagedTable>
      </el-card>
    </template>

    <template v-else-if="tab === 'flow'">
      <el-card shadow="never">
        <template #header>
          <div class="head">
            <span>流水拆解示例</span>
            <el-button :loading="loading" @click="loadFlow">刷新</el-button>
          </div>
        </template>
        <p class="hint" style="margin: 0 0 10px">
          命中 = 该原文被直接复用的次数，复用即不耗本地模型。
        </p>
        <PagedTable
          v-model:page="flowPage"
          v-model:page-size="flowPageSize"
          :total="flowTotal"
          @change="loadFlow"
        >
          <el-table :data="flowItems" v-loading="loading" border size="small">
            <el-table-column prop="level" label="级别" width="70" />
            <el-table-column prop="text_norm" label="原文归一" min-width="220" show-overflow-tooltip />
            <el-table-column label="结构化" min-width="220">
              <template #default="{ row }">
                <span class="mono">{{ summarizeFlow(row.flow) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="hits" label="命中" width="70" />
            <el-table-column prop="confirmed_by" label="确认人" width="120" />
            <el-table-column prop="updated_at" label="更新" width="170" />
          </el-table>
        </PagedTable>
      </el-card>
    </template>

    <template v-else-if="tab === 'history'">
      <el-card shadow="never">
        <template #header>
          <div class="head">
            <span>确认历史</span>
            <el-space>
              <el-select v-model="historySource" clearable placeholder="来源" style="width: 160px" @change="onHistoryFilter">
                <el-option label="流水确认" value="flow_confirm" />
                <el-option label="映射确认" value="map_confirm" />
              </el-select>
              <el-button :loading="loading" @click="loadHistory">刷新</el-button>
            </el-space>
          </div>
        </template>
        <PagedTable
          v-model:page="historyPage"
          v-model:page-size="historyPageSize"
          :total="historyTotal"
          @change="loadHistory"
        >
          <el-table :data="historyItems" v-loading="loading" border size="small">
            <el-table-column prop="created_at" label="时间" width="170" />
            <el-table-column prop="source" label="来源" width="120" />
            <el-table-column prop="decision" label="决策" width="120" />
            <el-table-column prop="detail" label="详情" min-width="160" show-overflow-tooltip />
            <el-table-column prop="note" label="备注" min-width="140" show-overflow-tooltip />
            <el-table-column prop="actor" label="操作者" width="120" />
          </el-table>
        </PagedTable>
      </el-card>
    </template>

    <template v-else>
      <el-card shadow="never">
        <template #header>
          <div class="head">
            <span>问答 SQL 示例</span>
            <el-button :loading="loading" @click="loadFewshot">刷新</el-button>
          </div>
        </template>
        <p class="hint" style="margin: 0 0 10px">
          命中 = 该示例被选为问答模板的次数，模板命中即不调本地模型生成 SQL。
        </p>
        <el-alert
          v-if="fewshotNote"
          type="warning"
          :closable="false"
          :title="fewshotNote"
          style="margin-bottom: 12px"
        />
        <PagedTable
          v-model:page="fewshotPage"
          v-model:page-size="fewshotPageSize"
          :total="fewshotTotal"
          @change="loadFewshot"
        >
          <el-table :data="fewshotItems" v-loading="loading" border size="small" empty-text="暂无">
            <el-table-column prop="question_type" label="类型" width="120" />
            <el-table-column prop="question" label="问题" min-width="200" show-overflow-tooltip />
            <el-table-column prop="sql_gold" label="金标 SQL" min-width="220" show-overflow-tooltip />
            <el-table-column prop="hits" label="命中" width="70" />
          </el-table>
        </PagedTable>
      </el-card>
    </template>

    <el-dialog
      v-model="previewVisible"
      :title="`规则变更预演：${previewData?.header || ''}`"
      width="540px"
      destroy-on-close
    >
      <template v-if="previewData">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="规则">
            「{{ previewData.header }}」→ {{ previewData.std_field }}（{{ previewData.business_domain }}）
          </el-descriptions-item>
          <el-descriptions-item label="变更">
            {{ previewData.current_status === 'active' ? '启用' : '停用' }} → {{ previewData.next_status === 'active' ? '启用' : '停用' }}
          </el-descriptions-item>
          <el-descriptions-item label="影响数据">
            {{ previewData.affected_rows }} 行待处理记录（未确认字段待办 + 阻塞明细同表头）
          </el-descriptions-item>
          <el-descriptions-item label="是否需要重建">
            {{ previewData.rebuild_needed ? '是' : '否' }}
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          :title="previewData.warning"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 10px"
        />
      </template>
      <template #footer>
        <el-button @click="previewVisible = false">取消</el-button>
        <el-button type="primary" :loading="confirmBusy" @click="confirmStatus">
          确认{{ previewData?.action === 'enable' ? '启用' : '停用' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="conflictsVisible" title="规则冲突检查" width="640px" destroy-on-close>
      <el-alert
        v-if="conflictHint"
        :type="conflicts.length ? 'warning' : 'success'"
        :closable="false"
        show-icon
        :title="conflictHint"
        style="margin-bottom: 10px"
      />
      <el-table v-if="conflicts.length" :data="conflicts" border size="small" max-height="320">
        <el-table-column prop="header" label="表头" min-width="140" />
        <el-table-column prop="business_domain" label="域" width="100" />
        <el-table-column label="冲突字段" min-width="180">
          <template #default="{ row }">{{ (row.fields || []).join(' / ') }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">{{ (row.statuses || []).join(', ') }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="无冲突" :image-size="56" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PagedTable from '@/components/PagedTable.vue'
import {
  formatApiError,
  listAssetHistory,
  listAssetFewshot,
  listFlowExamples,
  listRuleDict,
  ruleDictConflicts,
  ruleDictConfirm,
  ruleDictPreview,
  type RuleDictPreview,
} from '@/api/client'

const tab = ref('rules')
const loading = ref(false)
const q = ref('')

const rules = ref<Array<Record<string, unknown>>>([])
const rulesTotal = ref(0)
const rulesPage = ref(1)
const rulesPageSize = ref(20)

const previewVisible = ref(false)
const previewData = ref<RuleDictPreview | null>(null)
const confirmBusy = ref(false)
const conflictsVisible = ref(false)
const conflicts = ref<Array<Record<string, unknown>>>([])
const conflictLoading = ref(false)
const conflictHint = ref('')

const flowItems = ref<Array<Record<string, unknown>>>([])
const flowTotal = ref(0)
const flowPage = ref(1)
const flowPageSize = ref(20)

const historyItems = ref<Array<Record<string, unknown>>>([])
const historyTotal = ref(0)
const historyPage = ref(1)
const historyPageSize = ref(20)
const historySource = ref<string | undefined>()

const fewshotItems = ref<Array<Record<string, unknown>>>([])
const fewshotTotal = ref(0)
const fewshotPage = ref(1)
const fewshotPageSize = ref(20)
const fewshotNote = ref('')

const filteredRules = computed(() => {
  const needle = q.value.trim().toLowerCase()
  if (!needle) return rules.value
  return rules.value.filter(
    (r) =>
      String(r.header || '')
        .toLowerCase()
        .includes(needle) ||
      String(r.std_field || '')
        .toLowerCase()
        .includes(needle),
  )
})

function summarizeFlow(flow: unknown): string {
  const arr = Array.isArray(flow) ? flow : []
  const first = (arr[0] || {}) as Record<string, unknown>
  return [first.parse_level, first.flow_type, first.quantity != null ? `qty=${first.quantity}` : null, first.person]
    .filter(Boolean)
    .join(' · ') || '—'
}

async function loadRules() {
  loading.value = true
  try {
    const res = await listRuleDict(rulesPageSize.value, (rulesPage.value - 1) * rulesPageSize.value)
    rules.value = res.items as Array<Record<string, unknown>>
    rulesTotal.value = res.total
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    loading.value = false
  }
}

async function loadFlow() {
  loading.value = true
  try {
    const res = await listFlowExamples(flowPageSize.value, (flowPage.value - 1) * flowPageSize.value)
    flowItems.value = res.items as Array<Record<string, unknown>>
    flowTotal.value = res.total
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  loading.value = true
  try {
    const res = await listAssetHistory({
      limit: historyPageSize.value,
      offset: (historyPage.value - 1) * historyPageSize.value,
      source: historySource.value,
    })
    historyItems.value = res.items
    historyTotal.value = res.total
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    loading.value = false
  }
}

async function onHistoryFilter() {
  historyPage.value = 1
  await loadHistory()
}

async function loadFewshot() {
  loading.value = true
  try {
    const res = await listAssetFewshot(
      fewshotPageSize.value,
      (fewshotPage.value - 1) * fewshotPageSize.value,
    )
    fewshotItems.value = res.items
    fewshotTotal.value = res.total
    fewshotNote.value = res.note || ''
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    loading.value = false
  }
}

async function onTab(name: string | number) {
  const n = String(name)
  if (n === 'rules') await loadRules()
  else if (n === 'flow') await loadFlow()
  else if (n === 'history') await loadHistory()
  else await loadFewshot()
}

function needOpsToken(): boolean {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return false
  }
  return true
}

async function openPreview(row: Record<string, unknown>, action?: 'enable' | 'disable') {
  const rid = Number(row.rule_id)
  if (!rid) return
  const target: 'enable' | 'disable' =
    action || (row.status === 'disabled' ? 'enable' : 'disable')
  try {
    previewData.value = await ruleDictPreview(rid, target)
    previewVisible.value = true
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

async function confirmStatus() {
  const p = previewData.value
  if (!p) return
  if (!needOpsToken()) return
  try {
    await ElMessageBox.confirm(
      `确认${p.action === 'enable' ? '启用' : '停用'}规则「${p.header}」？\n` +
        `影响约 ${p.affected_rows} 行；${p.rebuild_needed ? '需要重建' : '不需要重建'}。\n${p.warning}`,
      '规则变更确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  confirmBusy.value = true
  const key =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `rule_${Date.now()}`
  try {
    await ruleDictConfirm(p.rule_id, {
      action: p.action as 'enable' | 'disable',
      note: '规则资产页面确认',
      idempotency_key: key,
    })
    ElMessage.success(p.action === 'enable' ? '已启用规则' : '已停用规则')
    previewVisible.value = false
    await loadRules()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    confirmBusy.value = false
  }
}

async function checkConflicts() {
  conflictLoading.value = true
  try {
    const res = await ruleDictConflicts()
    conflicts.value = (res.conflicts || []) as Array<Record<string, unknown>>
    conflictHint.value = res.ok
      ? '无规则冲突'
      : `发现 ${res.conflict_count} 组冲突（同一表头映射到多个标准字段，须人工处理）`
    conflictsVisible.value = true
    ElMessage[res.ok ? 'success' : 'warning'](conflictHint.value)
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    conflictLoading.value = false
  }
}

onMounted(loadRules)
</script>

<style scoped>
.assets { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 13px; margin: 8px 0 0; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; }
</style>
