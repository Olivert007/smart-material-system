# 总览页与治理页 Review · 落实方案

> 版本：v0.1（2026-08-10）· 状态：待评审
> 视角：**页面职责边界与首屏成本**（总览页信息密度 / 治理页心智模型 / 勾稽差异可理解性）
> 范围：`frontend/src/pages/HomeView.vue`、`frontend/src/pages/GovernView.vue` 及其关联路由 / 后端 `stats_overview`
> 关联：[user-perspective-analysis.md](file:///workspace/2026-07/smart-material-system/roadmap/user-perspective-analysis.md)（U-5 治理信息密度）、[examples-plan.md](file:///workspace/2026-07/smart-material-system/roadmap/examples-plan.md)（T3.2 空态）、[docs/07 §3.1/§3.4](file:///workspace/2026-07/治理方案/07-界面层设计.md)、[docs/12 §6](file:///workspace/2026-07/治理方案/12-出入库流水解析.md)

---

## 0. 结论摘要

总览页与治理页功能完备，但存在 **3 类职责越界 / 心智模糊** 问题，影响首屏性能与一线理解成本：

1. **总览页职责越界**：`HomeView` 同时承担"业务快照（应保留）"+"指标试跑（属指标字典）"+"模型配置详情（属模型管理）"三重身份，首屏 `onMounted` 串行 `runBizEvals` 阻塞迷你趋势/报表加载，且与 `MetricsView` / `ModelsView` 功能重叠。
2. **治理页心智模糊**：`GovernView` 6 Tab 中"流水分析"为只读分析展示，与其余 5 个写操作确认 Tab 性质不同，且与 `ReportsView` 种子报表口径重复，模糊了"治理=人机协同写操作确认"的心智。
3. **勾稽差异可理解性不足**：`gap_class` 三类（`inv_only` / `flow_only` / `mismatch`）含义仅在 `reconcileClassHint` 一行纯文本展示，新人无法理解每类代表什么、应如何处理。

**结论**：按本文 HG-1 / HG-2 / HG-3 修改后，总览页首屏职责收敛到"业务一眼 + 数据量 + 门禁"，治理页收敛到"5 个写操作确认 Tab"，勾稽差异对一线可读可操作，且不破坏既有可信流水线与口径克制。

---

## 1. 现状证据（2026-08-10 实测）

### 1.1 总览页 `HomeView.vue` 区块盘点

| 区块 | 行号 | 性质 | 是否与它页重叠 |
|---|---|---|---|
| 业务快照 9 卡 + Top3 + 迷你趋势 | `HomeView.vue:11-51` | 业务一眼 | 否（应保留） |
| 6 表行数卡片 | `HomeView.vue:53-58` | 数据量 | 否（应保留，对齐 07 §3.1） |
| 标准表 CSV 导出 | `HomeView.vue:63-80` | 只读导出入口 | 否（应保留） |
| 定期报表入口 | `HomeView.vue:82-108` | 报表快捷入口 | 否（应保留） |
| 流水与门禁 tag | `HomeView.vue:110-134` | 门禁状态 | 否（应保留，`gate ready/blocked` 有语义价值） |
| **业务指标(active) 试跑表** | `HomeView.vue:139-159` | 指标试跑 | **是，与 `MetricsView` 重叠** |
| **模型 Stage 卡片** | `HomeView.vue:161-188` | 模型配置详情 | **是，与 `ModelsView` 重叠** |
| 最近文件 | `HomeView.vue:191-199` | 文件台账 | 否（应保留） |

### 1.2 重叠证据

- **指标试跑**：`MetricsView.vue:115` 已有逐行"试跑"按钮（`runEval`），`MetricsView.vue:116` 已有"趋势"按钮（`openTrend`）。`HomeView` 的 `runBizEvals`（`HomeView.vue:324-339`）是串行调 `evaluateMetric`，与 `MetricsView` 功能完全重叠。
- **模型配置**：`ModelsView.vue:30-52` 卡片已展示 `model` / `role` / `endpoint` / `cardState` / `tags`，`HomeView` 的 `el-descriptions`（big/fast/embed/frontend_dist）属其子集。
- **首屏阻塞**：`HomeView.vue:384-389` `onMounted` 中 `await runBizEvals()` 在 `loadSpark / loadSeedReports` 之前，指标多 + DuckDB 冷启动时拖慢首屏。

### 1.3 后端 `stats_overview.overview()` 成本

`app/services/query/stats_overview.py:184-233` 中 `overview()` 对 big/fast/embed 三端点 **顺序** `probe_endpoint`（`stats_overview.py:188-190`，未用 `gather`），首屏需等 3 次探测；而 `app/api/routers/ops.py:17-21` 的 `models_status` 已用 `asyncio.gather` 并发探测。总览页模型卡片若精简，可同步把 `overview()` 的探测改为并发或下沉到 `models_status` 复用。

### 1.4 治理页 `GovernView.vue` Tab 盘点

| Tab | name | 性质 | 是否写操作 |
|---|---|---|---|
| 表头映射 | `map` | embed 候选 → 人工确认回写 `rule_dict` | 是 |
| 规则学习 | `rulelearn` | 从 `staging_blocked` 聚合 → 确认回写 `rule_dict/value_rule` | 是 |
| 主数据待审 | `master` | L3 独立物料 → 批准/合并/拒绝经 writer 写 DuckDB | 是 |
| 流水解析 | `flow` | LLM 建议预填 → 人工确认回写 `flow_example` | 是 |
| 勾稽差异 | `reconcile` | 期初种子 / 重算落库 / 导出 | 是 |
| **流水分析** | `analytics` | 只读：月趋势 / Top / 级别占比 | **否** |

`GovernView.vue:3-10` 6 Tab 平铺，"流水分析"（`GovernView.vue:473-511`）调 `flowMonthly / flowTop / flowLevel` 只读渲染 ECharts，与 `ReportsView` 种子报表 `rpt_flow_monthly` / `rpt_flow_top_material` 口径一致（`GovernView.vue:480` 自述"口径与报表快照种子报表一致，可互验"）。

### 1.5 勾稽差异可理解性证据

`GovernView.vue:515-521` alert 标题"勾稽差异（允许非零）"，描述 `ΣIN−ΣOUT ≟ 库存−期初；缺期初按 0。不宣称账已轧平。` —— 公式清楚，但 `gap_class` 三类含义未在 UI 解释：

- `GovernView.vue:539` 表格"类别"列直接显示 `inv_only` / `flow_only` / `mismatch` 英文枚举值，无中文释义。
- `GovernView.vue:791-794` `reconcileClassHint` 仅一行 `inv_only=X / flow_only=Y / mismatch=Z · material_id_overlap=N · 期初已填行=M`，未说明每类代表什么、应如何处理。
- 后端 `flowReconcile` 已返回 `by_class` / `material_id_overlap` / `opening_populated_rows`（`GovernView.vue:776-795` 的 `applyReconcilePayload` 已接收），数据齐全，仅 UI 未表达。

---

## 2. 任务拆解

### HG-1 · 总览页职责收敛

> 目标：移除与 `MetricsView` / `ModelsView` 重叠区块，首屏只保留"业务一眼 + 数据量 + 门禁 + 入口"。

| 任务 | 落点 | 验收 |
|---|---|---|
| HG-1.1 移除"业务指标(active) 试跑"卡片 | [HomeView.vue:139-159](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L139-L159) 删除整个 `<el-card>`；同步删除 `bizMetricRows` computed（`:299-310`）、`runBizEvals`（`:324-339`）、`evalMap`/`evalBusy`（`:239-242`）、`evaluateMetric` import（`:224`） | 总览页无指标试跑表；指标试跑统一在 `/metrics` |
| HG-1.2 `onMounted` 去阻塞 | [HomeView.vue:384-389](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L384-L389) 删除 `await runBizEvals()`，改为 `await load(); Promise.all([loadSpark(), loadSeedReports()])` | 首屏不再串行等指标试跑；迷你趋势/报表更早渲染 |
| HG-1.3 模型卡片精简为一行聚合状态 | [HomeView.vue:161-188](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L161-L188) 把 `el-descriptions` 4 行改为单行 `el-space`：`模型 big✓ fast✗ embed✓ · Stage 2`（用 `el-tag` 三态），移除 `configured_model` / `frontend_dist` 详情；详情交给 `/models` | 总览模型区只显示可用性，配置详情在模型管理页 |
| HG-1.4 后端 `overview()` 模型探测改并发 | [app/services/query/stats_overview.py:188-190](file:///workspace/2026-07/smart-material-system/app/services/query/stats_overview.py#L188-L190) 三次 `probe_endpoint` 改 `asyncio.gather` + `asyncio.to_thread`（参考 `app/api/routers/ops.py:17-21` 写法）；或复用 `models_status` 结果 | `overview()` 模型探测耗时从最坏 15s 降到最坏 5s |
| HG-1.5 总览页加跳转 hint | [HomeView.vue:201-212](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L201-L212) actions 区已有 `/metrics` `/models` 按钮，保留；在移除的指标卡原位加一行 hint "指标试跑与趋势见 指标字典" | 用户从总览可达指标试跑，无功能丢失感 |

### HG-2 · 治理页心智收敛

> 目标：治理页聚焦 5 个写操作确认 Tab，"流水分析"只读分析迁出或视觉隔离。

| 任务 | 落点 | 验收 |
|---|---|---|
| HG-2.1 "流水分析" Tab 迁到报表页（推荐） | 将 [GovernView.vue:473-511](file:///workspace/2026-07/smart-material-system/frontend/src/pages/GovernView.vue#L473-L511) analytics 区块 + `loadAnalytics/renderAnalytics/anTopItems/anMonthly/anLevel` 等逻辑（`:676-737`、`:743-774`）整体迁到 `ReportsView.vue` 新增"流水分析"分区（与种子报表 `rpt_flow_monthly`/`rpt_flow_top_material` 同页互验）；删除 `GovernView` 中 `analytics` Tab（`:9`）及 `onTab` 中 `analytics` 分支（`:829-831`） | 治理页剩 5 Tab 全为写操作；报表页同时有"种子报表快照"+"流水实时分析"，可互验 |
| HG-2.2 （备选）治理页内视觉隔离 | 保留 `analytics` Tab，但 [GovernView.vue:3-10](file:///workspace/2026-07/smart-material-system/frontend/src/pages/GovernView.vue#L3-L10) Tab 顺序调整为 `map / rulelearn / master / flow / reconcile` 在前，`analytics` 单独末位并加 label 后缀"（只读分析）"；analytics 区块顶部加 alert "本 Tab 只读，不写任何表；写操作见前 5 Tab" | 治理页心智：前 5 Tab 写操作 / 末 Tab 只读，界限清晰 |
| HG-2.3 治理页顶部加职责说明 | [GovernView.vue:2](file:///workspace/2026-07/smart-material-system/frontend/src/pages/GovernView.vue#L2) `<div class="govern">` 后加一行 `el-alert`："本页为人工裁决中心：机器不确定项进队列，确认后才写 rule_dict / flow_example / DuckDB。LLM 仅提案，不自动发布。" | 治理页顶部一句话点明职责，降低 U-5 信息密度痛点 |

### HG-3 · 勾稽差异可理解性

> 目标：`gap_class` 三类含义对一线可读，明确每类应如何处理。

| 任务 | 落点 | 验收 |
|---|---|---|
| HG-3.1 "类别"列加中文释义 tooltip | [GovernView.vue:539](file:///workspace/2026-07/smart-material-system/frontend/src/pages/GovernView.vue#L539) `gap_class` 列改用 `el-table-column` 自定义 header slot，加 `el-tooltip`：`inv_only=库存有流水无（流水覆盖缺失）/ flow_only=流水有库存无（编码对不上）/ mismatch=两边有但数额不符` | 鼠标悬停表头即见三类释义 |
| HG-3.2 `reconcileClassHint` 改为分类卡片 | [GovernView.vue:791-794](file:///workspace/2026-07/smart-material-system/frontend/src/pages/GovernView.vue#L791-L794) `applyReconcilePayload` 中 `reconcileClassHint` 由一行文本改为三个 `el-tag` 卡片组：`inv_only: X（流水覆盖缺失 → 期初种子或补录流水）` / `flow_only: Y（编码对不上 → /govern 主数据对齐）` / `mismatch: Z（数额不符 → 核对单位/数量）`；模板区同步替换展示 | 一线看到分类计数即知每类含义与下一步动作 |
| HG-3.3 alert 描述补"差异是常态"说明 | [GovernView.vue:520](file:///workspace/2026-07/smart-material-system/frontend/src/pages/GovernView.vue#L520) alert description 补一句："已知源头出库缺失率高（维护材料约 79%、备品备件约 98%），差异是常态；本页用于可见、可导出、可补录，不自动轧平。"（对齐 12 §6 产品话术） | 一线理解差异非异常，不试图强行平账 |
| HG-3.4 差异表行按 `gap_class` 着色 | [GovernView.vue:538-547](file:///workspace/2026-07/smart-material-system/frontend/src/pages/GovernView.vue#L538-L547) 表格 `row-class-name` 按 `gap_class` 着色：`inv_only` info / `flow_only` warning / `mismatch` danger | 一眼区分三类差异密度 |

---

## 3. 与既有方案依赖

| 依赖 | 说明 |
|---|---|
| [user-perspective-analysis.md](file:///workspace/2026-07/smart-material-system/roadmap/user-perspective-analysis.md) U-5 | HG-2.3 治理页职责说明与 U2.2"每 Tab 职责说明"互补，合并执行避免重复 |
| [examples-plan.md](file:///workspace/2026-07/smart-material-system/roadmap/examples-plan.md) T3.2 | HG-1.1 移除指标卡后，原位 hint 与 T3.2 空态引导对齐口径 |
| [docs/07 §3.1](file:///workspace/2026-07/治理方案/07-界面层设计.md) | HG-1 总览页收敛回归文档原定义"6 表行数 / 主数据数 / 待确认数 + 分布图" |
| [docs/07 §3.4](file:///workspace/2026-07/治理方案/07-界面层设计.md) | HG-2 治理页 Tab 收敛到文档列的 5 个写操作 Tab（表头映射 / 主数据 / 流水解析 / 勾稽差异 + 规则学习） |
| [docs/12 §6](file:///workspace/2026-07/治理方案/12-出入库流水解析.md) | HG-3 勾稽差异文案与"允许差异存在 / 不宣称账已轧平"产品话术对齐 |
| [docs/question/03](file:///workspace/2026-07/治理方案/question/03-界面分析面缺失（使用系统角度）.md) | HG-2.1 流水分析迁报表页，补齐"分析入口可达性"剩余缺口 |

---

## 4. 决策点

| ID | 决策点 | 候选 |
|---|---|---|
| ED-1 | "流水分析"归属 | HG-2.1 迁报表页（推荐，心智清晰）/ HG-2.2 治理页内视觉隔离（成本低） |
| ED-2 | 总览模型卡精简粒度 | 一行三态 tag（推荐，最简）/ 保留 big+embed 两行去掉 fast+frontend_dist |
| ED-3 | HG-1.4 后端探测改法 | `overview()` 内改 `gather`（推荐，自洽）/ 复用 `models_status` 结果（避免重复探测但耦合两个端点） |

---

## 5. 建议执行顺序

1. **HG-1.1 + HG-1.2**（前端独立可做，立即改善首屏）：移除指标试跑卡 + `onMounted` 去阻塞。
2. **HG-3.1 + HG-3.3**（前端独立可做，立即改善一线理解）：类别列 tooltip + alert 补"差异是常态"。
3. **HG-2.3**（前端独立可做）：治理页顶部职责说明。
4. **HG-1.3**（前端，依赖 ED-2）：模型卡精简。
5. **HG-3.2 + HG-3.4**（前端）：分类卡片 + 行着色。
6. **HG-2.1 或 HG-2.2**（前端，依赖 ED-1）：流水分析迁出或视觉隔离。
7. **HG-1.4**（后端，依赖 ED-3）：`overview()` 探测改并发。
8. **HG-1.5**（前端，收尾）：跳转 hint。

HG-1.1/HG-1.2/HG-3.1/HG-3.3/HG-2.3 五项无决策依赖、无后端改动，可作为第一批落地。

---

## 6. 验收总标准

1. 总览页无"业务指标(active) 试跑"卡片，`onMounted` 不再串行调 `evaluateMetric`；指标试跑只在 `/metrics`；
2. 总览页模型区为一行聚合状态（big/fast/embed 三态 + Stage），无 `configured_model` / `frontend_dist` 详情；
3. 后端 `overview()` 模型探测并发，首屏最坏耗时 ≤ 5s；
4. 治理页 Tab 数为 5（若 ED-1 选 HG-2.1）或 6 但末 Tab 标注"（只读分析）"且顶部 alert 隔离（若 ED-1 选 HG-2.2）；
5. 治理页顶部有职责说明 alert；
6. 勾稽差异表"类别"列表头有中文释义 tooltip，`reconcileClassHint` 区为三分类卡片，alert 含"差异是常态"说明，表格行按 `gap_class` 着色；
7. 既有可信流水线（写操作三件套、Ops Token、确认门）与口径克制（跨单位不加总、不宣称轧平、FLOW_* 双门禁）不受影响。

---

*评审通过后按 §5 顺序执行；与 user-perspective-analysis U-5 / examples-plan T3.2 节点对齐。*
