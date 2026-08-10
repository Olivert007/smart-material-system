<template>
  <div class="ops">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="运维面板"
      description="服务健康、任务队列、告警与大模型调用统计。版本血缘与行级修正见「版本血缘」页。"
    />

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>服务就绪</span>
          <el-button :loading="readyLoading" @click="loadReady">刷新</el-button>
        </div>
      </template>
      <el-descriptions v-if="ready" :column="2" border size="small">
        <el-descriptions-item label="状态">
          <el-tag :type="ready.status === 'ready' ? 'success' : 'danger'" size="small">
            {{ ready.status === 'ready' ? '就绪' : '异常' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="版本">{{ ready.version || '—' }}</el-descriptions-item>
        <el-descriptions-item label="元数据库">{{ yn(ready.meta_db) }}</el-descriptions-item>
        <el-descriptions-item label="业务数据库">{{ yn(ready.biz_db) }}</el-descriptions-item>
        <el-descriptions-item label="后台任务">{{ yn(ready.worker) }}</el-descriptions-item>
        <el-descriptions-item label="前端构建">{{ yn(ready.frontend_dist) }}</el-descriptions-item>
      </el-descriptions>
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
        <el-button link type="primary" @click="$router.push('/intake')">打开接入与任务</el-button>
      </p>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>模型探测（Stage {{ models?.stage ?? '—' }}）</span>
          <el-button :loading="modelsLoading" @click="loadModels">刷新</el-button>
        </div>
      </template>
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
          <span>大模型调用统计（近 7 日）</span>
          <el-button :loading="costLoading" @click="loadCost">刷新</el-button>
        </div>
      </template>
      <p v-if="cost" class="hint">
        总调用 {{ cost.total_calls }} · 成功 {{ cost.ok_calls }} · 失败 {{ cost.failed_calls }}
      </p>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>备份</span>
          <el-button type="warning" :loading="backupBusy" @click="doBackup">立即备份</el-button>
        </div>
      </template>
      <pre v-if="backupResult" class="mono">{{ backupResult }}</pre>
      <p v-else class="hint">需操作令牌；备份路径见下方结果。</p>
      <el-button link type="primary" @click="$router.push('/lineage')">打开版本血缘（高级操作）</el-button>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createBackup,
  formatApiError,
  healthReady,
  modelsStatus,
  opsAlerts,
  opsLlmCost,
  opsTasksSummary,
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
const costLoading = ref(false)
const backupBusy = ref(false)
const backupResult = ref('')

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
  return v ? '是' : '否'
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
  costLoading.value = true
  try { cost.value = await opsLlmCost(7) }
  catch (e: unknown) { ElMessage.error(formatApiError(e)) }
  finally { costLoading.value = false }
}

async function doBackup() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  backupBusy.value = true
  try {
    backupResult.value = JSON.stringify(await createBackup(), null, 2)
    ElMessage.success('备份完成')
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    backupBusy.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadReady(), loadModels(), loadTasks(), loadAlerts(), loadCost()])
})
</script>

<style scoped>
.ops { display: flex; flex-direction: column; gap: 16px; max-width: 1100px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 13px; margin: 8px 0 0; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; white-space: pre-wrap; }
@media (max-width: 720px) { .ops { max-width: 100%; } }
</style>
