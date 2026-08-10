<template>
  <div class="data-hub">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="数据中心"
      description="明细浏览验单行数据（含物资名称）；汇总报表下载定稿结果；趋势图与种子报表互验。"
    />
    <el-tabs v-model="tab" @tab-change="onTab">
      <el-tab-pane label="明细浏览" name="detail" />
      <el-tab-pane label="汇总报表" name="report" />
      <el-tab-pane label="趋势分析" name="trend" />
    </el-tabs>
    <BrowseView v-if="tab === 'detail'" />
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

const tab = ref(
  ['detail', 'report', 'trend'].includes(String(route.query.tab))
    ? String(route.query.tab)
    : 'detail',
)

function onTab(name: string | number) {
  router.replace({ path: '/data', query: { ...route.query, tab: String(name) } })
}

watch(
  () => route.query.tab,
  (v) => {
    if (v && ['detail', 'report', 'trend'].includes(String(v))) tab.value = String(v)
  },
)
</script>

<style scoped>
.data-hub { display: flex; flex-direction: column; gap: 12px; max-width: 1200px; }
</style>
