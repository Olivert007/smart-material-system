<template>
  <div class="intake">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="数据接入"
      description="四步完成接入：选择文件 → 查看识别结论 → 处理必要问题 → 确认进入规整。上传成功不等于解析完成，解析完成不等于数据可用，确认导入不等于正式发布。"
    />

    <el-steps :active="wizardStep" finish-status="success" align-center>
      <el-step title="选择文件" />
      <el-step title="识别结论" />
      <el-step title="处理问题" />
      <el-step title="进入规整" />
    </el-steps>

    <!-- Step 1 -->
    <el-card shadow="never" v-show="wizardStep === 0">
      <template #header>① 选择文件</template>
      <el-upload
        ref="uploadRef"
        drag
        :auto-upload="false"
        :show-file-list="true"
        :limit="5"
        :on-change="onChange"
        :on-remove="onRemove"
        :on-exceed="() => ElMessage.warning('单次最多 5 个文件')"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">拖拽文件到此处，或<em>点击选择</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 xlsx / csv / json</div>
        </template>
      </el-upload>
      <div class="actions">
        <div class="actions-left">
          <span v-if="pending.length" class="file-count">已选择 {{ pending.length }} 个文件，可开始上传解析</span>
          <span v-else class="file-count muted">请选择或拖拽文件，选择后才能上传并解析</span>
        </div>
        <el-button type="primary" :loading="uploading" :disabled="!pending.length" @click="doUpload">
          {{ pending.length ? '上传并开始解析' : '请先选择文件' }}
        </el-button>
      </div>
    </el-card>

    <!-- Step 2+3: current jobs with business conclusion -->
    <el-card shadow="never" v-show="wizardStep >= 1">
      <template #header>
        <div class="head">
          <span>{{ wizardStep === 1 ? '② 查看识别结论' : wizardStep === 2 ? '③ 处理必要问题' : '④ 确认进入规整' }}</span>
          <el-button size="small" @click="wizardStep = 0">重新选文件</el-button>
        </div>
      </template>

      <el-empty v-if="!jobs.length && !fileItems.length" description="暂无任务；请先上传文件" />

      <div v-for="job in jobs" :key="job.task_id + job.file_id" class="job-card">
        <div class="job-main">
          <div class="job-title">{{ job.filename }}</div>
          <el-tag :type="userStatusType(job)" size="small">{{ userStatusLabel(job) }}</el-tag>
          <el-progress
            v-if="isParsing(job)"
            :percentage="Math.min(100, Number(job.progress) || 0)"
            :stroke-width="10"
            style="flex: 1; min-width: 120px"
          />
        </div>
        <div class="job-conclusion">
          <strong>结论：</strong>{{ businessConclusion(job) }}
        </div>
        <div class="job-actions">
          <el-button
            v-if="canEnterStage(job) && !needsGovern(job)"
            type="primary"
            @click="goStage(job.file_id)"
          >
            确认进入规整
          </el-button>
          <el-button
            v-else-if="needsGovern(job) && jobConclusion(job)?.conclusion === 'structure_work'"
            type="warning"
            @click="goStage(job.file_id)"
          >
            去确认结构
          </el-button>
          <el-button v-else-if="needsGovern(job)" type="warning" @click="$router.push('/govern')">
            去处理字段/物资问题
          </el-button>
          <el-button v-else-if="job.status === 'failed'" type="danger" plain disabled>
            无法接入，请检查文件后重试
          </el-button>
          <el-button v-else disabled>解析完成后可进入规整</el-button>
        </div>
        <el-collapse class="adv">
          <el-collapse-item title="高级详情（任务与通道）" name="adv">
            <div class="mono">
              任务编号：{{ job.task_id }} · 文件编号：{{ job.file_id }} · 通道：{{
                job.channel === 'poll' ? '轮询' : job.channel === 'sse' ? '实时' : job.channel || '-'
              }}
              · 原始状态：{{ fileStatusLabel(job.status) }} · 进度：{{ job.progress }}
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>文件台账</span>
          <el-button size="small" :loading="filesLoading" @click="loadFiles">刷新</el-button>
        </div>
      </template>
      <div class="table-wrap">
        <el-table :data="fileItems" v-loading="filesLoading" border size="small">
          <el-table-column prop="filename" label="文件名" min-width="180" />
          <el-table-column label="业务状态" width="120">
            <template #default="{ row }">
              <el-tag size="small" :type="fileStatusType(row.status)">{{ fileStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="接入时间" width="170" />
          <el-table-column label="操作" width="140">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                :disabled="!['evidence_done', 'staged', 'released'].includes(row.status)"
                @click="goStage(row.file_id)"
              >
                进入规整
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-collapse class="adv">
        <el-collapse-item title="高级详情（格式与证据行）" name="files-adv">
          <div class="table-wrap">
            <el-table :data="fileItems" border size="small">
              <el-table-column prop="filename" label="文件" min-width="160" />
              <el-table-column prop="format" label="格式" width="80" />
              <el-table-column prop="rows" label="证据行" width="90" />
              <el-table-column label="原始状态" width="120">
                <template #default="{ row }">{{ fileStatusLabel(row.status) }}</template>
              </el-table-column>
              <el-table-column prop="file_id" label="文件编号" min-width="160" show-overflow-tooltip />
            </el-table>
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { UploadFile, UploadInstance } from 'element-plus'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import {
  formatApiError,
  getIntakeConclusion,
  listFiles,
  uploadFile,
  watchTask,
  type FileItem,
  type IntakeConclusion,
} from '@/api/client'
import {
  dataStateLabel,
  dataStateTagType,
  mapIntakeStatusToDataState,
} from '@/utils/dataStates'

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
const uploadRef = ref<UploadInstance>()
const pending = ref<File[]>([])
const uploading = ref(false)
const jobs = ref<Job[]>([])
const conclusions = ref<Record<string, IntakeConclusion>>({})
const fileItems = ref<FileItem[]>([])
const filesLoading = ref(false)
const stoppers = new Map<string, () => void>()
const wizardStep = ref(0)

const activeJob = computed(() => jobs.value[0])

watch(
  () => [jobs.value, activeJob.value?.status] as const,
  () => {
    if (!jobs.value.length) {
      if (wizardStep.value > 0) return
      return
    }
    const j = activeJob.value
    if (!j) return
    if (isParsing(j) || j.status === 'uploaded' || j.status === 'pending') {
      wizardStep.value = Math.max(wizardStep.value, 1)
    } else if (needsGovern(j) || j.status === 'failed') {
      wizardStep.value = 2
    } else if (canEnterStage(j)) {
      wizardStep.value = 3
    } else {
      wizardStep.value = Math.max(wizardStep.value, 1)
    }
  },
  { deep: true },
)

function onChange(file: UploadFile) {
  if (file.raw) pending.value = [...pending.value.filter((f) => f.name !== file.raw!.name), file.raw]
}

function onRemove(file: UploadFile) {
  const name = file.raw?.name || file.name
  pending.value = pending.value.filter((f) => f.name !== name)
}

function syncUrl(job?: Job) {
  const q: Record<string, string> = {}
  if (job?.task_id && job.task_id !== '-') q.task_id = job.task_id
  if (job?.file_id) q.file_id = job.file_id
  router.replace({ query: q })
}

function isParsing(job: Job) {
  return ['pending', 'processing', 'uploaded'].includes(job.status) || (job.progress > 0 && job.progress < 100 && job.status !== 'done' && job.status !== 'failed' && job.status !== 'evidence_done' && job.status !== 'staged' && job.status !== 'released')
}

function canEnterStage(job: Job) {
  return ['done', 'evidence_done', 'staged', 'released'].includes(job.status) && !!job.file_id && job.file_id !== '-'
}

function jobConclusion(job: Job): IntakeConclusion | undefined {
  if (!job.file_id || job.file_id === '-') return undefined
  return conclusions.value[job.file_id]
}

function needsGovern(job: Job) {
  const c = jobConclusion(job)
  return !!c && (c.conclusion === 'field_work' || c.conclusion === 'structure_work')
}

function userStatusLabel(job: Job) {
  const s = job.status
  if (s === 'failed') return '失败'
  const six = mapIntakeStatusToDataState(s)
  if (six === 'published') return dataStateLabel('published')
  if (six === 'standardized') return dataStateLabel('standardized')
  if (six === 'staging') return dataStateLabel('staging')
  if (six === 'raw') {
    if (isParsing(job)) return '解析中'
    return dataStateLabel('raw')
  }
  if (['done', 'evidence_done'].includes(s || '')) return dataStateLabel('staging')
  return s || '处理中'
}

function userStatusType(job: Job) {
  const label = userStatusLabel(job)
  if (label === '失败') return 'danger'
  const six = mapIntakeStatusToDataState(job.status)
  return dataStateTagType(six) || 'info'
}

function businessConclusion(job: Job) {
  const c = jobConclusion(job)
  if (c) {
    if (c.conclusion === 'failed') {
      return '无法接入：解析失败，请检查文件格式或内容后重新上传。'
    }
    if (c.conclusion === 'field_work' || c.conclusion === 'structure_work' || c.conclusion === 'staging_ready') {
      return c.hint
    }
    if (c.conclusion === 'published') {
      return '状态：已发布。已写入业务库（可用候选）；不等于正式发布报表。'
    }
    if (c.conclusion === 'standardized') return '状态：规整。可继续确认或查看质量结果。'
    return '状态：原始。系统正在识别文件结构，完成后给出是否可进入规整的结论。'
  }
  const label = userStatusLabel(job)
  if (label === '失败') return '无法接入：解析失败，请检查文件格式或内容后重新上传。'
  if (label === '解析中' || label === dataStateLabel('raw')) {
    return '状态：原始。系统正在识别文件结构，完成后给出是否可进入规整的结论。'
  }
  if (label === dataStateLabel('staging')) return '状态：暂存。结构已识别，可进入规整确认。'
  if (label === dataStateLabel('standardized')) return '状态：规整。可继续确认或查看质量结果。'
  if (label === dataStateLabel('published')) {
    return '状态：已发布。已写入业务库（可用候选）；不等于正式发布报表。'
  }
  return '请根据状态继续处理。'
}

function fileStatusLabel(status?: string) {
  const six = mapIntakeStatusToDataState(status)
  if (six) return dataStateLabel(six)
  const map: Record<string, string> = {
    uploaded: dataStateLabel('raw'),
    pending: dataStateLabel('raw'),
    processing: '解析中',
    evidence_done: dataStateLabel('staging'),
    staged: dataStateLabel('standardized'),
    released: dataStateLabel('published'),
    failed: '失败',
  }
  return map[status || ''] || status || '-'
}

function fileStatusType(status?: string) {
  if (status === 'failed') return 'danger'
  return dataStateTagType(mapIntakeStatusToDataState(status)) || 'info'
}

function goStage(fileId: string) {
  if (!fileId || fileId === '-') return
  router.push(`/stage/${fileId}`)
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
      if (t.status === 'done' || t.status === 'evidence_done') {
        ElMessage.success(`${t.filename || fileId} 识别完成，可进入规整`)
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
          ElMessage.warning('实时进度通道中断，已自动改用后台刷新')
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
    void refreshConclusions()
  }
}

async function refreshConclusions() {
  const targets = jobs.value.filter((j) => j.file_id && j.file_id !== '-')
  await Promise.all(
    targets.map(async (j) => {
      const fid = j.file_id!
      try {
        conclusions.value[fid] = await getIntakeConclusion(fid)
      } catch {
        delete conclusions.value[fid]
      }
    }),
  )
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
    uploadRef.value?.clearFiles()
    wizardStep.value = 1
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
      filename: '(恢复中的任务)',
      file_id: fileId || '-',
      task_id: taskId,
      status: 'pending',
      progress: 0,
      channel: 'sse',
    }]
    wizardStep.value = 1
    startWatch(taskId, fileId)
    void refreshConclusions()
  }
})

