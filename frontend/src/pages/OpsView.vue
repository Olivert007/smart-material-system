<template>
  <div class="ops">
    <div class="hero">
      <el-alert
        :type="headline.type"
        :closable="false"
        show-icon
        :title="headline.title"
        :description="headline.description"
      />
      <div class="quick-actions">
        <el-button @click="$router.push('/system?tab=settings')">账户角色</el-button>
        <el-button @click="$router.push('/system?tab=models')">本地模型</el-button>
        <el-button @click="$router.push('/trace')">追溯审计</el-button>
        <el-button :loading="refreshing" @click="refreshAll">刷新</el-button>
      </div>
    </div>

    <div class="biz-cards" v-loading="overviewLoading">
      <div class="biz-card clickable" @click="$router.push('/govern')">
        <div class="card-label">待办合计</div>
        <div class="card-value">{{ fmt(overview?.todos?.total) }}</div>
      </div>
      <div class="biz-card">
        <div class="card-label">可用行</div>
        <div class="card-value">{{ fmt(overview?.quality?.clean_rows) }}</div>
      </div>
      <div class="biz-card">
        <div class="card-label">阻塞行</div>
        <div class="card-value">{{ fmt(overview?.quality?.blocked_rows) }}</div>
      </div>
      <div class="biz-card clickable" @click="$router.push('/intake')">
        <div class="card-label">最近文件</div>
        <div class="card-value file">{{ recentFilenameShort }}</div>
      </div>
    </div>

    <p class="metric-row" :class="{ muted: metricRowEmpty }">{{ metricRowText }}</p>

    <el-collapse v-model="expandedPanels">
      <el-collapse-item title="服务检查" name="svc">
        <el-descriptions v-if="ready" :column="2" border size="small">
          <el-descriptions-item label="API 接口">
            <el-tag :type="ready.status === 'ready' ? 'success' : 'danger'" size="small">
              {{ ready.status === 'ready' ? '就绪' : '异常' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="版本">{{ ready.version || '—' }}</el-descriptions-item>
          <el-descriptions-item label="元数据库">{{ yn(ready.meta_db) }}</el-descriptions-item>
          <el-descriptions-item label="业务数据库">{{ yn(ready.biz_db) }}</el-descriptions-item>
          <el-descriptions-item label="后台任务">{{ yn(ready.worker) }}</el-descriptions-item>
          <el-descriptions-item label="前端产物">{{ yn(ready.frontend_dist) }}</el-descriptions-item>
        </el-descriptions>
      </el-collapse-item>

      <el-collapse-item title="备份与恢复演练" name="backup">
        <div class="head">
          <el-button type="warning" :loading="backupBusy" @click="doBackup">立即备份</el-button>
        </div>
        <p v-if="!backups.length" class="empty-backup">尚未创建备份</p>
        <el-table v-else :data="backups" v-loading="backupsLoading" border size="small">
          <el-table-column prop="backup_id" label="备份编号" min-width="200" show-overflow-tooltip />
          <el-table-column prop="created_at" label="时间" width="160" />
          <el-table-column prop="files" label="条目数" width="90" />
        </el-table>
        <div class="drill-box">
          <el-alert
            :type="drill?.recorded ? 'success' : 'warning'"
            :closable="false"
            show-icon
            :title="drill?.message || '加载演练状态…'"
            :description="drill?.record ? `最近演练：${drill.record.recorded_at} · ${drill.record.actor} · ${drill.record.note}` : ''"
          />
          <div class="actions">
            <el-input v-model="drillNote" placeholder="演练备注（可选）" style="max-width: 360px" />
            <el-button type="primary" plain :loading="drillBusy" @click="doDrill">登记演练</el-button>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <el-alert
      v-for="(a, i) in alerts?.active || []"
      :key="i"
      :type="a.level === 'danger' ? 'error' : 'warning'"
      :title="a.message"
      :closable="false"
      show-icon
      style="margin-bottom: 8px"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createBackup,
  formatApiError,
  getRestoreDrill,
  healthReady,
  listBackups,
  modelsStatus,
  opsAlerts,
  opsTasksSummary,
  recordRestoreDrill,
  statsOverview,
  type StatsOverview,
} from '@/api/client'

const ready = ref<Record<string, unknown> | null>(null)
const models = ref<Awaited<ReturnType<typeof modelsStatus>> | null>(null)
const tasks = ref<Awaited<ReturnType<typeof opsTasksSummary>> | null>(null)
const alerts = ref<Awaited<ReturnType<typeof opsAlerts>> | null>(null)
const overview = ref<StatsOverview | null>(null)
const overviewLoading = ref(false)
const refreshing = ref(false)
const backupBusy = ref(false)
const backups = ref<Array<{ backup_id: string; path: string; created_at?: string; files?: number | null }>>([])
const backupsLoading = ref(false)
const drill = ref<Awaited<ReturnType<typeof getRestoreDrill>> | null>(null)
const drillNote = ref('')
const drillBusy = ref(false)
const expandedPanels = ref<string[]>([])

const offlineModelNames = computed(() => {
  const m = models.value
  if (!m) return [] as string[]
  const names: string[] = []
  if (!m.big?.ok) names.push('主模型')
  if (!m.fast?.ok) names.push('快速模型')
  if (!m.embed?.ok) names.push('向量模型')
  return names
})

const firstFailure = computed(() => {
  const r = ready.value
  if (!r) return '就绪状态尚未拉取'
  if (!r.biz_db) return '业务数据库异常'
  if (!r.worker) return '后台任务未运行'
  if (!r.meta_db) return '元数据库缺失'
  if (!r.frontend_dist) return '前端产物缺失'
  return '服务未全部就绪'
})

const headline = computed(() => {
  if (!ready.value) {
    return { type: 'info' as const, title: '业务服务检查中', description: '正在拉取就绪状态' }
  }
  if (ready.value.status !== 'ready') {
    return {
      type: 'error' as const,
      title: '业务服务异常',
      description: `请展开「服务检查」；${firstFailure.value}`,
    }
  }
  const m = models.value
  const llmOk = !!m?.big?.ok || !!m?.fast?.ok
  if (m && !llmOk) {
    const offline = offlineModelNames.value.join('、') || '主模型与快速模型'
    return {
      type: 'warning' as const,
      title: '业务服务就绪',
      description: `智能能力已降级（${offline}），详情见「本地模型」；规则路径与指标问数仍可用`,
    }
  }
  return {
    type: 'success' as const,
    title: '业务服务就绪',
    description: '服务与智能能力正常',
  }
})

const recentFilename = computed(() => overview.value?.recent_files?.[0]?.filename || '')
const recentFilenameShort = computed(() => {
  const name = recentFilename.value
  if (!name) return '暂无'
  return name.length > 18 ? `${name.slice(0, 16)}…` : name
})

const latestBackupId = computed(() => backups.value[0]?.backup_id || '')

const metricRowText = computed(() => {
  const pending = tasks.value?.pending ?? '—'
  const processing = tasks.value?.processing ?? '—'
  const done = tasks.value?.done ?? '—'
  const failed = tasks.value?.failed ?? '—'
  const alertCount = alerts.value?.count ?? alerts.value?.active?.length ?? '—'
  const backup = latestBackupId.value || '无'
  return `接入任务 待处理 ${pending} · 处理中 ${processing} · 已完成 ${done} · 失败 ${failed} · 活跃告警 ${alertCount} · 最近备份 ${backup}`
})

const metricRowEmpty = computed(() => {
  const t = tasks.value
  const alertCount = alerts.value?.count ?? alerts.value?.active?.length ?? 0
  const allZero = !t || ((t.pending || 0) + (t.processing || 0) + (t.done || 0) + (t.failed || 0) === 0)
  return allZero && !alertCount && !latestBackupId.value
})

function fmt(v: unknown) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (Number.isFinite(n)) return n.toLocaleString('zh-CN')
  return String(v)
}

