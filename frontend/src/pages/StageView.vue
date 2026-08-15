<template>
  <div class="stage" v-loading="loading">
    <div class="steps">
      <el-steps :active="stepActive" finish-status="success" align-center style="margin-bottom: 8px">
        <el-step title="识别结构" description="表头与工作表" />
        <el-step title="质量检查" description="问题预检" />
        <el-step title="生成规整结果" description="可用候选预览" />
        <el-step title="确认写入" description="写入业务库" />
      </el-steps>
    </div>

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
          <span>规整结论摘要</span>
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
          <div class="slabel">可用候选行</div>
          <div class="svalue">{{ staging?.clean_rows ?? qualityStats?.clean_rows ?? '—' }}</div>
        </div>
        <div class="scard warn">
          <div class="slabel">阻塞行</div>
          <div class="svalue">{{ staging?.blocked_rows ?? qualityStats?.blocked_rows ?? '—' }}</div>
        </div>
        <div class="scard">
          <div class="slabel">预计写入</div>
          <div class="svalue">{{ impactSummary.will_insert }}</div>
        </div>
        <div class="scard warn">
          <div class="slabel">质量问题</div>
          <div class="svalue">{{ impactSummary.quality_issue_total }}</div>
        </div>
        <div class="scard">
          <div class="slabel">流水待确认</div>
          <div class="svalue">{{ impactSummary.flow_pending }}</div>
        </div>
        <div class="scard">
          <div class="slabel">业务状态</div>
          <div class="svalue sm">{{ stagingUserStatus }}</div>
        </div>
      </div>
      <p v-if="impactFieldsText" class="hint">涉及字段：{{ impactFieldsText }}</p>
      <p class="hint">
        确认后写入业务库成为可用候选；阻塞行不会进入可用结果。确认≠正式发布报表。
        <template v-if="impactSummary.quality_blocking">当前存在阻塞级质量问题，建议先处理后再确认。</template>
      </p>
      <div class="actions">
        <el-button type="warning" :loading="analyzeBusy" @click="runAnalyze">一键分析并生成规整</el-button>
        <el-button @click="runStage" :loading="stagingBusy">刷新规整结果</el-button>
        <el-button type="primary" :disabled="!canConfirm" :loading="confirmBusy" @click="runConfirm">
          确认进入规整并发布到业务库
        </el-button>
        <el-button @click="refresh" :loading="loading">刷新</el-button>
        <el-button @click="$router.push('/govern')">返回数据规整</el-button>
      </div>
    </el-card>

    <el-alert
      v-if="analyzeSummary"
      :type="analyzeSummary.blocking ? 'warning' : 'success'"
      :closable="false"
      :title="analyzeTitle"
      :description="analyzeSummary.hint"
    />
    <el-alert
      v-if="result"
      :type="result.idempotent || result.idempotency_replay ? 'info' : 'success'"
      :closable="false"
      :title="resultTitle"
      description="已写入业务库的可用候选数据；正式报表需绑定发布清单与口径版本。"
    />

    <el-card shadow="never" header="质量问题与阻塞（需处理时优先看）">
      <template v-if="quality">
        <div class="profile-meta">
          行数={{ quality.quality.row_count ?? '-' }}
          · 问题数={{ quality.quality.issue_total ?? 0 }}
          ·
          <el-tag :type="quality.quality.blocking ? 'danger' : quality.quality.ok ? 'success' : 'warning'" size="small">
            {{ quality.quality.blocking ? '存在阻塞' : quality.quality.ok ? '通过' : '有警告' }}
          </el-tag>
        </div>
        <el-table
          :data="quality.quality.issues_sample || []"
          size="small"
          border
          empty-text="无问题样本"
          max-height="220"
        >
          <el-table-column label="问题" min-width="160">
            <template #default="{ row }">{{ gateCodeLabel(row.code) }}</template>
          </el-table-column>
          <el-table-column prop="row" label="行号" width="70" />
          <el-table-column label="字段" width="140">
            <template #default="{ row }">{{ (row.fields || []).join(',') || '-' }}</template>
          </el-table-column>
          <el-table-column prop="detail" label="说明" min-width="180" show-overflow-tooltip />
        </el-table>
        <p class="hint">{{ quality.quality.hint }}</p>
      </template>
      <el-empty v-else description="生成规整结果后可见质量检查" :image-size="64" />

      <el-table
        style="margin-top: 12px"
        :data="blockedItems"
        border
        size="small"
        empty-text="无阻塞明细"
        max-height="200"
      >
        <el-table-column prop="source_row" label="行号" width="70" />
        <el-table-column label="原因" min-width="140">
          <template #default="{ row }">{{ gateCodeLabel(row.reason_code) }}</template>
        </el-table-column>
        <el-table-column prop="header" label="表头" width="120" />
        <el-table-column prop="reason_detail" label="详情" min-width="160" show-overflow-tooltip />
        <el-table-column prop="raw_value" label="原始值" width="100" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-card shadow="never" header="规整后预览（干净样本）">
      <template v-if="cleanSample.length">
        <el-table :data="cleanSample" border size="small" max-height="320" empty-text="无样本">
          <el-table-column
            v-for="col in cleanColumns"
            :key="col"
            :prop="col"
            :label="fieldZh(col)"
            min-width="110"
            show-overflow-tooltip
          />
        </el-table>
        <p class="hint">共 {{ staging?.clean_rows ?? '-' }} 行可用候选，仅预览前 20 行。</p>
      </template>
      <el-empty v-else description="生成规整结果后可见预览" :image-size="64" />
    </el-card>

    <el-card shadow="never" header="接入配置草案">
      <template v-if="plan">
        <div class="profile-meta">
          目标={{ plan.plan.target_domain || '-' }} / {{ plan.plan.target_table || '-' }}
          ·
          <el-tag :type="plan.plan.gate?.ok ? 'success' : 'danger'" size="small">
            {{ plan.plan.gate?.ok ? '门禁通过' : '门禁阻塞' }}
          </el-tag>
        </div>
        <el-alert
          v-for="b in plan.plan.gate?.blockers || []"
          :key="'b'+b.code+b.message"
          type="error"
          :closable="false"
          show-icon
          :title="gateCodeLabel(b.code) + '：' + b.message"
          style="margin-bottom: 6px"
        />
        <el-alert
          v-for="w in plan.plan.gate?.warnings || []"
          :key="'w'+w.code+w.message"
          type="warning"
          :closable="false"
          show-icon
          :title="gateCodeLabel(w.code) + '：' + w.message"
          style="margin-bottom: 6px"
        />
        <div class="actions">
          <el-button :loading="planBusy" @click="refreshPlan">刷新计划</el-button>
          <el-button type="warning" :loading="planConfirmBusy" @click="runConfirmPlan(false)">
            确认配置草案（不写业务库）
          </el-button>
          <el-button
            v-if="plan.plan.gate && !plan.plan.gate.ok"
            type="danger"
            plain
            :loading="planConfirmBusy"
            @click="runConfirmPlan(true)"
          >
            强制确认草案
          </el-button>
        </div>
        <p class="hint">{{ plan.plan.hint || '确认草案只写元数据；写入业务库仍需上方「确认进入规整并发布」。' }}</p>
      </template>
      <el-empty v-else description="生成规整结果后可见接入建议" :image-size="64" />
    </el-card>

    <el-collapse>
      <el-collapse-item title="高级详情：画像 / 技术状态 / 试运行 JSON" name="adv">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="文件编号">{{ fileId }}</el-descriptions-item>
          <el-descriptions-item label="原始状态">{{ stagingUserStatus }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ staging?.version ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ staging?.updated_at || '-' }}</el-descriptions-item>
          <el-descriptions-item label="指纹" :span="2">{{ staging?.fingerprint || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="adv-block" v-if="profile">
          <div class="profile-meta">
            工作表数={{ profile.profile.workbook?.sheet_count ?? 0 }}
            · 需模型辅助={{ (profile.profile.workbook?.needs_llm_sheets || []).join(', ') || '无' }}
          </div>
          <el-table :data="profile.profile.sheets || []" size="small" border empty-text="无工作表">
            <el-table-column prop="sheet" label="工作表" min-width="120" />
            <el-table-column prop="role_hint" label="角色" width="110" />
            <el-table-column prop="structure_hint" label="结构" width="130" />
            <el-table-column prop="rows" label="行" width="70" />
            <el-table-column prop="cols" label="列" width="70" />
          </el-table>
        </div>

        <div class="adv-block" v-if="plan">
          <el-table :data="plan.plan.sheets || []" size="small" border empty-text="无工作表配置">
            <el-table-column prop="sheet" label="工作表" width="120" />
            <el-table-column prop="role_hint" label="角色" width="100" />
            <el-table-column prop="structure" label="结构" width="120" />
            <el-table-column prop="header_row" label="表头行" width="80" />
            <el-table-column prop="target_table" label="目标表" width="140" />
          </el-table>
        </div>

        <div class="adv-block">
          <div class="profile-meta">试运行 / 影响评估（原始 JSON）</div>
          <pre>{{ pretty(staging?.dry_run) }}</pre>
          <pre>{{ pretty(staging?.impact) }}</pre>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ApiError,
  buildIntakePlan,
  confirmIntakePlan,
  confirmStaging,
  createStaging,
  formatApiError,
  getIntakePlan,
  getIntakeProfile,
  getIntakeQuality,
  getStaging,
  intakeAnalyze,
  getQualityStats,
  listQualityBlocked,
  type AnalyzeResult,
  type IntakePlan,
  type IntakeProfile,
  type QualityReport,
  type StagingInfo,
} from '@/api/client'
import { gateLabel as gateCodeLabel } from '@/utils/gateLabels'
import { fieldZh } from '@/utils/fields'

const props = defineProps<{ fileId: string }>()
const staging = ref<StagingInfo | null>(null)
const profile = ref<IntakeProfile | null>(null)
const quality = ref<QualityReport | null>(null)
const qualityStats = ref<{
  clean_rows: number
  blocked_rows: number
  block_rate: number
  detail_count: number
} | null>(null)
const blockedItems = ref<
  Array<{ source_row?: number; reason_code: string; header?: string; reason_detail?: string; raw_value?: string }>
>([])
const plan = ref<IntakePlan | null>(null)
const planBusy = ref(false)
const planConfirmBusy = ref(false)
const loading = ref(false)
const stagingBusy = ref(false)
const analyzeBusy = ref(false)
const analyzeSummary = ref<AnalyzeResult | null>(null)
const confirmBusy = ref(false)
const targetDomain = ref('inventory')
const result = ref<{
  release: { release_id: string; clean_rows?: number }
  target_table?: string
  rows?: number
  idempotent?: boolean
  idempotency_replay?: boolean
  status?: string
} | null>(null)

const canConfirm = computed(() => staging.value?.status === 'STAGED')
const stepActive = computed(() => {
  if (result.value?.release || staging.value?.status === 'RELEASED') return 4
  if (staging.value?.status === 'STAGED' || staging.value?.status === 'RELEASING') return 3
  if (quality.value) return 2
  if (profile.value) return 1
  return 0
})
const cleanSample = computed<Record<string, unknown>[]>(
  () => (staging.value?.dry_run?.clean_sample as Record<string, unknown>[] | undefined) || [],
)
const cleanColumns = computed<string[]>(
  () => (staging.value?.dry_run?.clean_columns as string[] | undefined) || [],
)

const impactSummary = computed(() => {
  const imp = (staging.value?.impact || {}) as Record<string, unknown>
  const num = (k: string, fallback: unknown = '—') => {
    const v = imp[k]
    if (v == null || v === '') return fallback
    return v as string | number
  }
  return {
    will_insert: num('will_insert', staging.value?.clean_rows ?? '—'),
    flow_pending: num('flow_pending', 0),
    quality_issue_total: num('quality_issue_total', quality.value?.quality?.issue_total ?? 0),
    blocked_detail_count: num('blocked_detail_count', staging.value?.blocked_rows ?? 0),
    quality_blocking: Boolean(imp.quality_blocking ?? quality.value?.quality?.blocking),
  }
})

const impactFieldsText = computed(() => {
  const cols = cleanColumns.value.filter(
    (c) => !['source_file', 'source_release_id', 'source_row', 'material_id'].includes(c),
  )
  if (!cols.length) return ''
  return cols
    .slice(0, 12)
    .map((c) => fieldZh(c))
    .join('、')
})

const stagingUserStatus = computed(() => {
  const s = staging.value?.status
  if (s === 'RELEASED') return '已写入业务库'
  if (s === 'STAGED') return '可确认'
  if (s === 'RELEASING') return '写入中'
  if (s === 'FAILED') return '失败'
  return s || '未生成'
})

const conclusionType = computed(() => {
  if (staging.value?.status === 'FAILED') return 'error'
  if ((staging.value?.blocked_rows || 0) > 0 || quality.value?.quality?.blocking) return 'warning'
  if (canConfirm.value || staging.value?.status === 'RELEASED') return 'success'
  if (plan.value?.plan?.gate && !plan.value.plan.gate.ok) return 'warning'
  return 'info'
})

const conclusionTitle = computed(() => {
  if (staging.value?.status === 'FAILED') return '不能确认：规整失败'
  if (plan.value?.plan?.gate && !plan.value.plan.gate.ok) return '需要处理异常：门禁未通过'
  if ((staging.value?.blocked_rows || 0) > 0) return '需要处理异常：存在阻塞行'
  if (quality.value?.quality?.blocking) return '需要处理字段或异常后才能放心确认'
  if (canConfirm.value) return '可以确认：规整结果已就绪'
  if (staging.value?.status === 'RELEASED') return '已确认：数据已写入业务库（可用候选）'
  return '请先生成规整结果'
})

const conclusionDesc = computed(() => {
  const clean = staging.value?.clean_rows ?? qualityStats.value?.clean_rows ?? 0
  const blocked = staging.value?.blocked_rows ?? qualityStats.value?.blocked_rows ?? 0
  const willInsert = impactSummary.value.will_insert
  return `预计可用候选 ${clean} 行（写入约 ${willInsert}），阻塞 ${blocked} 行。确认后写入业务库；阻塞行不会进入可用结果。确认≠正式发布报表。`
})

const resultTitle = computed(() => {
  if (!result.value) return ''
  const rid = result.value.release?.release_id || '-'
  const rows = result.value.rows ?? result.value.release?.clean_rows
  return `已写入业务库 ${rid}（${rows} 行可用候选）`
})
const analyzeTitle = computed(() => {
  if (!analyzeSummary.value) return ''
  return analyzeSummary.value.blocking
    ? '分析完成：仍有需处理问题'
    : '分析完成：可进入规整确认'
})

function pretty(v: unknown) {
  return v ? JSON.stringify(v, null, 2) : ''
}

function idemKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `idem_${Date.now()}_${Math.random().toString(16).slice(2)}`
}

