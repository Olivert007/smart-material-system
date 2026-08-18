<template>
  <div class="govern-hub">
    <div class="page-head">
      <p class="desc">处理新数据里还没确认的问题。</p>
      <div class="head-actions">
        <el-button text type="primary" @click="$router.push('/data?tab=materials')">查看物资台账</el-button>
        <el-button :loading="summaryLoading" @click="loadAll">刷新</el-button>
      </div>
    </div>

    <el-alert
      v-if="isNoData"
      type="info"
      :closable="false"
      show-icon
      title="当前还没有可规整数据"
      description="请先在「数据接入」上传原始需求表或台账，完成字段识别与暂存确认后再处理问题。"
    >
      <el-button type="primary" @click="$router.push('/intake')">去数据接入</el-button>
    </el-alert>

    <template v-else-if="summary">
      <section class="queue">
        <p v-if="!activeItems.length" class="all-clear">当前没有待处理问题。</p>
        <div v-if="activeItems.length" class="work-grid">
          <button
            v-for="item in activeItems"
            :key="item.id"
            class="work-card"
            :class="{
              primary: item.primary,
              'is-open': isOpen(item.id),
              warn: item.warn,
            }"
            type="button"
            :aria-pressed="isOpen(item.id)"
            @click="openDetailByType(item.id)"
          >
            <div class="work-name">{{ item.label }}</div>
            <div class="work-count">{{ item.count }}</div>
            <p class="work-hint">{{ item.hint }}</p>
            <span v-if="item.primary" class="work-cta">去处理</span>
          </button>
        </div>
        <div v-if="idleItems.length" class="idle-row">
          <span class="idle-label">其余队列</span>
          <button
            v-for="item in idleItems"
            :key="item.id"
            class="idle-chip"
            :class="{ 'is-open': isOpen(item.id) }"
            type="button"
            @click="openDetailByType(item.id)"
          >
            {{ item.label }} 0
          </button>
        </div>
      </section>

      <section v-if="detailVisible" ref="detailPanel" class="detail-section">
        <div class="section-head">
          <h3 v-if="!showFieldFamilyTabs">{{ detailTitle }}</h3>
          <div v-else class="family-tabs">
            <button
              class="family-tab"
              :class="{ on: activeGovernTab === 'map' }"
              type="button"
              @click="openDetailByType('map')"
            >
              待确认字段
            </button>
            <button
              class="family-tab"
              :class="{ on: activeGovernTab === 'rulelearn' }"
              type="button"
              @click="openDetailByType('rulelearn')"
            >
              待确认规则
            </button>
          </div>
          <el-button size="small" text @click="closeDetail">收起</el-button>
        </div>

        <GovernView
          v-if="detailInnerTab"
          :key="activeGovernTab"
          :initial-tab="activeGovernTab"
          :hide-outer-tabs="true"
          @tab-change="onGovernTabChange"
          @queue-changed="onQueueChanged"
        />
        <template v-else-if="detailType === 'release_blocker'">
          <p class="hint">指标口径尚未就绪时，先完成相关规整，再启用指标口径。</p>
          <MetricsView :editable="metricsEditable" />
        </template>
        <AssetsView v-else-if="detailType === 'assets'" />
      </section>
    </template>

    <div v-else v-loading="summaryLoading" class="loading-box" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import GovernView from '@/pages/GovernView.vue'
import AssetsView from '@/pages/AssetsView.vue'
import MetricsView from '@/pages/MetricsView.vue'
import {
  formatApiError,
  flowReconcile,
  listRuleLearnCandidates,
  statsOverview,
  type StatsOverview,
} from '@/api/client'

type QueueId = 'map' | 'rulelearn' | 'master' | 'flow' | 'reconcile' | 'release_blocker' | 'assets'

type QueueItem = {
  id: QueueId
  label: string
  hint: string
  count: number
  warn?: boolean
  primary?: boolean
}

const QUEUE_META: Array<Omit<QueueItem, 'count' | 'primary'>> = [
  { id: 'map', label: '待确认字段', hint: '确认系统不确定的字段。' },
  { id: 'rulelearn', label: '待确认规则', hint: '采用后变成后续可复用规则。' },
  { id: 'master', label: '待匹配物资', hint: '批准、修正、合并或拒绝候选物资。' },
  { id: 'flow', label: '待解析流水', hint: '审核无法自动确认的出入库记录。' },
  { id: 'reconcile', label: '对账差异', hint: '查看库存与流水差异，必要时补期初库存。' },
  { id: 'release_blocker', label: '门禁阻断', hint: '先完成相关规整，再启用指标口径。' },
]

