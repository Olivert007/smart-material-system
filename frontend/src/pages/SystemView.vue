<template>
  <div class="system-hub">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="系统管理"
      description="运维监控、模型、血缘、审计与指标维护；业务看数请使用「数据中心」与「问数」。"
    />
    <el-tabs v-model="tab" @tab-change="onTab">
      <el-tab-pane label="运维面板" name="ops" />
      <el-tab-pane label="模型管理" name="models" />
      <el-tab-pane label="版本血缘" name="lineage" />
      <el-tab-pane label="审计时间线" name="audit" />
      <el-tab-pane label="指标维护" name="metrics" />
      <el-tab-pane label="设置" name="settings" />
    </el-tabs>
    <OpsView v-if="tab === 'ops'" />
    <ModelsView v-else-if="tab === 'models'" />
    <LineageView v-else-if="tab === 'lineage'" />
    <AuditView v-else-if="tab === 'audit'" />
    <MetricsView v-else-if="tab === 'metrics'" :editable="true" />
    <SettingsView v-else />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import OpsView from '@/pages/OpsView.vue'
import ModelsView from '@/pages/ModelsView.vue'
import LineageView from '@/pages/LineageView.vue'
import AuditView from '@/pages/AuditView.vue'
import MetricsView from '@/pages/MetricsView.vue'
import SettingsView from '@/pages/SettingsView.vue'

const route = useRoute()
const router = useRouter()

const TAB_NAMES = ['ops', 'models', 'lineage', 'audit', 'metrics', 'settings'] as const

const tab = ref(
  TAB_NAMES.includes(route.query.tab as (typeof TAB_NAMES)[number])
    ? String(route.query.tab)
    : 'ops',
)

function onTab(name: string | number) {
  router.replace({ path: '/system', query: { tab: String(name) } })
}

watch(
  () => route.query.tab,
  (v) => {
    if (v && TAB_NAMES.includes(v as (typeof TAB_NAMES)[number])) tab.value = String(v)
  },
)
</script>

<style scoped>
.system-hub { display: flex; flex-direction: column; gap: 12px; }
</style>
