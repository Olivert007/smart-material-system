/** Relative API base — never hardcode host/port (docs/11 C13). */
export const API_BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  code: string
  body: unknown
  requestId: string | null
  constructor(status: number, body: unknown) {
    const msg =
      typeof body === 'object' && body && 'message' in body
        ? String((body as { message: string }).message)
        : `HTTP ${status}`
    super(msg)
    this.status = status
    this.body = body
    this.code =
      typeof body === 'object' && body && 'code' in body
        ? String((body as { code: string }).code)
        : `HTTP_${status}`
    this.requestId =
      typeof body === 'object' && body && 'request_id' in body
        ? String((body as { request_id: string }).request_id)
        : null
  }
}

export function formatApiError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 409) {
      const map: Record<string, string> = {
        STAGE_VERSION_CONFLICT: '版本冲突（409）：页面数据已过期，请刷新后重试',
        STAGE_STATUS_CONFLICT: '状态冲突（409）：Staging 状态已变化，请刷新',
        STAGE_CAS_CONFLICT: '并发冲突（409）：请刷新后重试',
        STAGE_CONFLICT: 'Staging 冲突（409）',
      }
      return map[e.code] || `冲突（409）：${e.code}`
    }
    if (e.status === 503) return `服务暂不可用（503）：${e.message}`
    if (e.status === 401 || e.status === 403) return `鉴权失败（${e.status}）：请检查 Ops Token`
    return e.message
  }
  return e instanceof Error ? e.message : String(e)
}

function opsHeaders(): HeadersInit {
  const token = localStorage.getItem('ops_token') || ''
  const role = localStorage.getItem('ops_role') || 'ops'
  const h: Record<string, string> = {}
  if (token) h['X-Ops-Token'] = token
  if (role) h['X-Ops-Role'] = role
  return h
}

function handleAuthError(status: number) {
  if (status === 401 && typeof window !== 'undefined') {
    const path = window.location.pathname
    if (path !== '/settings') {
      window.dispatchEvent(new CustomEvent('ops-auth-required'))
    }
  }
}

function newRequestId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `req_${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`
  }
  return `req_${Math.random().toString(16).slice(2, 14)}`
}

export async function apiJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  if (!headers.has('Content-Type') && init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (!headers.has('X-Request-ID')) {
    headers.set('X-Request-ID', newRequestId())
  }
  for (const [k, v] of Object.entries(opsHeaders())) {
    if (!headers.has(k)) headers.set(k, v)
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  const text = await res.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }
  if (!res.ok) {
    handleAuthError(res.status)
    throw new ApiError(res.status, body)
  }
  return body as T
}

export type FileItem = {
  file_id: string
  filename: string
  format?: string
  sha256?: string
  rows?: number
  sheets?: number
  status: string
  created_at: string
}

export type TaskInfo = {
  task_id: string
  file_id: string
  filename?: string
  status: string
  progress: number
  message?: string
}

export type StagingInfo = {
  staging_id: string
  file_id: string
  status: string
  version: number
  clean_rows?: number
  blocked_rows?: number
  fingerprint?: string
  dry_run?: Record<string, unknown>
  impact?: Record<string, unknown>
  release_id?: string
  updated_at?: string
}

export async function listFiles(limit = 20, offset = 0) {
  return apiJson<{
    items: FileItem[]
    total: number
    limit: number
    offset: number
    next_offset: number | null
  }>(`/files?limit=${limit}&offset=${offset}`)
}

export async function listTasks(limit = 50, offset = 0, status?: string) {
  const q = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (status) q.set('status', status)
  return apiJson<{ items: TaskInfo[]; total: number; limit: number; offset: number }>(
    `/tasks?${q}`,
  )
}

export async function uploadFile(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return apiJson<{
    file_id: string
    task_id: string | null
    status: string
    filename: string
    reused?: boolean
    status_url?: string | null
    events_url?: string | null
  }>('/files', { method: 'POST', body: fd })
}

/** Prefer SSE for task progress; falls back to polling if EventSource fails. */
export function watchTask(
  taskId: string,
  onUpdate: (t: TaskInfo) => void,
  opts?: { eventsUrl?: string | null; pollMs?: number; onFallback?: () => void },
): () => void {
  let closed = false
  let es: EventSource | null = null
  let timer: number | null = null
  const pollMs = opts?.pollMs ?? 800
  const eventsUrl = opts?.eventsUrl || `/events/tasks/${taskId}`

  const stop = () => {
    closed = true
    if (es) {
      es.close()
      es = null
    }
    if (timer != null) {
      window.clearInterval(timer)
      timer = null
    }
  }

  const startPoll = () => {
    if (closed || timer != null) return
    const tick = async () => {
      if (closed) return
      try {
        const t = await getTask(taskId)
        onUpdate(t)
        if (t.status === 'done' || t.status === 'failed') stop()
      } catch {
        /* keep polling briefly */
      }
    }
    timer = window.setInterval(tick, pollMs)
    void tick()
  }

  try {
    es = new EventSource(eventsUrl)
    es.addEventListener('task', (ev) => {
      try {
        const t = JSON.parse((ev as MessageEvent).data) as TaskInfo
        onUpdate(t)
      } catch {
        /* ignore */
      }
    })
    es.addEventListener('end', (ev) => {
      try {
        const t = JSON.parse((ev as MessageEvent).data) as TaskInfo
        onUpdate(t)
      } catch {
        /* ignore */
      }
      stop()
    })
    es.onerror = () => {
      if (es) {
        es.close()
        es = null
      }
      opts?.onFallback?.()
      startPoll()
    }
  } catch {
    startPoll()
  }

  return stop
}

