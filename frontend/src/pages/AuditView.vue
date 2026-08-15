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
            <el-button type="primary" :loading="loading" @click="load">查询</el-button>
          </el-space>
        </div>
      </template>
      <RetryBanner :message="errorMsg" @retry="load" />
      <el-table :data="items" v-loading="loading" border size="small" empty-text="暂无记录">
        <el-table-column prop="ts" label="时间" width="170" />
        <el-table-column prop="kind" label="类型" width="120" />
        <el-table-column prop="source" label="记录来源" width="120" show-overflow-tooltip />
        <el-table-column prop="action" label="操作内容" width="110" />
        <el-table-column prop="actor" label="操作者" width="90" />
        <el-table-column prop="release_id" label="发布版本" width="140" show-overflow-tooltip />
        <el-table-column prop="file_id" label="源文件" width="140" show-overflow-tooltip />
        <el-table-column prop="detail" label="详情" min-width="180" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auditTimeline, formatApiError } from '@/api/client'
import RetryBanner from '@/components/RetryBanner.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const errorMsg = ref('')
const items = ref<Array<Record<string, string>>>([])
const filterSource = ref('')
const filterActor = ref('')
const filterRelease = ref('')
const filterFile = ref('')
const filterQ = ref('')

function seedFromRoute() {
  if (typeof route.query.release_id === 'string') filterRelease.value = route.query.release_id
  if (typeof route.query.file_id === 'string') filterFile.value = route.query.file_id
  else if (typeof route.query.source_file === 'string') filterFile.value = route.query.source_file
  if (typeof route.query.q === 'string') filterQ.value = route.query.q
  if (typeof route.query.source === 'string') filterSource.value = route.query.source
  if (typeof route.query.actor === 'string') filterActor.value = route.query.actor
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
      limit: 200,
      source: filterSource.value.trim() || undefined,
      actor: filterActor.value.trim() || undefined,
      release_id: filterRelease.value.trim() || undefined,
      file_id: filterFile.value.trim() || undefined,
      q: filterQ.value.trim() || undefined,
    })
    items.value = (res.items || []) as Array<Record<string, string>>
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
@media (max-width: 720px) { .head :deep(.el-space) { flex-wrap: wrap; } }
</style>
