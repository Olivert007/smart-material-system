<template>
  <div class="audit">
    <h2 class="page-title">操作记录</h2>
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <el-space wrap>
            <el-input v-model="filterRelease" clearable placeholder="发布版本" style="width: 160px" />
            <el-input v-model="filterFile" clearable placeholder="源文件" style="width: 180px" />
            <el-input v-model="filterQ" clearable placeholder="关键词（规则/物资等）" style="width: 180px" />
            <el-input v-model="filterSource" clearable placeholder="记录来源" style="width: 120px" />
            <el-input v-model="filterActor" clearable placeholder="操作者" style="width: 120px" />
            <el-button type="primary" :loading="loading" @click="onSearch">查询</el-button>
          </el-space>
        </div>
      </template>
      <RetryBanner :message="errorMsg" @retry="load" />
      <el-table :data="rows" v-loading="loading" border size="small" empty-text="暂无记录">
        <el-table-column prop="ts" label="时间" width="170" />
        <el-table-column prop="kind_zh" label="类型" width="100" />
        <el-table-column prop="source_zh" label="记录来源" width="130" show-overflow-tooltip />
        <el-table-column prop="action_zh" label="操作内容" width="110" show-overflow-tooltip />
        <el-table-column prop="actor_zh" label="操作者" width="120" show-overflow-tooltip />
        <el-table-column prop="release_id" label="发布版本" width="140" show-overflow-tooltip />
        <el-table-column prop="file_id" label="源文件" width="140" show-overflow-tooltip />
        <el-table-column prop="detail_zh" label="详情" min-width="220" show-overflow-tooltip />
      </el-table>
      <div class="pager">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          :page-sizes="[20, 50, 100, 200]"
          @current-change="onPage"
          @size-change="onSize"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auditTimeline, formatApiError } from '@/api/client'
import RetryBanner from '@/components/RetryBanner.vue'
import {
  ACTOR_ZH,
  KIND_ZH,
  SOURCE_ZH,
  actionZh,
  mapZh,
  renderAuditDetail,
  zhToKey,
} from '@/utils/auditLabels'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const errorMsg = ref('')
const items = ref<Array<Record<string, string>>>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filterSource = ref('')
const filterActor = ref('')
const filterRelease = ref('')
const filterFile = ref('')
const filterQ = ref('')

const rows = ref<Array<Record<string, string>>>([])

function seedFromRoute() {
  if (typeof route.query.release_id === 'string') filterRelease.value = route.query.release_id
  if (typeof route.query.file_id === 'string') filterFile.value = route.query.file_id
  if (typeof route.query.q === 'string') filterQ.value = route.query.q
  if (typeof route.query.source === 'string') filterSource.value = route.query.source
  if (typeof route.query.actor === 'string') filterActor.value = route.query.actor
}

function onSearch() {
  page.value = 1
  load()
}

function onPage(p: number) {
  page.value = p
  load()
}

function onSize(s: number) {
  pageSize.value = s
  page.value = 1
  load()
}

async function load() {
  loading.value = true
  errorMsg.value = ''
  router.replace({
    path: '/trace',
    query: {
      ...route.query,
      tab: 'audit',
      ...(filterRelease.value.trim() ? { release_id: filterRelease.value.trim() } : { release_id: undefined }),
      ...(filterFile.value.trim() ? { file_id: filterFile.value.trim() } : { file_id: undefined }),
      ...(filterQ.value.trim() ? { q: filterQ.value.trim() } : { q: undefined }),
    },
  })
  try {
    const res = await auditTimeline({
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
      // 用户输入为中文标签，映射回库中英文枚举后再精确匹配
      source: zhToKey(SOURCE_ZH, filterSource.value.trim()) || undefined,
      actor: zhToKey(ACTOR_ZH, filterActor.value.trim()) || undefined,
      release_id: filterRelease.value.trim() || undefined,
      file_id: filterFile.value.trim() || undefined,
      q: filterQ.value.trim() || undefined,
    })
    total.value = res.total ?? 0
    items.value = (res.items || []) as Array<Record<string, string>>
    rows.value = items.value.map((it) => ({
      ...it,
      kind_zh: mapZh(KIND_ZH, it.kind),
      source_zh: mapZh(SOURCE_ZH, it.source),
      action_zh: actionZh(it.action),
      actor_zh: mapZh(ACTOR_ZH, it.actor),
      detail_zh: renderAuditDetail(it.detail || ''),
    }))
  } catch (e: unknown) {
    errorMsg.value = formatApiError(e)
  } finally {
    loading.value = false
  }
}

watch(
  () => [route.query.release_id, route.query.file_id, route.query.source_file, route.query.q],
  () => {
    seedFromRoute()
  },
)

onMounted(() => {
  seedFromRoute()
  load()
})
</script>

<style scoped>
.audit { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.page-title { font-size: 16px; font-weight: 600; color: var(--el-text-color-primary); margin: 0; }
.head { display: flex; justify-content: space-between; align-items: center; }
.pager { display: flex; justify-content: flex-end; margin-top: 12px; }
@media (max-width: 720px) { .head :deep(.el-space) { flex-wrap: wrap; } }
</style>
