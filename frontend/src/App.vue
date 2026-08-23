<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">物资数据规整</div>
      <el-menu :default-active="activePath" router class="nav-menu">
        <el-menu-item index="/">工作台</el-menu-item>
        <el-menu-item index="/intake">数据接入</el-menu-item>
        <el-menu-item index="/govern">数据规整</el-menu-item>
        <el-menu-item index="/data">数据成果</el-menu-item>
        <el-menu-item index="/ask">问数助手</el-menu-item>
        <el-menu-item index="/trace">追溯审计</el-menu-item>
        <el-menu-item index="/system" class="nav-settings">系统设置</el-menu-item>
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
const activePath = computed(() => {
  const p = route.path
  if (p === '/browse' || p === '/reports') return '/data'
  if (['/metrics', '/learning'].includes(p)) return '/govern'
  if (['/lineage', '/audit'].includes(p) || p === '/trace') return '/trace'
  if (['/models', '/ops', '/settings'].includes(p)) return '/system'
  if (p.startsWith('/stage/')) return '/intake'
  return p
})

const title = computed(() => {
  const map: Record<string, string> = {
    '/': '工作台',
    '/ask': '问数助手',
    '/data': '数据成果',
    '/govern': '数据规整',
    '/system': '系统设置',
    '/intake': '数据接入',
    '/trace': '追溯审计',
  }
  if (route.path.startsWith('/stage/')) return '规整确认'
  return map[route.path] || '物资数据规整系统'
})

function onAuthRequired() {
  router.push({ path: '/system', query: { tab: 'settings' } })
}

onMounted(async () => {
  window.addEventListener('ops-auth-required', onAuthRequired)
  try {
    const h = await healthReady()
    systemReady.value = h.status === 'ready'
  } catch {
    systemReady.value = false
  }
})

onUnmounted(() => {
  window.removeEventListener('ops-auth-required', onAuthRequired)
})
</script>

<style scoped>
.layout { min-height: 100vh; background: #f5f7fa; }
.aside { background: #004597; color: #fff; }
.brand {
  padding: 20px 16px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #fff;
  border-bottom: 1px solid rgba(255,255,255,0.15);
}
.aside :deep(.el-menu) { border-right: none; background: transparent; }
.nav-menu :deep(.el-menu-item) {
  color: rgba(255,255,255,0.88);
  height: 44px;
  line-height: 44px;
}
.nav-menu :deep(.el-menu-item:hover) { background: rgba(255,255,255,0.12); color: #fff; }
.nav-menu :deep(.el-menu-item.is-active) { background: #0053b7; color: #fff; }
.nav-menu :deep(.nav-settings) {
  margin-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
}
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
  .nav-menu :deep(.el-menu) {
    display: flex;
    flex-wrap: wrap;
    overflow-x: auto;
    gap: 4px 8px;
    padding: 8px;
  }
  .nav-menu :deep(.el-menu-item) {
    flex-shrink: 0;
    height: 40px;
    line-height: 40px;
    margin: 0;
    border-top: none;
  }
  .nav-menu :deep(.nav-settings) { margin-top: 0; border-top: none; }
  .header { padding: 0 12px; }
  .title { font-size: 16px; }
}
</style>
