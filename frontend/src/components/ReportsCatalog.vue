<template>
  <div class="catalog">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>汇总报表</span>
          <el-button link type="primary" :loading="loading" @click="load">刷新</el-button>
        </div>
      </template>
      <el-table
        :data="items"
        v-loading="loading"
        border
        size="small"
        empty-text="暂无报表；请等待种子就位或联系运维"
      >
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="分组" width="100">
          <template #default="{ row }">
            <el-tag :type="groupLabel(row) === '台账汇总' ? 'success' : 'info'" size="small">
              {{ groupLabel(row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="参数" min-width="120">
          <template #default="{ row }">
            <span v-if="paramDecls(row).length">
              {{ paramDecls(row).map((p) => p.label || paramLabelZh(p.name)).join('、') }}
            </span>
            <span v-else class="muted">无</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button link type="primary" @click="run(row)">运行并预览</el-button>
            <el-button v-if="lastDownload?.report_id === row.report_id" link @click="downloadLast">
              下载完整报表
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="preview" shadow="never">
      <template #header>
        <div class="head-between">
          <span>{{ previewTitle }}</span>
          <el-button type="primary" plain @click="downloadLast">下载完整报表</el-button>
        </div>
      </template>
      <el-table
        :data="preview.rows"
        v-loading="previewLoading"
        border
        size="small"
        max-height="360"
        empty-text="当前报表无数据，请调整参数后重新运行"
      >
        <el-table-column
          v-for="col in displayColumns"
          :key="col"
          :prop="col"
          :label="fieldZh(col)"
          min-width="120"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ formatCell(col, row[col]) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="paramVisible" :title="`运行：${paramReport?.name ?? ''}`" width="480px" destroy-on-close>
      <el-form label-width="110px">
        <el-form-item v-for="p in paramDecls(paramReport)" :key="p.name" :label="p.label || paramLabelZh(p.name)">
          <el-input
            v-if="p.type === 'number'"
            v-model.number="paramValues[p.name]"
            type="number"
            placeholder="必填，请输入数字"
          />
          <el-input v-else v-model="paramValues[p.name]" placeholder="可选，请输入文本" />
        </el-form-item>
      </el-form>
      <p v-if="paramPreview" class="muted" style="margin-top: 8px">将使用参数：{{ paramPreview }}</p>
      <template #footer>
        <el-button @click="paramVisible = false">取消</el-button>
        <el-button type="primary" :loading="running" @click="runWithParams">运行并预览</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { formatApiError, listReports, reportPreview, reportRunFileUrl, runReport, type ReportItem } from '@/api/client'
import { fieldZh, valueZh, visibleFields } from '@/utils/fields'

type ParamDecl = { name: string; label?: string; type?: 'text' | 'number' }

const PARAM_LABEL_ZH: Record<string, string> = {
  category: '物资种类',
  year: '年份',
  limit: '条数上限',
  min_qty: '最小数量',
}

function paramLabelZh(name: string) {
  return PARAM_LABEL_ZH[name] || fieldZh(name)
}

const items = ref<ReportItem[]>([])
const loading = ref(false)
const running = ref(false)
const lastDownload = ref<{ run_id: string; report_id: string; name: string } | null>(null)

const preview = ref<{
  run_id: string
  row_count: number
  preview_count: number
  columns: string[]
  rows: Record<string, unknown>[]
} | null>(null)
const previewLoading = ref(false)

const paramVisible = ref(false)
const paramReport = ref<ReportItem | null>(null)
const paramValues = reactive<Record<string, string | number>>({})

const displayColumns = computed(() => visibleFields(preview.value?.columns || []))

const previewTitle = computed(() => {
  const name = lastDownload.value?.name || '报表'
  const total = preview.value?.row_count ?? 0
  const shown = preview.value?.preview_count ?? preview.value?.rows?.length ?? 0
  return `${name}·共${total}行（展示前${shown}行）`
})

const paramPreview = computed(() => {
  const decls = paramDecls(paramReport.value)
  const parts: string[] = []
  for (const p of decls) {
    const v = paramValues[p.name]
    if (v === '' || v == null) continue
    parts.push(`${p.label || paramLabelZh(p.name)}=${v}`)
  }
  return parts.join('，')
})

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

function reportName(id: string) {
  return items.value.find((r) => r.report_id === id)?.name || id
}

function formatCell(col: string, val: unknown) {
  const v = valueZh(col, val)
  if (v == null || v === '') return '-'
  return v
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

async function doRun(id: string, params?: Record<string, unknown>) {
  try {
    const out = await runReport(id, params)
    lastDownload.value = { run_id: out.run_id, report_id: id, name: reportName(id) }
    ElMessage.success(`已生成${out.row_count}行`)
    loadPreview(out.run_id)
    return true
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
    return false
  }
}

async function loadPreview(runId: string) {
  previewLoading.value = true
  try {
    preview.value = await reportPreview(runId)
  } catch (e: unknown) {
    preview.value = null
    ElMessage.warning(`预览加载失败：${formatApiError(e)}`)
  } finally {
    previewLoading.value = false
  }
}

function downloadLast() {
  if (!lastDownload.value) return
  window.open(reportRunFileUrl(lastDownload.value.run_id), '_blank')
}

async function run(row: ReportItem) {
  const decls = paramDecls(row)
  if (decls.length) {
    paramReport.value = row
    for (const p of decls) {
      paramValues[p.name] = ''
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
        ElMessage.warning(`请填写 ${p.label || paramLabelZh(p.name)}`)
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
.catalog { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; gap: 10px; align-items: center; }
.head-between { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.muted { color: #909399; font-size: 12px; }
</style>
