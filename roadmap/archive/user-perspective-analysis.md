# 用户视角页面与功能分析 · 问题与解决方案

> 版本：v0.1（2026-08-10）· 状态：待评审
> 视角：**使用者视角**（业务查数者 / 数据接入员 / 治理员 / 指标管理员 / Ops / 模型运维）
> 范围：前端 11 个导航页 + 1 个动态路由页（`/stage/:fileId`），对应 `frontend/src/pages/*.vue`
> 关联：[examples-plan.md](file:///workspace/2026-07/smart-material-system/roadmap/examples-plan.md)、[ledger-export-plan.md](file:///workspace/2026-07/smart-material-system/roadmap/ledger-export-plan.md)、[field-zh-doc.md](file:///workspace/2026-07/smart-material-system/roadmap/field-zh-doc.md)

---

## 0. 结论摘要

系统以"**可信流水线 + 人工确认门**"为核心，11 页 SPA 覆盖"业务查数 / 数据接入 / 治理裁决 / 指标字典 / 报表 / 自学习资产 / 模型 / 运维 / 设置"全链路。写操作三件套（`version` + `expected_status` + `Idempotency-Key`，冲突 409）与"AI 提案 + 人工确认"范式已落地；用户可感知的**口径克制**（跨单位不加总、勾稽不宣称轧平、`FLOW_*` 双门禁、报表不写业务表）是显著优点。

但从使用者视角看，仍存在 **5 类共 12 项**可改进点：

1. **能力未闭环**：模型管理页"设为活跃/受控重启"按钮 disabled，LLM sheet-profile 未上。
2. **新用户上手难**：无端到端演示、AskView 示例仅 2 条、GovernView 1500+ 行信息密度高。
3. **凭证与权限薄弱**：Ops Token 仅存 localStorage，无角色分级，任何人持 Token 可做任何写操作。
4. **可观测性不足**：SSE/poll 降级不可见、无全局审计视图、可疑行只在 Ops 页静态展示。
5. **移动/弱网体验**：部分页面无响应式，无骨架屏/重试兜底。

**结论**：按本文 U1–U5 修改后，系统从"功能完备"走向"好用、可审计、可授权"，且不破坏既有可信流水线与口径克制。

---

## 1. 页面与功能现状（用户视角）

| # | 页面 | 路由 | 面向角色 | 核心能力 | 用户感知关键点 |
|---|---|---|---|---|---|
| P1 | 总览 | `/` | 所有人 | 业务快照 9 卡 + Top 排行 + 迷你趋势 + 标准表导出 + 种子报表 + 流水门禁 + 指标试跑 + 模型 Stage + 最近文件 | 开屏即"业务好不好、流水通不通、模型在不在" |
| P2 | 自然语言问答 | `/ask` | 业务查数者 | 指标 aliases 命中→definition_sql（不调 LLM）；未命中→Text2SQL+AST；自动图表 + CSV 导出 + 会话历史 | 模板优先、LLM 兜底，秒回与成本可控 |
| P3 | 接入上传 | `/intake` | 接入员 | 拖拽上传 xlsx/csv/json，202+task_id+SSE，URL 可恢复 | 异步可恢复，断网刷新不丢任务 |
| P4 | 治理中心 | `/govern` | 治理员 | 6 Tab：表头映射 / 规则学习 / 主数据待审 / 流水解析 / 勾稽差异 / 流水分析 | 所有"机器不确定"汇聚到一页人工裁决 |
| P5 | 指标字典 | `/metrics` | 指标管理员 | FLOW_* 激活门禁 + 列表 + 试跑 + 趋势(UI-3) + 编辑(version+1) | 口径集中管理，FLOW_* 须双门禁 |
| P6 | 报表快照 | `/reports` | 报表消费者 | 参数化(UI-4) `${name}` 占位符，AST 校验，parquet+csv 落盘，不写业务表 | 只读可重复，结果可追溯 |
| P7 | 自学习资产 | `/learning` | 治理员/模型 | 只读 4 Tab：rule_dict / flow_example / govern_confirm / sql_fewshot | AI 行为可解释、可审计 |
| P8 | 模型管理 | `/models` | 模型运维 | 只读探测卡片（big/fast/embed）+ 拓扑说明 | 看清部署状态与降级策略 |
| P9 | 运维面板 | `/ops` | Ops（需 Token） | 服务就绪 + 模型探测 + 流水统计/审计 + release 重建/吊销 + 修正提案 + 备份 | 发布版本/血缘/备份最后一道闸 |
| P10 | 文件与任务 | `/files` | 接入员/运维 | 文件台账（file_id/格式/证据行/状态/时间） | 跨任务回溯某文件到哪一步 |
| P11 | Staging 确认门 | `/stage/:fileId` | Ops 确认者 | Step1 画像 + Step3 质量预检 + Blocked 明细 + clean 预览 + Step4 接入建议 + Dry-run + 一键分析 + Ops 确认发布 | 单文件从画像到发布闭环在一页 |
| P12 | 设置 | `/settings` | 所有人 | Ops Token 输入（localStorage） | 写操作统一凭证入口 |

---

## 2. 问题清单（按用户感知优先级）

| ID | 类别 | 问题 | 现状证据 | 影响 |
|---|---|---|---|---|
| U-1 | 能力未闭环 | 模型管理页"设为活跃""受控重启"按钮 disabled | [ModelsView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/ModelsView.vue#L48-L49) `disabled` 硬编码 | 用户看到按钮却点不动，需 SSH/脚本切模型，体验断层 |
| U-2 | 能力未闭环 | LLM sheet-profile（`needs_llm` sheets）未上 | [README.md](file:///workspace/2026-07/smart-material-system/README.md#L93) "Stage B+" | 复杂多 sheet 异构文件 Step1 画像不全，治理员需手工补 |
| U-3 | 新用户上手难 | AskView 示例问题仅 2 条（行数 / 按库位） | [AskView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/AskView.vue#L23-L24) | 业务用户看不到真实业务问题样例（详见 examples-plan E-2） |
| U-4 | 新用户上手难 | 无端到端业务演示文档 | [README.md](file:///workspace/2026-07/smart-material-system/README.md) 全为启动/smoke/API 清单 | 新用户无"5 分钟上手"路径（详见 examples-plan T4） |
| U-5 | 新用户上手难 | GovernView 1500+ 行、6 Tab 信息密度高 | [GovernView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/GovernView.vue) | 新治理员学习曲线陡，易在错误 Tab 操作 |
| U-6 | 凭证与权限 | Ops Token 仅存 localStorage，单机模式 | [SettingsView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/SettingsView.vue#L13-L16) 自述"勿长期写入不可信共享环境" | 多人/生产环境 Token 易泄露，无过期/轮换 |
| U-7 | 凭证与权限 | 无角色分级，任何持 Token 者可做任何写操作 | 路由层仅 `OPS_TOKEN` 校验（[auth.py](file:///workspace/2026-07/smart-material-system/app/api/auth.py)） | 接入员误触 release 吊销/备份等高危操作无拦截 |
| U-8 | 可观测性 | SSE/poll 降级对用户不可见 | [IntakeView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/IntakeView.vue#L90-L98) 仅 `channel` 列标 `sse/poll` | SSE 失败回退 poll 时用户不知为何变慢，无重试提示 |
| U-9 | 可观测性 | 无全局审计视图（govern_confirm 仅 `/learning` 一 Tab 且只读） | [AssetsView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/AssetsView.vue#L86-L119) | 谁在何时改了什么需翻表，难追责 |
| U-10 | 可观测性 | 流水可疑行只在 Ops 页静态展示，无订阅/告警 | [OpsView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue#L80-L95) | 审计跑完才看，无新可疑行主动通知 |
| U-11 | 移动/弱网 | 部分页面无响应式（GovernView/OpsView/StageView 无 `@media`） | 对比 [HomeView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L426-L428) 有 `@media (max-width: 720px)` | 窄屏/平板操作困难 |
| U-12 | 移动/弱网 | 无骨架屏/统一重试兜底，失败仅 `ElMessage.error` | 各页 `catch` 块普遍仅 `formatApiError(e)` | 弱网下白屏或突兀报错，无重试入口 |

---

## 3. 解决方案与任务拆解

### U1 · 能力闭环（模型启停 / LLM sheet-profile）

| 任务 | 落点 | 验收 |
|---|---|---|
| U1.1 后端补 `POST /api/v1/models/{role}/activate` 与 `/restart`（受控，记 write_audit） | `app/api/routes.py` + `app/services/model_ctl.py`（新增） | curl 切换活跃模型后 `/models/status` 反映；非活跃角色回退 |
| U1.2 ModelsView 解除 disabled，加确认弹窗（"切换将中断当前任务，确认？"） | [ModelsView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/ModelsView.vue#L48-L49) | 点击弹确认后调 API，成功后自动 `load()` |
| U1.3 LLM sheet-profile：`needs_llm` sheets 走 big 模型生成画像并入 evidence | `app/services/profile_step1.py` 扩展 + `app/workers/intake_worker.py` | 多 sheet 异构样例 Step1 画像完整（含 needs_llm sheets） |

### U2 · 新用户上手（示例 / 演示 / 治理引导）

> 与 [examples-plan.md](file:///workspace/2026-07/smart-material-system/roadmap/examples-plan.md) 对齐，此处仅列本方案独有项。

| 任务 | 落点 | 验收 |
|---|---|---|
| U2.1 GovernView 顶部加"治理向导"入口：首次进入弹 4 步引导（映射→规则→主数据→流水→勾稽），可跳过 | [GovernView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/GovernView.vue#L2-L10) | 新会话首次进入弹引导；localStorage 记 `govern_guide_seen` |
| U2.2 每个 Tab 加"该 Tab 处理什么 / 不处理什么"折叠说明 | GovernView 各 Tab 顶部 | 6 Tab 均有 ≤3 行职责说明 |
| U2.3 StageView 加"步骤进度条"（Step1→3→4→Staging→发布），当前步高亮 | [StageView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/StageView.vue#L202-L211) | 用户一眼看到卡在哪步 |

### U3 · 凭证与权限

| 任务 | 落点 | 验收 |
|---|---|---|
| U3.1 Token 加过期/轮换：后端 `OPS_TOKEN` 支持 `exp` claim 或定时轮换 env，前端 401 时弹"重新登录" | `app/api/auth.py` + [client.ts](file:///workspace/2026-07/smart-material-system/frontend/src/api/client.ts) 401 拦截 | Token 过期后写操作返 401，前端引导回 `/settings` |
| U3.2 角色分级：`ops` / `govern` / `intake` / `viewer` 四角色，路由按角色白名单 | `app/api/auth.py` + `app/api/routes.py` 各路由注解 | 接入员调 `/release/revoke` 返 403；viewer 只读 |
| U3.3 SettingsView 增"当前角色"显示 + 角色不可见操作灰显 | [SettingsView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/SettingsView.vue) | 用户清楚自己能做什么 |

### U4 · 可观测性

| 任务 | 落点 | 验收 |
|---|---|---|
| U4.1 IntakeView SSE 失败时 toast"实时通道中断，已回退轮询"+ 重试按钮 | [IntakeView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/IntakeView.vue#L85-L108) | SSE error 后用户看到降级提示并可手动重连 |
| U4.2 新增 `/audit` 页：govern_confirm / write_audit / release 历史 / correction 全量时间线，可按 actor/source/时间筛选 | 新增 `frontend/src/pages/AuditView.vue` + `GET /api/v1/audit/timeline` | 任意写操作 30s 内可在该页查到 |
| U4.3 流水可疑行订阅：Ops 页"跑审计"后可"订阅"，新可疑行入站时 SSE 推送 | `app/api/events.py` + OpsView | 新可疑行产生时 Ops 收到通知 |

### U5 · 移动/弱网

| 任务 | 落点 | 验收 |
|---|---|---|
| U5.1 GovernView/OpsView/StageView 加 `@media (max-width: 720px)`：表格横向滚动、卡片单列、操作按钮换行 | 上述三页 `<style>` | 窄屏无横向溢出 |
| U5.2 统一 `PageSkeleton` 组件：首屏 loading 用骨架屏替代 `v-loading` 蒙层 | 新增 `frontend/src/components/PageSkeleton.vue` + 各页替换 | 首屏无白屏闪烁 |
| U5.3 统一 `RetryBanner`：请求失败时顶部展示"加载失败 [重试]"，替代一次性 `ElMessage` | 新增 `frontend/src/components/RetryBanner.vue` + 各页 catch 替换 | 失败后用户可一键重试 |

---

## 4. 用户角色与典型旅程（现状）

| 角色 | 典型路径 | 当前痛点 |
|---|---|---|
| 业务查数者 | `/` 看板 → `/ask` 提问 → 导出 CSV | 示例少（U-3），弱网失败无重试（U-12） |
| 数据接入员 | `/intake` 上传 → SSE 等进度 → `/stage/:id` 一键分析 → 找 Ops 确认 | SSE 降级不可见（U-8） |
| 数据治理员 | `/govern` 处理 4 队列 → `/learning` 复核 | 信息密度高（U-5） |
| 指标管理员 | `/metrics` 维护、试跑、看趋势、激活 FLOW_* | 无 |
| Ops 运维 | `/ops` 审计/重建/备份；`/settings` 配 Token | Token 无过期（U-6），无审计视图（U-9） |
| 模型/平台 | `/models` 看探测、`/ops` 看模型快表 | 启停按钮 disabled（U-1） |

---

## 5. 与既有方案依赖

| 依赖 | 说明 |
|---|---|
| [examples-plan.md](file:///workspace/2026-07/smart-material-system/roadmap/examples-plan.md) | U-3/U-4 与其 E-2/T4 重叠，合并执行避免重复 |
| [ledger-export-plan.md](file:///workspace/2026-07/smart-material-system/roadmap/ledger-export-plan.md) | U-2 LLM sheet-profile 依赖 4 表台账字段落地后才有完整样例 |
| [field-zh-doc.md](file:///workspace/2026-07/smart-material-system/roadmap/field-zh-doc.md) | U2 引导文案与汉化口径对齐 |

**建议执行顺序**：U1.1/U1.2（模型启停，独立可做）→ U3（凭证权限，安全优先）→ U4（可观测性）→ U2（引导，依赖功能稳定）→ U5（移动弱网，体验打磨）。U1.3 与 ledger-export-plan 对齐节点后再做。

---

## 6. 验收总标准

1. 模型管理页"设为活跃/受控重启"可点且后端受控记录，LLM sheet-profile 在多 sheet 异构样例上画像完整；
2. GovernView 首次进入弹引导、6 Tab 有职责说明，StageView 步骤进度条可见；
3. Ops Token 支持过期/轮换，401 引导回设置页；四角色分级，越权写操作返 403；
4. `/audit` 全量时间线可按 actor/source/时间筛选；SSE 降级有 toast + 重试；可疑行可订阅 SSE 推送；
5. GovernView/OpsView/StageView 窄屏无溢出；PageSkeleton/RetryBanner 覆盖主要页面。

---

## 7. 决策点（ED-1~ED-3）

| ID | 决策点 | 候选 |
|---|---|---|
| ED-1 | 模型启停 API 是否限 ops 角色 | 仅 ops（推荐，安全）/ ops+govern |
| ED-2 | 审计时间线落库 vs 实时聚合 | 落库（推荐，可追溯）/ 实时聚合（轻但难追溯） |
| ED-3 | 角色分级落地节奏 | 一次性四角色 / 先 ops+viewer 两档再细化 |

---

*评审通过后按 U1→U3→U4→U2→U5 执行；与 examples-plan / ledger-export-plan 节点对齐。*
