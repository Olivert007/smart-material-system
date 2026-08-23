import type { modelsStatus } from '@/api/client'

type ModelStatus = Awaited<ReturnType<typeof modelsStatus>>

export function resolveRuntimeLevel(s: ModelStatus | null): string {
  if (!s) return ''
  if (s.model_runtime) return s.model_runtime
  return s.big?.ok && s.fast?.ok && s.embed?.ok ? 'full' : 'stage1_degraded'
}

export function isLlmCapabilityLimited(s: ModelStatus | null): boolean {
  const level = resolveRuntimeLevel(s)
  return !!level && level !== 'full'
}

export const LLM_DEGRADED_GOVERN_HINT =
  '智能建议（字段映射、流水解析建议）可能不可用；规则路径与手工确认仍可继续。可在「系统设置 → 本地模型」查看详情。'

export const FIRST_USE_INTAKE_HINT =
  '建议先上传需求表或库存台账（xlsx/csv）；系统识别字段后，在「数据规整」确认并写入，结果可在「数据成果」浏览与问数。'
