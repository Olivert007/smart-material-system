/** User-facing labels for gate / quality codes (optv1/08). */

const GATE_LABELS: Record<string, string> = {
  rule_path_has_published_rows: '当前没有已发布的出入库流水，库存对账相关指标暂不可用',
  QUALITY_BLOCKING: '部分记录未通过质量门禁，请先处理阻塞问题',
  NO_COLUMNS: '部分工作表没有识别到可用字段，需要确认是否跳过或补充映射',
  MAP_PENDING: '仍有字段映射需要人工确认',
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
