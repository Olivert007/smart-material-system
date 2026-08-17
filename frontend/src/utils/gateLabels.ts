/** User-facing labels for gate / quality codes (optv1/08). */

const GATE_LABELS: Record<string, string> = {
  rule_path_has_published_rows: '当前没有已发布的出入库流水，库存对账相关指标暂不可用',
  QUALITY_BLOCKING: '部分记录未通过质量门禁，请先处理阻塞问题',
  NO_COLUMNS: '部分工作表没有识别到可用字段，需要确认是否跳过或补充映射',
  MAP_PENDING: '仍有字段映射需要人工确认',
  MAP_BUSINESS_UNMAPPED: '仍有业务列未映射，不能当作门禁通过',
  SKIP_ROLE: '该工作表是摘录/参考，不单独入库',
  DATE_FORMAT: '日期格式不统一',
  EMPTY_SERIAL: '出厂编号为空或占位',
  TYPE_ERROR: '类型错误（应为数字）',
  EMPTY_ROW: '整行空白',
  MISSING_REQUIRED: '必填字段为空',
  MISSING_COL: '缺少必填字段',
  REQUIRED_UNMAPPED: '必填列未映射',
  VALUE_RANGE: '取值越界',
  CELL_MARKER: '单元格标记异常',
  OTHER: '其他质量问题',
  missing_required_field: '缺少必填字段',
  low_confidence_map: '字段映射置信度低，需人工确认',
  unit_unresolved: '单位无法换算',
  material_unmatched: '物资无法匹配',
  quantity_anomaly: '数量异常',
}

export function gateLabel(code?: string | null): string {
  if (!code) return '-'
  return GATE_LABELS[code] || code
}

export { GATE_LABELS }
