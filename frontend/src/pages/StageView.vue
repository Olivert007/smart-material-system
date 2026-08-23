<template>
  <div class="stage" v-loading="loading">
    <el-steps
      v-if="!isReleased"
      :active="stepActive"
      finish-status="success"
      align-center
      class="steps"
    >
      <el-step title="识别" />
      <el-step title="质检" />
      <el-step title="预览" />
      <el-step title="写入" />
    </el-steps>

    <el-alert
      :title="conclusionTitle"
      :type="conclusionType"
      :closable="false"
      show-icon
      :description="conclusionDesc"
    />

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span class="filename">{{ displayFilename }}</span>
          <el-select v-model="targetDomain" size="small" style="width: 160px">
            <el-option label="库存" value="inventory" />
            <el-option label="资产" value="asset" />
            <el-option label="需求" value="demand" />
            <el-option label="出入库流水" value="stock_flow" />
          </el-select>
        </div>
      </template>
      <div class="summary-cards">
        <div class="scard">
          <div class="slabel">可用行</div>
          <div class="svalue">{{ staging?.clean_rows ?? '—' }}</div>
        </div>
        <div class="scard warn">
          <div class="slabel">阻塞行</div>
          <div class="svalue">{{ staging?.blocked_rows ?? '—' }}</div>
        </div>
        <div class="scard">
          <div class="slabel">预计写入</div>
          <div class="svalue">{{ willInsert }}</div>
        </div>
        <div class="scard">
          <div class="slabel">状态</div>
          <div class="svalue sm">{{ stagingStatusZh(staging?.status) }}</div>
        </div>
      </div>
      <div class="actions">
        <el-button
          v-if="!isReleased"
          type="primary"
          :disabled="!canConfirm"
          :loading="confirmBusy"
          @click="runConfirm"
        >
          确认写入业务库
        </el-button>
        <el-button v-if="isReleased" type="primary" @click="$router.push('/data')">
          查看数据成果
        </el-button>
        <el-button
          v-if="!isReleased"
          type="warning"
          :loading="analyzeBusy"
          @click="runAnalyze"
        >
          {{ staging ? '重新生成预览' : '生成规整预览' }}
        </el-button>
        <el-button @click="$router.push('/govern')">去数据规整</el-button>
        <el-button @click="$router.push('/intake')">返回接入</el-button>
      </div>
      <p v-if="confirmDisabledReason" class="action-hint warn">{{ confirmDisabledReason }}</p>
    </el-card>

    <el-alert
      v-if="showIssueSummary"
      type="warning"
      :closable="false"
      show-icon
      title="需要处理的问题"
      :description="issueSummaryText"
    />
    <el-card v-if="blockedDetailLines.length" shadow="never" header="问题定位（样例）">
      <ul class="blocked-list">
        <li v-for="(line, i) in blockedDetailLines" :key="i">{{ line }}</li>
      </ul>
    </el-card>

    <el-card shadow="never" header="规整后预览">
      <template v-if="previewRows.length">
        <div class="table-wrap">
          <el-table :data="previewRows" border size="small" max-height="360" empty-text="无样本">
            <el-table-column
              v-for="col in previewColumns"
              :key="col"
              :prop="col"
              :label="fieldZh(col)"
              min-width="110"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ valueZh(col, row[col]) }}</template>
            </el-table-column>
          </el-table>
        </div>
        <p class="hint">共 {{ previewRows.length }} 行样例</p>
      </template>
      <el-empty v-else description="分析完成后可见预览" :image-size="64" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ApiError,
  confirmStaging,
  createStaging,
  formatApiError,
  getStaging,
  intakeAnalyze,
  listFiles,
  listQualityBlocked,
  type StagingInfo,
} from '@/api/client'
import { gateLabel as gateCodeLabel } from '@/utils/gateLabels'
import { fieldZh, valueZh, visibleFields } from '@/utils/fields'
import {
  issueCountsSummary,
  sanitizeUserHint,
  stagingStatusZh,
  detailZh,
} from '@/utils/stageLabels'

type DomainQuality = {
  ok?: boolean
  blocking?: boolean
  issue_total?: number
  issue_counts?: Record<string, number>
  hint?: string
}

const props = defineProps<{ fileId: string }>()
const staging = ref<StagingInfo | null>(null)
const domainQuality = ref<DomainQuality | null>(null)
const filename = ref('')
const loading = ref(false)
const analyzeBusy = ref(false)
const confirmBusy = ref(false)
const targetDomain = ref('inventory')
const blockedSamples = ref<
  Array<{ source_row?: number; header?: string; reason_code?: string; reason_detail?: string }>
>([])

