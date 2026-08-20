<template>
  <div class="material-panel">
    <div class="filters">
      <el-select
        v-model="categories"
        multiple
        collapse-tags
        collapse-tags-tooltip
        clearable
        placeholder="物资种类：全部"
        class="filter-select"
      >
        <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
      </el-select>
      <el-select
        v-model="locations"
        multiple
        collapse-tags
        collapse-tags-tooltip
        clearable
        filterable
        placeholder="存放区域：全部"
        class="filter-select"
      >
        <el-option v-for="loc in locationOptions" :key="loc" :label="loc" :value="loc" />
      </el-select>
      <el-input
        v-model="keyword"
        clearable
        placeholder="请输入物资编码或物资名称"
        class="keyword"
        @keyup.enter="onSearch"
      />
      <el-button type="primary" @click="onSearch">查询</el-button>
      <el-button @click="onReset">重置</el-button>
    </div>

    <div class="panel-head">
      <h3 class="result-title">筛选结果</h3>
      <div class="result-meta">
        <span>当前共查询到 {{ result?.total ?? 0 }} 条物资记录</span>
        <el-button type="primary" plain :loading="exporting" @click="onExport">导出筛选结果</el-button>
      </div>
    </div>
    <div v-if="categorySummaryText" class="summary-break">{{ categorySummaryText }}</div>

    <el-card shadow="never">
      <el-empty
        v-if="!loading && result && result.total === 0"
        description="暂无匹配的物资数据，请调整物资种类或存放区域筛选条件"
      />
      <PagedTable
        v-else
        v-model:page="page"
        v-model:page-size="pageSize"
        :total="result?.total || 0"
        :show-pager="!!result"
        @change="load"
      >
        <div class="table-wrap">
          <el-table
            :data="result?.items || []"
            v-loading="loading"
            border
            size="small"
            max-height="560"
            empty-text="暂无匹配的物资数据，请调整物资种类或存放区域筛选条件"
          >
            <el-table-column label="物资编码" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ displayCode(row) }}</template>
            </el-table-column>
            <el-table-column prop="material_name" label="物资名称" min-width="260" show-overflow-tooltip />
            <el-table-column prop="category" label="物资种类" min-width="140" show-overflow-tooltip />
            <el-table-column label="存放区域" min-width="240" show-overflow-tooltip>
              <template #default="{ row }">{{ row.location || '—' }}</template>
            </el-table-column>
            <el-table-column label="规格型号" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.spec || '—' }}</template>
            </el-table-column>
            <el-table-column label="单位" min-width="90">
              <template #default="{ row }">{{ row.unit || '—' }}</template>
            </el-table-column>
            <el-table-column label="库存数量" min-width="120">
              <template #default="{ row }">{{ row.stock_qty ?? '—' }}</template>
            </el-table-column>
            <el-table-column prop="status" label="状态" min-width="100" />
            <el-table-column label="操作" min-width="100">
              <template #default="{ row }">
                <el-button
                  link
                  type="primary"
                  :disabled="!canTrace(row)"
                  @click="goTrace(row)"
                >
                  追溯
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </PagedTable>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PagedTable from '@/components/PagedTable.vue'
import {
  ApiError,
  exportMaterialStandardized,
  formatApiError,
  listMaterialStandardized,
  materialStandardizedFilters,
  MATERIAL_CATEGORIES,
  type MaterialStandardizedItem,
  type MaterialStandardizedResult,
} from '@/api/client'

const route = useRoute()
const router = useRouter()

const categoryOptions = ref<string[]>([...MATERIAL_CATEGORIES])
const locationOptions = ref<string[]>([])
const categories = ref<string[]>([])
const locations = ref<string[]>([])
const keyword = ref('')
const appliedCategories = ref<string[]>([])
const appliedLocations = ref<string[]>([])
const appliedKeyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const loading = ref(true)
const exporting = ref(false)
const result = ref<MaterialStandardizedResult | null>(null)

const categorySummaryText = computed(() => {
  const rows = (result.value?.summary?.by_category || []).filter((r) => r.count > 0)
  if (!rows.length) return ''
  return rows.map((r) => `物资种类 ${r.category} ${r.count} 条`).join(' / ')
})

function displayCode(row: MaterialStandardizedItem) {
  const s = (row.material_code || '').trim()
  return s || '未维护'
}

function canTrace(row: MaterialStandardizedItem) {
  return Boolean(row.source_release_id || row.source_file)
}

function csvList(v: unknown): string[] {
  if (Array.isArray(v)) return v.map(String).filter(Boolean)
  if (typeof v === 'string' && v.trim()) return v.split(',').map((s) => s.trim()).filter(Boolean)
  return []
}

