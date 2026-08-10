<template>
  <div class="govern-hub">
    <el-tabs v-model="tab" @tab-change="onTab">
      <el-tab-pane label="待确认" name="work" />
      <el-tab-pane label="规则资产" name="assets" />
      <el-tab-pane label="指标口径" name="metrics" />
    </el-tabs>
    <GovernView v-if="tab === 'work'" />
    <AssetsView v-else-if="tab === 'assets'" />
    <MetricsView v-else :editable="false" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GovernView from '@/pages/GovernView.vue'
import AssetsView from '@/pages/AssetsView.vue'
import MetricsView from '@/pages/MetricsView.vue'

const route = useRoute()
const router = useRouter()

const tab = ref(['work', 'assets', 'metrics'].includes(String(route.query.tab)) ? String(route.query.tab) : 'work')

function onTab(name: string | number) {
  router.replace({ path: '/govern', query: { tab: String(name) } })
}

watch(
  () => route.query.tab,
  (v) => {
    if (v && ['work', 'assets', 'metrics'].includes(String(v))) tab.value = String(v)
  },
)
</script>

<style scoped>
.govern-hub { display: flex; flex-direction: column; gap: 8px; }
</style>