watch(
  () => route.query.task_id,
  (tid) => {
    if (typeof tid === 'string' && tid && !jobs.value.some((j) => j.task_id === tid)) {
      const fileId = typeof route.query.file_id === 'string' ? route.query.file_id : ''
      jobs.value.unshift({
        filename: '(恢复中的任务)',
        file_id: fileId || '-',
        task_id: tid,
        status: 'pending',
        progress: 0,
        channel: 'sse',
      })
      wizardStep.value = 1
      startWatch(tid, fileId)
      void refreshConclusions()
    }
  },
)

onUnmounted(() => {
  for (const stop of stoppers.values()) stop()
  stoppers.clear()
})
</script>

<style scoped>
.intake {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}
.head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.actions {
  margin-top: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.actions-left { min-width: 0; }
.file-count { font-size: 13px; color: #606266; }
.file-count.muted { color: #909399; }
.table-wrap { width: 100%; overflow-x: auto; }
.job-card {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.job-main { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.job-title { font-weight: 600; }
.job-conclusion { color: #606266; font-size: 13px; line-height: 1.5; }
.job-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.adv { margin-top: 4px; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; color: #909399; word-break: break-all; }
@media (max-width: 720px) {
  .actions { flex-direction: column; align-items: stretch; }
  .actions .el-button { width: 100%; }
}
</style>
