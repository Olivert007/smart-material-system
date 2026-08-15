<template>
  <div class="data-hub">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="数据成果"
      description="规整明细展示已规整后的物资台账，可筛选和导出；报表与趋势基于当前业务库可用候选数据，均非正式发布。"
    />
    <el-tabs v-model="tab" @tab-change="onTab">
      <el-tab-pane label="规整明细" name="detail" />
      <el-tab-pane label="报表导出" name="report" />
      <el-tab-pane label="趋势分析" name="trend" />
    </el-tabs>

    <template v-if="tab === 'detail'">
      <MaterialStandardizedPanel />
      <el-collapse class="advanced-browse">
        <el-collapse-item title="其他表浏览（高级）" name="browse">
          <BrowseView mode="staged" />
        </el-collapse-item>
      </el-collapse>
    </template>
    <ReportsCatalog v-else-if="tab === 'report'" />
    <FlowAnalytics v-else />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrowseView from '@/pages/BrowseView.vue'
import MaterialStandardizedPanel from '@/components/MaterialStandardizedPanel.vue'
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

const tab = ref(normalizeTab(route.query.tab))

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
.advanced-browse { margin-top: 4px; }
</style>
