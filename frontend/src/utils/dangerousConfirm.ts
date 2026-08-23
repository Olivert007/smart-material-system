/** Dangerous action confirm body (doc 19 §7.3). */
export function dangerousConfirmMessage(opts: {
  objectId: string
  action: string
  impact: string
  extra?: string
}): string {
  const lines = [
    `对象：${opts.objectId}`,
    `操作：${opts.action}`,
    `影响范围：${opts.impact}`,
  ]
  if (opts.extra) lines.push(opts.extra)
  lines.push('此操作不可自动撤销，请确认后继续。')
  return lines.join('\n')
}
