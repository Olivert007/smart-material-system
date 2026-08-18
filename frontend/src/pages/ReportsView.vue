<template>
  <div class="reports">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="报表与分析"
      description="种子报表快照（参数化查询语句）+ 流水实时分析（只读，与种子报表互验）。"
    />

    <FlowAnalytics />

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>报表定义</span>
          <el-button type="primary" @click="create">新建并运行示例</el-button>
          <el-button link type="primary" :loading="loading" @click="load">刷新</el-button>
        </div>
      </template>
      <el-table :data="items" v-loading="loading" border size="small" empty-text="暂无报表；可先运行示例或等待种子就位">
        <el-table-column prop="report_id" label="报表编号" min-width="140" />
        <el-table-column label="分组" min-width="90">
          <template #default="{ row }">
            <el-tag :type="groupLabel(row) === '台账汇总' ? 'success' : 'info'" size="small">
              {{ groupLabel(row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column label="参数" min-width="140">
          <template #default="{ row }">
            <span v-if="paramDecls(row).length">{{ paramDecls(row).map((p) => p.name).join(', ') }}</span>
            <span v-else class="muted">无</span>
          </template>
        </el-table-column>
        <el-table-column prop="query_sql" label="查询语句" min-width="240" show-overflow-tooltip />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="primary" @click="run(row)">运行</el-button>
          </template>
        </el-table-column>
      </el-table>
      <pre v-if="last" class="mono">{{ last }}</pre>
    </el-card>

    <el-dialog v-model="paramVisible" :title="`运行：${paramReport?.name ?? ''}`" width="480px" destroy-on-close>
      <el-form label-width="110px">
        <el-form-item v-for="p in paramDecls(paramReport)" :key="p.name" :label="p.label || p.name">
          <el-input
            v-if="p.type === 'number'"
            v-model.number="paramValues[p.name]"
            type="number"
            placeholder="数字"
          />
          <el-input v-else v-model="paramValues[p.name]" placeholder="文本" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="paramVisible = false">取消</el-button>
        <el-button type="primary" :loading="running" @click="runWithParams">运行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import FlowAnalytics from '@/components/FlowAnalytics.vue'
import { createReport, formatApiError, listReports, runReport, type ReportItem } from '@/api/client'

type ParamDecl = { name: string; label?: string; type?: 'text' | 'number' }

const items = ref<ReportItem[]>([])
const loading = ref(false)
const running = ref(false)
const last = ref('')

const paramVisible = ref(false)
const paramReport = ref<ReportItem | null>(null)
const paramValues = reactive<Record<string, string | number>>({})

function paramDecls(row: ReportItem | null): ParamDecl[] {
  if (!row?.params_json) return []
  try {
    const raw: unknown = JSON.parse(row.params_json)
    if (Array.isArray(raw)) return raw as ParamDecl[]
    if (raw && typeof raw === 'object') {
      return Object.entries(raw).map(([name, v]) =>
        typeof v === 'string' ? { name, type: v as ParamDecl['type'] } : { name, ...(v as object) },
      )
    }
    return []
  } catch {
    return []
  }
}

function groupLabel(row: ReportItem): string {
  return row.report_id.startsWith('rpt_ledger_') ? '台账汇总' : '通用'
}

async function load() {
  loading.value = true
  try {
    items.value = (await listReports()).items || []
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    loading.value = false
  }
}

async function create() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先填写操作令牌')
    return
  }
  try {
    await createReport({
      name: '库存抽样',
      query_sql: 'SELECT material_id, stock_qty FROM fact_inventory LIMIT 100',
      report_id: `rpt_${Date.now().toString(16).slice(-8)}`,
    })
    ElMessage.success('已创建')
    await load()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

async function doRun(id: string, params?: Record<string, unknown>) {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先填写操作令牌')
    return false
  }
  try {
    const out = await runReport(id, params)
    last.value = JSON.stringify(out, null, 2)
    ElMessage.success(`完成 ${out.row_count} 行`)
    return true
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
    return false
  }
}

async function run(row: ReportItem) {
  const decls = paramDecls(row)
  if (decls.length) {
    paramReport.value = row
    for (const p of decls) {
      paramValues[p.name] = p.type === 'number' ? 0 : ''
    }
    paramVisible.value = true
    return
  }
  await doRun(row.report_id)
}

async function runWithParams() {
  const decls = paramDecls(paramReport.value)
  const params: Record<string, unknown> = {}
  for (const p of decls) {
    const v = paramValues[p.name]
    if (p.type === 'number') {
      if (v === '' || v == null) {
        ElMessage.warning(`请填写参数 ${p.name}`)
        return
      }
      params[p.name] = Number(v)
    } else if (String(v).trim() !== '') {
      params[p.name] = String(v).trim()
    }
  }
  running.value = true
  const ok = await doRun(paramReport.value!.report_id, params)
  running.value = false
  if (ok) paramVisible.value = false
}

onMounted(load)
</script>

<style scoped>
.reports { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.head { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; white-space: pre-wrap; }
.muted { color: #909399; font-size: 12px; }
</style>
