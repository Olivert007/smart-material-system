<template>
  <div class="blocked">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="阻塞数据"
      description="状态：阻塞。以下记录因缺字段、低置信匹配、异常值或未确认等原因，不能进入可用结果。忽略待办不会自动解除阻塞。"
    />
    <div class="toolbar">
      <el-select
        v-model="fileId"
        filterable
        clearable
        placeholder="选择接入文件"
        style="width: 320px"
        @change="onFileChange"
      >
        <el-option
          v-for="f in files"
          :key="f.file_id"
          :label="`${f.filename}（${fileStatusLabel(f.status)}）`"
          :value="f.file_id"
        />
      </el-select>
      <el-tag size="small" type="danger">{{ dataStateLabel('blocked') }}</el-tag>
      <el-button :loading="loading" @click="load">刷新</el-button>
      <el-button @click="$router.push('/govern')">去数据规整</el-button>
    </div>
    <div v-if="stats" class="meta">
      可用候选 {{ stats.clean_rows }} · 阻塞 {{ stats.blocked_rows }} · 阻塞率
      {{ Number(stats.block_rate || 0).toFixed(3) }}
    </div>
    <PagedTable
      v-model:page="page"
      v-model:page-size="pageSize"
      :total="total"
      @change="load"
    >
      <el-table :data="items" v-loading="loading" border size="small" empty-text="无阻塞明细或尚未选择文件">
        <el-table-column prop="source_row" label="行号" width="70" />
        <el-table-column label="原因" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span :title="row.reason_code">{{ reasonLabel(row.reason_code) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="header" label="表头" width="120" />
        <el-table-column prop="reason_detail" label="详情" min-width="180" show-overflow-tooltip />
        <el-table-column prop="raw_value" label="原始值" width="120" show-overflow-tooltip />
        <el-table-column label="追溯" width="100">
          <template #default>
            <el-button link type="primary" @click="goTrace">追溯</el-button>
          </template>
        </el-table-column>
      </el-table>
    </PagedTable>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PagedTable from '@/components/PagedTable.vue'
import {
  formatApiError,
  getQualityStats,
  listFiles,
  listQualityBlocked,
  type FileItem,
} from '@/api/client'
import { dataStateLabel, fileStatusLabel } from '@/utils/dataStates'
import { gateLabel } from '@/utils/gateLabels'

const router = useRouter()
const files = ref<FileItem[]>([])
const fileId = ref('')
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const items = ref<
  Array<{ source_row?: number; reason_code: string; header?: string; reason_detail?: string; raw_value?: string }>
>([])
const stats = ref<{ clean_rows: number; blocked_rows: number; block_rate: number } | null>(null)

function reasonLabel(code: string) {
  return gateLabel(code)
}

function goTrace() {
  router.push({
    path: '/trace',
    query: { tab: 'lineage', file_id: fileId.value || undefined },
  })
}

function onFileChange() {
  page.value = 1
  load()
}

async function load() {
  if (!fileId.value) {
    items.value = []
    stats.value = null
    total.value = 0
    return
  }
  loading.value = true
  try {
    stats.value = await getQualityStats(fileId.value)
    const resp = await listQualityBlocked(fileId.value, {
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    items.value = resp.items || []
    total.value = resp.total || 0
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    files.value = (await listFiles(50, 0)).items || []
    const prefer = files.value.find((f) =>
      ['staged', 'released', 'evidence_done'].includes(String(f.status)),
    )
    if (prefer) {
      fileId.value = prefer.file_id
      await load()
    }
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
})
</script>

<style scoped>
.blocked { display: flex; flex-direction: column; gap: 12px; }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.meta { color: #606266; font-size: 13px; }
</style>
