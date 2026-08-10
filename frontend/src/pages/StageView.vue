<template>
  <div class="stage" v-loading="loading">
    <el-steps :active="stepActive" finish-status="success" align-center style="margin-bottom: 16px">
      <el-step title="画像" description="第 1 步" />
      <el-step title="质量" description="第 3 步" />
      <el-step title="规整" description="暂存" />
      <el-step title="发布" description="确认门" />
    </el-steps>
    <el-descriptions title="规整评估" :column="2" border>
      <el-descriptions-item label="文件编号">{{ fileId }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="statusType" size="small">{{ staging?.status || '-' }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="目标域">
        <el-select v-model="targetDomain" size="small" style="width: 160px">
          <el-option label="库存" value="inventory" />
          <el-option label="资产" value="asset" />
          <el-option label="需求" value="demand" />
          <el-option label="出入库流水" value="stock_flow" />
        </el-select>
      </el-descriptions-item>
      <el-descriptions-item label="版本">
        <el-tag type="warning" effect="plain">{{ staging?.version ?? '-' }}</el-tag>
        <span class="hint">写操作乐观锁；版本不匹配会提示冲突</span>
      </el-descriptions-item>
      <el-descriptions-item label="更新时间">{{ staging?.updated_at || '-' }}</el-descriptions-item>
      <el-descriptions-item label="干净行">{{ staging?.clean_rows ?? '-' }}</el-descriptions-item>
      <el-descriptions-item label="阻塞行">{{ staging?.blocked_rows ?? '-' }}</el-descriptions-item>
      <el-descriptions-item label="指纹" :span="2">{{ staging?.fingerprint || '-' }}</el-descriptions-item>
    </el-descriptions>

    <el-card class="block" header="工作簿画像（规则）">
      <template v-if="profile">
        <div class="profile-meta">
          工作表数={{ profile.profile.workbook?.sheet_count ?? 0 }}
          · 需大模型={{ (profile.profile.workbook?.needs_llm_sheets || []).join(', ') || '无' }}
          · 来源={{ profile.profile.source || 'rule' }}
        </div>
        <el-table :data="profile.profile.sheets || []" size="small" border empty-text="无工作表">
          <el-table-column prop="sheet" label="工作表" min-width="120" />
          <el-table-column prop="role_hint" label="角色" width="110" />
          <el-table-column prop="structure_hint" label="结构" width="130" />
          <el-table-column label="表头候选" width="110">
            <template #default="{ row }">{{ (row.header_row_candidates || []).join(',') || '-' }}</template>
          </el-table-column>
          <el-table-column prop="rows" label="行" width="70" />
          <el-table-column prop="cols" label="列" width="70" />
          <el-table-column label="异常" min-width="140">
            <template #default="{ row }">{{ (row.anomalies || []).join(', ') || '-' }}</template>
          </el-table-column>
          <el-table-column label="大模型" width="70">
            <template #default="{ row }">
              <el-tag :type="row.needs_llm ? 'warning' : 'success'" size="small">
                {{ row.needs_llm ? '待' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </template>
      <el-empty v-else description="暂无画像（证据未就绪或尚未生成）" :image-size="64" />
    </el-card>

    <el-card class="block" header="质量预检（规则）">
      <template v-if="quality">
        <div class="profile-meta">
          目标域={{ quality.quality.domain || '-' }}
          · 行数={{ quality.quality.row_count ?? '-' }}
          · 问题数={{ quality.quality.issue_total ?? 0 }}
          ·
          <el-tag :type="quality.quality.blocking ? 'danger' : quality.quality.ok ? 'success' : 'warning'" size="small">
            {{ quality.quality.blocking ? '阻塞' : quality.quality.ok ? '通过' : '警告' }}
          </el-tag>
          · 去重建议={{ (quality.quality.suggested_dedup || []).join(',') || '-' }}
        </div>
        <el-space wrap style="margin-bottom: 8px">
          <el-tag
            v-for="(n, k) in quality.quality.issue_counts || {}"
            :key="k"
            size="small"
            :type="n ? 'warning' : 'info'"
          >
            {{ k }}={{ n }}
          </el-tag>
        </el-space>
        <el-table
          :data="quality.quality.issues_sample || []"
          size="small"
          border
          empty-text="无问题样本"
          max-height="240"
        >
          <el-table-column prop="code" label="编码" width="150" />
          <el-table-column prop="row" label="行号" width="70" />
          <el-table-column label="字段" width="160">
            <template #default="{ row }">{{ (row.fields || []).join(',') || '-' }}</template>
          </el-table-column>
          <el-table-column prop="detail" label="详情" min-width="200" />
        </el-table>
        <p class="hint">{{ quality.quality.hint }}</p>
      </template>
      <el-empty v-else description="生成规整结果后可见质量预检" :image-size="64" />
    </el-card>

    <el-card class="block" header="阻塞明细">
      <div class="profile-meta" v-if="qualityStats">
        干净={{ qualityStats.clean_rows }} · 阻塞={{ qualityStats.blocked_rows }}
        · 阻塞率={{ Number(qualityStats.block_rate || 0).toFixed(3) }}
        · 明细数={{ qualityStats.detail_count }}
      </div>
      <el-table :data="blockedItems" border size="small" empty-text="无阻塞明细" max-height="220">
        <el-table-column prop="source_row" label="行号" width="70" />
        <el-table-column prop="reason_code" label="编码" width="140" />
        <el-table-column prop="header" label="表头" width="120" />
        <el-table-column prop="reason_detail" label="详情" min-width="160" show-overflow-tooltip />
        <el-table-column prop="raw_value" label="原始值" width="100" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-card class="block" header="规整后预览（干净样本 ≤20 行）">
      <template v-if="cleanSample.length">
        <el-table :data="cleanSample" border size="small" max-height="360" empty-text="无样本">
          <el-table-column
            v-for="col in cleanColumns"
            :key="col"
            :prop="col"
            :label="col"
            min-width="110"
            show-overflow-tooltip
          />
        </el-table>
        <p class="hint">
          共 {{ staging?.clean_rows ?? '-' }} 行，仅预览前 20 行；完整数据在规整暂存集中，
          发布后进入标准表。
        </p>
      </template>
      <el-empty v-else description="生成规整结果后可见规整后样本" :image-size="64" />
    </el-card>

    <el-card class="block" header="接入建议（配置草案）">
      <template v-if="plan">
        <div class="profile-meta">
          状态={{ plan.plan_status }}
          · 目标域={{ plan.plan.target_domain || '-' }}
          · 目标表={{ plan.plan.target_table || '-' }}
          · 工作表数={{ (plan.plan.sheets || []).length }}
          ·
          <el-tag :type="plan.plan.gate?.ok ? 'success' : 'danger'" size="small">
            门禁 {{ plan.plan.gate?.ok ? '通过' : '阻塞' }}
          </el-tag>
          · 改库标志={{ plan.plan.mutates_state === false ? 'false' : '?' }}
        </div>
        <el-alert
          v-for="b in plan.plan.gate?.blockers || []"
          :key="'b'+b.code+b.message"
          type="error"
          :closable="false"
          show-icon
          :title="`${b.code}: ${b.message}`"
          style="margin-bottom: 6px"
        />
        <el-alert
          v-for="w in plan.plan.gate?.warnings || []"
          :key="'w'+w.code+w.message"
          type="warning"
          :closable="false"
          show-icon
          :title="`${w.code}: ${w.message}`"
          style="margin-bottom: 6px"
        />
        <el-table :data="plan.plan.sheets || []" size="small" border empty-text="无工作表配置">
          <el-table-column prop="sheet" label="工作表" width="120" />
          <el-table-column prop="role_hint" label="角色" width="100" />
          <el-table-column prop="structure" label="结构" width="120" />
          <el-table-column prop="header_row" label="表头行" width="80" />
          <el-table-column prop="target_table" label="目标表" width="140" />
          <el-table-column label="列数" width="70">
            <template #default="{ row }">{{ (row.columns || []).length }}</template>
          </el-table-column>
          <el-table-column label="去重" min-width="140">
            <template #default="{ row }">{{ (row.dedup || []).join(',') || '-' }}</template>
          </el-table-column>
        </el-table>
        <div class="actions" style="margin-top: 10px">
          <el-button :loading="planBusy" @click="refreshPlan">刷新计划</el-button>
          <el-button type="warning" :loading="planConfirmBusy" @click="runConfirmPlan(false)">
            确认计划（仅 meta）
          </el-button>
          <el-button
            v-if="plan.plan.gate && !plan.plan.gate.ok"
            type="danger"
            plain
            :loading="planConfirmBusy"
            @click="runConfirmPlan(true)"
          >
            强制确认计划
          </el-button>
        </div>
        <p class="hint">{{ plan.plan.hint || '确认计划不写业务库；发布仍走下方运维确认发布。' }}</p>
      </template>
      <el-empty v-else description="生成规整结果后可见接入建议" :image-size="64" />
    </el-card>

    <el-card class="block" header="试运行 / 影响评估">
      <pre>{{ pretty(staging?.dry_run) }}</pre>
      <pre>{{ pretty(staging?.impact) }}</pre>
    </el-card>

    <div class="actions">
      <el-button type="warning" :loading="analyzeBusy" @click="runAnalyze">
        一键分析（第1–4步 + 规整）
      </el-button>
      <el-button @click="runStage" :loading="stagingBusy">生成/刷新规整结果</el-button>
      <el-button type="primary" :disabled="!canConfirm" :loading="confirmBusy" @click="runConfirm">
        运维确认发布
      </el-button>
      <el-button @click="refresh" :loading="loading">刷新版本</el-button>
    </div>

    <el-alert
      v-if="analyzeSummary"
      class="block"
      :type="analyzeSummary.blocking ? 'warning' : 'success'"
      :closable="false"
      :title="analyzeTitle"
      :description="analyzeSummary.hint"
    />

    <el-alert
      v-if="result"
      class="block"
      :type="result.idempotent || result.idempotency_replay ? 'info' : 'success'"
      :closable="false"
      :title="resultTitle"
    />
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
  if (result.value?.release) return 4
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
const statusType = computed(() => {
  const s = staging.value?.status
  if (s === 'RELEASED') return 'success'
  if (s === 'STAGED') return 'warning'
  if (s === 'FAILED') return 'danger'
  return 'info'
})
const resultTitle = computed(() => {
  if (!result.value) return ''
  const rid = result.value.release?.release_id || '-'
  const rows = result.value.rows ?? result.value.release?.clean_rows
  const flags = [
    result.value.idempotent ? '幂等命中' : null,
    result.value.idempotency_replay ? 'Idempotency-Key 重放' : null,
  ].filter(Boolean)
  const suffix = flags.length ? `（${flags.join(' · ')}）` : ''
  return `已发布 ${rid} → ${result.value.target_table || ''} (${rows} 行)${suffix}`
})
const analyzeTitle = computed(() => {
  if (!analyzeSummary.value) return ''
  const codes = (analyzeSummary.value.codes || []).join(',') || '无'
  return `分析 ${analyzeSummary.value.ok ? '完成' : '部分失败'} · gate=${
    analyzeSummary.value.gate_ok ? 'ok' : 'blocked'
  } · codes=${codes}`
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
    // fallback: embed in dry_run
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
    ElMessage.success('接入计划已刷新（draft）')
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    planBusy.value = false
  }
}

async function runConfirmPlan(force: boolean) {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  try {
    await ElMessageBox.confirm(
      force
        ? '强制确认计划？仅写元数据，不写业务库。'
        : '确认接入配置草案？仅写元数据，不写业务库。',
      '计划确认门',
      { type: force ? 'error' : 'warning' },
    )
  } catch {
    return
  }
  planConfirmBusy.value = true
  try {
    const res = await confirmIntakePlan(props.fileId, { force })
    ElMessage.success(res.hint || `计划已确认（${res.plan_status}）`)
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
    ElMessage.success(`规整结果已生成（版本=${staging.value.version} · ${targetDomain.value}）`)
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
    ElMessage.success(
      res.blocking
        ? `分析完成（有门禁：${(res.codes || []).join(',') || 'blocked'}）`
        : '分析完成，可确认发布',
    )
    await refresh()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    analyzeBusy.value = false
  }
}

async function runConfirm() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  if (!staging.value) {
    ElMessage.warning('无规整结果，请先生成')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认将试运行结果幂等发布？\n版本=${staging.value.version} · 期望状态=STAGED` +
        (plan.value?.plan?.gate && !plan.value.plan.gate.ok
          ? '\n\n注意：门禁未通过，将尝试普通发布；若门禁冲突请先确认计划或勾选强制。'
          : ''),
      '确认门',
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
    ElMessage.success(result.value.idempotent || result.value.idempotency_replay ? '幂等返回（已发布）' : '发布成功')
    await refresh()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
    if (e instanceof ApiError && e.status === 409) {
      if (String(e.code).startsWith('GATE_')) {
        try {
          await ElMessageBox.confirm(
            `门禁拦截：${e.code}\n是否强制发布？（仍写审计记录）`,
            '强制发布',
            { type: 'error' },
          )
          result.value = await confirmStaging(props.fileId, {
            version: staging.value?.version,
            expected_status: 'STAGED',
            idempotencyKey: idemKey(),
            force: true,
          })
          ElMessage.warning('已强制发布')
          await refresh()
          return
        } catch {
          /* cancelled */
        }
      }
      await refresh()
      ElMessage.info(`已刷新 version → ${staging.value?.version ?? '-'}`)
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
.stage { display: flex; flex-direction: column; gap: 16px; max-width: 960px; }
.block { margin-top: 4px; }
.actions { display: flex; gap: 12px; flex-wrap: wrap; }
.hint { margin-left: 8px; color: #909399; font-size: 12px; }
.profile-meta { margin-bottom: 8px; color: #606266; font-size: 13px; }
pre {
  margin: 0 0 8px; white-space: pre-wrap; font-size: 12px; color: #303133;
  background: #f8fafc; padding: 8px; border-radius: 6px;
}
</style>
