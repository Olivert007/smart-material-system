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
        v-if="summary.next_action"
        type="info"
        :closable="false"
        show-icon
        :title="`下一步：${summary.next_action.label}`"
        :description="summary.next_action.reason"
      >
        <el-button type="primary" plain size="small" @click="$router.push(summary.next_action.path)">
          去处理
        </el-button>
      </el-alert>

      <div class="summary-row" v-loading="summaryLoading">
        <div class="scard clickable" @click="openDetailByType('map')">
          <div class="slabel">待确认字段</div>
          <div class="svalue">{{ summary.todos?.map_pending ?? 0 }}</div>
        </div>
        <div class="scard clickable" @click="openDetailByType('master')">
          <div class="slabel">待匹配物资</div>
          <div class="svalue">{{ summary.todos?.master_pending ?? 0 }}</div>
        </div>
        <div class="scard clickable" @click="openDetailByType('reconcile')">
          <div class="slabel">对账差异</div>
          <div class="svalue">{{ reconcileTotal }}</div>
        </div>
        <div class="scard clickable" @click="openDetailByType('flow')">
          <div class="slabel">待解析流水</div>
          <div class="svalue">{{ summary.flow?.pending ?? 0 }}</div>
        </div>
        <div class="scard warn clickable" title="点击查看指标口径" @click="openGateDetail">
          <div class="slabel">门禁阻断</div>
          <div class="svalue">
            {{ summary.gate?.ready === false ? (summary.gate.missing || []).length : 0 }}
          </div>
        </div>
        <div class="scard warn clickable" @click="openDetailByType('map')">
          <div class="slabel">待审核 AI 建议</div>
          <div class="svalue">{{ summary.todos?.ai_suggestion_pending ?? 0 }}</div>
        </div>
        <div class="scard warn clickable" @click="openDetailByType('exception')">
          <div class="slabel">阻塞行</div>
          <div class="svalue">{{ summary.quality?.blocked_rows ?? 0 }}</div>
        </div>
        <div class="scard ok">
          <div class="slabel">预计可释放</div>
          <div class="svalue">{{ summary.estimated_releasable_rows ?? 0 }}</div>
        </div>
      </div>

      <!-- Detail expands on demand -->
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
          description="指标门禁尚未就绪：请先完成相关规整，再启用指标口径。"
        />
        <el-alert
          v-else-if="detailType === 'exception'"
          type="warning"
          :closable="false"
          show-icon
          title="异常与阻塞"
          description="请到「数据成果 → 阻塞数据」查看明细并回到字段/物资规整修复；忽略不等于修复。"
        >
          <el-button type="primary" link @click="$router.push('/data?tab=blocked')">查看阻塞数据</el-button>
        </el-alert>
        <p class="hint">收起详情后，汇总卡片会自动刷新。</p>
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
import { ElMessage } from 'element-plus'
import GovernView from '@/pages/GovernView.vue'
import AssetsView from '@/pages/AssetsView.vue'
import MetricsView from '@/pages/MetricsView.vue'
import { gateLabel } from '@/utils/gateLabels'
import { formatApiError, flowReconcile, statsOverview, type StatsOverview } from '@/api/client'

const route = useRoute()
const router = useRouter()

/** 数据规整工作台：摘要卡片点击只在本页展开详情，不跳转其它治理入口 */
const hubTitle = computed(() => '数据规整工作台')
const hubDescription = computed(
  () =>
    '按优先级处理字段、物资、出入库和库存对账问题；AI 建议须人工确认后才会进入可用数据。',
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

const summary = ref<StatsOverview | null>(null)
const summaryLoading = ref(false)
const reconcileTotal = ref(0)
const detailOpen = ref(false)
const detailType = ref('')
const advInner = ref('rulelearn')
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
  // 规则沉淀 / 物资主数据 / 出入库记录处理等以 GovernView 内部 Tab 为准
  const inner = detailActiveTab.value || detailInnerTab.value
  const innerMap: Record<string, string> = {
    map: '字段规整',
    rulelearn: '规则沉淀',
    master: '物资主数据',
    flow: '出入库记录处理',
    reconcile: '库存对账',
  }
  if (inner && innerMap[inner]) return innerMap[inner]
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
  const q: Record<string, string> = {}
  if (detailOpen.value && detailType.value) q.detail = detailType.value
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

onMounted(async () => {
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

  await loadAll()
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
.loading-box { min-height: 120px; }
</style>
