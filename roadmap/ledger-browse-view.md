# 台账浏览页方案 · 规整后数据的在线可见性

> 版本：v0.1（2026-08-10）· 状态：**已落地**（`BrowseView` + `GET /api/v1/browse/{table}`）
> 视角：**数据规整与管理**（治理员 / 业务用户 / 接入员需在线查看治理成果）
> 范围：新增 `frontend/src/pages/BrowseView.vue` + 后端 `GET /api/v1/browse/{table}`；关联 `HomeView` 导出区、`GovernView` 确认闭环
> 关联：[home-govern-review.md](file:///workspace/2026-07/smart-material-system/roadmap/home-govern-review.md)、[metrics-home-binding.md](file:///workspace/2026-07/smart-material-system/roadmap/metrics-home-binding.md)、[assets-ops-user-view.md](file:///workspace/2026-07/smart-material-system/roadmap/assets-ops-user-view.md)、[ledger-export-plan.md](file:///workspace/2026-07/smart-material-system/roadmap/ledger-export-plan.md)、[docs/07 §3.1](file:///workspace/2026-07/治理方案/07-界面层设计.md)、[docs/03](file:///workspace/2026-07/治理方案/03-接入编排与可信管道.md)

---

## 0. 结论摘要

系统经完整治理链路（上传→证据→Step1 画像→Step2 映射→staging dry-run→Ops 确认→幂等 writer 发布）后，数据落在 6 张星型表，但**前端没有任何页面以列表方式展示这些规整后数据**——唯一途径是下载 CSV（`HomeView` 导出按钮）或自然语言问答（`/ask`，查询驱动非浏览）。这是数据治理平台的根本倒挂：治理成果对用户不可见。

关键发现：**后端基础设施已齐全**（`visible_fields` 过滤技术字段 / `zh_columns` 汉化列名 / `value_zh` 汉化枚举 / `sql_guard` 只读校验 / `export_table` 已实现完整取数+汉化链路），只差一个返回 JSON 分页的端点 + 一个前端浏览页。

**结论**：按本文 LB-1 / LB-2 / LB-3 / LB-4 落地后，6 张标准表可在线分页浏览（中文化列名/枚举、隐藏技术字段、基础筛选排序），治理闭环从"治理→发布→看不到"补齐为"治理→发布→浏览验证"，且不破坏既有只读安全与口径克制。

---

## 1. 现状证据（2026-08-10 实测）

### 1.1 规整后数据的存放与可见性

| 标准表 | 内容 | 前端可见途径 |
|---|---|---|
| `dim_material` | 物资主数据 | 仅 CSV 导出（`HomeView.vue:67-76`） |
| `fact_inventory` | 库存台账 | 仅 CSV 导出 |
| `fact_asset` | 资产台账 | 仅 CSV 导出 |
| `fact_demand` | 需求明细 | 仅 CSV 导出 |
| `fact_stock_flow` | 出入库流水 | 仅 CSV 导出 + `/govern` 流水解析 Tab（仅 pending，非全表） |
| `fact_quota_adjust` | 定额调整 | 无任何入口 |

### 1.2 前端 12 页无台账浏览页

`frontend/src/router/index.ts:18-31` 路由：`/` `/ask` `/intake` `/files` `/stage/:fileId` `/settings` `/govern` `/metrics` `/reports` `/learning` `/models` `/ops` —— **无 `/browse` 或台账浏览页**。`ReportsView` 是参数化报表快照（保存的 SQL 跑出 parquet/csv），非标准表浏览。

### 1.3 唯一取数入口：CSV 导出

`HomeView.vue:60-80` 标准表导出区，5 个按钮调 `tableExportUrl(table, 100000)`（`client.ts:1276`）→ `GET /export/table/{table}?limit=100000` → 下载 CSV。

`app/api/routers/reports.py:168-210` `export_table` 实现：表名白名单 → `sql_guard.validate_readonly_sql` → `SELECT * FROM "{table}" LIMIT n` → `visible_fields` 过滤技术字段 → `zh_columns` 汉化列名 → `value_zh` 汉化枚举 → 返回 CSV 文件流。（行号 2026-08-10 复核；另有新增 `/export/ledger/{sheet}` 端点在 `:211`）

### 1.4 后端基础设施已齐全

| 能力 | 位置 | 浏览页用途 |
|---|---|---|
| 列出可查表 | `query.py:16-18` `GET /query/tables` | 表选择下拉 |
| 过滤技术/溯源字段 | `govern/field_dict.py:159-161` `visible_fields()` | 隐藏 `source_release_id` 等内部列 |
| 列名汉化 | `govern/field_dict.py:164-166` `zh_columns()` | 显示"库存量"而非 `stock_qty` |
| 枚举值汉化 | `govern/field_dict.py:147-152` `value_zh()` | `flow_type` IN→入库、OUT→出库 |
| 只读 SQL 校验 | `sql_guard.validate_readonly_sql()` | 防注入，保证 `SELECT *` 安全 |
| 已有取数逻辑 | `reports.py:193` `con.execute(guard.sql).fetchdf()` | 同样 `SELECT * LIMIT n` |

**结论**：`export_table` 已实现完整取数+汉化链路，唯一区别是返回 CSV 文件流而非 JSON 分页数据。

---

## 2. 问题清单

| ID | 问题 | 现状证据 | 影响 |
|---|---|---|---|
| LB-1 | 无台账浏览页，规整后数据不可在线查看 | `router/index.ts` 12 页无 `/browse` | 治理成果对用户不可见 |
| LB-2 | 只能下载 CSV，不知数据什么样子 | `HomeView.vue:67-76` 仅导出按钮 | 新用户/业务用户无法"扫一眼"标准表 |
| LB-3 | CSV 导出有上限，无法翻页/筛选/排序 | `reports.py:187` `EXPORT_ROW_LIMIT` 约束 | 大表只能看前 N 行，无法定位问题 |
| LB-4 | 问答非浏览，需先想好问题 | `/ask` 返回聚合结果，非明细列表 | 想"扫一眼 fact_inventory 前 100 行"做不到 |
| LB-5 | 治理闭环断在最后一步 | 治理→发布→看不到 | 无法基于实际数据做下一步决策（如发现空值多该回治理补映射） |
| LB-6 | `fact_quota_adjust` 无任何前端入口 | `HomeView` 导出仅 5 表，缺该表 | 该表数据完全不可见 |

---

## 3. 任务拆解

### LB-1 · 后端浏览端点（与 export 同源，返回 JSON 分页）

> 目标：复用 `export_table` 取数+汉化链路，返回 JSON 分页数据。

| 任务 | 落点 | 验收 |
|---|---|---|
| LB-1.1 新增 `GET /api/v1/browse/{table}` | [app/api/routers/reports.py](file:///workspace/2026-07/smart-material-system/app/api/routers/reports.py) 新增端点，复用 `export_table` 的表名白名单 + `sql_guard` + `visible_fields` + `zh_columns` + `value_zh`；参数 `limit`（默认 100，上限 500）/ `offset`（默认 0）/ `zh`（默认 1）；返回 `{"table", "columns_zh", "rows", "total", "limit", "offset}` | curl 请求返回 JSON，列名中文化、枚举汉化、技术字段隐藏 |
| LB-1.2 总数统计 | `browse/{table}` 内 `SELECT COUNT(*) FROM "{table}"` 经 `sql_guard` 校验后单独执行，返回 `total` | 分页器显示总行数 |
| LB-1.3 行数上限与导出分离 | 浏览 `limit` 上限 500（单页），不触发 `EXPORT_ROW_LIMIT`（5 万）；导出仍走原上限 | 浏览不挤占导出配额 |
| LB-1.4 表白名单含全部 6 表 | `browse/{table}` 白名单含 `dim_material` / `fact_inventory` / `fact_asset` / `fact_demand` / `fact_stock_flow` / `fact_quota_adjust`（补 LB-6） | `fact_quota_adjust` 可浏览 |

### LB-2 · 前端台账浏览页

> 目标：新增 `/browse` 页，分页展示规整后标准表。

| 任务 | 落点 | 验收 |
|---|---|---|
| LB-2.1 新增 `BrowseView.vue` | `frontend/src/pages/BrowseView.vue`：顶部表选择下拉（6 表）+ 搜索框 + 分页器 + `el-table`；列名用 `columns_zh`，枚举值已汉化；技术字段已隐藏 | 选表后展示前 100 行，列名中文 |
| LB-2.2 路由注册 | [router/index.ts:18-31](file:///workspace/2026-07/smart-material-system/frontend/src/router/index.ts#L18-L31) 加 `{ path: '/browse', name: 'browse', component: BrowseView }`；支持 query `?table=fact_inventory` 初始选中 | `/browse?table=fact_inventory` 直接定位 |
| LB-2.3 分页与刷新 | `BrowseView` 分页器调 `browse/{table}?limit=100&offset=`；切换表重置 offset=0 | 翻页/切表正常 |
| LB-2.4 顶部职责说明 | `BrowseView` 顶部 `el-alert`："本页只读浏览治理发布后的标准台账（中文化列名、隐藏技术字段）。写操作请走治理中心；离线全量导出见总览页 CSV 按钮。" | 进页懂本页定位 |
| LB-2.5 空态引导 | 表无数据时显示"暂无数据，请先在 /intake 上传并在 /stage 确认发布" | 空库有明确下一步 |

### LB-3 · 首页与治理页联动

> 目标：浏览页与首页导出、治理确认闭环。

| 任务 | 落点 | 验收 |
|---|---|---|
| LB-3.1 首页导出按钮旁加"浏览"链接 | [HomeView.vue:67-76](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L67-L76) 每个导出按钮旁加 `el-button link` "浏览"跳 `/browse?table=...` | 看数据与下载数据并列 |
| LB-3.2 首页 actions 区加浏览入口 | [HomeView.vue:201-212](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue#L201-L212) actions 区加 `el-button` "台账浏览"跳 `/browse` | 总览可达浏览页 |
| LB-3.3 治理确认后提示浏览验证 | `GovernView` 各 Tab `decideMapPending` / `decideMaster` / `batchAccept` / `persistReconcile` 成功 toast 后加"去台账浏览验证"快捷链接（跳对应表） | 治理→发布→浏览验证闭环 |
| LB-3.4 侧栏菜单加浏览 | 侧栏菜单（概览→问答→...）在"指标字典"后或"报表快照"后加"台账浏览"项 | 侧栏可达 |

### LB-4 · 浏览页基础筛选排序（可选，二期）

> 目标：基础列筛选 + 排序，支持定位问题行。

| 任务 | 落点 | 验收 |
|---|---|---|
| LB-4.1 列筛选 | `browse/{table}` 加 `where` 参数（列名+操作符+值，经 `sql_guard` 校验拼 `WHERE`）；前端列头加筛选输入 | 可按列等于/包含筛选 |
| LB-4.2 列排序 | `browse/{table}` 加 `order_by` + `order_dir`（经 `sql_guard` 校验）；前端列头可点排序 | 可按列升降序 |
| LB-4.3 筛选 SQL 安全 | `where` / `order_by` 仅允许 `visible_fields` 内列名；值经参数化绑定，禁止字符串拼接 | 注入测试不通过 |

---

## 4. 与既有方案依赖

| 依赖 | 说明 |
|---|---|
| [ledger-export-plan.md](file:///workspace/2026-07/smart-material-system/roadmap/ledger-export-plan.md) | LB-1 浏览端点与该方案 CSV 导出同源（`export_table`），合并设计避免重复取数逻辑 |
| [home-govern-review.md](file:///workspace/2026-07/smart-material-system/roadmap/home-govern-review.md) HG-1.5 | LB-3.1 首页导出按钮旁加浏览链接，与 HG-1.5 跳转 hint 合并执行 |
| [metrics-home-binding.md](file:///workspace/2026-07/smart-material-system/roadmap/metrics-home-binding.md) MB-1 | LB 浏览页与 MB-1 首页指标卡片跳转互补：卡片跳指标口径、浏览跳数据明细 |
| [docs/07 §3.1](file:///workspace/2026-07/治理方案/07-界面层设计.md) | LB-2 浏览页落点补齐 07 §3.1 概览页缺失的"数据可见性"维度 |
| [docs/03](file:///workspace/2026-07/治理方案/03-接入编排与可信管道.md) | LB-3.3 治理确认后提示浏览验证，闭合 03 可信管道"发布→可见"环节 |
| [docs/12 §6](file:///workspace/2026-07/治理方案/12-出入库流水解析.md) | LB 浏览 `fact_stock_flow` 可与 `/govern` 勾稽差异互验：差异行定位回流水明细 |

---

## 5. 决策点

| ID | 决策点 | 候选 |
|---|---|---|
| ED-1 | 浏览页路由位置 | `/browse`（推荐，独立）/ `/ledger` / 嵌入概览页 Tab |
| ED-2 | 筛选排序落地节奏 | 一期只做分页（推荐，快速可见）/ 一期含基础筛选排序（LB-4 同步） |
| ED-3 | `fact_quota_adjust` 入口 | 浏览页含（推荐，补 LB-6）/ 首页导出也补该表按钮 |
| ED-4 | 浏览页是否复用 `ReportsView` | 独立页（推荐，心智清晰）/ ReportsView 加"标准表浏览"Tab |

---

## 6. 建议执行顺序

1. **LB-1.1 + LB-1.2 + LB-1.4**（后端，独立可做）：浏览端点 + 总数 + 6 表白名单。
2. **LB-2.1 + LB-2.2 + LB-2.4 + LB-2.5**（前端，依赖 LB-1）：浏览页 + 路由 + 职责说明 + 空态。
3. **LB-2.3**（前端）：分页与刷新。
4. **LB-3.1 + LB-3.2 + LB-3.4**（前端）：首页/侧栏联动。
5. **LB-3.3**（前端）：治理确认后提示浏览验证。
6. **LB-1.3**（后端）：行数上限与导出分离。
7. **LB-4.1 + LB-4.2 + LB-4.3**（后端 + 前端，二期）：筛选排序。

LB-1.1/LB-1.2/LB-1.4 三项后端改动是基础，落地后前端即可对接。一期不含筛选排序也能解决"看不到数据"的核心痛点。

---

## 7. 验收总标准

1. 新增 `/browse` 页，6 张标准表可在下拉选择并分页浏览（每页 100 行），列名中文化、枚举汉化、技术字段隐藏；
2. `fact_quota_adjust` 可浏览（补齐 LB-6）；
3. 浏览 `limit` 上限 500，不触发 `EXPORT_ROW_LIMIT`，与 CSV 导出配额分离；
4. 首页导出按钮旁有"浏览"链接，侧栏有"台账浏览"入口；
5. 治理页确认成功后有"去台账浏览验证"快捷链接，闭合治理→发布→浏览验证 loop；
6. 浏览页顶部有职责说明，空库有明确空态引导；
7. （二期）列可筛选（等于/包含）+ 排序，`where`/`order_by` 经 `sql_guard` 校验，仅允许 `visible_fields` 列名，参数化绑定；
8. 既有只读安全（`sql_guard` AST 校验、表名白名单）与口径克制（中文化、隐藏技术字段）不受影响。

---

*评审通过后按 §6 顺序执行；与 ledger-export-plan / home-govern-review HG-1.5 / metrics-home-binding MB-1 节点对齐。*
