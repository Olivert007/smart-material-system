<template>
  <div class="audit">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计时间线"
      description="汇总治理确认与写操作审计记录，可按来源/操作者筛选。"
    />
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <el-space wrap>
            <el-input v-model="filterSource" clearable placeholder="来源" style="width: 160px" />
            <el-input v-model="filterActor" clearable placeholder="操作者" style="width: 140px" />
            <el-button type="primary" :loading="loading" @click="load">查询</el-button>
          </el-space>
        </div>
      </template>
      <RetryBanner :message="errorMsg" @retry="load" />
      <el-table :data="items" v-loading="loading" border size="small" empty-text="暂无记录">
        <el-table-column prop="ts" label="时间" width="170" />
        <el-table-column prop="kind" label="类型" width="120" />
        <el-table-column prop="source" label="来源" width="140" show-overflow-tooltip />
        <el-table-column prop="action" label="动作" width="120" />
        <el-table-column prop="actor" label="操作者" width="100" />
        <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { auditTimeline, formatApiError } from '@/api/client'
import RetryBanner from '@/components/RetryBanner.vue'

const loading = ref(false)
const errorMsg = ref('')
const items = ref<Array<Record<string, string>>>([])
const filterSource = ref('')
const filterActor = ref('')

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await auditTimeline({
      limit: 200,
      source: filterSource.value.trim() || undefined,
      actor: filterActor.value.trim() || undefined,
    })
    items.value = res.items || []
  } catch (e: unknown) {
    errorMsg.value = formatApiError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.audit { display: flex; flex-direction: column; gap: 16px; max-width: 1100px; }
.head { display: flex; justify-content: space-between; align-items: center; }
@media (max-width: 720px) { .head :deep(.el-space) { flex-wrap: wrap; } }
</style>