async function refresh() {
  loading.value = true
  try {
    staging.value = await getStaging(props.fileId)
  } catch {
    staging.value = null
  }
  try {
    profile.value = await getIntakeProfile(props.fileId)
  } catch {
    profile.value = null
  }
  try {
    quality.value = await getIntakeQuality(props.fileId)
  } catch {
    const q = staging.value?.dry_run && (staging.value.dry_run as { quality?: QualityReport['quality'] }).quality
    quality.value = q
      ? {
          report_id: null,
          file_id: props.fileId,
          report_type: 'quality_precheck',
          created_at: null,
          quality: q,
        }
      : null
  }
  try {
    qualityStats.value = await getQualityStats(props.fileId)
    blockedItems.value = (await listQualityBlocked(props.fileId, { limit: 50 })).items || []
  } catch {
    qualityStats.value = null
    blockedItems.value = []
  }
  try {
    plan.value = await getIntakePlan(props.fileId)
  } catch {
    plan.value = null
  } finally {
    loading.value = false
  }
}

async function refreshPlan() {
  planBusy.value = true
  try {
    plan.value = await buildIntakePlan(props.fileId, targetDomain.value)
    ElMessage.success('接入计划已刷新')
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    planBusy.value = false
  }
}

async function runConfirmPlan(force: boolean) {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在系统设置填写操作令牌')
    return
  }
  try {
    await ElMessageBox.confirm(
      force
        ? '强制确认配置草案？仅写元数据，不写业务库。'
        : '确认接入配置草案？仅写元数据，不写业务库。',
      '确认配置草案',
      { type: force ? 'error' : 'warning' },
    )
  } catch {
    return
  }
  planConfirmBusy.value = true
  try {
    const res = await confirmIntakePlan(props.fileId, { force })
    ElMessage.success(res.hint || '配置草案已确认')
    await refresh()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    planConfirmBusy.value = false
  }
}

