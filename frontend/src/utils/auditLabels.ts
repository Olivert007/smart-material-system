/**
 * 追溯审计页（数据来源 / 操作记录）共用的枚举值汉化与详情渲染。
 */

import { fieldZh, tableZh } from '@/utils/fields'

export const KIND_ZH: Record<string, string> = {
  govern_confirm: '治理确认',
  write_audit: '系统写入',
}

/** 记录来源（write_audit 的 source=action，取值与操作内容重叠）。 */
export const SOURCE_ZH: Record<string, string> = {
  flow_confirm: '流水确认',
  intake_plan: '接入计划',
  map_confirm: '映射确认',
  map_pending: '映射待办',
  material_align: '物资对齐',
  intake_release: '接入发布',
  material_align_apply: '物资对齐应用',
  metric_activate_flow: '指标激活',
  model_activate_big: '主模型启用',
  model_activate_fast: '快速模型启用',
  model_activate_embed: '向量模型启用',
  model_restart_big: '主模型重启',
  model_restart_fast: '快速模型重启',
  model_restart_embed: '向量模型重启',
  report_run: '报表运行',
  seed_opening_snapshot: '期初快照',
  lineage_rebuild: '重建版本记录',
  lineage_revoke: '撤销发布',
  lineage_revoke_stock_flow: '撤销流水发布',
  lineage_rebuild_stock_flow: '重建流水发布',
  master_apply: '主数据应用',
  master_pending: '主数据待办',
  release_failed: '发布失败',
  release_supersede: '版本取代',
  correction_apply: '更正应用',
  correction: '数据更正',
  rule_learn: '规则学习',
  rule_dict_status: '规则字典状态',
  value_rule: '值规则',
}

/** 治理确认的决策动作。 */
export const DECISION_ZH: Record<string, string> = {
  accept: '接受',
  accepted: '已接受',
  'accept+overwrite': '接受并覆盖',
  amend: '修改',
  force_accepted: '强制接受',
  ignore: '忽略',
  approve: '批准',
  reject: '拒绝',
  merge: '合并',
  enable: '启用',
  disable: '停用',
  proposed: '待确认',
  applied: '已应用',
}

export const ACTOR_ZH: Record<string, string> = {
  ops: '运维',
  'ops:cli': '运维（命令行）',
  'ops:stage-d4': '运维（测试）',
  'seed:p2': '种子数据',
  system: '系统',
  'system:compensate': '系统（补偿）',
  'system:cron': '系统（定时）',
  'system:rule_learn': '系统（规则学习）',
  'system:preview': '系统（预览）',
  viewer: '查看者',
  smoke: '冒烟测试',
  tester: '测试',
}

/** 发布版本目标域。 */
export const DOMAIN_ZH: Record<string, string> = {
  asset: '资产',
  inventory: '库存',
  demand: '需求',
  stock_flow: '出入库流水',
  flow: '出入库流水',
  default: '默认',
}

/** Sheet 角色（app/services/intake/profile.py role_hint）。 */
export const ROLE_ZH: Record<string, string> = {
  summary: '汇总表',
  detail: '明细表',
  empty: '空表',
  wide_export: '宽表导出',
  reference: '参考表',
  history_copy: '历史副本',
  unknown: '未识别',
}

/** Sheet 结构（structure_hint）。 */
export const STRUCTURE_ZH: Record<string, string> = {
  standard_vertical: '标准纵向',
  stacked_regions: '堆叠分区',
  multi_level_header: '多层表头',
  wide_export: '宽表',
  report_only: '仅报表',
  empty: '空',
  unknown: '未识别',
}

/** 工作表名展示：内部名 tabular / Sheet1 等译成中文，未知保持原样。 */
export function sheetNameZh(s?: string | null): string {
  const raw = String(s ?? '').trim()
  if (!raw) return ''
  const map: Record<string, string> = {
    tabular: '表格数据',
    Sheet1: '工作表1',
    sheet1: '工作表1',
  }
  return map[raw] || raw
}

export const TASK_TYPE_ZH: Record<string, string> = {
  parse_evidence: '解析取证',
  analyze: '画像分析',
  map_headers: '表头映射',
  map_headers_repair: '表头映射修复',
  text2sql: '自动生成查询',
  text2sql_repair: '查询修复',
  ask_summary: '问答摘要',
  flow_parse_suggest: '流水拆解建议',
}

export const RULE_SOURCE_ZH: Record<string, string> = {
  seed: '种子规则',
  map_pending_confirm: '映射确认',
  rule_learn: '规则学习',
  exact: '精确匹配',
  norm: '规范化匹配',
  embed: '向量匹配',
  llm: '大模型',
  manual: '人工',
  example: '示例',
  rule: '规则',
}

export const MODEL_ROLE_ZH: Record<string, string> = {
  big: '主模型',
  fast: '快速模型',
  embed: '向量模型',
}

const FILE_FORMAT_ZH: Record<string, string> = {
  xlsx: 'Excel 工作簿',
  xlsm: 'Excel 工作簿',
  xlsb: 'Excel 工作簿',
  xls: 'Excel 工作簿',
  csv: 'CSV',
}

const POLICY_ZH: Record<string, string> = {
  'opening_qty=stock_qty where no fact_stock_flow for material_id':
    '无出入库流水时，期初数量取当前库存',
}

