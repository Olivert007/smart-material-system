<template>
  <div class="system-hub">
    <el-tabs v-model="tab" @tab-change="onTab">
      <el-tab-pane label="运行概览" name="ops" />
      <el-tab-pane label="本地模型" name="models" />
      <el-tab-pane label="本机设置" name="settings" />
    </el-tabs>
    <OpsView v-if="tab === 'ops'" />
    <ModelsView v-else-if="tab === 'models'" />
    <SettingsView v-else />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import OpsView from '@/pages/OpsView.vue'
import ModelsView from '@/pages/ModelsView.vue'
import SettingsView from '@/pages/SettingsView.vue'

const route = useRoute()
const router = useRouter()

const TAB_NAMES = ['ops', 'models', 'settings'] as const

function normalizeTab(v: unknown) {
  const s = String(v || '')
  if ((TAB_NAMES as readonly string[]).includes(s)) return s
  return 'ops'
}

const tab = ref(normalizeTab(route.query.tab))

function onTab(name: string | number) {
  router.replace({ path: '/system', query: { tab: String(name) } })
}

watch(
  () => route.query.tab,
  (v) => {
    if (String(v) === 'metrics') {
      router.replace({ path: '/govern', query: { tab: 'advanced' } })
      return
    }
    tab.value = normalizeTab(v)
  },
)

onMounted(() => {
  if (String(route.query.tab) === 'metrics') {
    router.replace({ path: '/govern', query: { tab: 'advanced' } })
  }
})
</script>

<style scoped>
.system-hub { display: flex; flex-direction: column; gap: 12px; width: 100%; }
</style>
