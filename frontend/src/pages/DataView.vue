<template>
  <div class="data-hub">
    <el-tabs v-model="tab" @tab-change="onTab">
      <el-tab-pane label="物资台账" name="materials" />
      <el-tab-pane label="规整明细" name="detail" />
      <el-tab-pane label="报表导出" name="report" />
      <el-tab-pane label="趋势分析" name="trend" />
    </el-tabs>

    <MaterialStandardizedPanel v-if="tab === 'materials'" />
    <BrowseView v-else-if="tab === 'detail'" mode="staged" />
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
import MaterialStandardizedPanel from '@/components/MaterialStandardizedPanel.vue'

const route = useRoute()
const router = useRouter()

function normalizeTab(v: unknown) {
  const s = String(v || '')
  if (s === 'trend') return 'trend'
  if (s === 'report') return 'report'
  if (s === 'detail' || s === 'available' || s === 'staged' || s === 'blocked') return 'detail'
  if (s === 'materials' || s === 'material' || s === 'ledger') return 'materials'
  if (route.query.categories || route.query.locations || route.query.q) return 'materials'
  return 'materials'
}

const tab = ref(normalizeTab(route.query.tab))

function onTab(name: string | number) {
  const t = String(name)
  tab.value = t
  const next: Record<string, string | string[]> = { ...route.query, tab: t }
  if (t !== 'materials') {
    delete next.categories
    delete next.locations
    delete next.q
    delete next.page
    delete next.page_size
  }
  router.replace({ path: '/data', query: next })
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
