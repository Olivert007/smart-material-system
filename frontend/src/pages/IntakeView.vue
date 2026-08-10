<template>
  <div class="intake">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="接入与任务"
      description="上传新文件并跟踪解析进度；下方文件台账可回溯历史接入状态。通过任务编号可恢复进度。"
    />

    <el-upload
      drag
      :auto-upload="false"
      :show-file-list="true"
      :limit="5"
      :on-change="onChange"
      :on-exceed="() => ElMessage.warning('单次最多 5 个文件')"
    >
      <el-icon class="el-icon--upload"><upload-filled /></el-icon>
      <div class="el-upload__text">拖拽文件到此处，或<em>点击选择</em></div>
      <template #tip>
        <div class="el-upload__tip">支持 xlsx / csv / json；上传后实时跟踪任务进度</div>
      </template>
    </el-upload>

    <el-button type="primary" :loading="uploading" :disabled="!pending.length" @click="doUpload">
      上传并入队
    </el-button>

    <el-tabs v-model="subTab">
      <el-tab-pane label="当前任务" name="jobs">
        <el-table v-if="jobs.length" :data="jobs" border size="small">
          <el-table-column prop="filename" label="文件" min-width="180" />
          <el-table-column prop="task_id" label="任务" width="140" />
          <el-table-column prop="status" label="状态" width="120" />
          <el-table-column prop="progress" label="进度" width="90" />
          <el-table-column label="通道" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.channel === 'poll' ? 'warning' : 'success'">
                {{ row.channel === 'poll' ? '轮询' : row.channel === 'sse' ? '实时' : row.channel }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                :disabled="!['done', 'evidence_done'].includes(row.status)"
                @click="$router.push(`/stage/${row.file_id}`)"
              >
                规整
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="暂无任务；上传文件后开始解析" />
      </el-tab-pane>
      <el-tab-pane label="文件台账" name="files">
        <el-button :loading="filesLoading" @click="loadFiles" style="margin-bottom: 8px">刷新</el-button>
        <el-table :data="fileItems" v-loading="filesLoading" border size="small">
          <el-table-column prop="filename" label="文件名" min-width="200" />
          <el-table-column prop="format" label="格式" width="80" />
          <el-table-column prop="rows" label="证据行" width="90" />
          <el-table-column prop="status" label="状态" width="120" />
          <el-table-column prop="created_at" label="时间" width="170" />
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                :disabled="!['evidence_done', 'staged', 'released'].includes(row.status)"
                @click="$router.push(`/stage/${row.file_id}`)"
              >
                规整
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { UploadFile } from 'element-plus'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { formatApiError, listFiles, uploadFile, watchTask, type FileItem } from '@/api/client'

type Job = {
  filename: string
  file_id: string
  task_id: string
  status: string
  progress: number
  channel?: string
  events_url?: string | null
}

const route = useRoute()
const router = useRouter()
const pending = ref<File[]>([])
const uploading = ref(false)
const jobs = ref<Job[]>([])
const subTab = ref('jobs')
const fileItems = ref<FileItem[]>([])
const filesLoading = ref(false)
const stoppers = new Map<string, () => void>()

function onChange(file: UploadFile) {
  if (file.raw) pending.value = [...pending.value.filter((f) => f.name !== file.raw!.name), file.raw]
}

function syncUrl(job?: Job) {
  const q: Record<string, string> = {}
  if (job?.task_id && job.task_id !== '-') q.task_id = job.task_id
  if (job?.file_id) q.file_id = job.file_id
  router.replace({ query: q })
}

function startWatch(taskId: string, fileId: string, eventsUrl?: string | null) {
  if (stoppers.has(taskId)) return
  let fallbackNotified = false
  const stop = watchTask(
    taskId,
    (t) => {
      const idx = jobs.value.findIndex((j) => j.task_id === taskId)
      if (idx >= 0) {
        jobs.value[idx] = {
          ...jobs.value[idx],
          status: t.status,
          progress: t.progress,
          file_id: t.file_id || fileId,
          filename: t.filename || jobs.value[idx].filename,
        }
        syncUrl(jobs.value[idx])
      }
      if (t.status === 'done') {
        ElMessage.success(`${t.filename || fileId} 解析完成`)
        void loadFiles()
      }
      if (t.status === 'failed') ElMessage.error(t.message || '解析失败')
    },
    {
      eventsUrl,
      onFallback: () => {
        const idx = jobs.value.findIndex((j) => j.task_id === taskId)
        if (idx >= 0) jobs.value[idx].channel = 'poll'
        if (!fallbackNotified) {
          fallbackNotified = true
          ElMessage.warning('实时通道中断，已回退轮询；进度仍会更新')
        }
      },
    },
  )
  stoppers.set(taskId, stop)
}

async function loadFiles() {
  filesLoading.value = true
  try {
    fileItems.value = (await listFiles(50, 0)).items
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    filesLoading.value = false
  }
}

async function doUpload() {
  uploading.value = true
  try {
    for (const file of pending.value) {
      const res = await uploadFile(file)
      if (res.reused && !res.task_id) {
        jobs.value.unshift({
          filename: res.filename,
          file_id: res.file_id,
          task_id: '-',
          status: res.status,
          progress: 100,
          channel: '-',
        })
        continue
      }
      const job: Job = {
        filename: res.filename,
        file_id: res.file_id,
        task_id: res.task_id!,
        status: 'pending',
        progress: 0,
        channel: 'sse',
        events_url: res.events_url,
      }
      jobs.value.unshift(job)
      syncUrl(job)
      startWatch(res.task_id!, res.file_id, res.events_url)
    }
    pending.value = []
    subTab.value = 'jobs'
    await loadFiles()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    uploading.value = false
  }
}

onMounted(async () => {
  await loadFiles()
  const taskId = typeof route.query.task_id === 'string' ? route.query.task_id : ''
  const fileId = typeof route.query.file_id === 'string' ? route.query.file_id : ''
  if (taskId) {
    jobs.value = [{
      filename: '(从 URL 恢复)',
      file_id: fileId || '-',
      task_id: taskId,
      status: 'pending',
      progress: 0,
      channel: 'sse',
    }]
    startWatch(taskId, fileId)
  }
})

watch(
  () => route.query.task_id,
  (tid) => {
    if (typeof tid === 'string' && tid && !jobs.value.some((j) => j.task_id === tid)) {
      const fileId = typeof route.query.file_id === 'string' ? route.query.file_id : ''
      jobs.value.unshift({
        filename: '(从 URL 恢复)',
        file_id: fileId || '-',
        task_id: tid,
        status: 'pending',
        progress: 0,
        channel: 'sse',
      })
      startWatch(tid, fileId)
    }
  },
)

onUnmounted(() => {
  for (const stop of stoppers.values()) stop()
  stoppers.clear()
})
</script>

<style scoped>
.intake { display: flex; flex-direction: column; gap: 16px; max-width: 960px; }
@media (max-width: 720px) { .intake { max-width: 100%; } }
</style>