const DETAIL_KEYS: Record<string, string> = {
  report_name: '报表',
  report_id: '报表编号',
  run_id: '运行编号',
  rows: '输出行数',
  file_id: '源文件',
  target_domain: '目标域',
  target_table: '目标表',
  updated_flows: '更新流水数',
  updated: '更新数量',
  activated: '激活指标',
  note: '说明',
  force: '强制',
  role: '角色',
  policy: '策略',
  material_id: '物资',
  pending_id: '待办',
  header: '表头',
  std_field: '标准字段',
  reason: '原因',
  pairs: '对齐对数',
  from: '来源',
  to: '去向',
  flows: '流水数',
  version: '版本',
  idempotent: '幂等',
  material_ops: '物资操作',
  flow_example_snapshot: '流水拆解示例',
  rebuilt: '已重建',
  deleted_flows: '删除流水',
  correction_id: '更正单',
  supersedes: '取代版本',
  row_key: '行',
  field: '字段',
  value_new: '新值',
  merge_to: '合并至',
  gate: '门禁',
  checks: '检查项',
  dry_run: '试运行',
  metric_id: '指标',
  domain: '业务域',
  business_domain: '业务域',
  actor: '操作者',
  action: '操作',
}

const DETAIL_SKIP = new Set(['staging_id', 'fingerprint', 'call_id'])

export function mapZh(map: Record<string, string>, v: unknown): string {
  const s = String(v ?? '')
  return map[s] || s
}

export function fileFormatZh(v: unknown): string {
  const s = String(v || '').toLowerCase()
  if (!s) return '—'
  return FILE_FORMAT_ZH[s] || String(v)
}

export function taskTypeZh(v: unknown): string {
  return mapZh(TASK_TYPE_ZH, v)
}

export function ruleSourceZh(v: unknown): string {
  return mapZh(RULE_SOURCE_ZH, v)
}

/** 中文标签/别名 → 英文枚举。筛选时把用户输入的中文映射回库中存储值；未命中原样返回。 */
export function zhToKey(map: Record<string, string>, v: string): string {
  const s = String(v || '').trim()
  if (!s) return s
  for (const [key, zh] of Object.entries(map)) {
    if (zh === s) return key
  }
  for (const [key, zh] of Object.entries(map)) {
    if (zh.includes(s) || s.includes(zh)) return key
  }
  return s
}

export function actionZh(action: unknown): string {
  const s = String(action ?? '')
  return DECISION_ZH[s] || SOURCE_ZH[s] || s
}

function shortId(id: string): string {
  return id.length > 8 ? id.slice(-8) : id
}

function looksLikeId(s: string): boolean {
  return /^(rel_|file_|stg_|run_|req_|corr_)/i.test(s) || /^[0-9a-f]{32,}$/i.test(s)
}

function enumZh(s: string): string {
  return (
    SOURCE_ZH[s] ||
    DECISION_ZH[s] ||
    DOMAIN_ZH[s] ||
    ACTOR_ZH[s] ||
    MODEL_ROLE_ZH[s] ||
    TASK_TYPE_ZH[s] ||
    RULE_SOURCE_ZH[s] ||
    s
  )
}

function formatDetailValue(
  key: string,
  v: unknown,
  files?: Record<string, string>,
): string {
  if (v == null || v === '') return ''
  if (typeof v === 'boolean') return v ? '是' : '否'
  if (Array.isArray(v)) {
    if (!v.length) return '无'
    if (v.every((x) => x == null || typeof x !== 'object')) {
      return v.map((x) => enumZh(String(x))).join('、')
    }
    return `${v.length} 项`
  }
  if (typeof v === 'object') {
    const inner = Object.entries(v as Record<string, unknown>)
      .map(([ik, iv]) => {
        const text = formatDetailValue(ik, iv, files)
        if (!text) return ''
        return `${DETAIL_KEYS[ik] || fieldZh(ik)} ${text}`
      })
      .filter(Boolean)
    return inner.join('，') || ''
  }
  const s = String(v)
  if (s === 'true' || s === 'false') return s === 'true' ? '是' : '否'
  if (key === 'target_domain' || key === 'domain' || key === 'business_domain') {
    return mapZh(DOMAIN_ZH, s)
  }
  if (key === 'target_table') return tableZh(s)
  if (key === 'std_field' || key === 'field') return fieldZh(s)
  if (key === 'action') return actionZh(s)
  if (key === 'role') return mapZh({ ...MODEL_ROLE_ZH, ...ACTOR_ZH }, s)
  if (key === 'actor') return mapZh(ACTOR_ZH, s)
  if (key === 'file_id') return files?.[s] || ''
  if (key === 'policy') return POLICY_ZH[s] || s
  if (key === 'note' && s === 'ui request') return '界面请求'
  if (key === 'supersedes' || key === 'release_id') {
    return looksLikeId(s) ? `版本 …${shortId(s)}` : s
  }
  if (looksLikeId(s) && (key.endsWith('_id') || key === 'row_key')) return ''
  return enumZh(s)
}

/** 审计详情 JSON 渲染为中文可读文本。 */
export function renderAuditDetail(raw: string, files?: Record<string, string>): string {
  if (!raw) return '—'
  let obj: unknown
  try {
    obj = JSON.parse(raw)
  } catch {
    return raw
  }
  if (typeof obj !== 'object' || obj === null) return raw
  const parts: string[] = []
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    if (DETAIL_SKIP.has(k)) continue
    const text = formatDetailValue(k, v, files)
    if (!text) continue
    const label = DETAIL_KEYS[k] || fieldZh(k)
    if (label === k && /^[a-z][a-z0-9_]*$/i.test(k)) continue
    parts.push(`${label} ${text}`)
  }
  return parts.join('；') || '—'
}
