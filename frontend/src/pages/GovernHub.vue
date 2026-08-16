<template>
  <div class="govern-hub">
    <div class="page-head">
      <div>
        <h2 class="title">数据规整</h2>
        <p class="desc">处理新数据中的待确认问题。完整结果在数据成果查看。</p>
      </div>
      <el-space wrap>
        <el-button type="primary" plain @click="$router.push('/data?tab=materials')">查看物资台账</el-button>
        <el-button :loading="summaryLoading" @click="loadAll">刷新</el-button>
      </el-space>
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
      <section class="pending-bar">
        <div class="pending-head">待处理问题</div>
        <p class="pending-hint">点击卡片进入处理。</p>
        <div class="pending-chips">
          <button class="chip" type="button" @click="openDetailByType('map')">
            待确认字段 <strong>{{ summary.todos?.map_pending ?? 0 }}</strong>
          </button>
          <button class="chip" type="button" @click="openDetailByType('master')">
            待匹配物资 <strong>{{ summary.todos?.master_pending ?? 0 }}</strong>
          </button>
          <button class="chip" type="button" @click="openDetailByType('flow')">
            待解析流水 <strong>{{ summary.flow?.pending ?? 0 }}</strong>
          </button>
          <button class="chip" type="button" @click="openDetailByType('reconcile')">
            对账差异 <strong>{{ reconcileTotal }}</strong>
          </button>
          <button class="chip warn" type="button" @click="openDetailByType('release_blocker')">
            门禁阻断 <strong>{{ gateMissing }}</strong>
          </button>
        </div>
        <p class="pending-foot">处理完成后刷新数量；完整结果在数据成果查看。</p>
      </section>

      <section v-if="detailVisible" ref="detailPanel" class="detail-section">
        <div class="section-head">
          <h3>处理详情：{{ detailTitle }}</h3>
          <el-button size="small" text @click="closeDetail">收起</el-button>
        </div>
        <p class="hint">处理完成后刷新数量。</p>

        <GovernView
          v-if="detailInnerTab"
          :initial-tab="activeGovernTab"
          :hide-outer-tabs="false"
          @tab-change="onGovernTabChange"
        />
        <template v-else-if="detailType === 'release_blocker'">
          <p class="hint">指标口径尚未就绪时，先完成相关规整，再启用指标口径。</p>
          <MetricsView :editable="metricsEditable" />
        </template>
        <AssetsView v-else-if="detailType === 'assets'" />
        <p v-else class="hint">请从上方待处理问题进入对应处理。</p>
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
import { formatApiError, flowReconcile, statsOverview, type StatsOverview } from '@/api/client'

const route = useRoute()
const router = useRouter()

const GOVERN_TABS = ['map', 'rulelearn', 'master', 'flow', 'reconcile'] as const
const LEDGER_TABS = new Set(['material', 'materials', 'ledger'])

const DETAIL_TAB_MAP: Record<string, string> = {
  map: 'map',
  unit: 'map',
  master: 'master',
  material_align: 'master',
  flow: 'flow',
  reconcile: 'reconcile',
  rulelearn: 'rulelearn',
}

const summary = ref<StatsOverview | null>(null)
const summaryLoading = ref(false)
const reconcileTotal = ref(0)
const detailVisible = ref(false)
const detailType = ref('')
const activeGovernTab = ref('map')
const detailPanel = ref<HTMLElement | null>(null)

const isNoData = computed(
  () =>
    summary.value != null &&
    summary.value.recent_files.length === 0 &&
    (summary.value.todos?.total ?? 0) === 0,
)

const metricsEditable = computed(() => {
  const role = localStorage.getItem('ops_role') || 'ops'
  return role === 'ops' || role === 'govern'
})

const gateMissing = computed(() => {
  if (summary.value?.gate?.ready === false) return (summary.value.gate.missing || []).length
  return 0
})

const detailTitle = computed(() => {
  const innerMap: Record<string, string> = {
    map: '字段规整',
    rulelearn: '规则沉淀',
    master: '待处理物资',
    flow: '出入库记录处理',
    reconcile: '库存对账',
  }
  if (innerMap[activeGovernTab.value]) return innerMap[activeGovernTab.value]
  if (detailType.value === 'release_blocker') return '门禁阻断'
  if (detailType.value === 'assets') return '规则资产'
  return '字段规整 / 规则沉淀 / 待处理物资 / 出入库记录处理 / 库存对账'
})

const detailInnerTab = computed(() => {
  const t = detailType.value
  if (t === 'release_blocker' || t === 'assets') return ''
  return DETAIL_TAB_MAP[t] || activeGovernTab.value || ''
})

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
  summaryLoading.value = true
  try {
    summary.value = await statsOverview()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    summaryLoading.value = false
  }
}

async function loadReconcileTotal() {
  try {
    const res = await flowReconcile()
    reconcileTotal.value = res.total ?? 0
  } catch {
    reconcileTotal.value = 0
  }
}

async function loadAll() {
  await Promise.all([loadSummary(), loadReconcileTotal()])
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
.govern-hub { display: flex; flex-direction: column; gap: 12px; width: 100%; }
.page-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.title { margin: 0; font-size: 18px; font-weight: 600; }
.desc { margin: 6px 0 0; color: #606266; font-size: 13px; line-height: 1.6; }
.pending-bar {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--el-fill-color-blank);
}
.pending-head { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.pending-hint { margin: 0 0 8px; color: #909399; font-size: 12px; line-height: 1.6; }
.pending-foot { margin: 8px 0 0; color: #909399; font-size: 12px; line-height: 1.6; }
.pending-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  color: #606266;
  cursor: pointer;
}
.chip strong { color: #303133; font-size: 14px; margin-left: 4px; font-variant-numeric: tabular-nums; }
.chip.warn { border-color: var(--el-color-warning-light-5); }
.chip:hover { border-color: var(--el-color-primary-light-5); }
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.section-head h3 { margin: 0; font-size: 16px; font-weight: 600; }
.hint { color: #909399; font-size: 12px; margin: 0 0 8px; }
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
