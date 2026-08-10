<template>
  <div class="browse">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <el-space wrap>
            <el-select v-model="table" style="width: 200px" @change="onTableChange">
              <el-option v-for="t in TABLES" :key="t.table" :label="t.label" :value="t.table" />
            </el-select>
            <el-button :loading="loading" @click="load">刷新</el-button>
            <el-button @click="openBrowse">在线浏览</el-button>
            <el-button @click="exportCsv">导出 CSV</el-button>
          </el-space>
        </div>
      </template>

      <el-empty v-if="!loading && result && result.total === 0" :description="emptyText" />
      <PagedTable
        v-else
        v-model:page="page"
        v-model:page-size="pageSize"
        :total="result?.total || 0"
        @change="load"
      >
        <el-table :data="result?.rows || []" v-loading="loading" border size="small" max-height="560">
          <el-table-column
            v-for="c in result?.columns_zh || []"
            :key="c"
            :prop="c"
            :label="c"
            min-width="120"
            show-overflow-tooltip
          />
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
const loading = ref(false)
const result = ref<BrowseResult | null>(null)

const emptyText = computed(() => '暂无数据，请先在「接入与任务」上传并确认发布')

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

function openBrowse() {
  load()
}

function exportCsv() {
  window.open(tableExportUrl(table.value, 100000, 'business'), '_blank')
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
.browse { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; }
</style>
