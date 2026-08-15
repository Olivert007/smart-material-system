<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">Smart Material</div>
      <el-menu :default-active="activePath" router>
        <el-menu-item index="/">工作台</el-menu-item>
        <el-menu-item index="/intake">数据接入</el-menu-item>
        <el-menu-item index="/govern">数据规整</el-menu-item>
        <el-menu-item index="/data">数据成果</el-menu-item>
        <el-menu-item index="/ask">问数助手</el-menu-item>
        <el-menu-item index="/trace">追溯审计</el-menu-item>
        <el-menu-item v-if="isOps" index="/system">系统运维</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="title">{{ title }}</span>
        <div class="header-right">
          <el-tag :type="systemReady ? 'success' : 'danger'" size="small">
            {{ systemReady ? '系统就绪' : '系统未就绪' }}
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
import { healthReady } from '@/api/client'

const route = useRoute()
const router = useRouter()
const systemReady = ref(false)
const opsRole = ref(localStorage.getItem('ops_role') || 'viewer')

const isOps = computed(() => opsRole.value === 'ops')

const activePath = computed(() => {
  const p = route.path
  if (p === '/browse' || p === '/reports') return '/data'
  if (['/metrics', '/learning'].includes(p)) return '/govern'
  if (['/lineage', '/audit'].includes(p) || p === '/trace') return '/trace'
  if (['/models', '/ops', '/settings'].includes(p)) return '/system'
  return p
})

const title = computed(() => {
  const map: Record<string, string> = {
    '/': '工作台',
    '/ask': '问数助手',
    '/data': '数据成果',
    '/govern': '数据规整',
    '/system': '系统运维',
    '/intake': '数据接入',
    '/trace': '追溯审计',
  }
  if (route.path.startsWith('/stage/')) return '规整确认'
  return map[route.path] || 'Smart Material System'
})

function onAuthRequired() {
  router.push({ path: '/system', query: { tab: 'settings' } })
}

function onStorage() {
  opsRole.value = localStorage.getItem('ops_role') || 'viewer'
}

onMounted(async () => {
  window.addEventListener('ops-auth-required', onAuthRequired)
  window.addEventListener('storage', onStorage)
  try {
    const h = await healthReady()
    systemReady.value = h.status === 'ready'
  } catch {
    systemReady.value = false
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
.aside :deep(.el-menu-item) { color: #c9d4e0; }
.aside :deep(.el-menu-item.is-active) { background: rgba(64,158,255,0.18); color: #fff; }
.header {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; border-bottom: 1px solid #ebeef5;
}
.title { font-size: 18px; font-weight: 600; }
@media (max-width: 900px) {
  .aside { width: 176px !important; }
}
@media (max-width: 720px) {
  .layout { flex-direction: column; }
  .aside { width: 100% !important; height: auto; }
  .brand { padding: 12px 16px; }
  .aside :deep(.el-menu) { display: flex; overflow-x: auto; }
  .aside :deep(.el-menu-item) { flex-shrink: 0; height: 44px; }
  .header { padding: 0 12px; }
  .title { font-size: 16px; }
}
</style>