function yn(v: unknown) {
  return v ? '正常' : '异常'
}

async function loadReady() {
  try { ready.value = (await healthReady()) as Record<string, unknown> }
  catch (e: unknown) { ElMessage.error(formatApiError(e)) }
}

async function loadModels() {
  try { models.value = await modelsStatus() }
  catch (e: unknown) { ElMessage.error(formatApiError(e)) }
}

async function loadTasks() {
  try { tasks.value = await opsTasksSummary() }
  catch (e: unknown) { ElMessage.error(formatApiError(e)) }
}

async function loadAlerts() {
  try { alerts.value = await opsAlerts() }
  catch (e: unknown) { ElMessage.error(formatApiError(e)) }
}

async function loadOverview() {
  overviewLoading.value = true
  try { overview.value = await statsOverview(5) }
  catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { overviewLoading.value = false }
}

async function loadBackups() {
  backupsLoading.value = true
  try {
    backups.value = (await listBackups(10)).items || []
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    backupsLoading.value = false
  }
}

async function loadDrill() {
  try {
    drill.value = await getRestoreDrill()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

async function refreshAll() {
  refreshing.value = true
  try {
    await Promise.all([
      loadReady(),
      loadModels(),
      loadTasks(),
      loadAlerts(),
      loadOverview(),
      loadBackups(),
      loadDrill(),
    ])
  } finally {
    refreshing.value = false
  }
}

async function doBackup() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  backupBusy.value = true
  try {
    await createBackup()
    ElMessage.success('备份完成')
    await loadBackups()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    backupBusy.value = false
  }
}

async function doDrill() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  drillBusy.value = true
  try {
    await recordRestoreDrill({
      note: drillNote.value || '人工确认已完成恢复演练',
      result: 'ok',
      backup_id: backups.value[0]?.backup_id,
    })
    ElMessage.success('已登记演练记录')
    drillNote.value = ''
    await loadDrill()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    drillBusy.value = false
  }
}

onMounted(refreshAll)
</script>

<style scoped>
.ops { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.hero { display: flex; flex-direction: column; gap: 12px; }
.quick-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.biz-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.biz-card {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 12px 14px;
  background: var(--el-bg-color);
}
.biz-card.clickable { cursor: pointer; }
.biz-card.clickable:hover { border-color: var(--el-color-primary); }
.card-label { color: #909399; font-size: 12px; margin-bottom: 6px; }
.card-value { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
.card-value.file { font-size: 15px; line-height: 1.35; word-break: break-all; }
.metric-row { color: #303133; font-size: 13px; margin: 0; line-height: 1.6; }
.metric-row.muted { color: #909399; }
.head { display: flex; justify-content: flex-end; margin-bottom: 10px; }
.empty-backup { color: #909399; font-size: 13px; margin: 0 0 10px; }
.drill-box { margin-top: 12px; display: flex; flex-direction: column; gap: 10px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
@media (max-width: 720px) {
  .biz-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
