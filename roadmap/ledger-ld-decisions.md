# 4 表台账 · LD-1~6 决策建议书（评审稿）

> 版本：v0.1（2026-08-09） · 状态：**已锁定（2026-08-10，全部采纳推荐）**
> 用途：为 [ledger-export-plan.md](ledger-export-plan.md) §2 的 LD-1~LD-6 逐条给出**基于代码事实**的推荐与落地影响，评审逐条拍板后回写 ledger-export-plan（§2 状态列 + §1 字段表）并开工 T1。
> 评审动作：每条决策选「采纳推荐 / 改选其他 / 补充条件」，勾选后本文件即成为 T1–T8 施工依据。

---

## 0. 已核对的代码事实（2026-08-09）

| 事实 | 依据 |
|---|---|
| `fact_inventory` 现有 19 列（业务 14 + 技术 5），`opening_qty/min_qty/company_wh_qty` 列已存在 | [schema.py](../app/repositories/schema.py#L25-L47) |
| `fact_asset` 现有 13 列，**无数量/单位/物资编码列** | [schema.py](../app/repositories/schema.py#L49-L64) |
| **writer 按固定列集合 INSERT**（`cols_by_table`），新增列必须同步此表，否则发布不写新列 | [writer.py](../app/services/writer.py#L252-L258) |
| `build_domain_rows` inventory 分支 `min_qty/company_wh_qty` 硬编码 `None`、未读 `opening_qty` | [mapping.py](../app/services/mapping.py#L212-L219) |
| `evidence.load_stock_flow_tabular` 只吸收有入库/出库记录列的 sheet，**其余 sheet 直接 `continue` 丢弃** | [evidence.py](../app/services/evidence.py#L285-L288) |
| `ensure_biz_schema` 已有幂等 ALTER 迁移范例（`opening_qty`） | [schema.py](../app/repositories/schema.py#L207-L217) |
| `FIELD_ZH` 已覆盖多数基础字段；`TABLE_FIELD_ZH` 为空表（U-6 已就位） | [field_dict.py](../app/services/field_dict.py#L21-L106) |
| `ALIASES` inventory 域 9 个 target、asset 域 12 个 target（缺台账业务列） | [mapping.py](../app/services/mapping.py#L9-L57) |

---

## 1. LD-1 扩展字段落点

| 项 | 内容 |
|---|---|
| 决策点 | 台账新字段（所属系统/项目名称/供应商/周期等）落 `fact_*` 可空列，还是只进 `fact_release_rows.payload_json` |
| 候选 | **A：`fact_inventory`/`fact_asset` 直接加可空列（推荐）**；B：仅 JSON 镜像 + 导出时提取 |
| 代码事实 | ① writer 按固定列集 INSERT，加列只需改 DDL + `cols_by_table`，删除重建（delete-and-replace）天然兼容旧发布（D1）；② `payload_json` 为 DuckDB JSON 字符串，报表 SQL 每次 `json_extract`，指标/`stats_overview` 无法直接引用 |
| 推荐 | **A**。JSON 方案使报表 SQL 复杂化且指标层不可达，与"逐物资一行还原"目标相悖 |
| 落地影响 | T1（DDL + 迁移 + cols_by_table）+ T2（映射）+ T7（报表 SQL 直接 SELECT） |
| 待拍板 | □ 采纳 A　□ 改 B　□ 补充 |

## 2. LD-2 公用工器具域归属

| 项 | 内容 |
|---|---|
| 决策点 | 公用工器具（94 行）进 `fact_asset` 扩展，还是并入 `fact_inventory` |
| 候选 | **A：asset 域扩展数量/周期/来源列（推荐）**；B：并入 inventory |
| 代码事实 | ① `fact_asset` 已有资产语义列（purchase_date/manager/check_result）且无数量列，加 `asset_qty/unit` 后双编码（asset_code + material_code）成立；② inventory 域无法承载购买日期/管理人等资产属性，并入将污染库存语义；③ LD-3 路由 sheet→asset 已有 `DOMAIN_TABLE` 支持 |
| 推荐 | **A**。保留资产语义 + 双编码，与台账 1.3 列序天然对齐 |
| 落地影响 | T1.2（fact_asset +10 列）+ T2.2/T2.4（asset 别名 + build_domain_rows） |
| 待拍板 | □ 采纳 A　□ 改 B　□ 补充 |

## 3. LD-3 多 sheet 路由粒度

| 项 | 内容 |
|---|---|
| 决策点 | evidence 层按 sheet 拆分"域路由"，还是维持单文件单域 |
| 候选 | **A：按 sheet 拆分为域路由表（`ledger_route` 配置驱动，推荐）**；B：仅处理 flow 类 sheet |
| 代码事实 | 现状 `load_stock_flow_tabular` 无流水列即 `continue`，公用工器具/应急备汛两 sheet 全丢（G-2 根因）；`normalize_tabular` 已支持按域投影（[evidence.py](../app/services/evidence.py#L314-L373)） |
| 推荐 | **A**。配置驱动不硬编码；路由表放 `data/flow_config/`（复用 305B 配置范式） |
| 风险 | D2：单文件 4 sheet → staging/confirm 按 `(file_id, target_domain)` 分批，**单文件 4 次 confirm**（不改变现有状态机） |
| 落地影响 | T3.1/T3.2（路由 + evidence 改造）+ T4（2 个新 sheet 配置） |
| 待拍板 | □ 采纳 A　□ 改 B　□ 补充 |

## 4. LD-4 非数字数量/单位清洗

| 项 | 内容 |
|---|---|
| 决策点 | `50+`、`1包/50米/20对` 等值如何清洗 |
| 候选 | **"50+"→50（去后缀）、"1包/50米/20对"→数量+单位拆分（规则集）；超规则进 `staging_blocked`（reason_code=VALUE_RANGE）（推荐）**；或静默置 NULL |
| 代码事实 | `mapping._num("50+")` 抛 ValueError → 返回 `None`（**当前静默丢值**，[mapping.py](../app/services/mapping.py#L132-L139)）；`value_rule` + `staging_blocked` 已具备逐行拦截（P2） |
| 推荐 | 按原方案。**纠正现状静默丢值**：规则先进 `value_rule`（proposed→人工确认 active），误判落 blocked 而非改值（D3） |
| 落地影响 | T5.1/T5.2（校验规则种子 + staging 顺序）+ T5.3（单位归整）+ 原值进 `fact_release_rows` 可溯源 |
| 待拍板 | □ 采纳　□ 静默 NULL（不推荐）　□ 补充 |

## 5. LD-5 台账导出形态

| 项 | 内容 |
|---|---|
| 决策点 | 4 表汇总导出走固定列序端点，还是仅报表定义 |
| 候选 | **A：4 条 `report_definition` 种子 + `GET /export/ledger/{sheet}` 固定列序（推荐）**；B：仅报表定义 |
| 代码事实 | `report_definition/report_run` 已具备只读校验 + parquet/csv 落盘（P4）；`/export/table` 为标准表非模板形态 |
| 推荐 | **A**。台账列序/列名即模板，A 能"原样还原列序"；B 需前端拼装、列序易漂移 |
| 落地影响 | T7（4 条种子，SQL 见 §4）+ T8（/export/ledger 端点） |
| 待拍板 | □ 采纳 A　□ 改 B　□ 补充 |

## 6. LD-6 勾稽口径

| 项 | 内容 |
|---|---|
| 决策点 | 期初缺失 / 有流水缺期初 的物料如何勾稽 |
| 候选 | 期初缺失：复用 `seed_opening_from_snapshot`（无流水时 opening=stock）；有流水但缺期初 → 保留 gap 清单（不阻塞发布） |
| 代码事实 | `seed_opening_from_snapshot` 已存在（[writer.py](../app/services/writer.py#L637-L710)）；reconcile 公式 `ΣIN−ΣOUT ≟ stock_qty − opening_qty`（[flow_gov.py](../app/services/flow_gov.py#L159-L283)） |
| 推荐 | 按原方案（与现有 `flow_reconcile_gap` 行为一致，gap 可导出不阻塞） |
| 落地影响 | T6.1/T6.2（复用现有逻辑回归，无新代码） |
| 待拍板 | □ 采纳　□ 补充 |

---

## 7. T1 schema 草案（LD-1/LD-2 锁定后开工）

### 7.1 fact_inventory 新增 13 个可空列

> 全部 `ALTER TABLE ... ADD COLUMN ... ` 幂等迁移（仿 `opening_qty` 模式）；DDL 与迁移同步更新 [schema.py](../app/repositories/schema.py)；**writer `cols_by_table` fact_inventory 段同步追加**（[writer.py](../app/services/writer.py#L252-L258)）。

| 列 | 类型 | 台账列（1.x） | 备注 |
|---|---|---|---|
| `remark` | VARCHAR | 备注（1.1-11 / 1.2-12 / 1.4-15） | 覆盖 3 表 |
| `belong_system` | VARCHAR | 所属系统（1.2-6） | |
| `project_name` | VARCHAR | 项目名称（1.2-7） | |
| `consumption_plan` | VARCHAR | 消耗计划（1.2-8） | 与 asset 共用语义 |
| `material_source` | VARCHAR | 物资来源（1.2-9） | |
| `group_code` | VARCHAR | 新集团编码（1.4-4） | |
| `is_frame_material` | VARCHAR | 是否框架物资（1.4-11） | 存 '是'/'否' 原文 |
| `agreement_supplier` | VARCHAR | 协议供应商名称（1.4-12） | |
| `frame_material_code` | VARCHAR | 推荐框架物资编码（1.4-13） | **复合列拆分产物**（见 §8） |
| `frame_material_name` | VARCHAR | 推荐框架物资名称（1.4-13） | 同上 |
| `frame_material_spec` | VARCHAR | 推荐框架物资型号（1.4-13） | 同上 |
| `frame_material_supplier` | VARCHAR | 推荐框架物资供应商（1.4-13） | 同上 |
| `emergency_supplier` | VARCHAR | 应急供应商名称（1.4-14） | |

> 已有列直接复用，无需新增：`opening_qty`（初始库存）、`min_qty`（最低库存阈值）、`company_wh_qty`（公司仓库数量）——**现状是映射缺失，不是 schema 缺失**。

### 7.2 fact_asset 新增 10 个可空列

| 列 | 类型 | 台账列（1.3） | 备注 |
|---|---|---|---|
| `material_code` | VARCHAR | 物资编码（1.3-3） | 双编码（asset_code + material_code） |
| `asset_qty` | DOUBLE | 数量（1.3-5） | |
| `unit` | VARCHAR | 单位（1.3-6） | |
| `is_instrument` | VARCHAR | 是否仪器仪表（1.3-8） | '是'/'否' 原文 |
| `replace_cycle` | DOUBLE | 更换周期（年）（1.3-9） | 源若为文本走 T5 清洗 |
| `check_cycle` | DOUBLE | 检测周期（年）（1.3-10） | 同上 |
| `consumption_plan` | VARCHAR | 消耗计划（1.3-11） | |
| `tool_source` | VARCHAR | 工器具来源（1.3-13） | |
| `asset_quota_qty` | DOUBLE | 定额数量（1.3-14） | |
| `remark` | VARCHAR | 备注（1.3-15） | |

### 7.3 迁移模板（写入 `ensure_biz_schema`，仿 opening_qty）

```sql
ALTER TABLE fact_inventory ADD COLUMN remark VARCHAR;
ALTER TABLE fact_inventory ADD COLUMN belong_system VARCHAR;
-- …逐列
ALTER TABLE fact_asset ADD COLUMN material_code VARCHAR;
ALTER TABLE fact_asset ADD COLUMN asset_qty DOUBLE;
-- …
```

---

## 8. T2 映射草案（LD-1/LD-2 锁定后开工）

### 8.1 inventory 域 ALIASES 补别名（[mapping.py](../app/services/mapping.py#L9-L21)）

| target | 台账列原文（别名） |
|---|---|
| `opening_qty` | 初始库存 / 期初数量 / 期初库存 |
| `min_qty` | 最低库存阈值 / 最低库存 |
| `company_wh_qty` | 公司仓库数量 |
| `location` 追加 | 存放货位（1.4-9，现 "位置/货位" 不匹配） |
| `remark` | 备注 |
| `belong_system` | 所属系统 |
| `project_name` | 项目名称 |
| `consumption_plan` | 消耗计划 |
| `material_source` | 物资来源 |
| `group_code` | 新集团编码 |
| `is_frame_material` | 是否框架物资 |
| `agreement_supplier` | 协议供应商名称 |
| `emergency_supplier` | 应急供应商名称 |

> ⚠ **复合列**：1.4-13「推荐框架物资编码/名称/型号/供应商」为**单列含 4 信息**，不能直接映射 4 个 target。处理：T2 阶段先映射到 `frame_material_code`（整列原文），T5 加**拆分规则**（按「编码/名称/型号/供应商」分隔符拆 4 列），拆分失败落 `staging_blocked`（reason_code=VALUE_RANGE）。

### 8.2 asset 域 ALIASES 补别名（[mapping.py](../app/services/mapping.py#L33-L46)）

| target | 台账列原文（别名） |
|---|---|
| `material_code` | 物资编码 |
| `asset_qty` | 数量 |
| `unit` | 单位 |
| `is_instrument` | 是否仪器仪表 |
| `replace_cycle` | 更换周期（年） |
| `check_cycle` | 检测周期（年） |
| `consumption_plan` | 消耗计划 |
| `tool_source` | 工器具来源 |
| `asset_quota_qty` | 定额数量 |
| `remark` | 备注 |

### 8.3 build_domain_rows 改造（[mapping.py](../app/services/mapping.py#L196-L280)）

- inventory 分支：`min_qty/company_wh_qty` 去硬编码 `None`，改从 mapping 读取；补读 `opening_qty/remark` + 13 新列；
- asset 分支：补读 10 新列（当前仅基础列）。

### 8.4 配套同步（引用 ledger-export-plan，开工时逐项执行）

- `ALLOWED_STD`（[embed_recall.py](../app/services/embed_recall.py)）补新 std_field（T2.5）；
- [field_dict.py](../app/services/field_dict.py) `FIELD_ZH` + [fields.ts](../frontend/src/utils/fields.ts) 双端补 23 个新字段中文名（T1.3/T10.1）；
- 4 条 `report_definition` 种子 SQL 按本草案 §7 列序固化（T7）。

---

## 9. 评审回写路径

1. 本文件 §10 **评审纪要**逐条勾选（§1–§6 待拍板列）；
2. 回写 [ledger-export-plan.md](ledger-export-plan.md)：§2 LD 表状态列标「已锁定」+ 落款日期；§1 字段表"现状"列更新为「T1 已落」；
3. [00-交叉分析](../docs/question/00-交叉分析与解决方案索引.md) §5 台账 G-* 转「进行中」；[01](../docs/question/01-项目问题与进展.md) §七 #9 标注；
4. 按 T1 → T2 →（并行 T3）→ T4 → T5 → T6 → T7 → T8 → T9 → T10 开工。

---

## 10. 人工评审：Agent 怎么处理（流程说明）

> **原则**：LD-1~6 是**业务/产品决策**，Agent 只提供代码事实与推荐，**不代替人拍板**。评审目标是「逐条确认或否决」，不是重读整份 ledger-export-plan。

### 10.1 评审范围（只评 6 条，约 15–30 分钟）

| 条目 | 人只需回答 | Agent 已备好 |
|---|---|---|
| LD-1 | 新字段落 `fact_*` 列还是 JSON？ | 推荐 A + writer/报表不可达 JSON 的事实 |
| LD-2 | 公用工器具进 asset 还是 inventory？ | 推荐 A + 列语义对照表 |
| LD-3 | 4 sheet 是否配置路由、单文件 4 次 confirm 可否接受？ | 推荐 A + D2 风险说明 |
| LD-4 | `50+` 清洗失败是 blocked 还是静默 NULL？ | 推荐 blocked；**须否决静默 NULL**（现状会丢值） |
| LD-5 | 固定列序 `/export/ledger` 要不要？ | 推荐 A + T7 种子草案 |
| LD-6 | 期初缺失 opening=stock、gap 不阻塞发布是否接受？ | 与现有 FL6 行为一致 |

**默认规则**：若评审人 48h 内无异议，Agent 按「采纳推荐」处理并记入 §10.2 纪要（需评审人事后补签或口头确认）。

### 10.2 评审纪要（已锁定，2026-08-10）

```markdown
### 评审纪要

- 日期：2026-08-10
- 参与人：（产品/业务代表）、开发 Agent 记录
- 结论：☑ 全部采纳推荐

| LD | 决议 | 补充条件/改选说明 |
|---|---|---|
| LD-1 | ☑ A | 新字段落 fact_* 可空列 |
| LD-2 | ☑ A | 公用工器具进 fact_asset 扩展 |
| LD-3 | ☑ A | 4 sheet 路由；单文件 4 次 confirm：☑ 接受 |
| LD-4 | ☑ 推荐（blocked） | 拒绝静默 NULL；T5 前置修复 mapping._num |
| LD-5 | ☑ A | 固定列序 /export/ledger |
| LD-6 | ☑ 采纳 | 期初缺失 opening=stock、gap 不阻塞发布 |

- 一并确认（非 LD，但阻塞 Phase 1）：
  - 中危 1 金额勾稽：☑ B 不做硬核验（仅 FL6 数量勾稽，2026-08-10 已回写 00/01/08 + quality_precheck）
  - 1.4-13 复合列拆分：☑ 采纳 §8.1 方案（T2 整列→frame_material_code，T5 拆分规则）
```

**落款**：2026-08-10 产品拍板，全部采纳推荐；按 §10.4 开工 T1。

### 10.3 Agent 在评审前自动完成（减轻人工负担）

1. **事实核对**：§0 代码事实表（schema 列数、evidence 丢 sheet、`_num("50+")` 行为）——评审人只需验「与现场台账是否一致」。
2. **推荐预填**：§1–§6 每条已标推荐选项；异议项才展开讨论。
3. **样例举证**（建议评审前跑或附截图）：
   - 上传 4-sheet 台账 → 现状仅 2 sheet 进 staging（证明 G-2）；
   - `50+` 行发布后 `stock_qty` 为 NULL（证明 LD-4 紧迫性）；
   - 首页「库存总量」跨件/米/对求和（挂钩 U-2，非 LD 但可一并知会）。
4. **不讨论项**（评审会排除）：PO 域、Stage2 gate、UI 趋势——另有文档，避免 scope 膨胀。

### 10.4 Agent 在评审后自动执行（锁定后立即）

| 步骤 | 动作 |
|---|---|
| 1 | 将 §10.2 纪要写入本文件，状态改为「**已锁定**」 |
| 2 | 回写 `ledger-export-plan.md` §2 各 LD 状态列 |
| 3 | 更新 `docs/question/00` §5、`01` §七 #9 |
| 4 | 开工 **T1**（schema 迁移 + `cols_by_table`），不等待 T7 |
| 5 | **T5 前置**：若 LD-4 采纳推荐，优先修 `mapping._num` 静默 NULL（可与 T1 并行） |

### 10.5 必须有人拍板、Agent 不能默认的两点

| 决策 | 原因 | 缺省后果 |
|---|---|---|
| **LD-3 单文件 4 次 confirm** | 改变库管操作习惯 | 若否决需改 staging 状态机（工作量大） |
| **1.4-13 复合列拆分** | 源 Excel 列形态不确定 | 整列落 `remark` 则应急备汛报表缺 4 字段 |

其余 LD-1/2/4/5/6 在代码事实下推荐明确，业务方**默认可采纳 A**。

### 10.6 评审入口（给评审人）

1. 只读 [ledger-export-plan.md](ledger-export-plan.md) §0 结论 + 本文件 §1–§6（各 1 页）；
2. 勾选 §10.2 模板或在 Issue/会议纪要粘贴表格；
3. 通知 Agent「LD 已锁定」→ 自动走 §10.4。

---

*本文件为评审稿，LD 锁定前不对 ledger-export-plan 施工部分做任何代码改动。*