const route = useRoute()
const router = useRouter()

const GOVERN_TABS = ['map', 'rulelearn', 'master', 'flow', 'reconcile', 'release_blocker'] as const
const LEDGER_TABS = new Set(['material', 'materials', 'ledger'])

const DETAIL_TAB_MAP: Record<string, string> = {
  map: 'map',
  unit: 'map',
  master: 'master',
  material_align: 'master',
  flow: 'flow',
  reconcile: 'reconcile',
  rulelearn: 'rulelearn',
  release_blocker: 'release_blocker',
}

const summary = ref<StatsOverview | null>(null)
const summaryLoading = ref(false)
const reconcileTotal = ref(0)
const ruleLearnTotal = ref(0)
const detailVisible = ref(false)
const detailType = ref('')
const activeGovernTab = ref('map')
const detailPanel = ref<HTMLElement | null>(null)
let queueRefreshTimer: ReturnType<typeof setTimeout> | undefined

const isNoData = computed(
  () =>
    summary.value != null &&
    summary.value.recent_files.length === 0 &&
    (summary.value.todos?.total ?? 0) === 0 &&
    reconcileTotal.value === 0,
)

const metricsEditable = computed(() => {
  const role = localStorage.getItem('ops_role') || 'ops'
  return role === 'ops' || role === 'govern'
})

const gateMissing = computed(() => {
  if (summary.value?.gate?.ready === false) return (summary.value.gate.missing || []).length
  return 0
})

const queueItems = computed<QueueItem[]>(() => {
  const counts: Record<string, number> = {
    map: summary.value?.todos?.map_pending ?? 0,
    rulelearn: ruleLearnTotal.value,
    master: summary.value?.todos?.master_pending ?? 0,
    flow: summary.value?.flow?.pending ?? 0,
    reconcile: reconcileTotal.value,
    release_blocker: gateMissing.value,
  }
  return QUEUE_META.map((meta) => ({
    ...meta,
    count: counts[meta.id] ?? 0,
    warn: meta.id === 'release_blocker' && (counts[meta.id] ?? 0) > 0,
  }))
})

const activeItems = computed(() => {
  const items = queueItems.value.filter((i) => i.count > 0)
  items.sort((a, b) => {
    if (Boolean(a.warn) !== Boolean(b.warn)) return a.warn ? -1 : 1
    if (b.count !== a.count) return b.count - a.count
    return 0
  })
  return items.map((item, idx) => ({ ...item, primary: idx === 0 }))
})

const idleItems = computed(() => queueItems.value.filter((i) => i.count <= 0))

const detailTitle = computed(() => {
  const found = QUEUE_META.find((m) => m.id === (detailInnerTab.value || detailType.value))
  if (found) return found.label
  if (detailType.value === 'assets') return '规则资产'
  return '待处理问题'
})

const detailInnerTab = computed(() => {
  const t = detailType.value
  if (t === 'release_blocker' || t === 'assets') return ''
  return DETAIL_TAB_MAP[t] || activeGovernTab.value || ''
})

const showFieldFamilyTabs = computed(() => {
  return detailVisible.value && (activeGovernTab.value === 'map' || activeGovernTab.value === 'rulelearn')
})

function isOpen(id: string) {
  if (!detailVisible.value) return false
  if (id === 'release_blocker') return detailType.value === 'release_blocker'
  return activeGovernTab.value === id || detailType.value === id
}

function syncQuery() {
  const q: Record<string, string | string[]> = { ...route.query } as Record<string, string | string[]>
  if (detailVisible.value && (activeGovernTab.value || detailType.value)) {
    q.tab = activeGovernTab.value || detailType.value
  } else {
    delete q.tab
  }
  delete q.detail
  delete q.type
  router.replace({ path: '/govern', query: q })
}

async function loadSummary() {
  summary.value = await statsOverview()
}

async function loadReconcileTotal() {
  try {
    const res = await flowReconcile()
    reconcileTotal.value = res.total ?? 0
  } catch {
    reconcileTotal.value = 0
  }
}

async function loadRuleLearnCount() {
  try {
    const res = await listRuleLearnCandidates(200, 'proposed')
    ruleLearnTotal.value = res.total ?? 0
  } catch {
    ruleLearnTotal.value = 0
  }
}

async function loadAll() {
  summaryLoading.value = true
  try {
    await Promise.all([loadSummary(), loadReconcileTotal(), loadRuleLearnCount()])
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    summaryLoading.value = false
  }
}

