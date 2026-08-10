# 指标字典与业务快照的用户视角绑定方案

> 版本：v0.1（2026-08-10）· 状态：待评审
> 视角：**用户视角**（业务查数者 / 指标管理员 / Ops 三层受众分层）
> 范围：`frontend/src/pages/MetricsView.vue`、`frontend/src/pages/HomeView.vue` 及二者的绑定关系
> 关联：[home-govern-review.md](file:///workspace/2026-07/smart-material-system/roadmap/home-govern-review.md)（HG-1 总览页收敛）、[user-perspective-analysis.md](file:///workspace/2026-07/smart-material-system/roadmap/user-perspective-analysis.md)（U-3/U-5）、[docs/08 §1/§9](file:///workspace/2026-07/治理方案/08-指标体系与口径管理.md)、[docs/07 §3.1/§3.8](file:///workspace/2026-07/治理方案/07-界面层设计.md)

---

## 0. 结论摘要

指标字典与业务快照本应是系统最强的绑定关系——首页 9 张卡 = 指标字典 9 个 active 业务指标的求值结果，是同一条 SQL。但 UI 上完全没建立这层关系，且两个页面充斥开发/治理层术语（`metric_id` / `engine` / `FLOW_*` / `meta` / `DuckDB` / `UI-3` / `L1 ratio` / `dim_material`），未按受众分层，导致：

1. **业务用户看不出"首页数字的口径在哪定义、怎么追溯"**——业务快照卡片只显示数字，不绑定指标。
2. **页面像给程序员看**——指标字典页开门是"FLOW_* 门禁 + 跑夹具 + 别名冲突"，全是内部质量机制，没说它解决"问'库存总金额'口径不一"这个业务问题。
3. **跟系统功能没绑定**——门禁/夹具/冲突检查是问答可信的保障，但页面只暴露按钮，不说意义；业务快照和指标字典是同一批 SQL，但无追溯链路。

**结论**：按本文 MB-1 / MB-2 / MB-3 修改后，首页数字可一键追溯到指标口径，指标字典按"业务口径区 / 质量门禁区"分受众呈现，术语按角色分层，且不破坏既有可信流水线。

---

## 1. 两个概念的业务含义

### 1.1 指标字典 = 系统的"口径登记本"

[docs/08 §1](file:///workspace/2026-07/治理方案/08-指标体系与口径管理.md) 开篇点明它解决的问题：同样的中文问法，不同人口径不同（库存金额含税否、需求含全期否、汇总明细对不上）。指标字典把"库存总金额"这种业务问法绑定到唯一、可执行、可审计的 SQL 定义，让任何人问同一问题都用同一条口径回答，而非 LLM 每次猜。

与系统功能的绑定（08 §9）：

| 系统功能 | 指标字典怎么参与 |
|---|---|
| 自然语言问答 `/ask` | 问"库存总金额"→ 命中 `INV_VALUE_TOTAL` aliases → 直接用 `definition_sql`，不调 LLM 猜 SQL |
| 接入编排 `/intake` | 汇总表数值列 ↔ 指标匹配，做"汇总值 vs 指标 SQL 值"对账 |
| 治理 `/govern` | 口径冲突进治理中心人工确认；修正回写字典（自学习） |
| 报表 `/reports` | 报表 SQL 须以 `definition_sql` 为基准，不能自由发挥 |

**一句话**：指标字典是问答和报表"可信"的根基——没有它，问"库存总金额"每次可能跑出不同口径的数。

### 1.2 业务快照 = 首页的"业务一眼"

`app/services/query/stats_overview.py:82-179` 的 `business_snapshot()` 跑 9 个聚合数 + 3 个 Top 排行，全部来自 `fact_inventory / fact_asset / fact_demand / fact_stock_flow`。

### 1.3 二者的同一性（关键绑定关系）

业务快照 9 卡 = 指标字典 9 个 active 业务指标的求值结果，同一条 SQL：

| 业务快照卡片 | 指标字典 active 指标 | 同一条 SQL |
|---|---|---|
| 库存总量 | `INV_QTY_TOTAL` | `SELECT SUM(stock_qty) FROM fact_inventory` |
| 库存金额 | `INV_VALUE_TOTAL` | `SELECT SUM(stock_value) FROM fact_inventory WHERE ...` |
| 定额利用率 | `INV_QUOTA_FILL_RATIO` | 同 |
| 超定额物资 | `INV_OVER_QUOTA_CNT` | 同 |
| 呆滞料行 | `INV_STALE_CNT` | 同 |
| 需求总量 | `DEMAND_QTY_TOTAL` | 同 |
| 资产台数 | `ASSET_COUNT_TOTAL` | 同 |
| 入库合计 | `FLOW_IN_QTY_TOTAL` | 同 |
| 出库合计 | `FLOW_OUT_QTY_TOTAL` | 同 |

证据：`app/services/metrics/metrics.py:65-256` 的 `BUSINESS_METRICS` 与 `app/services/query/stats_overview.py:87-121` 的 `business_snapshot` 字段一一对应。这本该是两个页面最强的绑定，但 UI 上完全看不出。

---

## 2. "像给程序员看"的具体证据

### 2.1 指标字典页 `MetricsView.vue`

| 位置 | 程序员视角证据 |
|---|---|
| `MetricsView.vue:3-9` 顶部 alert | `指标字典（08）` + `LLM 不可改字典。FLOW_* 须过 12/08 门禁后才能 active；激活只改 meta，不写 DuckDB。` —— `08`/`12/08`/`FLOW_*`/`meta`/`DuckDB`/`active` 全是内部模块号、技术编码、引擎名、状态枚举，无一是业务语言 |
| `MetricsView.vue:17-26` 操作按钮 | `跑固定夹具` / `别名冲突检查` / `激活 FLOW_*` —— "夹具"(fixtures)、"别名冲突"(alias conflict)、"FLOW_*"全是开发术语 |
| `MetricsView.vue:89-103` 列表表头 | `metric_id` / `unit` / `status` / `ver` / `engine` —— `metric_id` 是 `INV_QTY_TOTAL` 英文编码，`engine` 是 `biz/meta`，`ver` 是 version 缩写 |
| `MetricsView.vue:34-41` gate checks | `{{ key }}: ✓/✗` —— key 是英文检查项名（`flow_published` / `reconcile_visible`），业务用户看不懂 |
| `MetricsView.vue:124-164` 编辑弹窗 | 让用户填 `metric_id`（英文编码必填）、`engine`（biz/meta 下拉）、`definition_sql`（SQL 文本框必填）、`aliases` —— 让业务用户写 SQL 和英文 ID |
| `MetricsView.vue:158-163` FLOW_* 警告 | `FLOW_* 设为 active 须门禁通过；否则接口返回 403` —— "接口返回 403"是 HTTP 术语 |
| `MetricsView.vue:171` 趋势弹窗标题 | `快照趋势（UI-3）` —— `UI-3` 是内部任务编号，不该暴露给用户 |

### 2.2 业务快照 `HomeView.vue`

| 位置 | 程序员视角证据 |
|---|---|
| `HomeView.vue:3-9` 顶部 alert | `业务快照优先；表行数 / 流水 / 门禁为辅。写操作仍走治理与确认门；前端只读同源 /api/v1。` —— "门禁"、"同源 /api/v1"是技术术语 |
| `HomeView.vue:287-297` 6 表行数卡片 | 标签"中文名 + 英文物理表名"并列：`主数据 dim_material` / `库存 fact_inventory` —— 物理表名对业务用户无意义 |
| `HomeView.vue:119-130` 流水与门禁 | `published` / `L1 ratio` / `pending` / `L1: n` / `L2: n` / `L3: n` —— 全英文标签，L1/L2/L3 是流水解析置信级别（12 §4），页面没解释 |
| `HomeView.vue:40` Top 排行警告 | `按单位 Top（跨单位勿直接加总）` —— 口径警告对业务用户突兀，只在小字提示，没说为什么 |
| `HomeView.vue:165-188` 模型 Stage 卡片 | `big` / `fast` / `embed` / `frontend_dist` —— 全是模型角色编码，业务用户不知各干什么 |

---

## 3. "跟系统功能没绑定"的三个表现

### 表现 1：业务快照和指标字典是同一批数字，但 UI 无追溯链路

- `HomeView` 业务快照卡片只显示数字，不显示"这是哪个指标、什么口径"。
- `MetricsView` 指标列表"试跑"后显示 `value`（`MetricsView.vue:104-112`），用户看不出这个值和首页卡片是同一条 SQL 跑出来的。
- 没有"点击首页库存总量卡片 → 跳 `/metrics?id=INV_QTY_TOTAL` → 看口径说明 + 趋势"这条链路。

**结果**：业务用户在首页看到"库存总量 12345"，想知道"这个数怎么算的、含不含临时库"，无路可走——只能去 `/metrics` 自己搜 `INV_QTY_TOTAL`。

### 表现 2：指标字典页没说"为什么要有指标字典"

08 §1 用 3 个真实歧义场景（库存金额含税否、需求含全期否、汇总明细对不上）说明了业务价值。但 `MetricsView` 页面没有任何业务场景说明，开门就是"FLOW_* 门禁 + 跑夹具 + 别名冲突检查"。

业务用户进 `/metrics` 第一眼看到的全是内部质量机制，完全不知道这个页面跟自己日常问的"库存总金额是多少"有什么关系。

### 表现 3：内部质量机制暴露给业务用户，但没说意义

指标字典页的"跑固定夹具 / 别名冲突检查 / 激活 FLOW_*"和首页的"流水与门禁 L1 ratio / pending"，本质都是系统质量保障机制：

| UI 按钮/标签 | 真实含义 | 文档出处 |
|---|---|---|
| 跑固定夹具 | 验证 FLOW_* 指标 SQL 在样例数据上能跑通 | 08 §3 + 12 §8 门禁 |
| 别名冲突检查 | 防止两个指标抢同一个中文叫法 | 08 §4 |
| FLOW_* 门禁 | 流水指标激活前确认流水质量够好 | 12 §8 + 08 §8 |
| L1/L2/L3 | 流水解析置信级别（L1 规则直出 / L2 规则+LLM / L3 兜底） | 12 §4 |

这些是给**指标管理员 / Ops** 看的内部质量门。但页面把它们和"指标列表 / 试跑 / 趋势"混在一起，没区分受众——业务用户看到一堆自己不该点的按钮，指标管理员该看的门禁状态又没单独成区。

---

## 4. 任务拆解

### MB-1 · 首页业务快照绑定指标字典

> 目标：首页 9 卡每卡可一键追溯到指标口径，建立"数字 → 口径 → 趋势"链路。

| 任务 | 落点 | 验收 |
|---|---|---|
| MB-1.1 业务快照卡片加指标 tooltip | [HomeView.vue:19-23](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L19-L23) `bizCards` 卡片渲染处加 `el-tooltip`：显示该卡对应的 `metric_id` + `definition`（如"库存总量 = SUM(stock_qty)，含临时库"） | 鼠标悬停卡片即见口径 |
| MB-1.2 卡片可点击跳指标字典 | [HomeView.vue:272-285](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L272-L285) `bizCards` 加 `metric_id` 字段；卡片 `@click="$router.push('/metrics?id=' + c.metric_id)"` | 点击库存总量卡跳 `/metrics?id=INV_QTY_TOTAL` |
| MB-1.3 MetricsView 支持初始选中指标 | [MetricsView.vue:66-71](file:///workspace/2026-07/smart-material-system/frontend/src/pages/MetricsView.vue#L66-L71) 路由 query `id` 自动填搜索框 + 自动展开该指标趋势；[router/index.ts](file:///workspace/2026-07/smart-material-system/frontend/src/router/index.ts) `/metrics` 路由加 `props: (route) => ({ id: route.query.id })` | 从首页跳来时自动定位指标并展开趋势 |
| MB-1.4 业务快照 alert 换业务语言 | [HomeView.vue:3-9](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L3-L9) alert description 改为"下方数字均来自指标字典的统一口径，点击卡片可查看口径定义与历史趋势" | 删掉"门禁/同源 /api/v1"等技术术语 |

### MB-2 · 指标字典页术语分层 + 受众分区

> 目标：业务口径区面向指标管理员/业务用户，质量门禁区面向 Ops，术语按角色分层。

| 任务 | 落点 | 验收 |
|---|---|---|
| MB-2.1 顶部 alert 换业务语言 | [MetricsView.vue:3-9](file:///workspace/2026-07/smart-material-system/frontend/src/pages/MetricsView.vue#L3-L9) alert 改为"同一个'库存总金额'，不同人口径不同。本页登记所有指标的统一口径，问答与报表都以此为准。" 删掉 `08`/`12/08 门禁`/`meta`/`DuckDB` | 业务用户进页第一眼懂本页价值 |
| MB-2.2 拆"业务口径区"与"质量门禁区" | [MetricsView.vue:11-59](file:///workspace/2026-07/smart-material-system/frontend/src/pages/MetricsView.vue#L11-L59) FLOW_* 门禁卡（含跑夹具/别名冲突/激活）整体下移到列表下方，加 alert "以下为 Ops 质量门禁，业务用户可忽略"；上方保留"指标列表 + 试跑 + 趋势 + 编辑" | 业务用户上半页即满足；Ops 下半页操作 |
| MB-2.3 列表表头去英文 | [MetricsView.vue:89-103](file:///workspace/2026-07/smart-material-system/frontend/src/pages/MetricsView.vue#L89-L103) `metric_id` 列加副标题中文名（已有 `metric_name`，但 `metric_id` 仍显眼，改为 `metric_id` 列宽缩小 + 灰色小字）；`engine` 列对业务用户隐藏或改中文（业务/元数据）；`ver` 改"版本" | 表头无裸英文术语 |
| MB-2.4 gate checks 中文释义 | [MetricsView.vue:35-41](file:///workspace/2026-07/smart-material-system/frontend/src/pages/MetricsView.vue#L35-L41) `{{ key }}` 改中文映射（`flow_published=已发布流水` / `reconcile_visible=勾稽可见` 等），或加 `el-tooltip` 英文 key + 中文释义 | 业务用户看得懂门禁项 |
| MB-2.5 编辑弹窗加角色边界提示 | [MetricsView.vue:151-153](file:///workspace/2026-07/smart-material-system/frontend/src/pages/MetricsView.vue#L151-L153) `definition_sql` 字段上方加 hint"仅指标管理员可改；业务用户如需新指标，请在治理中心提案"（对应 08 §7"LLM 永远不能直接修改指标定义"） | 角色边界可见 |
| MB-2.6 趋势弹窗去内部编号 | [MetricsView.vue:171](file:///workspace/2026-07/smart-material-system/frontend/src/pages/MetricsView.vue#L171) 标题改为 `${metric_name} 快照趋势`，删掉 `（UI-3）` | 无内部任务编号暴露 |

### MB-3 · 首页术语分层

> 目标：首页物理表名、英文标签、模型角色编码改业务语言或加释义。

| 任务 | 落点 | 验收 |
|---|---|---|
| MB-3.1 6 表行数卡片去物理表名 | [HomeView.vue:287-297](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L287-L297) 标签只留中文（`主数据` / `库存` / `资产` / `需求` / `流水` / `流水待确认`），物理表名移到 tooltip | 卡片无裸物理表名 |
| MB-3.2 流水门禁 L1/L2/L3 加释义 | [HomeView.vue:119-130](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L119-L130) 各 tag 加 tooltip：`L1=规则直出 / L2=规则+LLM / L3=LLM 兜底`，`pending=待人工确认`，`published=已发布流水` | 英文标签可悬停见中文释义 |
| MB-3.3 模型卡改中文角色 | [HomeView.vue:165-188](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L165-L188) `big/fast/embed` 改`主模型/快速模型/向量模型`（与 home-govern-review HG-1.3 合并执行） | 模型区无英文角色编码 |
| MB-3.4 Top 排行警告改业务语言 | [HomeView.vue:40](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L40) `按单位 Top（跨单位勿直接加总）` 改`按单位 Top（不同单位不能直接相加，仅作分类对照）` | 口径警告可懂 |

---

## 5. 与既有方案依赖

| 依赖 | 说明 |
|---|---|
| [home-govern-review.md](file:///workspace/2026-07/smart-material-system/roadmap/home-govern-review.md) HG-1.3 | MB-3.3 模型卡中文角色与 HG-1.3 模型卡精简合并执行 |
| [home-govern-review.md](file:///workspace/2026-07/smart-material-system/roadmap/home-govern-review.md) HG-1.1 | MB-1 与 HG-1.1（移除首页指标试跑卡）互补：试跑归 `/metrics` 后，首页数字反而要能跳到 `/metrics` 试跑（MB-1.2/MB-1.3） |
| [user-perspective-analysis.md](file:///workspace/2026-07/smart-material-system/roadmap/user-perspective-analysis.md) U-3 | MB-1.1 卡片 tooltip 与 U-3"业务示例"互补 |
| [examples-plan.md](file:///workspace/2026-07/smart-material-system/roadmap/examples-plan.md) T3.2 | MB-1.4 alert 业务语言与 T3.2 空态引导对齐口径 |
| [docs/08 §1/§7/§9](file:///workspace/2026-07/治理方案/08-指标体系与口径管理.md) | MB-2.1 alert 文案、MB-2.5 角色边界对齐 08 §1 业务问题定义与 §7"LLM 不可改字典" |
| [docs/07 §3.1/§3.8](file:///workspace/2026-07/治理方案/07-界面层设计.md) | MB-1/MB-2 落点对齐概览页与指标字典页定义 |
| [docs/12 §4/§8](file:///workspace/2026-07/治理方案/12-出入库流水解析.md) | MB-3.2 L1/L2/L3 释义对齐 12 §4 置信分级与 §8 门禁 |

---

## 6. 决策点

| ID | 决策点 | 候选 |
|---|---|---|
| ED-1 | 业务快照卡片是否可点击 | 可点击跳 `/metrics`（推荐，建立追溯）/ 仅 tooltip 不可点（更轻） |
| ED-2 | 指标字典页分区方式 | 上下分区（推荐，业务口径上 / 质量门禁下）/ Tab 分区（口径 Tab / 门禁 Tab） |
| ED-3 | `engine` 列处理 | 隐藏（推荐，业务用户无需）/ 改中文（业务/元数据）保留 |
| ED-4 | MB-1.3 路由跳转是否自动展开趋势 | 自动展开（推荐，一步到位）/ 仅定位高亮，用户手动点趋势 |

---

## 7. 建议执行顺序

1. **MB-2.1 + MB-2.6**（前端独立，立即改善指标字典页第一印象）：alert 换业务语言 + 趋势弹窗去 `UI-3`。
2. **MB-3.1 + MB-3.2 + MB-3.4**（前端独立，立即改善首页术语）：6 表卡片去物理表名 + L1/L2/L3 释义 + Top 警告改业务语言。
3. **MB-1.4**（前端独立）：首页 alert 换业务语言。
4. **MB-2.4**（前端独立）：gate checks 中文释义。
5. **MB-2.3 + MB-2.5**（前端独立）：表头去英文 + 编辑弹窗角色边界提示。
6. **MB-2.2**（前端，依赖 ED-2）：指标字典页分区。
7. **MB-1.1 + MB-1.2 + MB-1.3**（前端 + 路由，依赖 ED-1/ED-4）：首页卡片绑定指标 + 跳转链路。
8. **MB-3.3**（前端，与 home-govern-review HG-1.3 合并）：模型卡中文角色。

MB-2.1 / MB-2.6 / MB-3.1 / MB-3.2 / MB-3.4 / MB-1.4 六项无决策依赖、无后端改动，可作为第一批落地。

---

## 8. 验收总标准

1. 首页业务快照 9 卡每卡有口径 tooltip，点击可跳 `/metrics?id=...` 并自动定位该指标（ED-1 选可点击时）；
2. 首页 alert 无"门禁/同源 /api/v1"等技术术语，6 表卡片无裸物理表名，L1/L2/L3/published/pending 有中文释义，模型卡无英文角色编码；
3. 指标字典页顶部 alert 用业务语言说明本页价值（库存金额口径不一场景），无 `08`/`12/08`/`meta`/`DuckDB`；
4. 指标字典页按"业务口径区 / 质量门禁区"分区，质量门禁区有"业务用户可忽略"标注；
5. 指标列表表头无裸英文术语（`metric_id` 缩小灰字 / `engine` 隐藏或中文 / `ver` 改"版本"），gate checks 有中文释义；
6. 编辑弹窗 `definition_sql` 有角色边界提示，趋势弹窗标题无 `UI-3`；
7. 既有可信流水线（指标字典 LLM 不可改、FLOW_* 双门禁、写操作三件套）不受影响。

---

*评审通过后按 §7 顺序执行；与 home-govern-review HG-1 / user-perspective-analysis U-3 / examples-plan T3.2 节点对齐。*
