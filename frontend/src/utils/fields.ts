/**
 * 标准表/字段中文名与技术字段定义（业务分析视角）。
 * 与后端 app/services/field_dict.py 保持一致。
 */

export const TABLE_ZH: Record<string, string> = {
  dim_material: '物资主数据',
  fact_inventory: '库存台账',
  fact_asset: '资产台账',
  fact_demand: '需求明细',
  fact_quota_adjust: '定额调整记录',
  fact_stock_flow: '出入库流水',
  v_material_inventory: '物资库存视图',
}

export const FIELD_ZH: Record<string, string> = {
  // 通用
  material_id: '物资ID',
  material_code: '物资编码',
  material_name: '物资名称',
  unit: '单位',
  category: '类别',
  spec: '规格型号',
  source_file: '来源文件',
  // dim_material
  name_alias: '名称别名',
  spec_alias: '规格别名',
  code_source: '编码来源',
  // fact_inventory
  inventory_id: '库存ID',
  region: '区域',
  stock_qty: '库存数量',
  opening_qty: '期初数量',
  quota_qty: '定额数量',
  min_qty: '最低数量',
  temp_qty: '临时数量',
  company_wh_qty: '公司仓数量',
  age_days: '库龄(天)',
  unit_cost: '单价',
  stock_value: '库存金额',
  location: '库位',
  custodian: '库管员',
  // T1/T2: ledger-export-plan §7.1（LD-1 锁定 2026-08-10）
  belong_system: '所属系统',
  project_name: '项目名称',
  consumption_plan: '消耗计划',
  material_source: '物资来源',
  group_code: '新集团编码',
  is_frame_material: '是否框架物资',
  agreement_supplier: '协议供应商',
  frame_material_code: '推荐框架物资编码',
  frame_material_name: '推荐框架物资名称',
  frame_material_spec: '推荐框架物资型号',
  frame_material_supplier: '推荐框架物资供应商',
  emergency_supplier: '应急供应商',
  // fact_asset
  asset_code: '资产编号',
  asset_name: '资产名称',
  company: '所属单位',
  domain: '业务域',
  user_name: '使用人',
  manager: '管理人',
  purchase_date: '购置日期',
  status: '状态',
  check_result: '盘点结果',
  // T1/T2: ledger-export-plan §7.2（LD-1/LD-2 锁定 2026-08-10）
  asset_qty: '资产数量',
  is_instrument: '是否仪器仪表',
  replace_cycle: '更换周期(年)',
  check_cycle: '检测周期(年)',
  tool_source: '工器具来源',
  asset_quota_qty: '资产定额数量',
  // fact_demand
  demand_id: '需求ID',
  demand_period: '需求期间',
  quantity: '数量',
  unit_price: '单价',
  total_price: '需求金额',
  reporter: '申报人',
  remark: '备注',
  // fact_quota_adjust
  quota_id: '调整ID',
  adjust_type: '调整类型',
  installed_qty: '装机数量',
  accident_quota: '事故定额',
  reserve_quota: '储备定额',
  verified_quota: '核定定额',
  device_name: '设备名称',
  reason: '原因',
  // fact_stock_flow
  flow_id: '流水ID',
  flow_type: '出入类型',
  flow_date: '日期',
  person: '经手人',
  purpose: '用途',
}

/** 溯源/解析/治理类技术字段：业务表格与导出中隐藏。 */
export const TECHNICAL_FIELDS = new Set([
  'source_release_id',
  'source_era',
  'color_flag',
  'delete_flag',
  'parse_level',
  'parse_source',
  'source_sheet',
  'source_row',
  'source_segment',
  'match_level',
])

export function tableZh(table: string): string {
  return TABLE_ZH[table] || table
}

export function fieldZh(field: string): string {
  return FIELD_ZH[field] || field
}

/** 枚举值汉化（U-6）：flow_type IN→入库、OUT→出库；无映射时原样返回。 */
export const VALUE_ZH: Record<string, Record<string, string>> = {
  flow_type: { IN: '入库', OUT: '出库' },
}

export function valueZh(field: string, value: unknown): unknown {
  const mp = VALUE_ZH[field]
  if (!mp || value == null) return value
  return mp[String(value)] ?? value
}

/** 按表字段中文名：与后端 field_dict.table_field_zh 保持一致。 */
export function tableFieldZh(_table: string, field: string): string {
  return fieldZh(field)
}

/** 按表汉化列名。 */
export function tableZhColumns(table: string, columns: string[]): string[] {
  return columns.map((c) => tableFieldZh(table, c))
}

export function isTechnical(field: string): boolean {
  return TECHNICAL_FIELDS.has(field)
}

/** 过滤技术字段后的业务列。 */
export function visibleFields(columns: string[]): string[] {
  return columns.filter((c) => !isTechnical(c))
}

/** 列名汉化（未在字典中的保持原名）。 */
export function zhColumns(columns: string[]): string[] {
  return columns.map((c) => fieldZh(c))
}