const isReleased = computed(() => staging.value?.status === 'RELEASED')
const canConfirm = computed(() => staging.value?.status === 'STAGED')
const displayFilename = computed(() => filename.value || '规整确认')

const stepActive = computed(() => {
  if (isReleased.value) return 4
  if (staging.value?.status === 'STAGED' || staging.value?.status === 'RELEASING') return 3
  if (domainQuality.value) return 2
  if (staging.value) return 1
  return 0
})

const previewRows = computed<Record<string, unknown>[]>(
  () => (staging.value?.dry_run?.clean_sample as Record<string, unknown>[] | undefined) || [],
)
const previewColumns = computed<string[]>(() => {
  const cols = (staging.value?.dry_run?.clean_columns as string[] | undefined) || []
  return visibleFields(cols)
})

const willInsert = computed(() => {
  const imp = (staging.value?.impact || {}) as Record<string, unknown>
  const v = imp.will_insert
  if (v == null || v === '') return staging.value?.clean_rows ?? '—'
  return v as string | number
})

const issueTotal = computed(() => Number(domainQuality.value?.issue_total || 0))
const showIssueSummary = computed(() => {
  if (isReleased.value) return false
  const blocked = Number(staging.value?.blocked_rows || 0)
  return blocked > 0 || issueTotal.value > 0
})

const issueSummaryText = computed(() => {
  const summary = issueCountsSummary(domainQuality.value?.issue_counts)
  const hint = sanitizeUserHint(domainQuality.value?.hint)
  const plan = staging.value?.dry_run?.intake_plan as Record<string, unknown> | undefined
  const sheetHint =
    Array.isArray(plan?.needs_llm_sheets) && plan!.needs_llm_sheets!.length
      ? `需关注工作表：${(plan!.needs_llm_sheets as string[]).join('、')}`
      : ''
  const blockedN = Number(staging.value?.dry_run?.blocked_detail_count || 0)
  const blockedHint = blockedN > 0 ? `共 ${blockedN} 处单元格/行被阻塞` : ''
  return [summary, blockedHint, sheetHint, hint].filter(Boolean).join('。')
})

const blockedDetailLines = computed(() => {
  if (!blockedSamples.value.length) return []
  return blockedSamples.value.map((row) => {
    const rowNo = row.source_row != null ? `第 ${row.source_row} 行` : ''
    const col = row.header ? `列「${fieldZh(row.header)}」` : ''
    const reason = detailZh(String(row.reason_detail || row.reason_code || ''))
    const loc = [rowNo, col].filter(Boolean).join(' ')
    return loc ? `${loc}：${reason || '数据异常'}` : reason || '数据异常'
  })
})

const confirmDisabledReason = computed(() => {
  if (isReleased.value) return ''
  if (staging.value?.status === 'FAILED') return '规整失败：请重新生成预览，或返回接入页处理源文件'
  if (!staging.value) return '请先点击「生成规整预览」，系统会识别字段并给出可写入行数'
  if ((staging.value.blocked_rows || 0) > 0) {
    return `仍有 ${staging.value.blocked_rows} 行被阻塞，需先处理问题或前往治理页确认字段/物资`
  }
  if (domainQuality.value?.blocking) return '质量检查未通过，请查看上方问题说明'
  if (!canConfirm.value) {
    return `当前状态为「${stagingStatusZh(staging.value.status)}」，完成预览后方可写入业务库`
  }
  return ''
})

const conclusionType = computed(() => {
  if (staging.value?.status === 'FAILED') return 'error'
  if (isReleased.value) return 'success'
  if ((staging.value?.blocked_rows || 0) > 0 || domainQuality.value?.blocking) return 'warning'
  if (canConfirm.value) return 'success'
  return 'info'
})

const conclusionTitle = computed(() => {
  if (staging.value?.status === 'FAILED') return '不能确认：规整失败'
  if (isReleased.value) return '已写入，可查看数据成果'
  if ((staging.value?.blocked_rows || 0) > 0 || domainQuality.value?.blocking) {
    return '需要处理问题后再确认'
  }
  if (canConfirm.value) return '可以确认：规整结果已就绪'
  return '请先开始分析'
})

const conclusionDesc = computed(() => {
  if (isReleased.value) return ''
  const clean = staging.value?.clean_rows ?? 0
  const blocked = staging.value?.blocked_rows ?? 0
  return `预计可用 ${clean} 行（写入约 ${willInsert.value}），阻塞 ${blocked} 行。`
})

function idemKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `idem_${Date.now()}_${Math.random().toString(16).slice(2)}`
}

function applyQuality(row: StagingInfo | null) {
  const q = row?.dry_run && (row.dry_run as { quality?: DomainQuality }).quality
  domainQuality.value = q || null
}

