<template>
  <div class="govern-hub">
    <MaterialStandardizedPanel />

    <el-alert
      v-if="isNoData"
      type="info"
      :closable="false"
      show-icon
      title="当前还没有可规整数据"
      description="请先在「数据接入」上传原始需求表或台账，完成字段识别与暂存确认后再查看物资台账。"
    >
      <el-button type="primary" @click="$router.push('/intake')">去数据接入</el-button>
    </el-alert>

    <template v-else-if="summary">
      <el-alert
        v-if="summary.next_action"
        type="info"
        :closable="false"
        show-icon
        :title="`待处理：${summary.next_action.label}`"
        :description="summary.next_action.reason"
      >
        <el-button type="primary" plain size="small" @click="$router.push(summary.next_action.path)">
          去处理
        </el-button>
      </el-alert>

      <section class="pending-bar">
        <div class="pending-head">待处理问题</div>
        <p class="pending-hint">不影响上方物资台账查询。需要处理字段、物资或对账问题时再展开。</p>
        <div class="pending-chips">
          <button class="chip" type="button" @click="openDetailByType('map')">
            待确认字段 <strong>{{ summary.todos?.map_pending ?? 0 }}</strong>
          </button>
          <button class="chip" type="button" @click="openDetailByType('master')">
            待匹配物资 <strong>{{ summary.todos?.master_pending ?? 0 }}</strong>
          </button>
          <button class="chip" type="button" @click="openDetailByType('reconcile')">
            对账差异 <strong>{{ reconcileTotal }}</strong>
          </button>
          <button class="chip" type="button" @click="openDetailByType('flow')">
            待解析流水 <strong>{{ summary.flow?.pending ?? 0 }}</strong>
          </button>
          <button class="chip warn" type="button" @click="openGateDetail">
            指标未就绪 <strong>{{ summary.gate?.ready === false ? (summary.gate.missing || []).length : 0 }}</strong>
          </button>
          <button class="chip warn" type="button" @click="openDetailByType('map')">
            待审核智能建议 <strong>{{ summary.todos?.ai_suggestion_pending ?? 0 }}</strong>
          </button>
          <button class="chip warn" type="button" @click="openDetailByType('exception')">
            阻塞行 <strong>{{ summary.quality?.blocked_rows ?? 0 }}</strong>
          </button>
          <span class="chip ok">
            预计可释放 <strong>{{ summary.estimated_releasable_rows ?? 0 }}</strong>
          </span>
        </div>
      </section>

      <section v-if="detailOpen" class="detail-section">
        <div class="section-head">
          <h3>处理详情：{{ detailTitle }}</h3>
          <el-button size="small" text @click="closeDetail">收起</el-button>
        </div>

        <GovernView
          v-if="detailInnerTab"
          :initial-tab="detailInnerTab"
          :hide-outer-tabs="true"
          @tab-change="detailActiveTab = $event"
        />
        <el-alert
          v-else-if="detailType === 'release_blocker'"
          type="warning"
          :closable="false"
          show-icon
          title="发布阻断"
          description="指标口径尚未就绪：请先完成相关规整，再启用指标口径。"
        />
        <el-alert
          v-else-if="detailType === 'exception'"
          type="warning"
          :closable="false"
          show-icon
          title="异常与阻塞"
          description="请到「数据成果」查看阻塞明细，并回到字段或物资待审中修复；忽略不等于修复。"
        >
          <el-button type="primary" link @click="$router.push('/data?tab=blocked')">查看阻塞数据</el-button>
        </el-alert>
        <p class="hint">收起详情后，汇总数字会自动刷新。</p>
      </section>

      <el-collapse v-model="advancedOpen" class="advanced-fold">
        <el-collapse-item title="高级治理（字段 / 物资待审 / 规则 / 出入库 / 库存对账）" name="adv">
          <template v-if="advancedOpen.includes('adv')">
            <el-alert
              type="warning"
              :closable="false"
              show-icon
              title="面向治理人员"
              description="规则变更前请先看影响预演；日常请优先使用上方物资台账查询，需要处理问题时再进入本区。"
              style="margin-bottom: 10px"
            />
            <el-tabs v-model="advInner">
              <el-tab-pane label="字段规整" name="map" />
              <el-tab-pane label="物资待审" name="master" />
              <el-tab-pane label="规则沉淀" name="rulelearn" />
              <el-tab-pane label="出入库记录处理" name="flow" />
              <el-tab-pane label="库存对账" name="reconcile" />
              <el-tab-pane label="规则资产" name="assets" />
              <el-tab-pane label="指标口径" name="metrics" />
            </el-tabs>
            <GovernView
              v-if="['map', 'master', 'rulelearn', 'flow', 'reconcile'].includes(advInner)"
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
import { ElMessage } from 'element-plus'
import GovernView from '@/pages/GovernView.vue'
import AssetsView from '@/pages/AssetsView.vue'
import MetricsView from '@/pages/MetricsView.vue'
import MaterialStandardizedPanel from '@/components/MaterialStandardizedPanel.vue'
import { gateLabel } from '@/utils/gateLabels'
import { formatApiError, flowReconcile, statsOverview, type StatsOverview } from '@/api/client'

