import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/pages/HomeView.vue'
import IntakeView from '@/pages/IntakeView.vue'
import StageView from '@/pages/StageView.vue'
import AskView from '@/pages/AskView.vue'
import DataView from '@/pages/DataView.vue'
import GovernHub from '@/pages/GovernHub.vue'
import SystemView from '@/pages/SystemView.vue'
import TraceView from '@/pages/TraceView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/ask', name: 'ask', component: AskView },
    { path: '/data', name: 'data', component: DataView },
    { path: '/govern', name: 'govern', component: GovernHub },
    { path: '/system', name: 'system', component: SystemView },
    { path: '/intake', name: 'intake', component: IntakeView },
    { path: '/trace', name: 'trace', component: TraceView },
    { path: '/stage/:fileId', name: 'stage', component: StageView, props: true },
    { path: '/browse', redirect: (to) => ({ path: '/data', query: { tab: 'available', ...to.query } }) },
    { path: '/reports', redirect: { path: '/data', query: { tab: 'report' } } },
    { path: '/metrics', redirect: { path: '/govern', query: { tab: 'advanced' } } },
    { path: '/learning', redirect: { path: '/govern', query: { tab: 'advanced' } } },
    { path: '/govern/todos', redirect: (to) => ({ path: '/govern', query: to.query }) },
    { path: '/todos', redirect: (to) => ({ path: '/govern', query: to.query }) },
    { path: '/ai-review', redirect: '/govern' },
    { path: '/suggestions', redirect: { path: '/govern', query: { tab: 'map' } } },
    { path: '/models', redirect: { path: '/system', query: { tab: 'models' } } },
    { path: '/ops', redirect: { path: '/system', query: { tab: 'ops' } } },
    { path: '/lineage', redirect: { path: '/trace', query: { tab: 'lineage' } } },
    { path: '/audit', redirect: { path: '/trace', query: { tab: 'audit' } } },
    { path: '/settings', redirect: { path: '/system', query: { tab: 'settings' } } },
    { path: '/files', redirect: '/intake' },
  ],
})
