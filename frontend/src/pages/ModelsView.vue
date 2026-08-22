<template>
  <div class="models">
    <el-alert
      v-if="runtimeBanner"
      :title="runtimeBanner.title"
      :type="runtimeBanner.type"
      :closable="false"
      show-icon
      :description="runtimeBanner.desc"
      class="runtime-banner"
    />
    <div class="toolbar">
      <el-space wrap>
        <el-button type="primary" :loading="loading" @click="load">重扫</el-button>
      </el-space>
    </div>

    <div class="cards" v-loading="loading">
      <div v-for="c in cards" :key="c.role" class="card" :class="{ down: !c.ok }">
        <div class="card-top">
          <div class="title">{{ c.model }}</div>
          <el-space>
            <el-tag size="small">{{ roleLabel(c.role) }}</el-tag>
            <el-tag size="small" :type="cardStateType(c)">{{ stateLabel(c.cardState) }}</el-tag>
          </el-space>
        </div>
        <p class="duty">{{ c.duty }}</p>
        <el-space wrap class="tags">
          <el-tag size="small" type="info" v-for="t in c.tags" :key="t">{{ t }}</el-tag>
        </el-space>
        <div class="meta">
          <div v-if="c.ok">状态：可用</div>
          <div v-else class="err">状态：不可用（已保留规则路径）</div>
        </div>
        <el-collapse v-if="isOps">
          <el-collapse-item title="高级详情（接口地址 / 错误信息）" :name="c.role">
            <div class="mono">
              <div>接口地址: {{ c.endpoint || '—' }}</div>
              <div v-if="c.error" class="err">错误信息: {{ c.error }}</div>
            </div>
          </el-collapse-item>
        </el-collapse>
        <div class="actions">
          <el-button size="small" :loading="actionBusy === c.role" @click="activate(c.role)">设为活跃</el-button>
          <el-button size="small" :loading="actionBusy === c.role" @click="restart(c.role)">受控重启</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatApiError, modelActivate, modelRestart, modelsStatus } from '@/api/client'

type RoleCard = {
  role: 'embed' | 'fast' | 'big'
  model: string
  ok: boolean
  cardState: string
  duty: string
  tags: string[]
  endpoint?: string
  error?: string
}

type RuntimeModelEntry = {
  ok?: boolean
  configured_model?: string
  models?: string[]
  lexical_fallback?: boolean
  note?: string
  error?: string
  endpoint?: string
}

const loading = ref(false)
const actionBusy = ref('')
const status = ref<Awaited<ReturnType<typeof modelsStatus>> | null>(null)
const isOps = computed(() => (localStorage.getItem('ops_role') || '') === 'ops')

const runtimeBanner = computed(() => {
  const s = status.value
  if (!s) return null
  const level = s.model_runtime || (s.big?.ok && s.fast?.ok && s.embed?.ok ? 'full' : 'stage1_degraded')
  if (level === 'full') return null
  const blocking = (s.blocking || []).join('、') || '部分模型不可用或名称不匹配'
  return {
    title: `runtime_level: ${level}`,
    type: 'warning' as const,
    desc: `当前非完整运行态。影响：${blocking}。规则路径仍可演示；复杂生成与语义召回可能降级。`,
  }
})

function displayModel(entry?: RuntimeModelEntry | null) {
  const configured = String(entry?.configured_model || '').trim()
  if (configured) return configured
  const runtime = Array.isArray(entry?.models) ? entry?.models?.[0] : ''
  if (runtime) return String(runtime)
  return '(未配置)'
}

const cards = computed<RoleCard[]>(() => {
  const s = status.value
  if (!s) return []
  const stage = s.stage
  const big = s.big as RuntimeModelEntry
  const fast = s.fast as RuntimeModelEntry
  const embed = s.embed as RuntimeModelEntry
  return [
    {
      role: 'big',
      model: displayModel(big),
      ok: !!big?.ok,
      cardState: big?.ok ? (stage >= 1 ? 'active' : 'deployed') : big?.configured_model || big?.models?.[0] ? 'unreachable' : 'not_configured',
      duty: '复杂 SQL / 质量解读 / 接入建议终稿；复杂问数的优先模型',
      tags: ['阶段 1+', '复杂任务'],
      endpoint: big?.endpoint,
      error: big?.error,
    },
    {
      role: 'fast',
      model: displayModel(fast),
      ok: !!fast?.ok,
      cardState: fast?.ok
        ? stage >= 2
          ? 'active'
          : 'deployed'
        : fast?.configured_model || fast?.models?.[0]
          ? 'unreachable'
          : 'not_configured',
      duty: '流水建议 / 常规映射 / 轻任务草稿；不可用时降级到主模型',
      tags: ['阶段 2+ 过渡', '轻量任务'],
      endpoint: fast?.endpoint,
      error: fast?.error,
    },
    {
      role: 'embed',
      model: displayModel(embed),
      ok: !!embed?.ok,
      cardState: embed?.ok
        ? 'active'
        : embed?.lexical_fallback
          ? 'configured'
          : embed?.configured_model || embed?.models?.[0]
            ? 'unreachable'
            : 'not_configured',
      duty: '表头/主数据候选召回；不可用时走词法兜底（不直连库）',
      tags: [
        '阶段 1+',
        '候选召回',
        embed?.lexical_fallback ? '词法兜底' : '向量检索',
      ],
      endpoint: embed?.endpoint,
      error: embed?.error,
    },
  ]
})

function cardStateType(c: RoleCard) {
  if (c.cardState === 'active') return 'success'
  if (c.cardState === 'unreachable') return 'danger'
  if (c.cardState === 'configured' || c.cardState === 'deployed') return 'warning'
  return 'info'
}

function stateLabel(s: string) {
  const map: Record<string, string> = {
    active: '当前活跃',
    deployed: '已部署',
    unreachable: '不可达',
    not_configured: '未配置',
    configured: '词法兜底',
  }
  return map[s] || s
}

function roleLabel(r: string) {
  const map: Record<string, string> = { big: '主模型', fast: '快速模型', embed: '向量模型' }
  return map[r] || r
}

async function load() {
  loading.value = true
  try {
    status.value = await modelsStatus()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    loading.value = false
  }
}

async function activate(role: 'big' | 'fast' | 'embed') {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  try {
    await ElMessageBox.confirm(`切换 ${role} 为活跃档位？将记录审计。`, '确认', { type: 'warning' })
  } catch { return }
  actionBusy.value = role
  try {
    const out = await modelActivate(role)
    ElMessage.success(out.note || '已记录')
    await load()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    actionBusy.value = ''
  }
}

async function restart(role: 'big' | 'fast' | 'embed') {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  try {
    await ElMessageBox.confirm(`请求受控重启 ${role}？`, '确认', { type: 'warning' })
  } catch { return }
  actionBusy.value = role
  try {
    const out = await modelRestart(role)
    ElMessage.success(out.note || '已记录')
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    actionBusy.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.models { display: flex; flex-direction: column; gap: 16px; width: 100%; min-width: 0; }
.toolbar { display: flex; }
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr));
  gap: 14px;
}
.card {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 14px 16px;
  background: var(--el-bg-color);
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.card.down { opacity: 0.92; border-style: dashed; }
.card-top { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; }
.title { font-weight: 600; font-size: 15px; word-break: break-all; flex: 1 1 auto; min-width: 0; }
.duty { margin: 0; color: #606266; font-size: 13px; line-height: 1.45; }
.tags { min-height: 24px; }
.meta { font-size: 12px; color: #909399; }
.err { color: #f56c6c; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; overflow-wrap: anywhere; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: auto; }
</style>
