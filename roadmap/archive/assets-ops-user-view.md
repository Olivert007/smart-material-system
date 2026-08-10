# 自学习资产与运维面板的用户视角方案

> 版本：v0.1（2026-08-10）· 状态：待评审
> 视角：**用户视角**（治理员 / 模型运维 / Ops 三层受众）
> 范围：`frontend/src/pages/AssetsView.vue`、`frontend/src/pages/OpsView.vue`
> 关联：[metrics-home-binding.md](file:///workspace/2026-07/smart-material-system/roadmap/metrics-home-binding.md)、[home-govern-review.md](file:///workspace/2026-07/smart-material-system/roadmap/home-govern-review.md)、[user-perspective-analysis.md](file:///workspace/2026-07/smart-material-system/roadmap/user-perspective-analysis.md)（U-9/U-10）、[docs/04 §6](file:///workspace/2026-07/治理方案/04-治理Copilot与自学习.md)、[docs/07 §3.5/§3.6](file:///workspace/2026-07/治理方案/07-界面层设计.md)、[docs/06 §8/§9](file:///workspace/2026-07/治理方案/06-运维手册.md)

---

## 0. 结论摘要

自学习资产与运维面板都是"后端表/JSON 的前台镜像"，不是"用户问题的解答"，存在 3 类问题：

1. **自学习资产埋没产品卖点**：本该讲"人工修正即资产、系统越用越准"的闭环故事（04 §6），但四个 Tab 只做表直读，`hits` 列只显示数字不说明"命中即省一次 LLM 调用"，用户看完不知道这些表怎么让系统变聪明。
2. **运维面板偏离用户目标**：文档要求"看服务是否健康"6 项（任务队列/显存/告警/成本/验收清单/状态卡片），实际只做 2 项，却塞进大量"血缘审计"高级操作（release 重建/吊销/diff/supersede/修正），把简单仪表盘搞成 Ops 高级控制台。
3. **两页充斥开发术语**：物理表名做卡片标题（`rule_dict`/`flow_example`/`govern_confirm`/`sql_fewshot`）、JSON key 直接渲染（`meta_db`/`biz_db`/`worker`/`frontend_dist`）、英文角色编码（`big`/`fast`/`embed`）、未翻译术语（`supersedes`/`superseded_by`/`sql_gold`/`few-shot`/`落盘`/`原地 UPDATE`）。

**结论**：按本文 AO-1 / AO-2 / AO-3 修改后，自学习资产讲清闭环故事，运维面板补齐健康仪表盘并拆走高级操作，两页术语按角色分层，且不破坏既有可信流水线。

---

## 1. 两个页面的业务含义

### 1.1 自学习资产 = "系统越用越准"的资产账

[04 §6](file:///workspace/2026-07/治理方案/04-治理Copilot与自学习.md) 核心命题"**人工修正即资产**"：每次治理员确认一条表头映射 / 流水拆解 / SQL 修正，回写进资产表，下次同输入直接命中、不再调 LLM。这是项目区别于一次性 ETL 工具的产品卖点。

四个 Tab 的闭环价值（本该讲的故事）：

| Tab | 物理表 | 闭环价值 |
|---|---|---|
| 规则字典 | `rule_dict` | 确认"库位→location"后，下次任何文件"库位"表头自动命中，不调 embed/LLM |
| 流水示例 | `flow_example` | 确认"领用 5 件"→OUT/qty=5 后，下次同文本直接复用，不耗 LLM |
| 确认历史 | `govern_confirm` | 谁在何时确认了什么——审计 + 回溯 |
| SQL few-shot | `sql_fewshot` | 问答修正的 SQL 进池，下次类似问题模板填参 |

### 1.2 运维面板 = "服务是否健康"的仪表盘

[07 §3.6](file:///workspace/2026-07/治理方案/07-界面层设计.md) 定位"看服务是否健康"，列 6 项该有：状态卡片 / 任务队列 / 显存占用 / 告警面板 / LLM 成本统计 / 验收清单。

---

## 2. "像给程序员看"的具体证据

### 2.1 自学习资产 `AssetsView.vue`

| 位置 | 程序员视角证据 |
|---|---|
| `AssetsView.vue:7-8` alert | `自学习资产（07 §3.5）` + `只读浏览 rule_dict / flow_example / 确认历史。few-shot 池待评测集扩容后落表。` —— `07 §3.5`/`rule_dict`/`flow_example`/`few-shot 池`/`落表` 全是内部模块号、物理表名、开发术语 |
| `AssetsView.vue:12-15` Tab 标签 | `规则字典` / `流水示例` / `确认历史` / `SQL few-shot` —— 前三个中文化，第四个 `SQL few-shot` 是裸开发术语 |
| `AssetsView.vue:22,56,90,126` 卡片标题 | `rule_dict` / `flow_example` / `govern_confirm` / `sql_fewshot` —— 四个卡片标题全是物理表名 |
| `AssetsView.vue:30-36` 规则字典表头 | ~~`header` / `std_field` / `business_domain` / `hits` / `source` / `confirmed_by` —— 全英文列名~~ **已过时（2026-08-10 复核）**：`label` 已是中文（`表头`/`标准字段`/`域`/`命中`/`来源`/`确认人`），英文仅 `prop` 数据绑定 |
| `AssetsView.vue:93-94` 确认历史筛选 | `flow_confirm` / `map_confirm` —— 英文枚举做选项 |
| `AssetsView.vue:138-141` few-shot 表头 | ~~`question_type` / `question` / `sql_gold` / `hits` —— `sql_gold`（金标 SQL）是纯开发术语~~ **已过时（2026-08-10 复核）**：`label` 已是中文（`类型`/`问题`/`金标 SQL`/`命中`） |
| 整页 | **没有一句话说明"自学习"是什么意思**——为什么这几张表叫"自学习资产"？它们怎么让系统越用越准？ |

### 2.2 运维面板 `OpsView.vue`

| 位置 | 程序员视角证据 |
|---|---|
| `OpsView.vue:7-8` alert | `运维 / 模型 / 血缘` + `只读探测 + Ops Token 写操作（备份、通用血缘 rebuild）。前端不直连 vLLM / DuckDB。` —— `血缘`/`rebuild`/`vLLM`/`DuckDB` 全是技术术语 |
| `OpsView.vue:19-28` 服务就绪 | `status` / `version` / `meta_db` / `biz_db` / `worker` / `frontend_dist` —— 全英文 key，`meta_db`/`biz_db` 是数据库名，`frontend_dist` 是构建产物名 |
| `OpsView.vue:44-51` 模型探测 | `role` 列显示 `big`/`embed`/`fast` —— 英文角色编码；`note` 列出现 `lexical fallback on` / `Stage 2+` |
| `OpsView.vue:66-78` 流水统计 | `published` / `L1 ratio` / `pending` / `L1/L2/L3` / `suspicious` —— 全英文标签，L1/L2/L3 无释义 |
| `OpsView.vue:100` 重建输入框 | `release_id（全域吊销/重建，禁止原地 UPDATE）` —— "原地 UPDATE"是 SQL 术语 |
| `OpsView.vue:116-121` 发布表表头 | `release_id` / `target_domain` / `clean_rows` / `supersedes` / `superseded_by` —— "supersedes/superseded_by"未翻译 |
| `OpsView.vue:124-127` 版本 diff | `release_a` / `release_b` / `版本 diff` / `标记 supersede` —— "supersede"未翻译 |
| `OpsView.vue:131-135` 修正提案 | `correction_id` / `row_key` / `field` / `value_new` —— 全英文字段名做 placeholder |
| `OpsView.vue:182` 备份 hint | `备份落盘路径见返回 JSON` —— "落盘"、"返回 JSON"是技术术语 |

---

## 3. "跟系统功能没绑定"的表现

### 表现 1：自学习资产只展示表，不讲闭环故事

四个 Tab 都是"只读浏览一张表"，但**没有任何一处说明这些表怎么参与系统运行**：

- 用户看到 `rule_dict` 里"库位→location hits=12"，不知道"hits=12 意味着 12 个文件的'库位'表头被自动命中、省了 12 次 LLM 调用"。
- 用户看到 `flow_example` 里"领用 5 件→OUT/qty=5 hits=8"，不知道"hits=8 意味着 8 次同文本直接复用、不耗 LLM"。
- `AssetsView.vue:33` 有 `hits` 列，表头只写"命中"两字，没说命中之后发生什么。

**结果**：用户看完只知道"系统存了一堆映射"，看不出"自学习"这个产品卖点——本该是项目亮点，却因只展示静态表而埋没。

### 表现 2：运维面板该有的没有，不该有的塞满

| 文档要求（07 §3.6） | 实现状态 |
|---|---|
| 状态卡片（embed/fast/big 存活） | ✅ `OpsView.vue:32-53` |
| 任务队列（pending/processing/failed 计数） | ❌ 无 |
| 显存占用时序图 | ❌ 无 |
| 告警面板（06 §8） | ❌ 无 |
| LLM 成本统计 | ❌ 无 |
| 验收清单（06 §9） | ❌ 无 |

实际做的：服务就绪 + 模型探测 + 流水统计 + **血缘审计（`OpsView.vue:97-171`，占近一半篇幅）** + 备份。

**问题**：血缘审计（release 重建/吊销/diff/supersede/修正提案）是 Ops 高级操作，和"看服务是否健康"几乎无关。想确认"系统还活着吗"的用户，进来看到 `release_id / supersedes / 禁止原地 UPDATE / 标记 supersede`，完全偏离预期。

### 表现 3：两页都把内部数据模型当展示对象

- 自学习资产：四个 Tab = 四张 meta 表直读，列名用物理列名（`header`/`std_field`/`business_domain`/`question_type`/`sql_gold`）。
- 运维面板：服务就绪 = `healthReady()` 返回的 JSON key 直接渲染（`meta_db`/`biz_db`/`worker`/`frontend_dist`）；修正提案 = 物理字段名做 placeholder（`row_key`/`field`/`value_new`）。

**根因**：两页是"后端表/JSON 的前台镜像"，不是"用户问题的解答"。用户问"系统学到了什么 / 系统健康吗"，页面给的是"这是 rule_dict 表 / 这是 healthReady 返回"。

---

## 4. 任务拆解

### AO-1 · 自学习资产讲清闭环故事

> 目标：四个 Tab 不再是表直读，而是讲"人工修正→回写→下次自动命中→省 LLM"的闭环。

| 任务 | 落点 | 验收 |
|---|---|---|
| AO-1.1 顶部 alert 讲闭环 | [AssetsView.vue:7-8](file:///workspace/2026-07/smart-material-system/frontend/src/pages/AssetsView.vue#L7-L8) alert 改"每次确认都让系统更准：表头映射 / 流水拆解 / SQL 修正确认后回写，下次同输入自动命中、不耗 LLM。本页只读浏览这些资产。" 删掉 `07 §3.5`/`rule_dict`/`flow_example`/`few-shot 池`/`落表` | 进页第一眼懂"自学习"价值 |
| AO-1.2 每个 Tab 加"命中之后"说明 | 各 Tab 卡片 header 下方加 hint：规则字典"hits=该表头被自动命中的次数，命中即省一次 LLM 调用"；流水示例"hits=该原文被直接复用的次数，复用即不耗 LLM"；few-shot"hits=该示例被选为模板的次数" | hits 列有语义 |
| AO-1.3 卡片标题改中文 | [AssetsView.vue:22,56,90,126](file:///workspace/2026-07/smart-material-system/frontend/src/pages/AssetsView.vue#L22) `rule_dict`→`表头映射规则`、`flow_example`→`流水拆解示例`、`govern_confirm`→`确认历史`、`sql_fewshot`→`问答 SQL 示例` | 卡片标题无物理表名 |
| AO-1.4 Tab 标签去开发术语 | [AssetsView.vue:15](file:///workspace/2026-07/smart-material-system/frontend/src/pages/AssetsView.vue#L15) `SQL few-shot`→`问答 SQL 示例` | Tab 标签无开发术语 |
| AO-1.5 表头英文列名改中文 | ~~[AssetsView.vue:30-36,138-141](file:///workspace/2026-07/smart-material-system/frontend/src/pages/AssetsView.vue#L30-L36)~~ **已过时（2026-08-10 复核）**：表头 `label` 已是中文（`表头`/`标准字段`/`域`/`命中`/`来源`/`确认人`/`类型`/`问题`/`金标 SQL`），英文仅 `prop` 数据绑定。本任务取消 | ~~已无需改~~ |
| AO-1.6 确认历史筛选改中文 | [AssetsView.vue:93-94](file:///workspace/2026-07/smart-material-system/frontend/src/pages/AssetsView.vue#L93-L94) `flow_confirm`→`流水确认`、`map_confirm`→`映射确认` | 筛选项无英文枚举 |
| AO-1.6 确认历史筛选改中文 | [AssetsView.vue:93-94](file:///workspace/2026-07/smart-material-system/frontend/src/pages/AssetsView.vue#L93-L94) `flow_confirm`→`流水确认`、`map_confirm`→`映射确认` | 筛选项无英文枚举 |

### AO-2 · 运维面板补齐健康仪表盘

> 目标：首屏只留"服务健康"信息，补齐文档要求的任务队列/告警/成本。

| 任务 | 落点 | 验收 |
|---|---|---|
| AO-2.1 补任务队列计数 | [OpsView.vue:11-30](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue#L11-L30) 服务就绪卡下方加"任务队列"卡：pending/processing/failed 计数（新增 `GET /api/v1/ops/tasks` 或复用现有 tasks 接口） | 任务队列可见 |
| AO-2.2 补告警面板 | [OpsView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue) 新增"告警"卡：active 告警列表（任务卡死/模型连续失败/配额耗尽/口径冲突/显存磁盘阈值），按规则分组（对齐 06 §8） | 告警可见 |
| AO-2.3 补 LLM 成本统计 | [OpsView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue) 新增"LLM 成本"卡：每日调用次数/token/降级熔断次数趋势（对齐 01 §5.7） | 成本可见 |
| AO-2.4 服务就绪 key 改中文 | [OpsView.vue:19-28](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue#L19-L28) `meta_db`→`元数据库`、`biz_db`→`业务数据库`、`worker`→`后台任务`、`frontend_dist`→`前端构建`、`status`→`状态`、`version`→`版本` | 服务就绪无英文 key |
| AO-2.5 模型角色改中文 | [OpsView.vue:44-51,240-265](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue#L44-L51) `big`/`fast`/`embed`→`主模型`/`快速模型`/`向量模型`；`note` 列 `lexical fallback on`→`词法兜底`、`Stage 2+`→`阶段 2+` | 模型区无英文角色 |
| AO-2.6 流水统计标签改中文 | [OpsView.vue:66-78](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue#L66-L78) `published`→`已发布`、`L1 ratio`→`L1 占比`、`pending`→`待确认`、`suspicious`→`可疑行`，L1/L2/L3 加 tooltip 释义 | 流水统计无英文标签 |
| AO-2.7 alert 去技术术语 | [OpsView.vue:7-8](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue#L7-L8) 改"查看服务健康状态；高危操作（备份/版本回滚）需 Ops Token" 删掉 `vLLM`/`DuckDB`/`血缘 rebuild` | alert 无技术术语 |

### AO-3 · 运维面板拆走高级操作

> 目标：血缘审计（release 重建/吊销/diff/supersede/修正）不挤占健康仪表盘首屏。

| 任务 | 落点 | 验收 |
|---|---|---|
| AO-3.1 血缘审计拆独立页（推荐） | 将 [OpsView.vue:97-171](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue#L97-L171) 血缘审计区（重建/吊销/diff/supersede/修正提案）整体迁到新页 `LineageView.vue`（路由 `/lineage`）；运维面板只留服务就绪/模型/任务队列/告警/成本/备份 | 运维首屏只剩健康信息；高级操作在独立页 |
| AO-3.2 （备选）血缘审计折叠 | 保留在 OpsView，但 [OpsView.vue:97](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue#L97) 血缘审计卡改为默认折叠 `el-collapse`，标题"高级操作：版本回滚 / 行级修正（Ops 专用）" | 首屏不见高级操作，需手动展开 |
| AO-3.3 血缘审计术语中文化 | [OpsView.vue:100,116-121,124-135](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue#L100) `release_id`→`发布版本号`、`supersedes`→`取代`、`superseded_by`→`被取代`、`clean_rows`→`行数`、`target_domain`→`域`、`correction_id`→`修正编号`、`row_key`→`行标识`、`field`→`字段`、`value_new`→`新值`、`禁止原地 UPDATE`→`按域删除重建，不直接改原表` | 血缘审计无未翻译术语 |
| AO-3.4 备份 hint 去技术术语 | [OpsView.vue:182](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue#L182) `备份落盘路径见返回 JSON` 改"备份文件保存路径见下方结果" | 备份区无技术术语 |

---

## 5. 与既有方案依赖

| 依赖 | 说明 |
|---|---|
| [user-perspective-analysis.md](file:///workspace/2026-07/smart-material-system/roadmap/user-perspective-analysis.md) U-9 | AO-2.2 告警面板与 U4.2 `/audit` 全局审计视图互补，合并设计避免重复 |
| [user-perspective-analysis.md](file:///workspace/2026-07/smart-material-system/roadmap/user-perspective-analysis.md) U-10 | AO-2.2 告警面板含"流水可疑行订阅"，与 U4.3 SSE 推送对齐 |
| [home-govern-review.md](file:///workspace/2026-07/smart-material-system/roadmap/home-govern-review.md) HG-1.3 | AO-2.5 模型角色中文化与 HG-1.3 首页模型卡精简、metrics-home-binding MB-3.3 合并执行 |
| [metrics-home-binding.md](file:///workspace/2026-07/smart-material-system/roadmap/metrics-home-binding.md) MB-3.2 | AO-2.6 L1/L2/L3 释义与 MB-3.2 首页 L1/L2/L3 释义同口径，统一文案 |
| [docs/04 §6](file:///workspace/2026-07/治理方案/04-治理Copilot与自学习.md) | AO-1.1/1.2 闭环故事文案对齐 04 §6"人工修正即资产" |
| [docs/07 §3.5/§3.6](file:///workspace/2026-07/治理方案/07-界面层设计.md) | AO-1 落点对齐自学习资产定义；AO-2 补齐 07 §3.6 列的 6 项 |
| [docs/06 §8/§9](file:///workspace/2026-07/治理方案/06-运维手册.md) | AO-2.2 告警规则对齐 06 §8；AO-2.3 成本统计对齐 01 §5.7 |

---

## 6. 决策点

| ID | 决策点 | 候选 |
|---|---|---|
| ED-1 | 血缘审计归属 | AO-3.1 拆独立 `/lineage` 页（推荐，心智清晰）/ AO-3.2 OpsView 内折叠（成本低） |
| ED-2 | 任务队列/告警/成本数据源 | 新增后端接口（推荐，对齐 07 §3.6）/ 复用现有 `/ops/status` 扩展字段 |
| ED-3 | AO-1.2 "命中之后"说明位置 | 每个 Tab 卡片 header 下方 hint（推荐）/ 表头 `hits` 列加 tooltip |

---

## 7. 建议执行顺序

1. **AO-1.1 + AO-1.4 + AO-2.7**（前端独立，立即改善两页第一印象）：自学习 alert 讲闭环 + few-shot Tab 改中文 + 运维 alert 去技术术语。
2. **AO-1.3 + AO-1.6**（前端独立）：自学习卡片标题/筛选改中文。（AO-1.5 已过时取消：表头 `label` 已是中文）
3. **AO-2.4 + AO-2.5 + AO-2.6 + AO-3.4**（前端独立）：运维服务就绪/模型/流水统计/备份 hint 改中文。
4. **AO-1.2**（前端独立，依赖 ED-3）：各 Tab 加"命中之后"说明。
5. **AO-3.3**（前端独立）：血缘审计术语中文化。
6. **AO-3.1 或 AO-3.2**（前端，依赖 ED-1）：血缘审计拆走或折叠。
7. **AO-2.1 + AO-2.2 + AO-2.3**（前端 + 后端，依赖 ED-2）：补任务队列/告警/成本。

AO-1.1 / AO-1.4 / AO-2.7 / AO-1.3 / AO-1.6 / AO-2.4 / AO-2.5 / AO-2.6 / AO-3.4 九项无决策依赖、无后端改动，可作为第一批落地。（AO-1.5 已过时取消）

---

## 8. 验收总标准

1. 自学习资产顶部 alert 讲清"人工修正→回写→下次自动命中→省 LLM"闭环，无 `07 §3.5`/`rule_dict`/`flow_example`/`few-shot 池`/`落表`；
2. 自学习资产四个 Tab 各有"命中之后"说明，`hits` 列有语义；卡片标题/表头/Tab 标签/筛选无物理表名或英文术语；
3. 运维面板首屏为"服务健康"信息（服务就绪/模型/任务队列/告警/成本），无 `release_id`/`supersedes`/`原地 UPDATE` 等高级操作挤占；
4. 运维面板补齐 07 §3.6 要求的任务队列/告警/成本（显存/验收清单可二期）；
5. 服务就绪/模型/流水统计/备份区无英文 key 或未翻译术语；模型角色为中文；
6. 血缘审计拆独立页或折叠区，术语中文化，不污染健康仪表盘；
7. 既有可信流水线（Ops Token 写操作、血缘 delete-and-replace、备份）不受影响。

---

*评审通过后按 §7 顺序执行；与 user-perspective-analysis U-9/U-10 / home-govern-review HG-1.3 / metrics-home-binding MB-3 节点对齐。*