export async function getTask(taskId: string) {
  return apiJson<TaskInfo>(`/tasks/${taskId}`)
}

export type AnalyzeResult = {
  ok: boolean
  file_id: string
  report_id?: string
  target_domain?: string
  blocking?: boolean
  gate_ok?: boolean
  codes?: string[]
  next_actions?: string[]
  hint?: string
  steps?: Record<string, unknown>
  task_id?: string
  status?: string
  task_type?: string
}

export async function intakeAnalyze(
  fileId: string,
  body?: {
    target_domain?: string
    include_stage?: boolean
    refresh_profile?: boolean
    config_version?: string
    async_mode?: boolean
  },
) {
  return apiJson<AnalyzeResult>(`/intake/analyze/${fileId}`, {
    method: 'POST',
    body: JSON.stringify({
      target_domain: body?.target_domain ?? 'inventory',
      include_stage: body?.include_stage ?? true,
      refresh_profile: body?.refresh_profile ?? false,
      config_version: body?.config_version ?? 'v1',
      async_mode: body?.async_mode ?? false,
    }),
  })
}

export async function getIntakeAnalyze(fileId: string) {
  return apiJson<{
    report_id: string
    file_id: string
    report_type: string
    created_at?: string
    analyze: AnalyzeResult
  }>(`/intake/analyze/${fileId}`)
}

export async function getIntakeReportBundle(fileId: string) {
  return apiJson<{
    file_id: string
    file?: Record<string, unknown>
    profile?: unknown
    quality?: unknown
    plan?: unknown
    analyze?: unknown
    staging?: unknown
  }>(`/intake/report/${fileId}`)
}

export async function createStaging(fileId: string, body?: { config_version?: string; target_domain?: string }) {
  return apiJson<StagingInfo>(`/intake/stage/${fileId}`, {
    method: 'POST',
    body: JSON.stringify(body || { config_version: 'v1', target_domain: 'inventory' }),
  })
}

export async function getStaging(fileId: string) {
  return apiJson<StagingInfo>(`/intake/stage/${fileId}`)
}

export type SheetProfile = {
  sheet: string
  rows: number
  cols: number
  density: number
  role_hint: string
  role_confidence: number
  header_row_candidates: number[]
  data_bounds: { start_row: number | null; end_row: number | null; data_row_count?: number }
  structure_hint: string
  adapter_hint: string
  anomalies: string[]
  needs_llm: boolean
  signals: string[]
}

export type IntakeProfile = {
  report_id: string | null
  file_id: string
  report_type: string
  created_at: string | null
  profile: {
    step?: string
    source?: string
    workbook?: {
      sheet_count: number
      needs_llm_sheets: string[]
      role_counts: Record<string, number>
    }
    sheets?: SheetProfile[]
  }
}

export async function getIntakeProfile(fileId: string) {
  return apiJson<IntakeProfile>(`/intake/profile/${fileId}`)
}

export type QualityReport = {
  report_id: string | null
  file_id: string
  report_type: string
  created_at: string | null
  quality: {
    ok?: boolean
    blocking?: boolean
    issue_total?: number
    issue_counts?: Record<string, number>
    issues_sample?: Array<Record<string, unknown>>
    suggested_dedup?: string[]
    hint?: string
    domain?: string
    row_count?: number
  }
}

export async function getIntakeQuality(fileId: string) {
  return apiJson<QualityReport>(`/intake/quality/${fileId}`)
}

export type IntakeConclusion = {
  file_id: string
  status: string
  conclusion:
    | 'failed'
    | 'parsing'
    | 'published'
    | 'standardized'
    | 'structure_work'
    | 'field_work'
    | 'staging_ready'
  reason_codes: string[]
  hint: string
}

export async function getIntakeConclusion(fileId: string) {
  return apiJson<IntakeConclusion>(`/intake/conclusion/${fileId}`)
}

export type IntakePlan = {
  report_id: string | null
  file_id: string
  report_type?: string
  created_at?: string | null
  plan_status: string
  plan: {
    target_domain?: string
    target_table?: string
    sheets?: Array<Record<string, unknown>>
    gate?: {
      ok?: boolean
      can_confirm_release?: boolean
      blockers?: Array<{ code: string; message: string }>
      warnings?: Array<{ code: string; message: string }>
    }
    quality_summary?: Record<string, unknown>
    hint?: string
    mutates_state?: boolean
  }
}

export async function getIntakePlan(fileId: string) {
  return apiJson<IntakePlan>(`/intake/plan/${fileId}`)
}

export async function buildIntakePlan(fileId: string, targetDomain = 'inventory') {
  return apiJson<IntakePlan>(`/intake/plan/${fileId}`, {
    method: 'POST',
    body: JSON.stringify({ target_domain: targetDomain }),
  })
}

