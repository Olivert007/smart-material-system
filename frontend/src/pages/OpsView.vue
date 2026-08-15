<template>
  <div class="ops">
    <el-alert
      :type="overallReady ? 'success' : 'warning'"
      :closable="false"
      show-icon
      :title="overallReady ? '环境自检：系统就绪' : '环境自检：尚未全部就绪'"
      :description="selfCheckDesc"
    />

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>分项检查</span>
          <el-button :loading="readyLoading" @click="refreshAll">刷新自检</el-button>
        </div>
      </template>
      <el-descriptions v-if="ready" :column="2" border size="small">
        <el-descriptions-item label="API / Ready">
          <el-tag :type="ready.status === 'ready' ? 'success' : 'danger'" size="small">
            {{ ready.status === 'ready' ? '就绪' : '异常' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="版本">{{ ready.version || '—' }}</el-descriptions-item>
        <el-descriptions-item label="元数据库">{{ yn(ready.meta_db) }}</el-descriptions-item>
        <el-descriptions-item label="业务数据库">{{ yn(ready.biz_db) }}</el-descriptions-item>
        <el-descriptions-item label="后台 Worker">{{ yn(ready.worker) }}</el-descriptions-item>
        <el-descriptions-item label="前端产物">{{ yn(ready.frontend_dist) }}</el-descriptions-item>
        <el-descriptions-item label="主模型">{{ modelOk('big') }}</el-descriptions-item>
        <el-descriptions-item label="向量模型">{{ modelOk('embed') }}</el-descriptions-item>
        <el-descriptions-item label="最近备份" :span="2">
          {{ latestBackupText }}
        </el-descriptions-item>
        <el-descriptions-item label="恢复演练" :span="2">
          {{ drillText }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never" v-if="modelImpact.length">
      <template #header>模型不可用影响</template>
      <el-alert
        v-for="m in modelImpact"
        :key="m.role"
        type="warning"
        :closable="false"
        show-icon
        :title="m.title"
        :description="m.desc"
        style="margin-bottom: 8px"
      />
      <p class="hint">规则路径仍可用；需要模型建议的事项将进入待审核或稍后重试。</p>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>任务队列</span>
          <el-button :loading="tasksLoading" @click="loadTasks">刷新</el-button>
        </div>
      </template>
      <el-space wrap>
        <el-tag type="warning">待处理 {{ tasks?.pending ?? '—' }}</el-tag>
        <el-tag type="primary">处理中 {{ tasks?.processing ?? '—' }}</el-tag>
        <el-tag type="success">已完成 {{ tasks?.done ?? '—' }}</el-tag>
        <el-tag type="danger">失败 {{ tasks?.failed ?? '—' }}</el-tag>
      </el-space>
      <p class="hint">
        <el-button link type="primary" @click="$router.push('/intake')">打开数据接入</el-button>
      </p>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>告警</span>
          <el-button :loading="alertsLoading" @click="loadAlerts">刷新</el-button>
        </div>
      </template>
      <el-empty v-if="!alerts?.active?.length" description="当前无活跃告警" />
      <el-alert
        v-for="(a, i) in alerts?.active || []"
        :key="i"
        :type="a.level === 'danger' ? 'error' : 'warning'"
        :title="a.message"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
      />
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>备份与恢复演练</span>
          <el-button type="warning" :loading="backupBusy" @click="doBackup">立即备份</el-button>
        </div>
      </template>
      <el-table :data="backups" v-loading="backupsLoading" border size="small" empty-text="暂无备份">
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
          :description="drill?.record ? `最近演练：${drill.record.recorded_at} · ${drill.record.actor} · ${drill.record.note}` : '未演练前不承诺生产级备份恢复。'"
        />
        <div class="actions">
          <el-input v-model="drillNote" placeholder="演练备注（可选）" style="max-width: 360px" />
          <el-button type="primary" plain :loading="drillBusy" @click="doDrill">登记已完成恢复演练</el-button>
        </div>
        <p class="hint">登记仅写入演练记录，不会自动执行全量恢复，避免误伤数据。</p>
      </div>
      <el-button link type="primary" @click="$router.push('/trace?tab=lineage')">打开追溯审计 / 数据来源</el-button>
    </el-card>

    <el-collapse>
      <el-collapse-item title="高级：模型探测明细 / LLM 调用统计" name="adv">
        <el-table :data="modelRows" border size="small" v-loading="modelsLoading">
          <el-table-column prop="role" label="角色" width="90" />
          <el-table-column prop="model" label="配置模型" min-width="160" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.ok ? 'success' : 'danger'" size="small">{{ row.ok ? '在线' : '离线' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="note" label="备注" min-width="180" />
        </el-table>
        <p v-if="cost" class="hint" style="margin-top: 12px">
          近 7 日本地模型调用：总 {{ cost.total_calls }} · 成功 {{ cost.ok_calls }} · 失败 {{ cost.failed_calls }}
        </p>
      </el-collapse-item>
    </el-collapse>
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
  opsLlmCost,
  opsTasksSummary,
  recordRestoreDrill,
} from '@/api/client'

const ready = ref<Record<string, unknown> | null>(null)
const readyLoading = ref(false)
const models = ref<Awaited<ReturnType<typeof modelsStatus>> | null>(null)
const modelsLoading = ref(false)
const tasks = ref<Awaited<ReturnType<typeof opsTasksSummary>> | null>(null)
const tasksLoading = ref(false)
const alerts = ref<Awaited<ReturnType<typeof opsAlerts>> | null>(null)
const alertsLoading = ref(false)
const cost = ref<Awaited<ReturnType<typeof opsLlmCost>> | null>(null)
const backupBusy = ref(false)
const backups = ref<Array<{ backup_id: string; path: string; created_at?: string; files?: number | null }>>([])
const backupsLoading = ref(false)
const drill = ref<Awaited<ReturnType<typeof getRestoreDrill>> | null>(null)
const drillNote = ref('')
const drillBusy = ref(false)

const overallReady = computed(() => ready.value?.status === 'ready')
const latestBackupText = computed(() => {
  const b = backups.value[0]
  return b ? `${b.backup_id}（${b.created_at || '-'}）` : '无备份记录'
})
const drillText = computed(() =>
  drill.value?.recorded
    ? `已登记 · ${drill.value.record?.recorded_at || ''}`
    : '未登记（不承诺生产级恢复）',
)

const selfCheckDesc = computed(() => {
  if (overallReady.value) {
    return `API/数据库/Worker/前端产物正常。最近备份：${latestBackupText.value}；恢复演练：${drillText.value}`
  }
  return '请检查下方分项；模型离线不影响规则路径，但会影响建议与部分问数能力。'
})

const modelImpact = computed(() => {
  const m = models.value
  if (!m) return [] as Array<{ role: string; title: string; desc: string }>
  const out: Array<{ role: string; title: string; desc: string }> = []
  if (!m.big?.ok) {
    out.push({
      role: 'big',
      title: '主模型不可用',
      desc: '影响：复杂问数生成、低置信解释、接入辅助建议。已保留规则路径与指标模板问数。',
    })
  }
  if (!m.embed?.ok) {
    out.push({
      role: 'embed',
      title: '向量模型不可用或已降级',
      desc: '影响：字段/主数据召回可能改为词法兜底；匹配建议置信度下降，须人工确认。',
    })
  }
  if (m.fast && !m.fast.ok) {
    out.push({
      role: 'fast',
      title: '快速模型不可用',
      desc: '影响：轻量建议变慢或不可用；不阻断规则确认与发布写入。',
    })
  }
  return out
})

const modelRows = computed(() => {
  const m = models.value
  if (!m) return []
  return [
    { role: '主模型', model: m.big?.configured_model || '—', ok: !!m.big?.ok, note: m.big?.ok ? '在线' : '离线' },
    { role: '向量模型', model: m.embed?.configured_model || '—', ok: !!m.embed?.ok, note: m.embed?.lexical_fallback ? '词法兜底' : '向量检索' },
    { role: '快速模型', model: m.fast?.configured_model || '(未配置)', ok: !!m.fast?.ok, note: m.fast?.note || '阶段 2+' },
  ]
})

function yn(v: unknown) {
  return v ? '正常' : '异常'
}

function modelOk(role: 'big' | 'embed') {
  const m = models.value?.[role]
  return m?.ok ? '可用' : '不可用 / 降级'
}

async function loadReady() {
  readyLoading.value = true
  try { ready.value = (await healthReady()) as Record<string, unknown> }
  catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { readyLoading.value = false }
}

async function loadModels() {
  modelsLoading.value = true
  try { models.value = await modelsStatus() }
  catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { modelsLoading.value = false }
}

async function loadTasks() {
  tasksLoading.value = true
  try { tasks.value = await opsTasksSummary() }
  catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { tasksLoading.value = false }
}

async function loadAlerts() {
  alertsLoading.value = true
  try { alerts.value = await opsAlerts() }
  catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { alertsLoading.value = false }
}

async function loadCost() {
  try { cost.value = await opsLlmCost(7) } catch { /* optional */ }
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
  await Promise.all([loadReady(), loadModels(), loadTasks(), loadAlerts(), loadCost(), loadBackups(), loadDrill()])
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
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 13px; margin: 8px 0 0; }
.drill-box { margin-top: 12px; display: flex; flex-direction: column; gap: 10px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
</style>