const route = useRoute()
const router = useRouter()

const DETAIL_TAB_MAP: Record<string, string> = {
  map: 'map',
  unit: 'map',
  master: 'master',
  material_align: 'master',
  flow: 'flow',
  reconcile: 'reconcile',
  exception: 'reconcile',
}

const summary = ref<StatsOverview | null>(null)
const summaryLoading = ref(false)
const reconcileTotal = ref(0)
const detailOpen = ref(false)
const detailType = ref('')
const advInner = ref('map')
const advancedOpen = ref<string[]>([])

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

const detailTitle = computed(() => {
  const t = detailType.value
  const inner = detailActiveTab.value || detailInnerTab.value
  const innerMap: Record<string, string> = {
    map: '字段规整',
    rulelearn: '规则沉淀',
    master: '待处理物资',
    flow: '出入库记录处理',
    reconcile: '库存对账',
  }
  if (inner && innerMap[inner]) return innerMap[inner]
  const map: Record<string, string> = {
    map: '字段规整',
    unit: '单位规整',
    master: '待处理物资',
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

/** GovernView 内部 Tab 实时状态，随 tab-change 事件同步，保证详情标题一致（9.6）。 */
const detailActiveTab = ref('')
watch(detailInnerTab, (v) => {
  detailActiveTab.value = v
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

function syncQuery() {
  const q: Record<string, string | string[]> = { ...route.query } as Record<string, string | string[]>
  if (detailOpen.value && detailType.value) q.detail = detailType.value
  else delete q.detail
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
  detailOpen.value = true
  syncQuery()
}

function openGateDetail() {
  advInner.value = 'metrics'
  advancedOpen.value = ['adv']
}

async function closeDetail() {
  detailOpen.value = false
  detailType.value = ''
  syncQuery()
  await loadAll()
}

/** 按当前 URL query 展开对应详情/高级能力（首次加载与 SPA 内 query 变化共用）。 */
function applyRouteQuery() {
  const qTab = String(route.query.tab || '')
  const qDetail = typeof route.query.detail === 'string' ? route.query.detail : ''
  const qType = typeof route.query.type === 'string' ? route.query.type : ''

  // Legacy ?tab=map|master|... → expand detail
  if (qTab === 'map' || qTab === 'master' || qTab === 'reconcile' || qTab === 'units') {
    detailType.value = qTab === 'units' ? 'unit' : qTab
    detailOpen.value = true
  } else if (qTab === 'assets' || qTab === 'metrics' || qTab === 'rulelearn' || qTab === 'flow') {
    advInner.value = qTab
    advancedOpen.value = ['adv']
    if (qTab === 'flow') {
      detailType.value = 'flow'
      detailOpen.value = true
    }
  } else if (qTab === 'advanced') {
    advancedOpen.value = ['adv']
  } else if (qDetail) {
    openDetailByType(qDetail)
  } else if (
    qType &&
    ['map', 'unit', 'master', 'material_align', 'flow', 'reconcile', 'exception', 'release_blocker'].includes(
      qType,
    )
  ) {
    // 旧入口 /govern?type=map|master|exception|... → 本页展开对应详情
    detailType.value = qType
    detailOpen.value = true
  }
}

/** SPA 内 query 变化（如 next_action「去处理」跳 /govern?tab=map）也要即时展开详情。 */
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
.pending-bar {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--el-fill-color-blank);
}
.pending-head { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.pending-hint { margin: 0 0 8px; color: #909399; font-size: 12px; line-height: 1.6; }
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
.chip.ok { border-color: var(--el-color-success-light-5); cursor: default; }
.chip:hover:not(.ok) { border-color: var(--el-color-primary-light-5); }
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.section-head h3 { margin: 0; font-size: 16px; font-weight: 600; }
.hint { color: #909399; font-size: 12px; margin-top: 8px; }
.detail-section {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 12px;
  background: var(--el-fill-color-blank);
}
.advanced-fold { margin-top: 4px; }
.loading-box { min-height: 80px; }
</style>
