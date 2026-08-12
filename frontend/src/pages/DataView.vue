<template>
  <div class="data-hub">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="数据成果"
      description="结果统一标注六态：原始 / 暂存 / 规整 / 可用 / 阻塞 / 已发布。可用不等于正式发布报表。"
    />
    <div class="state-legend">
      <span class="legend-label">数据状态</span>
      <el-tag
        v-for="s in DATA_STATE_LEGEND"
        :key="s.code"
        size="small"
        :type="s.tagType || 'info'"
        effect="plain"
        :title="s.hint"
      >
        {{ s.label }}
      </el-tag>
    </div>
    <el-tabs v-model="tab" @tab-change="onTab">
      <el-tab-pane label="可用" name="available" />
      <el-tab-pane label="规整" name="staged" />
      <el-tab-pane label="阻塞" name="blocked" />
      <el-tab-pane label="报表与趋势" name="report" />
    </el-tabs>

    <BrowseView v-if="tab === 'available'" mode="available" />
    <BrowseView v-else-if="tab === 'staged'" mode="staged" />
    <BlockedDataPanel v-else-if="tab === 'blocked'" />
    <div v-else class="report-wrap">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="报表快照说明"
        description="以下报表与趋势基于当前业务库可用候选数据，须核对来源 release 与指标口径版本；非正式发布报告。"
        style="margin-bottom: 12px"
      />
      <el-tabs v-model="reportInner">
        <el-tab-pane label="汇总报表" name="report" />
        <el-tab-pane label="趋势分析" name="trend" />
      </el-tabs>
      <ReportsCatalog v-if="reportInner === 'report'" />
      <FlowAnalytics v-else />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrowseView from '@/pages/BrowseView.vue'
import BlockedDataPanel from '@/components/BlockedDataPanel.vue'
import ReportsCatalog from '@/components/ReportsCatalog.vue'
import FlowAnalytics from '@/components/FlowAnalytics.vue'
import { DATA_STATE_LEGEND } from '@/utils/dataStates'

const route = useRoute()
const router = useRouter()

const TAB_NAMES = ['available', 'staged', 'blocked', 'report'] as const

function normalizeTab(v: unknown) {
  const s = String(v || '')
  if (s === 'detail') return 'available'
  if (s === 'trend') return 'report'
  if ((TAB_NAMES as readonly string[]).includes(s)) return s
  return 'available'
}

const tab = ref(normalizeTab(route.query.tab))
const reportInner = ref(String(route.query.tab) === 'trend' ? 'trend' : 'report')

function onTab(name: string | number) {
  const t = String(name)
  tab.value = t
  router.replace({ path: '/data', query: { ...route.query, tab: t } })
}

watch(
  () => route.query.tab,
  (v) => {
    tab.value = normalizeTab(v)
    if (String(v) === 'trend') reportInner.value = 'trend'
  },
)
</script>

<style scoped>
.data-hub { display: flex; flex-direction: column; gap: 12px; width: 100%; }
.report-wrap { display: flex; flex-direction: column; gap: 8px; }
.state-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.legend-label { color: #909399; font-size: 12px; margin-right: 4px; }
</style>
