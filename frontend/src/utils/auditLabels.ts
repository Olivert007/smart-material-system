/**
 * 追溯审计页（数据来源 / 操作记录）共用的枚举值汉化与详情渲染。
 */

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
  model_activate_big: '大模型启用',
  model_restart_big: '大模型重启',
  report_run: '报表运行',
  seed_opening_snapshot: '期初快照',
}

/** 治理确认的决策动作。 */
export const DECISION_ZH: Record<string, string> = {
  accept: '接受',
  accepted: '已接受',
  'accept+overwrite': '接受并覆盖',
  amend: '修改',
  force_accepted: '强制接受',
  ignore: '忽略',
}

export const ACTOR_ZH: Record<string, string> = {
  ops: '运维',
  'ops:cli': '运维（命令行）',
  'ops:stage-d4': '运维（测试）',
  'seed:p2': '种子数据',
  system: '系统',
  'system:compensate': '系统（补偿）',
  'system:cron': '系统（定时）',
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

const DETAIL_KEYS: Record<string, string> = {
  report_name: '报表',
  report_id: '报表编号',
  run_id: '运行',
  rows: '输出行数',
  file_id: '文件',
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
}

export function mapZh(map: Record<string, string>, v: unknown): string {
  const s = String(v ?? '')
  return map[s] || s
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

/** 审计详情 JSON 渲染为中文可读文本。 */
export function renderAuditDetail(raw: string): string {
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
    const label = DETAIL_KEYS[k] || k
    if (Array.isArray(v)) parts.push(`${label} ${v.length} 项`)
    else if (typeof v === 'object' && v !== null) parts.push(`${label} ${JSON.stringify(v)}`)
    else parts.push(`${label} ${String(v)}`)
  }
  return parts.join('；')
}
