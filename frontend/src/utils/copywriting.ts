/** 全站用户可见固定文案（HI-1：免责声明只引用此处）。 */
export const DATA_SCOPE_DISCLAIMER =
  '当前展示的是规整后可用的工作数据，不是领导签字发布的正式报表。'
/** 短版：用于导出 toast 等单行场景。 */
export const DATA_SCOPE_DISCLAIMER_SHORT = '内部参考，非正式报表。'
/** 问数页结果区：不再重复长 disclaimer，只用此短句（可选）。 */
export const ASK_RESULT_SCOPE = '基于当前可用数据'

/** 运行态等级用户可见标题（不暴露 runtime_level 技术名）。 */
export function runtimeLevelTitle(level: string): string {
  const map: Record<string, string> = {
    none: '系统未就绪',
    dev_ok: '基础功能可用，本地模型未启动',
    stage1_degraded: '智能能力受限',
    full: '系统完整可用',
  }
  return map[level] || '运行状态检查中'
}

/** 模型页操作说明：Web 按钮不直接启停进程。 */
export const MODEL_WEB_ACTION_HINT =
  '以下按钮仅向后端记录切换/重启请求并写审计，不会在本页直接启动或停止模型进程；真实启停请使用 scripts/models.sh。'