async function loadFilename() {
  try {
    const res = await listFiles(100, 0)
    const hit = res.items.find((f) => f.file_id === props.fileId)
    filename.value = hit?.filename || ''
  } catch {
    filename.value = ''
  }
}

async function loadBlockedSamples() {
  const blocked = Number(staging.value?.blocked_rows || 0)
  if (!blocked) {
    blockedSamples.value = []
    return
  }
  try {
    const res = await listQualityBlocked(props.fileId, {
      limit: 8,
      target_domain: targetDomain.value,
    })
    blockedSamples.value = res.items || []
  } catch {
    blockedSamples.value = []
  }
}

async function refresh() {
  loading.value = true
  try {
    try {
      staging.value = await getStaging(props.fileId, targetDomain.value)
    } catch {
      staging.value = null
    }
    applyQuality(staging.value)
    await loadBlockedSamples()
  } finally {
    loading.value = false
  }
}

async function runAnalyze() {
  analyzeBusy.value = true
  try {
    const res = await intakeAnalyze(props.fileId, {
      target_domain: targetDomain.value,
      include_stage: true,
      refresh_profile: true,
    })
    ElMessage.success(res.blocking ? '分析完成，仍有需处理问题' : '分析完成，可确认')
    await refresh()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    analyzeBusy.value = false
  }
}

async function runConfirm() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先到本地设置点击「一键启用本地验证」')
    return
  }
  if (!staging.value) {
    ElMessage.warning('尚无规整预览，请先点击「生成规整预览」')
    return
  }
  const clean = staging.value.clean_rows ?? 0
  const blocked = staging.value.blocked_rows ?? 0
  try {
    await ElMessageBox.confirm(
      `确认写入业务库？\n预计写入 ${clean} 行，阻塞 ${blocked} 行不会写入。`,
      '确认写入',
      { type: 'warning' },
    )
  } catch {
    return
  }
  confirmBusy.value = true
  try {
    await confirmStaging(props.fileId, {
      version: staging.value.version,
      expected_status: 'STAGED',
      idempotencyKey: idemKey(),
      force: false,
      target_domain: targetDomain.value,
      staging_id: staging.value.staging_id,
    })
    ElMessage.success('已写入')
    await refresh()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
    if (e instanceof ApiError && e.status === 409 && String(e.code).startsWith('GATE_')) {
      try {
        await ElMessageBox.confirm(
          `门禁拦截：${gateCodeLabel(e.code)}\n是否强制写入？`,
          '强制确认',
          { type: 'error' },
        )
        await confirmStaging(props.fileId, {
          version: staging.value?.version,
          expected_status: 'STAGED',
          idempotencyKey: idemKey(),
          force: true,
          target_domain: targetDomain.value,
          staging_id: staging.value?.staging_id,
        })
        ElMessage.warning('已强制写入')
        await refresh()
      } catch {
        /* cancelled */
      }
    }
  } finally {
    confirmBusy.value = false
  }
}

watch(targetDomain, () => {
  void refresh()
})

onMounted(async () => {
  await loadFilename()
  await refresh()
  if (!staging.value) {
    try {
      staging.value = await createStaging(props.fileId, {
        config_version: 'v1',
        target_domain: targetDomain.value,
      })
      applyQuality(staging.value)
    } catch {
      /* 用户可点开始分析 */
    }
  }
})
</script>

<style scoped>
.stage { display: flex; flex-direction: column; gap: 16px; width: 100%; min-width: 0; }
.steps { width: 100%; overflow-x: auto; margin-bottom: 8px; padding-bottom: 4px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.filename { font-weight: 600; word-break: break-all; }
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 8px;
}
.scard {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 10px 12px;
  min-width: 0;
}
.scard.warn { border-color: var(--el-color-warning-light-5); }
.slabel { color: #909399; font-size: 12px; margin-bottom: 4px; }
.svalue { font-size: 22px; font-weight: 600; }
.svalue.sm { font-size: 16px; }
.actions { display: flex; gap: 12px; flex-wrap: wrap; }
.action-hint { font-size: 13px; color: #909399; margin: 4px 0 0; line-height: 1.5; }
.action-hint.warn { color: var(--el-color-warning); }
.blocked-list { margin: 0; padding-left: 18px; color: #606266; font-size: 13px; line-height: 1.6; }
.hint { color: #909399; font-size: 12px; margin: 8px 0; }
.table-wrap { overflow-x: auto; width: 100%; }
@media (max-width: 720px) {
  .head { flex-direction: column; align-items: stretch; }
  .actions { flex-direction: column; align-items: stretch; }
  .actions .el-button { width: 100%; }
  .summary-cards { grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); }
  .svalue { font-size: 18px; }
}
</style>
