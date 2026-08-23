<template>
  <div class="browse">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <el-space wrap>
            <el-select v-model="table" style="width: 180px" @change="onTableChange">
              <el-option
                v-for="t in TABLES"
                :key="t.table"
                :label="t.label"
                :value="t.table"
              />
            </el-select>
            <el-tag size="small" :type="dataStateTagType(modeState)">
              {{ dataStateLabel(modeState) }}
            </el-tag>
            <el-button :loading="loading" @click="load">刷新</el-button>
            <el-button type="primary" plain @click="exportCsv">导出 {{ exportLabel }}</el-button>
          </el-space>
        </div>
      </template>

      <el-empty v-if="!loading && result && result.total === 0" :description="emptyText" />
      <PagedTable
        v-else
        v-model:page="page"
        v-model:page-size="pageSize"
        :total="result?.total || 0"
        :show-pager="!!result"
        @change="load"
      >
        <el-table :data="result?.rows || []" v-loading="loading" border size="small" max-height="560" empty-text="暂无数据">
          <el-table-column
            v-for="c in displayColumns"
            :key="c"
            :prop="c"
            :label="c"
            min-width="120"
            show-overflow-tooltip
          />
          <el-table-column label="追溯" width="90" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="goTrace(row)">追溯</el-button>
            </template>
          </el-table-column>
        </el-table>
      </PagedTable>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PagedTable from '@/components/PagedTable.vue'
import { browseTable, formatApiError, tableExportUrl, type BrowseResult } from '@/api/client'
import { dataStateLabel, dataStateTagType } from '@/utils/dataStates'
import { DATA_SCOPE_DISCLAIMER_SHORT } from '@/utils/copywriting'

const props = withDefaults(defineProps<{ mode?: 'available' | 'staged' }>(), { mode: 'available' })

const TABLES = [
  { table: 'dim_material', label: '主数据' },
  { table: 'fact_inventory', label: '库存' },
  { table: 'fact_asset', label: '资产' },
  { table: 'fact_demand', label: '需求' },
  { table: 'fact_stock_flow', label: '流水' },
  { table: 'fact_quota_adjust', label: '定额调整' },
]

const route = useRoute()
const router = useRouter()

const table = ref(
  TABLES.some((t) => t.table === route.query.table) ? String(route.query.table) : 'fact_inventory',
)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(true)
const result = ref<BrowseResult | null>(null)

const modeState = computed(() => (props.mode === 'staged' ? 'standardized' : 'available'))
const emptyText = computed(() =>
  table.value === 'fact_quota_adjust'
    ? '该业务表当前为空：尚未接入并发布定额调整记录'
    : '暂无数据，请先在「数据接入」上传并完成规整确认',
)
const exportLabel = computed(() =>
  props.mode === 'staged' ? '规整快照' : '可用数据',
)
/** 展示列：隐藏溯源英文键（仍保留在 row 上供追溯）。 */
const displayColumns = computed(() =>
  (result.value?.columns_zh || []).filter(
    (c) => c !== 'source_release_id' && c !== '发布ID' && c !== 'row_key' && c !== '行键',
  ),
)

async function load() {
  loading.value = true
  try {
    result.value = await browseTable(table.value, pageSize.value, (page.value - 1) * pageSize.value)
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    loading.value = false
  }
}

function onTableChange() {
  page.value = 1
  router.replace({ query: { ...route.query, table: table.value } })
  load()
}

function exportCsv() {
  ElMessage.info(`即将导出：${exportLabel.value}（${DATA_SCOPE_DISCLAIMER_SHORT}）`)
  window.open(tableExportUrl(table.value, 100000, 'business'), '_blank')
}

function goTrace(row: Record<string, unknown>) {
  const releaseId = String(row.source_release_id || row.release_id || '')
  const sourceFile = String(row.source_file || row['来源文件'] || '')
  const rowKey = String(row.row_key || '')
  router.push({
    path: '/trace',
    query: {
      tab: 'lineage',
      ...(releaseId && releaseId !== 'null' && releaseId !== 'undefined'
        ? { release_id: releaseId }
        : {}),
      ...(sourceFile && sourceFile !== 'null' && sourceFile !== 'undefined'
        ? { source_file: sourceFile }
        : {}),
      ...(rowKey && rowKey !== 'null' && rowKey !== 'undefined'
        ? { row_key: rowKey }
        : {}),
    },
  })
}

watch(
  () => route.query.table,
  (v) => {
    if (v && String(v) !== table.value && TABLES.some((t) => t.table === v)) {
      table.value = String(v)
      page.value = 1
      load()
    }
  },
)

onMounted(load)
</script>

<style scoped>
.browse { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.head { display: flex; align-items: center; justify-content: space-between; }
</style>
