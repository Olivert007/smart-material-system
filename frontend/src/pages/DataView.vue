<template>
  <div class="data-hub">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="数据成果"
      description="本页查看规整后的业务库明细、报表和趋势。按物资种类、存放区域筛选并导出，请到「数据规整」。"
    >
      <el-button type="primary" link @click="$router.push('/govern')">去物资台账</el-button>
    </el-alert>
    <el-tabs v-model="tab" @tab-change="onTab">
      <el-tab-pane label="规整明细" name="detail" />
      <el-tab-pane label="报表导出" name="report" />
      <el-tab-pane label="趋势分析" name="trend" />
    </el-tabs>

    <BrowseView v-if="tab === 'detail'" mode="staged" />
    <ReportsCatalog v-else-if="tab === 'report'" />
    <FlowAnalytics v-else />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrowseView from '@/pages/BrowseView.vue'
import ReportsCatalog from '@/components/ReportsCatalog.vue'
import FlowAnalytics from '@/components/FlowAnalytics.vue'

const route = useRoute()
const router = useRouter()

/** 顶层 Tab 与参考项目一致：detail=规整明细、report=报表导出、trend=趋势分析。 */
function normalizeTab(v: unknown) {
  const s = String(v || '')
  if (s === 'trend') return 'trend'
  if (s === 'report') return 'report'
  // 兼容旧链接：available/staged/blocked 都回到「规整明细」
  return 'detail'
}

const LEDGER_QUERY_KEYS = ['categories', 'locations', 'q', 'page', 'page_size'] as const

/** 旧的物资台账筛选链接曾挂在本页，转到数据规整正门，避免筛选项落空。 */
function redirectLegacyLedgerQuery() {
  const hasLedgerFilter = Boolean(route.query.categories || route.query.locations)
  if (!hasLedgerFilter) return false
  const next: Record<string, string> = {}
  for (const k of LEDGER_QUERY_KEYS) {
    const v = route.query[k]
    if (typeof v === 'string' && v) next[k] = v
  }
  router.replace({ path: '/govern', query: next })
  return true
}

const tab = ref(normalizeTab(route.query.tab))
redirectLegacyLedgerQuery()

function onTab(name: string | number) {
  const t = String(name)
  tab.value = t
  router.replace({ path: '/data', query: { ...route.query, tab: t } })
}

watch(
  () => route.query.tab,
  (v) => {
    tab.value = normalizeTab(v)
  },
)
</script>

<style scoped>
.data-hub { display: flex; flex-direction: column; gap: 12px; width: 100%; }
</style>
