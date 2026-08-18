<template>
  <el-card shadow="never" class="row-evidence" v-loading="loading">
    <template #header>
      <div class="head">
        <span>行级证据（原始值 → 规整值）</span>
        <el-button size="small" text @click="$emit('close')">收起</el-button>
      </div>
    </template>
    <el-alert
      v-if="errorMsg"
      type="error"
      :closable="false"
      show-icon
      :title="errorMsg"
    />
    <template v-else-if="data">
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="来源文件">{{ data.source_file }}</el-descriptions-item>
        <el-descriptions-item label="工作表">{{ data.source_sheet || '—' }}</el-descriptions-item>
        <el-descriptions-item label="来源行号">{{ data.source_row ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="发布版本">{{ shortRelease(data.release_id) }}</el-descriptions-item>
        <el-descriptions-item label="业务域">{{ domainZh(data.domain) }}</el-descriptions-item>
        <el-descriptions-item label="配置版本">{{ data.staging?.config_version || '—' }}</el-descriptions-item>
        <el-descriptions-item label="发布人">{{ actorZh(data.release?.released_by) }}</el-descriptions-item>
        <el-descriptions-item label="发布时间">{{ data.release?.released_at || '—' }}</el-descriptions-item>
        <el-descriptions-item label="处理任务">
          {{ data.task ? `${taskTypeZh(data.task.task_type)} · ${fileStatusLabel(String(data.task.status))}` : '—' }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="sub">逐字段对照</div>
      <el-table :data="data.compare" border size="small" empty-text="无对照字段">
        <el-table-column prop="field_zh" label="标准字段" min-width="140" />
        <el-table-column label="来源列" min-width="140">
          <template #default="{ row }">{{ row.source_header || '—' }}</template>
        </el-table-column>
        <el-table-column label="来源值" min-width="160">
          <template #default="{ row }">
            <span v-if="row.raw_value != null">{{ String(valueZh(row.field, row.raw_value)) }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="规整值" min-width="160">
          <template #default="{ row }">
            <span v-if="row.clean_value != null">{{ String(valueZh(row.field, row.clean_value)) }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="变化" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.changed" size="small" type="warning">已规整</el-tag>
            <el-tag v-else-if="row.changed === false" size="small" type="info">一致</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="sub">字段映射</div>
      <el-space wrap>
        <el-tag v-for="m in data.mapping" :key="m.std_field" size="small" type="info">
          {{ fieldZh(m.std_field) }} ← {{ m.source_header }}
        </el-tag>
      </el-space>

      <template v-if="data.rule_hits?.length">
        <div class="sub">规则依据</div>
        <el-table :data="data.rule_hits" border size="small">
          <el-table-column prop="header" label="表头" width="140" />
          <el-table-column label="标准字段" width="140">
            <template #default="{ row }">{{ fieldZh(String(row.std_field || '')) }}</template>
          </el-table-column>
          <el-table-column label="来源" width="120">
            <template #default="{ row }">{{ ruleSourceZh(row.source) }}</template>
          </el-table-column>
          <el-table-column label="确认人" width="100">
            <template #default="{ row }">{{ actorZh(row.confirmed_by) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">{{ ruleStatusLabel(row.status) }}</template>
          </el-table-column>
        </el-table>
      </template>

      <template v-if="data.material && Object.keys(data.material).length">
        <div class="sub">物资匹配</div>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="物资编码">{{ data.material.material_code || '—' }}</el-descriptions-item>
          <el-descriptions-item label="物资名称">{{ data.material.material_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="匹配方式">{{ parseLevelLabel(String(data.material.match_level || '')) }}</el-descriptions-item>
        </el-descriptions>
      </template>

      <div class="sub">人工确认与审计</div>
      <p class="hint">
        确认 {{ data.confirms?.length || 0 }} 条 · 写操作审计 {{ data.audit?.length || 0 }} 条
        <template v-if="data.note"> · {{ data.note }}</template>
      </p>
    </template>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { formatApiError, getRowEvidence, type RowEvidence } from '@/api/client'
import { fileStatusLabel } from '@/utils/dataStates'
import { parseLevelLabel } from '@/utils/parseLevel'
import { fieldZh, valueZh } from '@/utils/fields'
import {
  ACTOR_ZH,
  DOMAIN_ZH,
  mapZh,
  ruleSourceZh,
  taskTypeZh,
} from '@/utils/auditLabels'

const props = defineProps<{ releaseId: string; rowKey: string }>()
defineEmits<{ (e: 'close'): void }>()

const loading = ref(false)
const data = ref<RowEvidence | null>(null)
const errorMsg = ref('')

function domainZh(v?: string | null): string {
  return mapZh(DOMAIN_ZH, v) || '—'
}

function actorZh(v?: unknown): string {
  const s = String(v ?? '')
  if (!s) return '—'
  return mapZh(ACTOR_ZH, s)
}

function shortRelease(id?: string | null): string {
  const s = String(id || '')
  if (!s) return '—'
  return s.length > 8 ? `版本 …${s.slice(-8)}` : `版本 ${s}`
}

function ruleStatusLabel(s?: unknown): string {
  const map: Record<string, string> = { active: '启用', disabled: '停用', proposed: '待确认' }
  const key = String(s || '')
  return map[key] || (key ? key : '—')
}

onMounted(async () => {
  loading.value = true
  errorMsg.value = ''
  try {
    data.value = await getRowEvidence(props.releaseId, props.rowKey)
  } catch (e: unknown) {
    errorMsg.value = formatApiError(e)
    ElMessage.error(errorMsg.value)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.row-evidence { width: 100%; }
.head { display: flex; align-items: center; justify-content: space-between; }
.sub { font-weight: 600; margin: 14px 0 8px; }
.hint { color: #909399; font-size: 12px; margin: 8px 0 0; }
.muted { color: #c0c4cc; }
</style>
