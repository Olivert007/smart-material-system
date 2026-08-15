<template>
  <div class="catalog">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>汇总报表（候选快照）</span>
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
              {{ paramDecls(row).map((p) => p.label || p.name).join('、') }}
            </span>
            <span v-else class="muted">无</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link type="primary" @click="run(row)">运行</el-button>
            <el-button v-if="lastRun?.report_id === row.report_id" link @click="downloadLast">
              下载
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="lastRun" shadow="never">
      <template #header>最近运行结果</template>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        :title="`共 ${lastRun.row_count} 行 · 状态：${dataStateLabel('available')} · 非正式发布`"
        :description="lastRun.note"
      />
      <el-descriptions :column="1" border size="small" style="margin-top: 10px">
        <el-descriptions-item label="运行编号">{{ lastRun.run_id }}</el-descriptions-item>
        <el-descriptions-item label="来源版本">
          {{
            lastRun.source_release_ids?.length
              ? lastRun.source_release_ids.join('、')
              : '无发布清单'
          }}
        </el-descriptions-item>
        <el-descriptions-item label="指标口径版本">
          <template v-if="lastRun.metric_versions?.length">
            {{
              lastRun.metric_versions
                .slice(0, 8)
                .map((m) => `${m.metric_id}@v${m.version ?? '?'}`)
                .join('；')
            }}
            <span v-if="lastRun.metric_versions.length > 8">
              …共 {{ lastRun.metric_versions.length }} 项
            </span>
          </template>
          <template v-else>无启用口径</template>
        </el-descriptions-item>
        <el-descriptions-item label="数据范围">可用候选（非正式发布）</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-dialog v-model="paramVisible" :title="`运行：${paramReport?.name ?? ''}`" width="480px" destroy-on-close>
      <el-form label-width="110px">
        <el-form-item v-for="p in paramDecls(paramReport)" :key="p.name" :label="p.label || p.name">
          <el-input
            v-if="p.type === 'number'"
            v-model.number="paramValues[p.name]"
            type="number"
            placeholder="必填，请输入数字"
          />
          <el-input v-else v-model="paramValues[p.name]" placeholder="可选，请输入文本" />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="paramPreview"
        type="info"
        :closable="false"
        show-icon
        :title="`将使用参数：${paramPreview}`"
        style="margin-top: 8px"
      />
      <template #footer>
        <el-button @click="paramVisible = false">取消</el-button>
        <el-button type="primary" :loading="running" @click="runWithParams">运行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { formatApiError, listReports, reportRunFileUrl, runReport, type ReportItem } from '@/api/client'
import { dataStateLabel } from '@/utils/dataStates'

type ParamDecl = { name: string; label?: string; type?: 'text' | 'number' }

const items = ref<ReportItem[]>([])
const loading = ref(false)
const running = ref(false)
const lastRun = ref<{
  report_id: string
  run_id: string
  row_count: number
  note: string
  source_release_ids?: string[]
  metric_versions?: Array<{ metric_id: string; version?: number | string }>
} | null>(null)

const paramVisible = ref(false)
const paramReport = ref<ReportItem | null>(null)
const paramValues = reactive<Record<string, string | number>>({})

/** 运行前展示实际参数（评审 §2.5.3）：只列出已填写的参数。 */
const paramPreview = computed(() => {
  const decls = paramDecls(paramReport.value)
  const parts: string[] = []
  for (const p of decls) {
    const v = paramValues[p.name]
    if (v === '' || v == null) continue
    parts.push(`${p.label || p.name}=${v}`)
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
    lastRun.value = {
      report_id: id,
      run_id: out.run_id,
      row_count: out.row_count,
      source_release_ids: out.source_release_ids,
      metric_versions: out.metric_versions,
      note:
        out.note ||
        `运行编号 ${out.run_id}；数据范围：可用候选（非正式发布），可下载 CSV/Parquet 产物`,
    }
    ElMessage.success(`完成 ${out.row_count} 行`)
    return true
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
    return false
  }
}

function downloadLast() {
  if (!lastRun.value) return
  window.open(reportRunFileUrl(lastRun.value.run_id), '_blank')
}

async function run(row: ReportItem) {
  const decls = paramDecls(row)
  if (decls.length) {
    paramReport.value = row
    // 评审 §2.5.2：必填参数不默认填 0/空串，避免直接运行得到误导性结果
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
        ElMessage.warning(`请填写 ${p.label || p.name}`)
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
.muted { color: #909399; font-size: 12px; }
</style>