async function refreshCounts(includeReconcile: boolean) {
  try {
    const tasks: Array<Promise<unknown>> = [loadSummary(), loadRuleLearnCount()]
    if (includeReconcile) tasks.push(loadReconcileTotal())
    await Promise.all(tasks)
  } catch {
    /* keep last counts */
  }
}

function onQueueChanged() {
  if (queueRefreshTimer) clearTimeout(queueRefreshTimer)
  queueRefreshTimer = setTimeout(() => {
    const needReconcile =
      activeGovernTab.value === 'reconcile' || detailType.value === 'release_blocker'
    void refreshCounts(needReconcile)
  }, 280)
}

function openDetailByType(t: string) {
  detailType.value = t
  activeGovernTab.value = DETAIL_TAB_MAP[t] || 'map'
  detailVisible.value = true
  syncQuery()
  nextTick(() => detailPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}

function onGovernTabChange(tab: string) {
  activeGovernTab.value = tab
  detailType.value = tab
  syncQuery()
}

async function closeDetail() {
  detailVisible.value = false
  detailType.value = ''
  syncQuery()
  await loadAll()
}

function applyRouteQuery() {
  const qTab = String(route.query.tab || '')
  const qDetail = typeof route.query.detail === 'string' ? route.query.detail : ''
  const qType = typeof route.query.type === 'string' ? route.query.type : ''

  if (LEDGER_TABS.has(qTab)) {
    router.replace({ path: '/data', query: { tab: 'materials' } })
    return
  }

  if (qTab === 'assets' || qTab === 'metrics' || qTab === 'advanced') {
    detailType.value = qTab === 'assets' ? 'assets' : 'release_blocker'
    detailVisible.value = true
    return
  }

  if ((GOVERN_TABS as readonly string[]).includes(qTab) || qTab === 'units') {
    const mapped = qTab === 'units' ? 'map' : qTab
    detailType.value = mapped
    activeGovernTab.value = mapped
    detailVisible.value = true
    return
  }

  if (qDetail) {
    openDetailByType(qDetail)
    return
  }

  if (
    qType &&
    ['map', 'unit', 'master', 'material_align', 'flow', 'reconcile', 'exception', 'release_blocker'].includes(qType)
  ) {
    openDetailByType(qType === 'exception' ? 'reconcile' : qType)
  }
}

watch(
  () => [route.query.tab, route.query.detail, route.query.type] as const,
  () => applyRouteQuery(),
)

onMounted(async () => {
  applyRouteQuery()
  await loadAll()
})
</script>

<style scoped>
.govern-hub { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.desc { margin: 0; color: #606266; font-size: 13px; line-height: 1.6; }
.head-actions { display: flex; align-items: center; gap: 4px; }
.all-clear { margin: 0 0 8px; color: #67c23a; font-size: 13px; }
.work-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}
.work-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  text-align: left;
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  border-radius: 8px;
  padding: 14px 16px;
  cursor: pointer;
  color: inherit;
}
.work-card:hover { border-color: var(--el-color-primary-light-5); }
.work-card.primary { border-color: var(--el-color-primary-light-5); background: var(--el-color-primary-light-9); }
.work-card.is-open { border-color: var(--el-color-primary); }
.work-card.warn { border-color: var(--el-color-warning); background: var(--el-color-warning-light-9); }
.work-name { font-size: 14px; font-weight: 600; color: #303133; }
.work-count {
  margin-top: 6px;
  font-size: 24px;
  font-weight: 650;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
  color: #303133;
}
.work-card.primary .work-count { color: var(--el-color-primary); }
.work-card.warn .work-count { color: var(--el-color-warning-dark-2); }
.work-hint { margin: 8px 0 0; color: #909399; font-size: 12px; line-height: 1.5; }
.work-cta {
  margin-top: 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.idle-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.idle-label { font-size: 12px; color: #c0c4cc; }
.idle-chip {
  border: 1px dashed var(--el-border-color);
  background: transparent;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  color: #c0c4cc;
  cursor: pointer;
}
.idle-chip:hover { color: #606266; border-color: #c0c4cc; }
.idle-chip.is-open { color: var(--el-color-primary); border-color: var(--el-color-primary-light-5); border-style: solid; }
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.section-head h3 { margin: 0; font-size: 16px; font-weight: 600; }
.hint { color: #909399; font-size: 12px; margin: 0 0 8px; }
.family-tabs { display: flex; gap: 8px; }
.family-tab {
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 13px;
  color: #606266;
  cursor: pointer;
}
.family-tab.on {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  font-weight: 600;
}
.detail-section {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 12px;
  background: var(--el-fill-color-blank);
}
.loading-box { min-height: 80px; }
@media (max-width: 720px) {
  .page-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
