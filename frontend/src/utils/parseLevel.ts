export const PARSE_LEVEL_LABEL: Record<string, string> = {
  L1: '规则直接识别',
  L2: '规则校验后识别',
  L3: '需要人工确认',
}

export function parseLevelLabel(v?: string | null) {
  const s = String(v || '').trim()
  if (!s) return '—'
  return PARSE_LEVEL_LABEL[s] || s
}