async function runStage() {
  stagingBusy.value = true
  try {
    staging.value = await createStaging(props.fileId, {
      config_version: 'v1',
      target_domain: targetDomain.value,
    })
    ElMessage.success('规整结果已生成')
    await refresh()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    stagingBusy.value = false
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
    analyzeSummary.value = res
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
    ElMessage.warning('请先在系统设置填写操作令牌')
    return
  }
  if (!staging.value) {
    ElMessage.warning('无规整结果，请先生成')
    return
  }
  const clean = staging.value.clean_rows ?? 0
  const blocked = staging.value.blocked_rows ?? 0
  try {
    await ElMessageBox.confirm(
      `确认进入规整并发布到业务库？\n预计写入可用候选 ${clean} 行，阻塞 ${blocked} 行不会进入可用结果。\n确认不等于正式发布报表。`,
      '规整确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  confirmBusy.value = true
  const key = idemKey()
  try {
    result.value = await confirmStaging(props.fileId, {
      version: staging.value.version,
      expected_status: 'STAGED',
      idempotencyKey: key,
      force: false,
    })
    ElMessage.success('已写入业务库（可用候选）')
    await refresh()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
    if (e instanceof ApiError && e.status === 409) {
      if (String(e.code).startsWith('GATE_')) {
        try {
          await ElMessageBox.confirm(
            `门禁拦截：${gateCodeLabel(e.code)}\n是否强制写入？（仍记审计；不等于正式发布）`,
            '强制确认',
            { type: 'error' },
          )
          result.value = await confirmStaging(props.fileId, {
            version: staging.value?.version,
            expected_status: 'STAGED',
            idempotencyKey: idemKey(),
            force: true,
          })
          ElMessage.warning('已强制写入业务库')
          await refresh()
          return
        } catch {
          /* cancelled */
        }
      }
      await refresh()
    }
  } finally {
    confirmBusy.value = false
  }
}

onMounted(async () => {
  await refresh()
  if (!staging.value) await runStage()
})
</script>

<style scoped>
.stage { display: flex; flex-direction: column; gap: 16px; max-width: 960px; width: 100%; min-width: 0; }
.steps { width: 100%; overflow-x: auto; padding-bottom: 4px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
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
.hint { color: #909399; font-size: 12px; margin: 8px 0; }
.profile-meta { margin-bottom: 8px; color: #606266; font-size: 13px; }
.adv-block { margin-top: 14px; }
pre {
  margin: 0 0 8px; white-space: pre-wrap; font-size: 12px; color: #303133;
  background: #f8fafc; padding: 8px; border-radius: 6px;
}
@media (max-width: 720px) {
  .head { flex-direction: column; align-items: stretch; }
  .actions { flex-direction: column; align-items: stretch; }
  .actions .el-button { width: 100%; }
  .summary-cards { grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); }
  .svalue { font-size: 18px; }
  .stage :deep(.el-step__description) { display: none; }
  .stage :deep(.el-step__title) { font-size: 13px; }
}
</style>
