/**
 * 规整确认页（StageView）用户可见文案 SSOT。
 * 模板中禁止裸染后端 detail / hint / reason_detail。
 */
import { fieldZh, tableZh } from '@/utils/fields'

const DOMAIN_ZH: Record<string, string> = {
  inventory: '库存',
  asset: '资产',
  demand: '需求',
  stock_flow: '出入库流水',
  generic: '通用',
}

const STATUS_ZH: Record<string, string> = {
  STAGED: '待确认',
  RELEASED: '已写入',
  RELEASING: '写入中',
  FAILED: '失败',
}

const ISSUE_COUNT_ZH: Record<string, string> = {
  missing_required: '必填项为空',
  duplicate_pk: '主键重复',
  qty_non_numeric: '数量非数字',
  qty_negative: '数量为负',
  qty_year_like: '数量疑似年份',
  empty_rows: '整行空白',
  empty_row: '整行空白',
  required_unmapped: '缺少必填字段',
}

export function domainZh(domain?: string | null): string {
  if (!domain) return ''
  return DOMAIN_ZH[domain] || domain
}

export function stagingStatusZh(status?: string | null): string {
  if (!status) return '未生成'
  return STATUS_ZH[status] || status
}

export function targetTableZh(table?: string | null): string {
  if (!table) return ''
  return tableZh(table)
}

export function fieldsListZh(fields?: Array<string | null | undefined> | null): string {
  if (!fields?.length) return ''
  return fields
    .map((f) => fieldZh(String(f || '')))
    .filter(Boolean)
    .join('、')
}

export function sanitizeUserHint(text?: string | null): string {
  if (!text) return ''
  let s = String(text)
  s = s.replace(/blocking\s*=\s*true/gi, '存在阻塞项')
  s = s.replace(/blocking\s*=\s*false/gi, '无阻塞项')
  s = s.replace(/\bLLM\b/g, '大模型')
  s = s.replace(/\bconfirm\b/gi, '确认写入')
  s = s.replace(/\bOpsToken\b/gi, '操作令牌')
  s = s.replace(/\bgate\b/gi, '门禁')
  return s.replace(/[ \t]+/g, ' ').replace(/\n+/g, ' ').trim()
}

export function issueCountsSummary(counts?: Record<string, number> | null): string {
  if (!counts) return ''
  const parts: string[] = []
  for (const [key, n] of Object.entries(counts)) {
    const num = Number(n)
    if (!num) continue
    const label = ISSUE_COUNT_ZH[key] || key
    parts.push(`${label} ${num} 行`)
  }
  return parts.join('；')
}

export function detailZh(detail?: string | null): string {
  if (!detail) return ''
  const t = String(detail).trim()
  if (!t) return ''
  if (/required group blank/i.test(t)) return '必填项为空'
  if (/all mapped cells blank/i.test(t)) return '整行空白'
  const keyCount = /key\s*=\s*(.+?)\s*(?:\||,)?\s*count\s*=\s*(\d+)/i.exec(t)
  if (keyCount) return `字段「${keyCount[1].trim()}」异常，共 ${keyCount[2]} 行`
  const required = /^([a-z_][a-z0-9_]*)\s+required$/i.exec(t)
  if (required) return `${fieldZh(required[1])}不能为空`
  const blank = /^([a-z_][a-z0-9_]*)\s+blank$/i.exec(t)
  if (blank) return `${fieldZh(blank[1])}不能为空`
  const notMapped = /^([a-z_][a-z0-9_]*)\s+not mapped$/i.exec(t)
  if (notMapped) return `字段「${fieldZh(notMapped[1])}」未映射`
  if (/none of .+ mapped/i.test(t)) return '必填列未映射'
  const value = /^value=(.+)$/i.exec(t)
  if (value) return `取值 ${value[1]}`
  return sanitizeUserHint(t)
}