function applyForm() {
  appliedCategories.value = [...categories.value]
  appliedLocations.value = [...locations.value]
  appliedKeyword.value = keyword.value.trim()
}

function readQuery() {
  categories.value = csvList(route.query.categories)
  locations.value = csvList(route.query.locations)
  keyword.value = typeof route.query.q === 'string' ? route.query.q : ''
  applyForm()
  const p = Number(route.query.page || 1)
  page.value = Number.isFinite(p) && p > 0 ? Math.floor(p) : 1
  const ps = Number(route.query.page_size || 20)
  pageSize.value = [10, 20, 50, 100].includes(ps) ? ps : 20
}

function syncQuery() {
  const q: Record<string, string | string[]> = { ...route.query } as Record<string, string | string[]>
  if (route.path === '/data') q.tab = 'materials'
  if (appliedCategories.value.length) q.categories = appliedCategories.value.join(',')
  else delete q.categories
  if (appliedLocations.value.length) q.locations = appliedLocations.value.join(',')
  else delete q.locations
  if (appliedKeyword.value) q.q = appliedKeyword.value
  else delete q.q
  if (page.value > 1) q.page = String(page.value)
  else delete q.page
  if (pageSize.value !== 20) q.page_size = String(pageSize.value)
  else delete q.page_size
  router.replace({ path: route.path, query: q })
}

async function loadFilters() {
  try {
    const f = await materialStandardizedFilters()
    if (f.categories?.length) categoryOptions.value = f.categories
    locationOptions.value = f.locations || []
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

async function load() {
  syncQuery()
  loading.value = true
  try {
    const fetchPage = () =>
      listMaterialStandardized({
        categories: appliedCategories.value,
        locations: appliedLocations.value,
        q: appliedKeyword.value,
        limit: pageSize.value,
        offset: (page.value - 1) * pageSize.value,
      })
    let res = await fetchPage()
    const maxPage = Math.max(1, Math.ceil((res.total || 0) / pageSize.value))
    if (res.total > 0 && page.value > maxPage) {
      page.value = maxPage
      syncQuery()
      res = await fetchPage()
    }
    result.value = res
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  applyForm()
  load()
}

function onReset() {
  categories.value = []
  locations.value = []
  keyword.value = ''
  page.value = 1
  pageSize.value = 20
  applyForm()
  load()
}

async function onExport() {
  const total = result.value?.total ?? 0
  if (total <= 0) {
    ElMessage.warning('当前筛选条件查询结果为空，不支持导出，请重新设置筛选条件')
    return
  }
  try {
    await ElMessageBox.confirm(
      `当前筛选条件共查询到【${total}】条物资记录，确认导出电子表格？`,
      '导出确认',
      { type: 'info', confirmButtonText: '导出', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  exporting.value = true
  try {
    await exportMaterialStandardized({
      categories: appliedCategories.value,
      locations: appliedLocations.value,
      q: appliedKeyword.value,
    })
    ElMessage.success('导出任务已完成，文件开始下载')
  } catch (e: unknown) {
    if (e instanceof ApiError && e.code === 'EMPTY_EXPORT') {
      ElMessage.warning(formatApiError(e))
    } else {
      ElMessage.error('导出失败，请稍后重试')
    }
  } finally {
    exporting.value = false
  }
}

function goTrace(row: MaterialStandardizedItem) {
  const releaseId = String(row.source_release_id || '')
  const rowKey = String(row.row_key || '')
  router.push({
    path: '/trace',
    query: {
      tab: 'lineage',
      ...(releaseId ? { release_id: releaseId } : {}),
      ...(rowKey ? { row_key: rowKey } : {}),
      ...(row.source_file ? { source_file: String(row.source_file) } : {}),
    },
  })
}

onMounted(async () => {
  await loadFilters()
  readQuery()
  await load()
})
</script>

<style scoped>
.material-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  width: 100%;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.filter-select { width: 240px; max-width: 100%; }
.keyword { width: 280px; max-width: 100%; }
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.result-title { margin: 0; font-size: 16px; font-weight: 600; }
.result-meta { display: flex; align-items: center; gap: 12px; color: #606266; font-size: 13px; }
.summary-break { color: #909399; font-size: 13px; }
.table-wrap { width: 100%; max-width: 100%; overflow-x: auto; }
.table-wrap :deep(.el-scrollbar__bar.is-horizontal) {
  display: block !important;
  opacity: 1 !important;
  height: 10px !important;
  z-index: 3;
}
.table-wrap :deep(.el-scrollbar__bar.is-horizontal > div) {
  height: 100%;
  border-radius: 5px;
}
@media (max-width: 720px) {
  .panel-head {
    align-items: flex-start;
    flex-direction: column;
  }
  .filter-select,
  .keyword {
    width: 100%;
  }
}
</style>
