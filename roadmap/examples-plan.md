# 示例信息建设方案（功能多、示例少 的补齐计划）

> 版本：v0.1（2026-08-09）· 状态：待评审
> 背景：项目功能规模大（API 84 路由 / services 45 模块 / 前端 12 页 / 治理文档 14+ 篇），但示例信息明显不足——样例数据仅 1 个、前端示例问题仅 2 个、评测样本 57/10/12 条。本文为补齐"示例信息"的实施方案。
> 关联：[ledger-export-plan.md](file:///workspace/2026-07/smart-material-system/roadmap/ledger-export-plan.md)（字段扩展，本方案 T1/T2 依赖）、[docs/question/06](file:///workspace/2026-07/smart-material-system/docs/question/06-数据分析与智能化能力（用户视角）.md)（能力手册）

---

## 0. 结论摘要（现状核实，2026-08-09 实测）

| 功能侧 | 数量 | 示例侧 | 数量 |
|---|---|---|---|
| API 路由 | 84 | 样例数据 `data/samples/` | 1 个文件 |
| 后端服务模块 | 45 | 评测样本 `data/eval/` | 57+10+12 条 |
| 前端页面 | 12 | 冒烟脚本（可跑证明） | 25 个 |
| 治理文档 | 14+ 篇 | 前端示例问题（AskView） | 2 个 |
| 测试用例 | 19 文件 | 业务场景演示文档 | 基本无 |

**根因**：项目定位"治理/可信管道"，开发验证靠 smoke 断言与评测分数（重正确性证明、轻用户可见示例）；且 4 表台账字段缺口未落地 → 无数据可演示 → 缺样例 → 示例问题也写不出来（恶性循环）。

---

## 1. 示例缺口清单

| 编号 | 缺口 | 现状 | 影响 |
|---|---|---|---|
| E-1 | **目标场景样例缺失** | `data/samples/` 仅 1 个库存概览单表文件 | 4 表台账（维护材料/备品备件/公用工器具/应急备汛）无演示数据、无流水文本样例、无多 sheet 异构样例 |
| E-2 | **问答示例业务性弱** | [AskView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/AskView.vue#L16-L24) 仅 2 个计数类示例按钮 | 用户看不到真实业务问题（如"哪些物资低于最低库存阈值"） |
| E-3 | **README/文档无业务演示** | [README.md](file:///workspace/2026-07/smart-material-system/README.md) 全为启动/smoke/API 清单 | 新用户无"端到端使用路径"可循 |
| E-4 | **评测样本量少** | text2sql 57 / header_mapping 10 / flow_parse 12 条 | 智能化能力证明样本不足 |
| E-5 | **smoke 无结果形态展示** | 25 个 smoke 只输出 `XXX_OK` | 业务用户看不到实际输出长什么样 |

---

## 2. 任务拆解（按依赖排序）

### T1 · 目标场景样例（依赖 ledger-export-plan 字段落地）

| 任务 | 落点 | 验收 |
|---|---|---|
| T1.1 将 4 表台账制作为 `data/samples/` 标准样例（含出入库流水文本、多 sheet、定额/最低库存/所属系统等列；脱敏） | `data/samples/` | 样例可被 intake 完整接入（字段落地后） |
| T1.2 样例接入脚本（仿 `run_real_sample.py` 一键跑通：上传→staging→confirm→release） | `scripts/run_ledger_sample.py` | 一键产出 4 表入库 + 快照 + 报表 |
| T1.3 样例即评测基线：流水解析 L1/L2、勾稽差异在样例上收敛 | `data/eval/` | 样例跑完 gap=0（或仅注明合理差异） |

### T2 · 问答示例库

| 任务 | 落点 | 验收 |
|---|---|---|
| T2.1 按能力分层建问答示例集：指标类（10 条）/明细类（10 条）/趋势类（5 条），每条标注预期 SQL 与预期列 | `data/eval/text2sql.jsonl` 扩充 + `docs/question/06` 附录 | 示例在样例库上全部可跑通 |
| T2.2 示例落库 `sql_fewshot`（文本 2SQL 走 few-shot 时天然可用） | `app/services/fewshot.py` 种子 | 新库即带示例 |
| T2.3 AskView 示例按钮升级：按"业务场景"分组展示示例问题（指标/明细/趋势），点击即问 | `frontend/src/pages/AskView.vue` | 示例 ≥10 条、可一键提问 |

### T3 · 前端引导与空态

| 任务 | 落点 | 验收 |
|---|---|---|
| T3.1 各页面空态补"无数据时的操作引导"（如"先上传样例或真实台账"） | `frontend/src/pages/*.vue` | 空库首次打开有明确下一步 |
| T3.2 HomeView 快照卡为"暂无数据"字段加提示（关联 U-3：呆滞料/库存金额） | `frontend/src/pages/HomeView.vue` | 不误导用户 |

### T4 · README 业务演示章节

| 任务 | 落点 | 验收 |
|---|---|---|
| T4.1 README 增"业务演示（5 分钟上手）"：上传样例→首页快照→Ask 问答→报表下载→治理确认，附预期输出 | `README.md` | 新用户可照做 |
| T4.2 治理方案文档 00-总览 补充"功能→示例"索引表 | `docs/00-总览.md` | 每个模块至少 1 个示例链接 |

### T5 · 评测样本扩充

| 任务 | 落点 | 验收 |
|---|---|---|
| T5.1 text2sql 样本 57→80+（覆盖指标/明细/趋势/中文条件 LIKE） | `data/eval/text2sql.jsonl` | 全量通过 ≥ 基线 1.0 |
| T5.2 header_mapping 10→30+（覆盖 4 表台账各 sheet 表头） | `data/eval/header_mapping.jsonl` | mapping ≥ 0.95 |

---

## 3. 与既有方案依赖

| 依赖 | 说明 |
|---|---|
| [ledger-export-plan](file:///workspace/2026-07/smart-material-system/roadmap/ledger-export-plan.md) T1/T3 | 4 表台账字段落库 + 多 sheet 路由，E-1 样例才能完整接入、E-2 业务问题才能回答 |
| docs/question/03 二.5（U-1~U-6） | 指标口径/汉化整改完成前，T2 部分示例（如"最低库存预警"）受字段限制，需标注"待字段落地" |
| docs/question/06 | 示例库沉淀后回写"能力手册"附录（问题示例清单） |

**串行顺序**：ledger-export-plan T1/T3 → 本方案 T1 → T2 → T3/T4/T5（可并行）。

---

## 4. 验收总标准

1. `data/samples/` 含 4 表台账标准样例，`scripts/run_ledger_sample.py` 一键跑通（上传→发布→快照→报表）；
2. 问答示例集 ≥25 条（指标/明细/趋势分层）在样例上全部可跑通；AskView 示例按钮 ≥10 条分组展示；
3. README 含可照做的"5 分钟业务演示"，治理文档 00-总览 每个模块有示例索引；
4. text2sql 样本 57→80+、header_mapping 10→30+，基线不回落；
5. 空态引导覆盖主要页面。

---

## 5. 决策点（ED-1~ED-3）

| ID | 决策点 | 候选 |
|---|---|---|
| ED-1 | 样例脱敏程度 | 原样脱敏（姓名/编码打码） / 构造合成数据（推荐，规避敏感信息） |
| ED-2 | 问答示例落库时机 | 随 T2 一步到位 / 先静态文件后逐步进 `sql_fewshot` |
| ED-3 | 示例库是否进评测门禁 | 是（示例即回归基线，推荐）/ 否（仅作演示） |

---

*评审通过后按 T1→T2→T3/T4/T5 执行；与 ledger-export-plan 字段落地节点对齐。*
