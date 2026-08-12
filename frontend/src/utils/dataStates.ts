/** 全站统一六态：原始 / 暂存 / 规整 / 可用 / 阻塞 / 已发布（optv1/01） */

export type DataStateCode =
  | 'raw'
  | 'staging'
  | 'standardized'
  | 'available'
  | 'blocked'
  | 'published'

export type DataStateMeta = {
  code: DataStateCode
  label: string
  tagType: 'info' | 'success' | 'warning' | 'danger' | ''
  hint: string
}

export const DATA_STATES: Record<DataStateCode, DataStateMeta> = {
  raw: {
    code: 'raw',
    label: '原始',
    tagType: 'info',
    hint: '未规整的源文件或原始单元格值',
  },
  staging: {
    code: 'staging',
    label: '暂存',
    tagType: 'info',
    hint: '已识别结构、待确认写入前的暂存结果',
  },
  standardized: {
    code: 'standardized',
    label: '规整',
    tagType: 'info',
    hint: '已按字段/物资/单位规则规整的结构数据',
  },
  available: {
    code: 'available',
    label: '可用',
    tagType: 'success',
    hint: '通过门禁的可用候选；不等于正式发布',
  },
  blocked: {
    code: 'blocked',
    label: '阻塞',
    tagType: 'danger',
    hint: '因缺字段、低置信或异常而不能进入可用结果',
  },
  published: {
    code: 'published',
    label: '已发布',
    tagType: 'warning',
    hint: '已写入业务库的发布版本；报表/问数仍非正式定稿',
  },
}

export const DATA_STATE_LEGEND: DataStateMeta[] = [
  DATA_STATES.raw,
  DATA_STATES.staging,
  DATA_STATES.standardized,
  DATA_STATES.available,
  DATA_STATES.blocked,
  DATA_STATES.published,
]

export function dataStateLabel(code: string | null | undefined): string {
  if (!code) return '—'
  const hit = DATA_STATES[code as DataStateCode]
  return hit?.label || code
}

export function dataStateTagType(
  code: string | null | undefined,
): DataStateMeta['tagType'] {
  if (!code) return 'info'
  return DATA_STATES[code as DataStateCode]?.tagType ?? 'info'
}

/** 将接入/任务原始 status 映射到六态 */
export function mapIntakeStatusToDataState(
  status?: string | null,
): DataStateCode | null {
  const s = (status || '').toLowerCase()
  if (!s) return null
  if (['uploaded', 'pending', 'processing', 'failed'].includes(s)) return 'raw'
  if (['done', 'evidence_done'].includes(s)) return 'staging'
  if (s === 'staged') return 'standardized'
  if (s === 'released') return 'published'
  return null
}

/** 文件/接入任务原始状态 → 用户中文（下拉与状态列通用，optv1/08） */
export function fileStatusLabel(status?: string | null): string {
  const s = (status || '').toLowerCase()
  if (!s) return '—'
  const map: Record<string, string> = {
    uploaded: dataStateLabel('raw'),
    pending: dataStateLabel('raw'),
    processing: '解析中',
    done: dataStateLabel('staging'),
    evidence_done: dataStateLabel('staging'),
    staged: dataStateLabel('standardized'),
    released: dataStateLabel('published'),
    failed: '失败',
  }
  return map[s] || s
}

/** 数据成果 Tab → 六态 */
export function mapDataTabToState(
  tab: string,
): DataStateCode | null {
  if (tab === 'available' || tab === 'report' || tab === 'trend') return 'available'
  if (tab === 'staged') return 'standardized'
  if (tab === 'blocked') return 'blocked'
  return null
}