export async function confirmIntakePlan(fileId: string, opts?: { note?: string; force?: boolean }) {
  return apiJson<{
    ok: boolean
    plan_status: string
    mutates_state: boolean
    hint?: string
    gate?: IntakePlan['plan']['gate']
  }>(`/intake/plan/${fileId}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ note: opts?.note || '', force: !!opts?.force }),
  })
}

export async function confirmStaging(fileId: string, opts?: {
  version?: number
  expected_status?: string
  idempotencyKey?: string
  force?: boolean
}) {
  const headers: HeadersInit = {}
  if (opts?.idempotencyKey) {
    headers['Idempotency-Key'] = opts.idempotencyKey
  }
  return apiJson<{
    status: string
    idempotent?: boolean
    idempotency_replay?: boolean
    target_table?: string
    rows?: number
    release: { release_id: string; clean_rows?: number }
  }>(`/intake/stage/${fileId}/confirm`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      version: opts?.version ?? null,
      expected_status: opts?.expected_status ?? 'STAGED',
      force: !!opts?.force,
    }),
  })
}

export async function healthLive() {
  const res = await fetch('/health/live')
  return res.json() as Promise<{ status: string }>
}

export async function healthReady() {
  const res = await fetch('/health/ready')
  return res.json() as Promise<{
    status: string
    frontend_dist?: boolean
    version?: string
  }>
}

export type AskResult = {
  ok: boolean
  question?: string
  sql?: string | null
  rows?: number | null
  total_rows?: number | null
  truncated?: boolean
  columns?: string[]
  data?: Record<string, unknown>[]
  answer?: string | null
  model?: string | null
  model_state?: string
  model_invoked?: boolean
  latency_ms?: number
  error?: string | null
  code?: string
  summary_model_state?: string
  source?: string
  metric_id?: string
  metric_name?: string
  metric_version?: number | string | null
  unit?: string | null
  data_scope?: string
  hint?: string
  degraded?: boolean
  available_capabilities?: string[]
  suggested_examples?: string[]
}

export async function askQuestion(question: string) {
  return apiJson<AskResult>('/ask', {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}

export type MapSuggestResult = {
  ok: boolean
  mapping?: Record<string, string>
  candidates?: Record<string, Array<{ std_field: string; score: number; source?: string }>>
  unmapped_columns?: string[]
  illegal_columns?: string[]
  hint?: string
  model_state?: string
  model_invoked?: boolean
  latency_ms?: number
  error?: string | null
}

export async function mapSuggest(headers: string[]) {
  return apiJson<MapSuggestResult>('/govern/map-suggest', {
    method: 'POST',
    body: JSON.stringify({ headers }),
  })
}

export async function mapConfirm(mapping: Record<string, string>, note = '', businessDomain = 'default') {
  return apiJson<{ ok: boolean; saved: number; actor: string }>('/govern/map-confirm', {
    method: 'POST',
    body: JSON.stringify({ mapping, note, business_domain: businessDomain }),
  })
}

export type MapPendingItem = {
  pending_id: string
  file_id?: string | null
  sheet?: string | null
  header: string
  suggested_field?: string | null
  candidates: Array<{ std_field: string; score?: number }>
  reason: string
  status: string
  business_domain?: string
  created_at?: string
}

export async function listMapPending(opts?: {
  limit?: number
  offset?: number
  status?: string
  file_id?: string
}) {
  const q = new URLSearchParams()
  q.set('limit', String(opts?.limit ?? 50))
  q.set('offset', String(opts?.offset ?? 0))
  q.set('status', opts?.status ?? 'pending')
  if (opts?.file_id) q.set('file_id', opts.file_id)
  return apiJson<{ total: number; items: MapPendingItem[] }>(`/govern/map/pending?${q}`)
}

export async function enqueueMapHeaders(body: {
  headers?: string[]
  file_id?: string
  sheet?: string
  business_domain?: string
  from_file?: boolean
}) {
  return apiJson<{
    ok: boolean
    enqueued: number
    items?: unknown[]
    hint?: string
    sheets?: unknown[]
  }>('/govern/map/enqueue', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function confirmMapPending(body: {
  pending_id: string
  decision: 'accept' | 'amend' | 'ignore'
  std_field?: string
  note?: string
}) {
  return apiJson<{
    ok: boolean
    pending_id: string
    decision: string
    std_field: string
    status: string
  }>('/govern/map/pending/confirm', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export type GovernTodoSummary = {
  state?: 'no_data' | 'parsing' | 'blocked' | 'needs_standardization' | 'ready' | 'published' | string
  state_message?: string
  map_pending_count: number
  unit_pending_count?: number
  material_pending_count: number
  master_pending_count: number
  material_align_count: number
  flow_pending_count: number
  exception_pending_count: number
  ai_suggestion_pending_count: number
  rule_conflict_count: number
  correction_count: number
  release_blocker_count: number
  blocked_rows: number
  estimated_releasable_rows?: number
  file_count: number
  staging_count?: number
  release_count?: number
  total: number
  gate: { ready?: boolean; missing?: string[] }
  empty_reason?: string | null
  next_actions: Array<{ code: string; label: string; path: string }>
}

export type GovernTodoItem = {
  todo_id: string
  todo_type: string
  title: string
  status: string
  priority?: string
  affected_rows?: number
  source_file?: string | null
  source_sheet?: string | null
  suggestion?: string
  confidence?: number | null
  actions?: string[]
  requires_review?: boolean
  forms_rule?: boolean
  version?: number
  raw_ref?: Record<string, unknown>
  suggestion_source?: string
  suggestion_kind?: string
  source_label?: string
  kind_label?: string
  review_status?: string
  review_label?: string
}

export async function governTodoSummary() {
  return apiJson<GovernTodoSummary>('/govern/standardization/summary')
}

export async function governTodoList(opts?: {
  limit?: number
  offset?: number
  todo_type?: string
  sort?: string
}) {
  const q = new URLSearchParams()
  q.set('limit', String(opts?.limit ?? 50))
  q.set('offset', String(opts?.offset ?? 0))
  q.set('sort', opts?.sort ?? 'impact')
  if (opts?.todo_type) q.set('todo_type', opts.todo_type)
  return apiJson<{ total: number; limit: number; offset: number; items: GovernTodoItem[] }>(
    `/govern/todos?${q}`,
  )
}

export async function governTodoDecision(
  todoId: string,
  body: {
    decision: 'accept' | 'amend' | 'reject' | 'ignore'
    amended_value?: Record<string, unknown>
    note?: string
    expected_version?: number
    idempotency_key?: string
    dry_run?: boolean
  },
) {
  return apiJson<{
    ok: boolean
    dry_run?: boolean
    todo_id: string
    todo_type?: string
    decision?: string
    affected_rows?: number
    forms_rule?: boolean
    suggestion?: string
    warning?: string | null
    idempotent?: boolean
    result?: Record<string, unknown>
  }>(`/govern/todos/${encodeURIComponent(todoId)}/decision`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export type MasterPendingItem = {
  pending_id: string
  material_id?: string | null
  material_code?: string | null
  material_name?: string | null
  spec?: string | null
  unit?: string | null
  category?: string | null
  source_file?: string | null
  match_level?: string
  conflict_type?: string | null
  candidates: Array<{
    material_id?: string
    material_code?: string
    material_name?: string
    spec?: string
    why?: string
  }>
  status: string
  created_at?: string
}

export async function proposeMasterPending(limit = 500) {
  return apiJson<{
    ok: boolean
    scanned: number
    enqueued: number
    refreshed: number
    hint?: string
    actor?: string
  }>('/govern/master/propose', {
    method: 'POST',
    body: JSON.stringify({ limit }),
  })
}

export async function listMasterPending(opts?: {
  limit?: number
  offset?: number
  status?: string
}) {
  const q = new URLSearchParams()
  q.set('limit', String(opts?.limit ?? 50))
  q.set('offset', String(opts?.offset ?? 0))
  q.set('status', opts?.status ?? 'pending')
  return apiJson<{ total: number; items: MasterPendingItem[] }>(`/govern/master/pending?${q}`)
}

export async function confirmMasterPending(body: {
  pending_id: string
  decision: 'approve' | 'reject' | 'merge'
  note?: string
  merge_to_material_id?: string
}) {
  return apiJson<{
    ok: boolean
    pending_id: string
    decision: string
    status: string
    mutates_biz?: boolean
  }>('/govern/master/pending/confirm', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function listStdFields() {
  return apiJson<{ fields: string[]; aliases: Record<string, string[]> }>('/govern/std-fields')
}

export async function listRuleDict(limit = 50, offset = 0) {
  return apiJson<{
    total: number
    items: Array<{
      rule_id: number
      header: string
      std_field: string
      business_domain: string
      hits: number
      source?: string
      confirmed_by?: string
      created_at: string
      status?: string
      changed_by?: string
      updated_at?: string
      pending_map_hits?: number
      pending_blocked_hits?: number
    }>
  }>(`/assets/rule-dict?limit=${limit}&offset=${offset}`)
}

export type RuleDictPreview = {
  ok: boolean
  dry_run: boolean
  rule_id: number
  header: string
  std_field: string
  business_domain: string
  current_status: string
  next_status: string
  action: string
  affected_rows: number
  rebuild_needed: boolean
  warning: string
}

export async function ruleDictPreview(ruleId: number, action: 'enable' | 'disable' = 'enable') {
  return apiJson<RuleDictPreview>(`/assets/rule-dict/${ruleId}/preview`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
}

export async function ruleDictConfirm(
  ruleId: number,
  body: { action: 'enable' | 'disable'; note?: string; idempotency_key?: string },
) {
  return apiJson<RuleDictPreview & { idempotent?: boolean; idempotency_replay?: boolean }>(
    `/assets/rule-dict/${ruleId}/confirm`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export async function ruleDictConflicts() {
  return apiJson<{
    ok: boolean
    conflict_count: number
    conflicts: Array<{
      header: string
      business_domain: string
      fields: string[]
      rule_ids: number[]
      statuses: string[]
    }>
  }>('/assets/rule-dict/conflicts')
}

export type FlowPendingItem = {
  pending_id: string
  file_id?: string
  source_sheet?: string
  source_row?: number
  source_segment?: number
  flow_type?: string
  text_raw: string
  text_norm?: string
  parse_level?: string
  suggested?: Record<string, unknown>
  suggested_json?: string
  status: string
  conflict?: number
  llm_state?: string
  llm_role?: string
  llm_error?: string
  created_at?: string
  updated_at?: string
}

export async function listFlowPending(opts?: {
  limit?: number
  offset?: number
  status?: string
  parse_level?: string
}) {
  const limit = opts?.limit ?? 50
  const offset = opts?.offset ?? 0
  const status = opts?.status ?? 'pending'
  const lvl = opts?.parse_level ? `&parse_level=${encodeURIComponent(opts.parse_level)}` : ''
  return apiJson<{
    total: number
    limit: number
    offset: number
    items: FlowPendingItem[]
  }>(`/govern/flow/pending?limit=${limit}&offset=${offset}&status=${encodeURIComponent(status)}${lvl}`)
}

export async function confirmFlowPending(body: {
  pending_id: string
  decision: 'accept' | 'amend' | 'ignore'
  corrected?: Record<string, unknown> | null
  note?: string
  overwrite?: boolean
}) {
  return apiJson<{
    ok: boolean
    pending_id: string
    decision?: string
    example_id?: string
    level?: string
    actor?: string
    code?: string
    conflict?: boolean
    overwrite?: boolean
  }>('/govern/flow/confirm', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function suggestFlowPending(body?: {
  pending_id?: string
  limit?: number
  force_role?: 'fast' | 'big'
}) {
  return apiJson<Record<string, unknown>>('/govern/flow/suggest', {
    method: 'POST',
    body: JSON.stringify(body || { limit: 5 }),
  })
}

export async function flowStats() {
  return apiJson<{
    published_by_level: Record<string, number>
    published_total: number
    l1_ratio: number | null
    pending: number
    pending_by_level?: Record<string, number>
    by_source_file?: Record<string, Record<string, number>>
    by_source_sheet?: Array<Record<string, unknown>>
  }>('/govern/flow/stats')
}

export type FlowReconcileItem = {
  material_id?: string
  stock_qty?: number
  opening_qty?: number
  expected_net?: number
  flow_net?: number
  gap?: number
  source_file?: string
  gap_class?: string
}

export async function flowReconcile() {
  return apiJson<{
    total: number
    threshold: number
    formula?: string
    opening_mode?: string
    opening_default?: number
    opening_populated_rows?: number
    material_id_overlap?: number
    by_class?: Record<string, number>
    note?: string
    items: FlowReconcileItem[]
  }>('/govern/flow/reconcile')
}

/** Explicit rewrite of flow_reconcile_gap (requires ops token). */
export async function flowReconcilePersist() {
  return apiJson<{
    total: number
    threshold: number
    formula?: string
    opening_mode?: string
    opening_default?: number
    opening_populated_rows?: number
    material_id_overlap?: number
    by_class?: Record<string, number>
    note?: string
    items: FlowReconcileItem[]
    persisted?: boolean
    actor?: string
  }>('/govern/flow/reconcile', { method: 'POST', body: '{}' })
}

/** Seed opening_qty=stock_qty for inv-only materials (ops / writer). */
export async function flowOpeningSeed(dryRun = false) {
  return apiJson<{
    dry_run: boolean
    updated?: number
    would_update?: number
    policy?: string
    actor?: string
    sample?: Array<Record<string, unknown>>
  }>('/govern/flow/opening/seed', {
    method: 'POST',
    body: JSON.stringify({ dry_run: dryRun }),
  })
}

export async function listFlowExamples(limit = 50, offset = 0) {
  return apiJson<{
    total: number
    items: Array<{
      example_id: string
      text_norm: string
      flow?: unknown[]
      level?: string
      hits?: number
      confirmed_by?: string
      updated_at?: string
    }>
  }>(`/assets/flow-examples?limit=${limit}&offset=${offset}`)
}

export async function listAssetHistory(opts?: {
  limit?: number
  offset?: number
  source?: string
}) {
  const limit = opts?.limit ?? 50
  const offset = opts?.offset ?? 0
  const q = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (opts?.source) q.set('source', opts.source)
  return apiJson<{
    total: number
    limit: number
    offset: number
    items: Array<Record<string, unknown>>
  }>(`/assets/history?${q}`)
}

export async function listAssetFewshot(limit = 50, offset = 0) {
  return apiJson<{
    total: number
    limit: number
    offset: number
    items: Array<Record<string, unknown>>
    note?: string
  }>(`/assets/fewshot?limit=${limit}&offset=${offset}`)
}

export type MetricItem = {
  metric_id: string
  metric_name: string
  aliases?: string[]
  unit?: string
  definition?: string
  definition_sql: string
  source_tables?: string
  status: string
  version: number
  engine?: string
  metric_group?: string
  data_check_sql?: string | null
  confirmed_by?: string
  updated_at?: string
}

export async function listMetrics(status?: string) {
  const q = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiJson<{ total: number; items: MetricItem[] }>(`/metrics${q}`)
}

export async function getMetric(metricId: string) {
  return apiJson<MetricItem>(`/metrics/${encodeURIComponent(metricId)}`)
}

export async function evaluateMetric(metricId: string) {
  return apiJson<{
    metric_id: string
    status: string
    version: number
    value: number | null
    unit?: string
    engine?: string
    active: boolean
    data_status?: string
    note?: string | null
    snapshot_written?: boolean
  }>(`/metrics/${encodeURIComponent(metricId)}/evaluate`, { method: 'POST' })
}

export async function checkMetricConflicts() {
  return apiJson<{
    ok: boolean
    conflict_count: number
    conflicts: Array<{ alias: string; metric_ids: string[] }>
    hint?: string
  }>('/metrics/check', { method: 'POST' })
}

export async function listMetricSnapshots(metricId: string, limit = 20) {
  return apiJson<{
    metric_id: string
    total: number
    items: Array<{ snapshot_id: number; value: number | null; unit?: string; evaluated_at: string }>
  }>(`/metrics/${encodeURIComponent(metricId)}/snapshots?limit=${limit}`)
}

export async function getQualityStats(fileId: string) {
  return apiJson<{
    file_id: string
    clean_rows: number
    blocked_rows: number
    block_rate: number
    detail_count: number
    by_reason_code: Record<string, number>
  }>(`/stats/quality/${fileId}`)
}

export async function listQualityBlocked(fileId: string, opts?: { limit?: number; offset?: number }) {
  const q = new URLSearchParams()
  q.set('limit', String(opts?.limit ?? 50))
  q.set('offset', String(opts?.offset ?? 0))
  return apiJson<{
    total: number
    items: Array<{
      block_id: string
      source_row?: number
      header?: string
      reason_code: string
      reason_detail?: string
      raw_value?: string
    }>
  }>(`/stats/quality/${fileId}/blocked?${q}`)
}

export async function releaseDiff(release_a: string, release_b: string) {
  return apiJson<{
    ok: boolean
    counts: Record<string, number>
    added: unknown[]
    removed: unknown[]
    changed: unknown[]
  }>('/govern/release/diff', {
    method: 'POST',
    body: JSON.stringify({ release_a, release_b }),
  })
}

export async function releaseSupersede(newer: string, older: string) {
  return apiJson<{ ok: boolean }>('/govern/release/supersede', {
    method: 'POST',
    body: JSON.stringify({ newer_release_id: newer, older_release_id: older }),
  })
}

export async function proposeRuleLearn(opts?: { limit?: number; min_count?: number }) {
  return apiJson<{
    ok: boolean
    scanned_groups: number
    created: number
    items: unknown[]
  }>('/govern/rule-learn/propose', {
    method: 'POST',
    body: JSON.stringify({
      limit: opts?.limit ?? 50,
      min_count: opts?.min_count ?? 2,
    }),
  })
}

export async function listRuleLearnCandidates(limit = 50) {
  return apiJson<{
    total: number
    items: Array<{
      id: number
      decision: string
      proposal?: Record<string, unknown>
      note?: string
      created_at?: string
    }>
  }>(`/govern/rule-learn/candidates?limit=${limit}`)
}

export async function confirmRuleLearn(
  confirmId: number,
  body: { decision: string; std_field?: string; dry_run?: boolean },
) {
  return apiJson<{
    ok: boolean
    dry_run?: boolean
    affected_rows?: number
    will_write?: string | null
    warning?: string
    decision?: string
    applied?: Record<string, unknown> | null
  }>(`/govern/rule-learn/${confirmId}/confirm`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function listCorrections(status?: string) {
  const q = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiJson<{ total: number; items: Array<Record<string, unknown>> }>(
    `/govern/corrections${q}`,
  )
}

export async function proposeCorrection(body: {
  release_id: string
  row_key: string
  field: string
  value_new?: string | null
  reason?: string
}) {
  return apiJson<{ ok: boolean; correction_id: string }>('/govern/corrections', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function decideCorrection(correctionId: string, action: 'apply' | 'decline') {
  return apiJson<{ ok: boolean; new_release_id?: string }>(
    `/govern/corrections/${encodeURIComponent(correctionId)}/decide`,
    { method: 'POST', body: JSON.stringify({ action }) },
  )
}

export type ReportItem = {
  report_id: string
  name: string
  query_sql: string
  cron_expr?: string | null
  params_json?: string | null
}

export async function listReports() {
  return apiJson<{ total: number; items: ReportItem[] }>('/reports')
}

export async function createReport(body: { name: string; query_sql: string; report_id?: string }) {
  return apiJson<{ ok: boolean; report_id: string }>('/reports', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function runReport(reportId: string, params?: Record<string, unknown>) {
  const hasParams = params && Object.keys(params).length > 0
  return apiJson<{
    ok: boolean
    run_id: string
    row_count: number
    artifact_path?: string
    data_scope?: string
    formal_publish?: boolean
    note?: string
    source_release_ids?: string[]
    metric_versions?: Array<{ metric_id: string; version?: number | string }>
  }>(`/reports/${encodeURIComponent(reportId)}/run`, {
    method: 'POST',
    body: hasParams ? JSON.stringify({ params }) : undefined,
  })
}

export async function upsertMetric(body: {
  metric_id: string
  metric_name: string
  definition_sql: string
  aliases?: string[]
  unit?: string
  definition?: string
  source_tables?: string
  engine?: string
  status?: string
}) {
  return apiJson<MetricItem & { actor?: string }>('/metrics', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function metricsFixtures() {
  return apiJson<{
    ok: boolean
    passed: number
    total: number
    items: Array<{ metric_id: string; ok: boolean; expect: unknown; got: unknown }>
  }>('/metrics/fixtures')
}

export async function flowGate() {
  return apiJson<{
    ready: boolean
    checks: Record<string, boolean>
    missing: string[]
    fixtures?: { ok: boolean; passed: number; total: number }
    stats?: Record<string, unknown>
  }>('/govern/flow/gate')
}

export async function activateFlowMetrics(metricIds?: string[]) {
  return apiJson<{
    ok: boolean
    activated: Array<{ metric_id: string; version: number; idempotent?: boolean }>
    gate?: Record<string, unknown>
  }>('/metrics/flow/activate', {
    method: 'POST',
    body: JSON.stringify({ metric_ids: metricIds ?? null }),
  })
}

export async function modelsStatus() {
  return apiJson<{
    stage: number
    big: {
      ok: boolean
      configured_model?: string
      latency_ms?: number
      error?: string
      endpoint?: string
    }
    embed: {
      ok: boolean
      configured_model?: string
      lexical_fallback?: boolean
      latency_ms?: number
      error?: string
      endpoint?: string
    }
    fast: {
      ok: boolean
      configured_model?: string
      note?: string
      error?: string
      endpoint?: string
    }
  }>('/models/status')
}

export async function flowAudit(limit = 200) {
  return apiJson<{
    ok: boolean
    total_rows: number
    suspicious_count: number
    by_release: Record<string, unknown>
    suspicious: Array<{
      flow_id?: string
      reasons?: string[]
      quantity?: number
      remark?: string
      source_file?: string
      parse_level?: string
    }>
  }>(`/govern/flow/audit?limit=${limit}`)
}

export async function flowRebuild(body: { release_id: string; revoke_only?: boolean }) {
  return apiJson<{ ok: boolean; release_id?: string; rows?: number; mode?: string }>(
    '/govern/flow/rebuild',
    {
      method: 'POST',
      body: JSON.stringify({
        release_id: body.release_id,
        revoke_only: body.revoke_only ?? false,
      }),
    },
  )
}

export async function listLineageReleases(opts?: {
  limit?: number
  offset?: number
  domain?: string
}) {
  const q = new URLSearchParams()
  q.set('limit', String(opts?.limit ?? 50))
  q.set('offset', String(opts?.offset ?? 0))
  if (opts?.domain) q.set('domain', opts.domain)
  return apiJson<{
    total: number
    items: Array<{
      release_id: string
      file_id: string
      target_domain?: string
      clean_rows?: number
      status?: string
      released_at?: string
      released_by?: string
    }>
  }>(`/govern/lineage/releases?${q}`)
}

export async function lineageRebuild(body: { release_id: string; revoke_only?: boolean }) {
  return apiJson<{
    ok: boolean
    release_id?: string
    target_domain?: string
    rows?: number
    deleted_rows?: number
    rebuilt?: boolean
  }>('/govern/lineage/rebuild', {
    method: 'POST',
    body: JSON.stringify({
      release_id: body.release_id,
      revoke_only: body.revoke_only ?? false,
    }),
  })
}

export async function createBackup() {
  return apiJson<{
    ok?: boolean
    path?: string
    tag?: string
    files?: string[]
    created_at?: string
    backup_id?: string
    [k: string]: unknown
  }>('/ops/backup', { method: 'POST' })
}

export async function listBackups(limit = 20) {
  return apiJson<{
    total: number
    items: Array<{ backup_id: string; path: string; created_at?: string; files?: number | null }>
    backup_root?: string
  }>(`/ops/backups?limit=${limit}`)
}

export async function getRestoreDrill() {
  return apiJson<{
    recorded: boolean
    message: string
    record: null | {
      recorded_at?: string
      actor?: string
      note?: string
      result?: string
      backup_id?: string | null
      disclaimer?: string
    }
  }>('/ops/restore-drill')
}

export async function recordRestoreDrill(body?: {
  note?: string
  result?: string
  backup_id?: string
}) {
  const q = new URLSearchParams()
  if (body?.note) q.set('note', body.note)
  if (body?.result) q.set('result', body.result)
  if (body?.backup_id) q.set('backup_id', body.backup_id)
  const qs = q.toString()
  return apiJson<{ ok: boolean; record: Record<string, unknown> }>(
    `/ops/restore-drill${qs ? `?${qs}` : ''}`,
    { method: 'POST' },
  )
}

export type StatsOverview = {
  tables: Record<string, number>
  dim_material: number
  business?: {
    stock_qty_total?: number | null
    stock_value_total?: number | null
    quota_fill_ratio?: number | null
    over_quota_count?: number | null
    stale_count?: number | null
    demand_qty_total?: number | null
    asset_count?: number | null
    flow_in_qty?: number | null
    flow_out_qty?: number | null
    top_by_category?: Array<{ name: string; value: number }>
    top_by_location?: Array<{ name: string; value: number }>
    top_by_unit?: Array<{ name: string; value: number }>
  }
  quality?: {
    clean_rows: number
    blocked_rows: number
  }
  estimated_releasable_rows?: number
  todos?: {
    map_pending: number
    master_pending: number
    flow_pending: number
    material_align: number
    ai_suggestion_pending?: number
    total: number
  }
  next_action?: {
    code: string
    label: string
    path: string
    reason: string
  }
  flow: {
    published_total?: number
    published_by_level?: Record<string, number>
    l1_ratio?: number | null
    pending?: number
  }
  gate: { ready?: boolean; missing?: string[] }
  recent_files: Array<{
    file_id: string
    filename: string
    format?: string
    rows?: number
    sheets?: number
    status?: string
    created_at?: string
  }>
  metrics_active: Array<{
    metric_id: string
    metric_name?: string
    status?: string
    unit?: string
    version?: number
    metric_group?: string
  }>
  models: {
    stage: number
    big: { ok: boolean; configured_model?: string }
    fast: { ok: boolean; configured_model?: string; note?: string }
    embed: { ok: boolean; configured_model?: string }
  }
}

export async function statsOverview(recentLimit = 5) {
  return apiJson<StatsOverview>(`/stats/overview?recent_limit=${recentLimit}`)
}

/** 分析面（question/03 UI-1/UI-2）—— 只读聚合 */
export type FlowMonthly = {
  items: Array<{ month: string; flow_type: string; qty: number }>
  months: string[]
  in: number[]
  out: number[]
}

export async function flowMonthly() {
  return apiJson<FlowMonthly>('/analytics/flow-monthly')
}

export type FlowTopItem = {
  material_id: string
  asset_code?: string
  material_name?: string
  spec?: string
  display_name?: string
  flow_type: string
  n: number
  qty: number
}

export async function flowTop(limit = 10) {
  return apiJson<{ limit: number; items: FlowTopItem[] }>(`/analytics/flow-top?limit=${limit}`)
}

export type FlowLevel = {
  total: number
  items: Array<{ name: string; value: number; ratio: number | null }>
}

export async function flowLevel() {
  return apiJson<FlowLevel>('/analytics/flow-level')
}

export async function opsTasksSummary() {
  return apiJson<{
    pending: number
    processing: number
    done: number
    failed: number
    by_status: Record<string, number>
  }>('/ops/tasks')
}

export async function opsAlerts() {
  return apiJson<{ active: Array<{ level: string; rule: string; message: string; ts?: string }>; count: number }>(
    '/ops/alerts',
  )
}

export async function opsLlmCost(days = 7) {
  return apiJson<{
    days: number
    total_calls: number
    ok_calls: number
    failed_calls: number
    by_day: Array<{ day: string; calls: number; ok_calls: number }>
  }>(`/ops/llm-cost?days=${days}`)
}

export async function auditTimeline(params?: {
  limit?: number
  offset?: number
  source?: string
  actor?: string
  release_id?: string
  file_id?: string
  q?: string
}) {
  const q = new URLSearchParams()
  if (params?.limit) q.set('limit', String(params.limit))
  if (params?.offset) q.set('offset', String(params.offset))
  if (params?.source) q.set('source', params.source)
  if (params?.actor) q.set('actor', params.actor)
  if (params?.release_id) q.set('release_id', params.release_id)
  if (params?.file_id) q.set('file_id', params.file_id)
  if (params?.q) q.set('q', params.q)
  const qs = q.toString()
  return apiJson<{
    items: Array<{
      ts: string
      kind: string
      source: string
      action: string
      actor: string
      detail: string
      release_id?: string | null
      file_id?: string | null
    }>
    total: number
  }>(`/audit/timeline${qs ? `?${qs}` : ''}`)
}

export async function modelActivate(role: 'big' | 'fast' | 'embed') {
  return apiJson<{ ok: boolean; role: string; note?: string }>(`/models/${role}/activate`, { method: 'POST' })
}

export async function modelRestart(role: 'big' | 'fast' | 'embed') {
  return apiJson<{ ok: boolean; role: string; note?: string }>(`/models/${role}/restart`, { method: 'POST' })
}

/** 只读导出标准表 CSV 的下载 URL（后端 /export/table/{table}）。 */
export function tableExportUrl(table: string, limit = 50000, mode: 'business' | 'raw' = 'business') {
  const q = new URLSearchParams({ limit: String(limit), mode })
  return `${API_BASE}/export/table/${encodeURIComponent(table)}?${q}`
}

/** 报表运行产物下载 URL（后端 /reports/{run_id}/file）。 */
export function reportRunFileUrl(runId: string) {
  return `${API_BASE}/reports/${encodeURIComponent(runId)}/file`
}

export type BrowseResult = {
  table: string
  mode?: string
  data_scope?: string
  columns_zh: string[]
  rows: Record<string, unknown>[]
  total: number
  limit: number
  offset: number
}

/** 台账在线分页浏览（后端 /api/v1/browse/{table}，LB-1）。 */
export async function browseTable(table: string, limit = 100, offset = 0) {
  return apiJson<BrowseResult>(`/browse/${encodeURIComponent(table)}?limit=${limit}&offset=${offset}`)
}

export type RowEvidence = {
  ok: boolean
  release_id: string
  row_key: string
  domain: string
  source_file: string
  source_sheet?: string | null
  source_row?: number | string | null
  source_file_id: string
  release: Record<string, unknown>
  staging: Record<string, unknown>
  task: Record<string, unknown> | null
  material: Record<string, unknown>
  mapping: Array<{ std_field: string; source_header: string }>
  rule_hits: Array<Record<string, unknown>>
  confirms: Array<Record<string, unknown>>
  audit: Array<Record<string, unknown>>
  compare: Array<{
    field: string
    field_zh: string
    source_header?: string | null
    raw_value?: unknown
    clean_value?: unknown
    changed?: boolean | null
  }>
  note: string
}

/** 行级证据：发布结果行 → 来源原始值 + 规整值 + 血缘链条（optv1/05 Q11）。 */
export async function getRowEvidence(releaseId: string, rowKey: string) {
  return apiJson<RowEvidence>(
    `/govern/lineage/row?release_id=${encodeURIComponent(releaseId)}&row_key=${encodeURIComponent(rowKey)}`,
  )
}

/** 触发浏览器下载 Blob。 */
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** 将查询结果（columns + rows）客户端导出为 CSV（csv-export-harden T1.3/T2.4/T3.2）。 */
export function downloadCsv(
  rows: Record<string, unknown>[],
  columns: string[],
  filename: string,
  note?: string,
) {
  const escape = (v: unknown) => {
    if (v == null) return ''
    const s = String(v)
    const quoted = /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
    // 公式注入防护：危险前缀（= + - @ 等）前置 `'`，Excel 按文本解析
    return /^[=+\-@\t\r]/.test(s) ? `'${quoted}` : quoted
  }
  const lines = [
    columns.join(','),
    ...rows.map((r) => columns.map((c) => escape(r[c])).join(',')),
  ]
  if (note) lines.push(`# ${note}`)
  // UTF-8 BOM：Excel 直接打开中文不乱码
  const content = '\uFEFF' + lines.join('\n')
  downloadBlob(new Blob([content], { type: 'text/csv;charset=utf-8' }), filename)
}
