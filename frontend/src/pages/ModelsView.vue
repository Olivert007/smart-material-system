<template>
  <div class="models">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="本地模型状态"
      description="面向运维：查看模型是否可用及能力影响。模型输出只做建议，不能自动写入业务事实或发布。"
    />

    <el-alert
      v-if="impactLines.length"
      type="warning"
      :closable="false"
      show-icon
      title="当前降级 / 不可用影响"
      :description="impactLines.join(' ')"
      style="margin-bottom: 8px"
    />
    <div class="toolbar">
      <el-space wrap>
        <el-tag type="success" size="large">Stage {{ status?.stage ?? '—' }}</el-tag>
        <el-tag :type="status?.fast?.ok ? 'success' : 'info'">fast {{ status?.fast?.ok ? 'up' : 'down' }}</el-tag>
        <el-tag :type="status?.big?.ok ? 'success' : 'danger'">big {{ status?.big?.ok ? 'up' : 'down' }}</el-tag>
        <el-tag :type="status?.embed?.ok ? 'success' : 'warning'">
          embed {{ status?.embed?.ok ? 'up' : 'down / lexical' }}
        </el-tag>
        <el-input
          v-model="q"
          clearable
          placeholder="筛选角色 / 模型名"
          style="width: 220px"
        />
        <el-button type="primary" :loading="loading" @click="load">重新扫描</el-button>
      </el-space>
    </div>

    <div class="cards" v-loading="loading">
      <div v-for="c in filtered" :key="c.role" class="card" :class="{ down: !c.ok }">
        <div class="card-top">
          <div class="title">{{ c.model }}</div>
          <el-space>
            <el-tag size="small">{{ c.role }}</el-tag>
            <el-tag size="small" :type="cardStateType(c)">{{ c.cardState }}</el-tag>
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
        <el-collapse>
          <el-collapse-item title="高级详情（endpoint / 错误）" :name="c.role">
            <div class="mono">
              <div>endpoint: {{ c.endpoint || '—' }}</div>
              <div v-if="c.error" class="err">error: {{ c.error }}</div>
            </div>
          </el-collapse-item>
        </el-collapse>
        <div class="actions">
          <el-button size="small" :loading="actionBusy === c.role" @click="activate(c.role)">设为活跃</el-button>
          <el-button size="small" :loading="actionBusy === c.role" @click="restart(c.role)">受控重启</el-button>
        </div>
      </div>
    </div>

    <el-card shadow="never" class="topology">
      <template #header>当前拓扑说明</template>
      <p class="hint">
        GB10 同卡难塞 fast+big+embed。当前常见：fast(:8000)+big(:8001) 双驻时 embed 停用并走
        lexical_fallback；或 big+embed（Stage1）。docs/10 评测门槛未过前，仅作过渡探测，不宣称生产双常驻达标。
      </p>
      <el-button link type="primary" @click="$router.push('/system?tab=ops')">打开运维面板（备份 / 自检）</el-button>
    </el-card>
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

const loading = ref(false)
const actionBusy = ref('')
const q = ref('')
const status = ref<Awaited<ReturnType<typeof modelsStatus>> | null>(null)

const cards = computed<RoleCard[]>(() => {
  const s = status.value
  if (!s) return []
  const stage = s.stage
  return [
    {
      role: 'big',
      model: s.big?.configured_model || '(未配置)',
      ok: !!s.big?.ok,
      cardState: s.big?.ok ? (stage >= 1 ? 'active' : 'deployed') : s.big?.configured_model ? 'unreachable' : 'not_configured',
      duty: '复杂 SQL / 质量解读 / 接入建议终稿；PolicyRouter escalate 目标',
      tags: ['Stage1+', 'port :8001', '生成'],
      endpoint: (s.big as { endpoint?: string })?.endpoint,
      error: s.big?.error,
    },
    {
      role: 'fast',
      model: s.fast?.configured_model || '(未配置)',
      ok: !!s.fast?.ok,
      cardState: s.fast?.ok
        ? stage >= 2
          ? 'active'
          : 'deployed'
        : s.fast?.configured_model
          ? 'unreachable'
          : 'not_configured',
      duty: '流水 suggest / 常规映射 / 轻任务草稿；不可用时 degraded_up → big',
      tags: ['Stage2+ 过渡 7B', 'port :8000', '生成'],
      endpoint: (s.fast as { endpoint?: string })?.endpoint,
      error: s.fast?.error,
    },
    {
      role: 'embed',
      model: s.embed?.configured_model || '(未配置)',
      ok: !!s.embed?.ok,
      cardState: s.embed?.ok
        ? 'active'
        : s.embed?.lexical_fallback
          ? 'configured'
          : s.embed?.configured_model
            ? 'unreachable'
            : 'not_configured',
      duty: '表头/主数据候选召回；down 时可 lexical_fallback（不直连库）',
      tags: [
        'Stage1+',
        'port :8002',
        s.embed?.lexical_fallback ? 'lexical fallback' : 'vector',
      ],
      endpoint: (s.embed as { endpoint?: string })?.endpoint,
      error: (s.embed as { error?: string })?.error,
    },
  ]
})

const filtered = computed(() => {
  const needle = q.value.trim().toLowerCase()
  if (!needle) return cards.value
  return cards.value.filter(
    (c) =>
      c.role.includes(needle) ||
      c.model.toLowerCase().includes(needle) ||
      c.duty.toLowerCase().includes(needle),
  )
})

const impactLines = computed(() => {
  const lines: string[] = []
  const s = status.value
  if (!s) return lines
  if (!s.big?.ok) lines.push('主模型离线：复杂问数/解释建议不可用，规则与指标模板仍可用。')
  if (!s.embed?.ok) lines.push('向量模型离线或词法兜底：映射召回降级，须人工确认。')
  if (s.fast && !s.fast.ok) lines.push('快速模型离线：轻量建议降级，不阻断确认与写入。')
  return lines
})

function cardStateType(c: RoleCard) {
  if (c.cardState === 'active') return 'success'
  if (c.cardState === 'unreachable') return 'danger'
  if (c.cardState === 'configured' || c.cardState === 'deployed') return 'warning'
  return 'info'
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
.models { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.toolbar { display: flex; }
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
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
}
.card.down { opacity: 0.92; border-style: dashed; }
.card-top { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; }
.title { font-weight: 600; font-size: 15px; word-break: break-all; }
.duty { margin: 0; color: #606266; font-size: 13px; line-height: 1.45; }
.tags { min-height: 24px; }
.meta { font-size: 12px; color: #909399; }
.err { color: #f56c6c; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: auto; }
.hint { color: #909399; font-size: 13px; margin: 0 0 8px; line-height: 1.5; }
.topology { width: 100%; }
</style>
