<template>
  <div class="trace-hub">
    <el-alert
      v-if="contextLine"
      type="warning"
      :closable="false"
      show-icon
      :title="contextLine"
      style="margin-top: -4px"
    />
    <el-tabs v-model="tab" @tab-change="onTab">
      <el-tab-pane label="数据来源" name="lineage" />
      <el-tab-pane label="操作记录" name="audit" />
    </el-tabs>
    <LineageView v-if="tab === 'lineage'" />
    <AuditView v-else />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LineageView from '@/pages/LineageView.vue'
import AuditView from '@/pages/AuditView.vue'

const route = useRoute()
const router = useRouter()

const TAB_NAMES = ['lineage', 'audit'] as const

const tab = ref(
  TAB_NAMES.includes(route.query.tab as (typeof TAB_NAMES)[number])
    ? String(route.query.tab)
    : 'lineage',
)

const contextLine = computed(() => {
  const parts: string[] = []
  if (route.query.release_id) parts.push(`发布版本 ${route.query.release_id}`)
  if (route.query.source_file || route.query.file_id) {
    parts.push(`源文件 ${route.query.source_file || route.query.file_id}`)
  }
  if (route.query.q) parts.push(`关键词 ${route.query.q}`)
  return parts.length ? `当前追溯上下文：${parts.join(' · ')}` : ''
})

function onTab(name: string | number) {
  router.replace({
    path: '/trace',
    query: { ...route.query, tab: String(name) },
  })
}

watch(
  () => route.query.tab,
  (v) => {
    if (v && TAB_NAMES.includes(v as (typeof TAB_NAMES)[number])) tab.value = String(v)
  },
)
</script>

<style scoped>
.trace-hub { display: flex; flex-direction: column; gap: 12px; width: 100%; }
</style>
