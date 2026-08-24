/** 问数结果来源标签（docs/19 Step4）。 */
export function askSourceLabel(source?: string | null): string | null {
  switch (source) {
    case 'metric_template':
      return '指标模板'
    case 'vanna':
      return 'Vanna 问数'
    case 'llm_text2sql':
      return '基础问数'
    default:
      return source ? String(source) : null
  }
}

export function askSourceTagType(
  source?: string | null,
): 'success' | 'info' | 'warning' | '' {
  switch (source) {
    case 'metric_template':
      return 'success'
    case 'vanna':
      return 'info'
    case 'llm_text2sql':
      return 'warning'
    default:
      return ''
  }
}
