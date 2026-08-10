<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">Smart Material</div>
      <el-menu :default-active="activePath" router>
        <el-menu-item-group title="看数">
          <el-menu-item index="/">总览</el-menu-item>
          <el-menu-item index="/ask">问数</el-menu-item>
          <el-menu-item index="/data">数据中心</el-menu-item>
        </el-menu-item-group>
        <el-menu-item-group title="接入">
          <el-menu-item index="/intake">接入与任务</el-menu-item>
        </el-menu-item-group>
        <el-menu-item-group title="治理">
          <el-menu-item index="/govern">治理中心</el-menu-item>
        </el-menu-item-group>
        <el-menu-item-group v-if="isOps" title="系统">
          <el-menu-item index="/system">系统</el-menu-item>
        </el-menu-item-group>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="title">{{ title }}</span>
        <div class="header-right">
          <el-tag :type="apiOk ? 'success' : 'danger'" size="small">
            API {{ apiOk ? '在线' : '离线' }}
          </el-tag>
        </div>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { healthLive } from '@/api/client'

const route = useRoute()
const router = useRouter()
const apiOk = ref(false)
const opsRole = ref(localStorage.getItem('ops_role') || 'ops')

const isOps = computed(() => opsRole.value === 'ops')

const activePath = computed(() => {
  const p = route.path
  if (p === '/browse' || p === '/reports') return '/data'
  if (['/metrics', '/learning'].includes(p)) return '/govern'
  if (['/models', '/ops', '/lineage', '/audit', '/settings'].includes(p)) return '/system'
  return p
})

const title = computed(() => {
  const map: Record<string, string> = {
    '/': '总览',
    '/ask': '问数',
    '/data': '数据中心',
    '/govern': '治理中心',
    '/system': '系统',
    '/intake': '接入与任务',
  }
  if (route.path.startsWith('/stage/')) return '规整确认门'
  return map[route.path] || 'Smart Material System'
})

function onAuthRequired() {
  router.push({ path: '/system', query: { tab: 'settings' } })
}

function onStorage() {
  opsRole.value = localStorage.getItem('ops_role') || 'ops'
}

onMounted(async () => {
  window.addEventListener('ops-auth-required', onAuthRequired)
  window.addEventListener('storage', onStorage)
  try {
    const h = await healthLive()
    apiOk.value = h.status === 'live'
  } catch {
    apiOk.value = false
  }
})

onUnmounted(() => {
  window.removeEventListener('ops-auth-required', onAuthRequired)
  window.removeEventListener('storage', onStorage)
})
</script>

<style scoped>
.layout { min-height: 100vh; background: #f5f7fa; }
.aside { background: #1f2a37; color: #fff; }
.brand {
  padding: 20px 16px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #e8eef6;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.aside :deep(.el-menu) { border-right: none; background: transparent; }
.aside :deep(.el-menu-item-group__title) { color: #8a9bb0; font-size: 11px; padding-left: 16px; }
.aside :deep(.el-menu-item) { color: #c9d4e0; }
.aside :deep(.el-menu-item.is-active) { background: rgba(64,158,255,0.18); color: #fff; }
.header {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; border-bottom: 1px solid #ebeef5;
}
.title { font-size: 18px; font-weight: 600; }
</style>
