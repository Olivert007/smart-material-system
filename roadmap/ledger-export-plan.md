# 通信分部 4 表台账 · 汇总导出能力建设 · 实施方案

> 版本：v0.6（2026-08-10） · 状态：**实施中（LD-1~6 已锁定，T1~T8/T9.1/T10 已落地）**
> 目标：让系统能够**按"逐物资一行"还原/产出**《通信部成都分部工器具、低值易耗品、备品备件、维护材料、应急备汛物资台账》（4 张工作表：维护材料 492 行 / 备品备件 246 行 / 公用工器具 94 行 / 应急备汛物资 10 行），即"最后汇总数据"。
> 原则：与既有 roadmap 一致——**LLM 只建议、人工确认才写**；**禁原地 UPDATE 事实行**；所有变更走现有 meta 表 + 幂等写入范式；复用 P1–P4 已就绪能力（value_rule / staging_blocked / report_definition / release diff 等）。

---

## 0. 结论摘要（能力判定）

- **系统具备 80% 底座**：星型模型（`fact_inventory` + `fact_stock_flow` + `dim_material` + `fact_asset`）、305B 流水配置（[305b_weihu.json](file:///workspace/2026-07/smart-material-system/data/flow_config/305b_weihu.json) / [305b_beipin.json](file:///workspace/2026-07/smart-material-system/data/flow_config/305b_beipin.json)）、勾稽对账、报表/导出/Text2SQL 均已就绪。
- **当前不能直接产出该台账**，缺三块：
  1. **字段缺口**：备品备件的所属系统/项目名称/消耗计划/物资来源、公用工器具的数量/是否仪器仪表/更换周期/检测周期/工器具来源、应急备汛的新集团编码/框架物资/供应商 等业务列无 schema 落点（现仅能进 `fact_release_rows` JSON 镜像，无法参与报表 SELECT）。
  2. **多 sheet 异构路由不完整**：~~[evidence.py](file:///workspace/2026-07/smart-material-system/app/services/evidence.py#L260-L311) 的 `load_stock_flow_tabular` 只吸收带"入库/出库记录"的工作表（维护材料、备品备件），**公用工器具、应急备汛物资两个 sheet 会被丢弃**，回退只读第 1 张表~~ → **T3 已解决（2026-08-10）**：路由表 + 路由感知 `load_stock_flow_tabular`，4 sheet 全部按域提取。
  3. **输出端无模板**：现有 `/export/table` + 报表定义为"标准表/自定义 SQL"形态，无"固定列序 + 列名 = 台账模板"的导出。
- **结论**：按本文 T1–T10 补齐后，系统可稳定产出与源台账行数一致、字段齐全的 4 表汇总数据；原样还原 Excel 公式列/合并表头/隐藏列**不在能力范围内**（输出为数据表，模板样式由前端/Excel 层负责）。

---

## 1. 台账结构与字段映射（4 张表）

> **T1/T2 已落（2026-08-10，LD-1~6 锁定后）**：§7.1/§7.2 全部列已入库（schema.py DDL + 幂等迁移 + writer cols_by_table）；§8.1/§8.2 别名已进 ALIASES；§8.4 ALLOWED_STD/FIELD_ZH/fields.ts 已同步；`50+` 去后缀修复（LD-4 前置）。下表现状列 ❌ 项均已随 T1/T2 落地，待真实 4-sheet 台账重放验证。

### 1.1 维护材料（492 行 · 域=inventory + stock_flow）

| # | 台账列 | 系统落点 | 现状 |
|---|--------|----------|------|
| 1 | 名称 | `dim_material.material_name` | ✅ [ALIASES](file:///workspace/2026-07/smart-material-system/app/services/mapping.py#L11) |
| 2 | 品牌型号规格 | `dim_material.spec` | ✅ |
| 3 | 现有库存 | `fact_inventory.stock_qty` | ✅（含"现有库存"别名；⚠ 值域有 `50+ / 150+ / 0.5` 非数字，见 T5） |
| 4 | 单位 | `fact_inventory.unit` | ✅ |
| 5 | 存放位置 | `fact_inventory.location` | ✅ |
| 6 | 保管人 | `fact_inventory.custodian` | ✅ |
| 7 | 初始库存 | `fact_inventory.opening_qty` | ❌ 无别名 + [build_domain_rows](file:///workspace/2026-07/smart-material-system/app/services/mapping.py#L212) 硬编码 None |
| 8 | 入库记录 / 入库数量 | `fact_stock_flow`(IN) | ✅ flow_config 305b_weihu |
| 9 | 出库记录 / 出库数量 | `fact_stock_flow`(OUT) | ✅ |
| 10 | 最低库存阈值 | `fact_inventory.min_qty` | ❌ 无别名 + 硬编码 None |
| 11 | 备注 | 仅 `fact_release_rows.payload_json` | △ 建议 T1 补 `remark` 列 |

### 1.2 备品备件（246 行 · 域=inventory + stock_flow）

| # | 台账列 | 系统落点 | 现状 |
|---|--------|----------|------|
| 1 | 物资名称 / 品牌规格型号 / 单位 | material_name / spec / unit | ✅ |
| 2 | 存放位置 / 保管人 | location / custodian | ✅ |
| 3 | 现有库存量 | `stock_qty` | ✅（`现有库存量` 命中 contains 匹配） |
| 4 | 初始库存 | `opening_qty` | ❌ 同 1.1-7 |
| 5 | 入库记录/数量、出库记录/数量 | `fact_stock_flow` | ✅ flow_config 305b_beipin |
| 6 | **所属系统**（通信电源/光传输/时钟…） | `belong_system`（T1 新增） | ❌ |
| 7 | **项目名称** | `project_name`（T1 新增） | ❌ |
| 8 | **消耗计划**（损坏更换/系统已退运） | `consumption_plan`（T1 新增） | ❌ |
| 9 | **物资来源**（备品备件采购/建设期…） | `material_source`（T1 新增） | ❌ |
| 10 | 定额数量 | `quota_qty` | ✅ |
| 11 | 公司仓库数量 | `company_wh_qty` | ❌ 无别名 + 硬编码 None |
| 12 | 备注 | `remark`（T1 新增） | ❌ |

### 1.3 公用工器具（94 行 · 域=asset）

| # | 台账列 | 系统落点 | 现状 |
|---|--------|----------|------|
| 1 | 物资名称 | `dim_material.material_name` | ✅（asset 域名称映射） |
| 2 | 规格型号 | `dim_material.spec` | ✅ asset ALIASES 有 spec |
| 3 | 物资编码 | `dim_material.material_code` | ❌ asset 域 ALIASES 无 material_code，需补 |
| 4 | 资产编码 | `fact_asset.asset_code` | ✅ |
| 5 | 数量 | `fact_asset.asset_qty`（T1 新增） | ❌ fact_asset 无数量列 |
| 6 | 单位 | `fact_asset.unit`（T1 新增） | ❌ |
| 7 | 存放位置 / 保管人 | `fact_asset.location` / `manager` | ✅ |
| 8 | **是否仪器仪表** | `is_instrument`（T1 新增） | ❌ |
| 9 | **更换周期（年）** | `replace_cycle`（T1 新增） | ❌ |
| 10 | **检测周期（年）** | `check_cycle`（T1 新增） | ❌ |
| 11 | 消耗计划 | `consumption_plan`（T1 新增，与备品备件共用语义） | ❌ |
| 12 | 购买日期 | `fact_asset.purchase_date` | ✅ |
| 13 | **工器具来源** | `tool_source`（T1 新增） | ❌ |
| 14 | 定额数量 | `fact_asset.asset_quota_qty`（T1 新增） | ❌ |
| 15 | 备注 | `fact_asset.check_result`（现有"备注"别名） | △ 可复用或 T1 补 `remark` |

### 1.4 应急备汛物资（10 行 · 域=inventory）

| # | 台账列 | 系统落点 | 现状 |
|---|--------|----------|------|
| 1 | 区域（TD/TDCD） | `region` | ✅ |
| 2 | 物资类别 | `category` | ✅（"物资类别"命中 contains） |
| 3 | 物资编码 | `material_code` | ✅ |
| 4 | **新集团编码** | `group_code`（T1 新增） | ❌ |
| 5 | 物资名称 / 型号规格 | material_name / spec | ✅ |
| 6 | 计量单位 | `unit` | ✅ |
| 7 | 定额数量 | `quota_qty` | ✅ |
| 8 | 现有数量 | `stock_qty` | ✅ |
| 9 | 存放货位 | `location` | ❌ "存放货位"不在 location 别名（"位置"与"货位"不匹配），需补别名 |
| 10 | 管理员 | `custodian` | ✅ |
| 11 | **是否框架物资** | `is_frame_material`（T1 新增） | ❌ |
| 12 | **协议供应商名称** | `agreement_supplier`（T1 新增） | ❌ |
| 13 | **推荐框架物资编码/名称/型号/供应商** | `frame_material_code/name/spec/supplier`（T1 新增） | ❌ |
| 14 | **应急供应商名称** | `emergency_supplier`（T1 新增） | ❌ |
| 15 | 备注 | `remark`（T1 新增） | ❌ |

---

## 2. 前置决策（实施前必须锁定，LD-1~LD-6）

> **人工评审流程**（范围、纪要模板、评审后 Agent 动作）：见 [ledger-ld-decisions.md §10](ledger-ld-decisions.md#10-人工评审agent-怎么处理流程说明)。逐条推荐与 T1/T2 草案见该文 §1–§8；评审人勾选 §10.2 后开工 T1。

| ID | 决策点 | 候选 | 影响面 | 状态 |
|---|---|---|---|---|
| LD-1 | 扩展字段落点 | **方案 A：`fact_inventory`/`fact_asset` 直接加可空列（推荐）**；方案 B：只进 `fact_release_rows.payload_json`，导出时 JSON 提取 | T1 schema / T8 报表 SQL | ✅ 已锁定（2026-08-10） |
| LD-2 | 公用工器具域归属 | **方案 A：asset 域扩展数量/周期/来源列（推荐，保留资产语义 + 双编码）**；方案 B：并入 inventory | T1 / T2 / T3 | ✅ 已锁定（2026-08-10） |
| LD-3 | 多 sheet 路由粒度 | **方案 A：evidence 层按 sheet 拆分为"域路由表"（推荐）**；方案 B：维持单文件单域，仅处理 flow 类 sheet | T3 | ✅ 已锁定（2026-08-10，单文件 4 次 confirm 接受） |
| LD-4 | 非数字数量/单位清洗 | **"50+"→50（去后缀）、"1包/50米/20对"→数量+单位拆分（规则集）**；超出规则的进 `staging_blocked`（reason_code=VALUE_RANGE） | T4 / T5 | ✅ 已锁定（2026-08-10，拒绝静默 NULL） |
| LD-5 | 台账导出形态 | **方案 A：4 条 `report_definition` 种子 + `/export/ledger/{sheet}` 固定列序端点（推荐）**；方案 B：仅报表定义、前端拼装 | T7 / T8 | ✅ 已锁定（2026-08-10） |
| LD-6 | 勾稽口径 | 期初缺失的物料：复用 `seed_opening_from_snapshot`（无流水时 opening=stock）；有流水但缺期初 → 保留 gap 清单（不阻塞发布） | T6 | ✅ 已锁定（2026-08-10） |

---

## 3. 任务拆解（按依赖排序）

### T1 · 数据模型扩展（schema，依赖 LD-1/LD-2）

| 任务 | 落点 | 验收 |
|---|---|---|
| T1.1 `fact_inventory` 增 9 个可空列：`opening_qty`(已有) 之外的 `remark`、`belong_system`、`project_name`、`consumption_plan`、`material_source`、`group_code`、`is_frame_material`、`agreement_supplier`、`frame_material_code/name/spec/supplier`、`emergency_supplier` | [schema.py](file:///workspace/2026-07/smart-material-system/app/repositories/schema.py#L24-L47) STAR_DDL + 迁移分支（仿 `opening_qty` 的 ALTER 模式） | 新列可查、旧库迁移不炸；`source_release_id` 血缘列保持 |
| T1.2 `fact_asset` 增 7 个可空列：`material_code`(或经 dim 关联)、`asset_qty`、`unit`、`is_instrument`、`replace_cycle`、`check_cycle`、`consumption_plan`、`tool_source`、`asset_quota_qty`、`remark` | 同上 `fact_asset` DDL | 同上 |
| T1.3 新增列同步 [field_dict.py](file:///workspace/2026-07/smart-material-system/app/services/field_dict.py) `FIELD_ZH` + [utils/fields.ts](file:///workspace/2026-07/smart-material-system/frontend/src/utils/fields.ts)（双端字典必须同步） | 见 roadmap/field-zh-doc.md §1 | `zh=1` 导出显示中文表头 |

### T2 · 映射层扩展（依赖 T1）

| 任务 | 落点 | 验收 |
|---|---|---|
| T2.1 `ALIASES["inventory"]` 补别名：`opening_qty`←初始库存/期初数量、`min_qty`←最低库存阈值、`company_wh_qty`←公司仓库数量、`location`←存放货位、`remark`←备注、新字段中文名（所属系统/项目名称/消耗计划/物资来源/新集团编码/是否框架物资/协议供应商/应急供应商…） | [mapping.py](file:///workspace/2026-07/smart-material-system/app/services/mapping.py#L9-L21) | resolve_columns 对 4 表表头全部命中 |
| T2.2 `ALIASES["asset"]` 补：`material_code`←物资编码、`asset_qty`←数量、`unit`←单位、`is_instrument`←是否仪器仪表、`replace_cycle`←更换周期（年）、`check_cycle`←检测周期（年）、`tool_source`←工器具来源、`consumption_plan`←消耗计划、`asset_quota_qty`←定额数量 | [mapping.py](file:///workspace/2026-07/smart-material-system/app/services/mapping.py#L33-L46) | 公用工器具表头全部命中 |
| T2.3 `build_domain_rows` inventory 分支把 `opening_qty/min_qty/company_wh_qty/remark/新字段` 从 mapping 读取（当前硬编码 None，[mapping.py](file:///workspace/2026-07/smart-material-system/app/services/mapping.py#L212-L219)） | [mapping.py](file:///workspace/2026-07/smart-material-system/app/services/mapping.py#L196-L229) | 发布后新字段非空可查 |
| T2.4 `build_domain_rows` asset 分支读取新字段（当前仅资产基础列，[mapping.py](file:///workspace/2026-07/smart-material-system/app/services/mapping.py#L257-L280)） | 同上 | 同上 |
| T2.5 `ALLOWED_STD` 补 `belong_system/project_name/…/is_instrument/replace_cycle/…`，治理中心表头映射可出建议 | `app/services/embed_recall.py` | 治理页可生成候选 |

### T3 · 多 sheet 异构路由（依赖 LD-3）—— ✅ 已落地（2026-08-10，冒烟通过）

> **T3 落地**：T3.1 路由表 [ledger_route.json](file:///workspace/2026-07/smart-material-system/data/flow_config/ledger_route.json)（4-sheet→域）+ [flow_config.py](file:///workspace/2026-07/smart-material-system/app/services/govern/flow_config.py#L181-L257) `get_ledger_route/ledger_sheet_names`（exact/canon/contains/aliases 四级匹配，缓存 + FLOW_CONFIG_DIR/`config.DATA` 路径）；T3.2 [evidence.py](file:///workspace/2026-07/smart-material-system/app/services/intake/evidence.py#L271-L325) `load_stock_flow_tabular` 路由感知（flow=true→stock_flow、flow=false→asset/inventory 域投影，`sheet` 列保留，未命中维持旧 flow 行为）+ [staging.py](file:///workspace/2026-07/smart-material-system/app/services/intake/staging.py) 按域过滤路由 sheet。4-sheet 合成 xlsx 冒烟：维护材料/备品备件→flow 列、公用工器具→asset 列（含 replace_cycle）、应急备汛→inventory 列，全部正确；`pytest` 63 passed 无回归。

| 任务 | 落点 | 验收 |
|---|---|---|
| T3.1 新增"sheet→域"路由：维护材料/备品备件→`inventory+stock_flow`；公用工器具→`asset`；应急备汛物资→`inventory`。路由表进 `data/flow_config/*.json`（新增 `ledger_route` 字段或独立路由 JSON，不硬编码） | `data/flow_config/` + [flow_config.py](file:///workspace/2026-07/smart-material-system/app/services/govern/flow_config.py#L181-L257) | ✅ 4 sheet 各自路由正确（冒烟验证 exact/alias/contains） |
| T3.2 [evidence.py](file:///workspace/2026-07/smart-material-system/app/services/intake/evidence.py#L271-L325) `load_stock_flow_tabular` 改造：不再"无流水列即丢弃"，改为按路由表逐 sheet 生成（stock_flow 类 sheet 走现有 flow 逻辑；asset/inventory 类 sheet 走 `normalize_tabular` 域投影，`sheet` 列标记保留） | [evidence.py](file:///workspace/2026-07/smart-material-system/app/services/intake/evidence.py#L271-L325) | ✅ 一个 4-sheet 文件产出一个含 `sheet` 标记的完整 tabular（冒烟验证） |
| T3.3 流水域复用：`build_stock_flow_bundle` 已按 sheet 查 flow_config（[mapping.py](file:///workspace/2026-07/smart-material-system/app/services/mapping.py#L351-L356)），无需改动；确认 305b_weihu/305b_beipin 配置的 `qty_column=入库数量/出库数量` 与 `unit_column=单位` 生效 | 现有逻辑回归 | 流水行数与源台账一致（待真实文件重放） |
| T3.4 发布路径：`writer.DOMAIN_FACT_TABLE` 已含 asset/inventory/stock_flow（[writer.py](file:///workspace/2026-07/smart-material-system/app/services/writer.py#L442-L447)）；确认单文件多域 staging/confirm 各自独立 release 正常 | [writer.py](file:///workspace/2026-07/smart-material-system/app/services/writer.py#L54-L145) | 4 个域可分别 confirm/release/吊销（待真实文件重放） |

### T4 · flow_config 补充（依赖 T3）—— ✅ 已落地（2026-08-10）

> **T4 落地**：新增 [305b_gongju.json](file:///workspace/2026-07/smart-material-system/data/flow_config/305b_gongju.json)（公用工器具 → domain=asset）与 [305b_beixun.json](file:///workspace/2026-07/smart-material-system/data/flow_config/305b_beixun.json)（应急备汛物资 → domain=inventory），aliases + domain 标记、无流水列；修复 [flow_config.py](file:///workspace/2026-07/smart-material-system/app/services/govern/flow_config.py#L14-L21) `DEFAULT_DIR` 指向 `app/data` 的路径错误（改为 `parents[3]/data/flow_config`）并将 `_ledger_route_path()` 与 flow_config 同源解析（不再依赖运行时 `config.DATA`），`ensure_flow_configs_seed` 默认生产路径可命中；E2E 验证 `get_flow_config` 命中新 sheet。T4.2 的"现有库存非纯数字进清洗"由 T5 的 `clean_ledger_qtys` + 种子规则承担（qty_column 已在 [305b_weihu.json](file:///workspace/2026-07/smart-material-system/data/flow_config/305b_weihu.json) flow_columns 声明）。

| 任务 | 落点 | 验收 |
|---|---|---|
| T4.1 为 公用工器具/应急备汛物资 增加配置（无流水列 → 仅 `aliases` + `domain` 标记，供路由与列解析） | `data/flow_config/` | ✅ get_flow_config 可命中（E2E 验证） |
| T4.2 `flow_config.json` 补充 `qty_column/unit_column` 校验：维护材料"现有库存"列非纯数字时进入 T5 清洗 | 同上 | ✅ 由 T5 清洗链承担（50+/120对/已取消，0 等真实形态全过） |

### T5 · 数量/单位清洗与校验（依赖 LD-4，复用 P2 能力）—— ✅ 已落地（2026-08-10）

> **T5 落地**（基于真实 4-sheet 台账实测形态）：
> - T5.1 [value_validator.py](file:///workspace/2026-07/smart-material-system/app/services/govern/value_validator.py) 新增 `clean_ledger_qtys`/`_clean_qty_value` 规则集：`50+`→50（去 + 后缀）、`120对`→120（数量数值化，单位列原值保留）、`已取消，0`→0、`一年一次`→1、`无定额`/`/`→空；新增 5 条 `value_rule` 种子（inventory opening/min/quota + asset asset_qty/check_cycle，severity=block），其余不可解析值落 `staging_blocked`（VALUE_RANGE），不静默置 NULL（LD-4）。
> - T5.2 [staging.py](file:///workspace/2026-07/smart-material-system/app/services/intake/staging.py) 清洗链 `normalize → resolve → clean_ledger_qtys → apply_checks`；`numeric_positive` 允许空值（空≠类型错误，真实台账大量行无入库/定额记录，拦截会整批误伤；必填由 required 规则负责）。
> - 真实文件 E2E：维护材料 366 落 + 125 blocked（MISSING_COL=空物资名称，既有 required 规则，需人工补录）、备品备件 247+1、公用工器具 94+0、应急备汛物资 11+0；文档化非数字形态零误拦；`pytest` 63 passed。

| 任务 | 落点 | 验收 |
|---|---|---|
| T5.1 新增种子校验规则：`stock_qty` 允许 "+" 后缀数字（"50+"→50，保留原值于 `fact_release_rows`）、`单位` 与数量联合拆分（"1包/50米/20对"） | `app/services/value_validator.py` + `value_rule` 种子 | ✅ 违反规则行落 `staging_blocked` 明细（VALUE_RANGE），不整批回滚（E2E 零误拦） |
| T5.2 清洗规则写入 staging 顺序 `normalize → resolve → apply_checks`（既有 P2 集成点） | [staging.py](file:///workspace/2026-07/smart-material-system/app/services/intake/staging.py) | ✅ "50+"可入库（清洗后 50）、原值可溯源 |
| T5.3 单位归一整列：`20对→20（对）`保留原始 `unit` 字段，数量数值化 | 同上 + [field_dict.py](file:///workspace/2026-07/smart-material-system/app/services/field_dict.py) | ✅ 数量数值化、单位列原值保留（导出列正确性随 T7 报表验证） |

### T6 · 勾稽与期初（依赖 T2）—— ✅ 已落地（2026-08-10，真实文件 E2E）

> **T6 落地**（真实 4-sheet 台账 `ce84beaa91ca.xlsx` 全域 release 后验证；数字为 T10.2 库存快照列修复后的最新口径）：
> - T6.1 [flow_gov.py](file:///workspace/2026-07/smart-material-system/app/services/flow_gov.py#L159-L288) `reconcile()` 原样复用：`GET /api/v1/govern/flow/reconcile` 返回 `total=319`（gap 清单）、`opening_populated_rows=305`、`material_id_overlap=196`、`by_class={inv_only:311, flow_only:9, mismatch:199}`（mismatch 计数含 items 内元素叠加，≥total 属预期；不宣称账已轧平）。
> - T6.2 `POST /api/v1/govern/flow/opening/seed`（LD-6：无流水物料 opening=stock）：`updated=185`，策略 `opening_qty=stock_qty where no fact_stock_flow for material_id`；有流水但缺期初保留 gap 清单不阻塞发布。
> - 支撑修复：**A0-4**（[db.py](file:///workspace/2026-07/smart-material-system/app/repositories/db.py) `_RWLock`+`_LockedConn` 连接生命周期持锁，消除 DuckDB 同文件只读/读写连接并存冲突；健康探针改 `readonly_probe`，按路径 bootstrap 缓存）——真实文件三域 confirm 连续通过、零混合模式冲突。

| 任务 | 落点 | 验收 |
|---|---|---|
| T6.1 期初落库后复用 [flow_gov.py](file:///workspace/2026-07/smart-material-system/app/services/flow_gov.py#L159-L288) reconcile（`ΣIN−ΣOUT ≟ stock_qty − opening_qty`） | 现有逻辑回归 | ✅ gap 清单可见、可导出（E2E `total=201`） |
| T6.2 无流水物料：复用 `seed_opening_from_snapshot`（[writer.py](file:///workspace/2026-07/smart-material-system/app/services/writer.py#L637-L710)）置 opening=stock | 现有逻辑回归 | ✅ `updated=9`，该类物料 expected_net=0 |

### T7 · 台账导出报表种子（依赖 T1/T2/T6）—— ✅ 已落地（2026-08-10，真实文件 E2E）

> **T7 落地**（真实 4-sheet 台账验证）：
> - T7.1 4 条种子在 [report_runner.py](file:///workspace/2026-07/smart-material-system/app/services/query/report_runner.py#L73-L146) `SEED_REPORTS`（`rpt_ledger_weihu/beipin/yjbm/gongju`，LD-5 固定列序）：inventory 类 3 表固定 17 列、asset 类 14 列；按 `source_sheet` 过滤（LD-5 约束固定列序），流水聚合列经 `fact_stock_flow` 子查询 GROUP BY material_id。
> - T7.2 前置：`source_sheet` 落库 —— [mapping.py](file:///workspace/2026-07/smart-material-system/app/services/govern/mapping.py#L274-L277) inventory/asset 分支回退 T3.2 保留的 `sheet` 标记列；事实表分布：`fact_inventory`（维护材料 365 / 备品备件 246 / 应急备汛物资 10）、`fact_asset`（公用工器具 94）、`fact_stock_flow`（维护材料 238 / 备品备件 69）。
> - T7.3 修复报表数据截断缺陷：`run_readonly_query` 原 `df.head(QUERY_ROW_LIMIT=200)` 截断报表产物 → 新增 `row_limit=None` 全量语义（[query.py](file:///workspace/2026-07/smart-material-system/app/services/query/query.py#L29-L67)），[report_runner.py](file:///workspace/2026-07/smart-material-system/app/services/query/report_runner.py#L289) 取全量；legacy/analytics 显式传 cap 保持原行为。产物为 parquet（`/reports/{run_id}/file` 返回 `PAR1` 二进制）+ csv。
> - 真实文件 E2E：4 报表 `row_count` 与 fact 表按 sheet 分组计数**完全对齐**（365 / 246 / 10 / 94），LD-5 固定列序抽查（前 8 列 `material_name, spec, stock_qty, opening_qty, quota_qty, min_qty, unit, location`）通过。

| 任务 | 落点 | 验收 |
|---|---|---|
| T7.1 4 条 `report_definition` 种子（[report_runner.py](file:///workspace/2026-07/smart-material-system/app/services/query/report_runner.py#L73-L146) `SEED_REPORTS` 追加）：`rpt_ledger_weihu`、`rpt_ledger_beipin`、`rpt_ledger_gongju`、`rpt_ledger_yjbm`，SQL 形如：`SELECT m.material_name, m.spec, i.stock_qty, i.opening_qty, i.quota_qty, i.min_qty, i.unit, i.location, i.custodian, i.belong_system, … FROM fact_inventory i LEFT JOIN dim_material m USING(material_id) WHERE i.source_sheet='维护材料'` | [report_runner.py](file:///workspace/2026-07/smart-material-system/app/services/query/report_runner.py#L73-L146) SEED_REPORTS | ✅ 可运行、可下载 parquet/csv（E2E 行数对齐） |
| T7.2 流水聚合列（入库量/出库量/次数）经子查询 join `fact_stock_flow` GROUP BY material_id | 同上 | ✅ 与源台账"入库数量/出库数量"对齐（E2E 验证） |
| T7.3 `report_runner` 只读校验 + 行数上限复用（[report_runner.py](file:///workspace/2026-07/smart-material-system/app/services/query/report_runner.py) 现有实现） | 现有逻辑回归 | ✅ 非只读 SQL 被拒；报表全量不受 QUERY_ROW_LIMIT 截断（row_limit=None 语义） |

### T8 · 模板导出端点（可选增强，依赖 T7）—— ✅ 已落地（2026-08-10）

> **T8 落地**：`GET /api/v1/export/ledger/{sheet}`（[reports.py](file:///workspace/2026-07/smart-material-system/app/api/routers/reports.py#L107-L152)）。`LEDGER_SHEETS` 定义 4 sheet → report_id + 台账模板列名（§1.1–§1.4）；实时执行对应种子 SQL（只读 AST 校验），列序以种子 SELECT 为准（LD-5 单一来源）；`zh=1` 表头汉化为台账模板列名（如 `现有库存/存放位置/保管人`，独立于 FIELD_ZH），`zh=0` 原始英文列名；CSV 附件中文文件名。未知 sheet 404。
> - E2E：4 sheet 导出行数 365/246/10/94 与 fact 表按 `source_sheet` 计数完全对齐；表头首列正确（名称/物资名称/物资名称/资产编码）。
> - 回归：[tests/test_export_ledger.py](file:///workspace/2026-07/smart-material-system/tests/test_export_ledger.py)（模板表头 + 行数 + 404 ×2）。

| 任务 | 落点 | 验收 |
|---|---|---|
| T8.1 `GET /api/v1/export/ledger/{sheet}`：固定列序 + 台账模板列名 + `zh=1` 中文表头，直接读 `report_definition` 已跑产物或实时执行 | [reports.py](file:///workspace/2026-07/smart-material-system/app/api/routers/reports.py#L107-L152)（routes 拆分后置于 routers/） | ✅ 返回 4 表固定模板列（E2E + 单测） |

### T9 · 展示层（依赖 T7/T8）—— ✅ T9.1 已落地（2026-08-10）；T9.2 可选未做

| 任务 | 落点 | 验收 |
|---|---|---|
| T9.1 前端 ReportsView 已支持报表下载；增"台账汇总"分组展示 4 条报表 | [ReportsView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/ReportsView.vue#L21-L27) | ✅ 新增「分组」列：`rpt_ledger_*` → 台账汇总（success 标签），其余 → 通用（类型检查通过；本环境无 npm 工具链，未跑 vite build） |
| T9.2 HomeView「标准表导出」卡增加"台账模板导出"入口（可选） | `frontend/src/pages/HomeView.vue` | 未做（可选，跳过） |

### T10 · 文档与验收物料 —— ✅ 已落地（2026-08-10）

| 任务 | 落点 | 验收 |
|---|---|---|
| T10.1 更新 [field-zh-doc.md](file:///workspace/2026-07/smart-material-system/roadmap/field-zh-doc.md) §3 字段映射表（新增列） | roadmap/field-zh-doc.md（v1.1） | ✅ fact_inventory/fact_asset 新增列 + §2 应用点补 `/export/ledger` |
| T10.2 产出源台账字段↔系统列对照测试样例（4 sheet 各抽样 3~5 行） | [ledger_source_samples.json](file:///workspace/2026-07/smart-material-system/tests/fixtures/ledger_source_samples.json) + [test_ledger_samples.py](file:///workspace/2026-07/smart-material-system/tests/test_ledger_samples.py) | ✅ 源表头可解析关键字段、sheet 集合与导出模板一致、样例行有值 |

> **T10.2 样例测试暴露并修复的真实数据缺陷（重要）**：flow=true sheet（维护材料/备品备件）的 evidence 投影此前仅按 `stock_flow` 域映射，**库存快照列（stock_qty/opening_qty/location/custodian/…）全部落空**——事实表行数对齐但值全 NULL，勾稽/期初/报表数值失真。修复：
> 1. [evidence.py](file:///workspace/2026-07/smart-material-system/app/services/intake/evidence.py#L296-L300)：flow sheet 合并 `resolve_columns(df, "inventory")` 映射，补回库存快照列；
> 2. [mapping.py](file:///workspace/2026-07/smart-material-system/app/services/govern/mapping.py#L16)：`stock_qty` 别名重排，具体名称（现有库存/现有库存数值/现有数量/…）先于通用「数量」，避免 contains 误匹配「入库数量」。
> 修复后验证：`fact_inventory` 维护材料/备品备件 `stock_qty/opening_qty/location/custodian` 全部 365/246 行有值且与源表对拍一致（如 `现有库存=5/5/50`、`存放位置=成都三峡大厦6楼通信材料室`、`保管人=张停伟、沈鸿`）；全链 smoke `T6_T7_LEDGER_OK`（reconcile `total=319`、`opening_populated_rows=305`、seed `updated=185`）；pytest 68 passed。

---

## 4. 验收总标准

1. 上传该 4-sheet 台账文件 → staging → confirm 后：维护材料/备品备件 → `fact_inventory`+`fact_stock_flow`；公用工器具 → `fact_asset`；应急备汛物资 → `fact_inventory`，**行数分别为 492 / 246 / 94 / 10（±少量 blocked）**；
2. 新字段入库：`belong_system/project_name/consumption_plan/material_source/group_code/is_frame_material/供应商列/is_instrument/replace_cycle/check_cycle/tool_source` 均非空可查；
3. 4 条台账报表可运行，`期初 + Σ入库 − Σ出库 = 期末(stock_qty)` 与源台账公式列一致（勾稽 gap 收敛或可见清单）；
4. "50+" 等非数字数量入库为数值、原值可在 `fact_release_rows` 溯源；
5. 全程无 `UPDATE fact_*` 原地修改（write_audit 可查）。

---

## 5. 落地顺序（建议）

```
T1 schema 扩展（LD-1/LD-2 先锁定）
  → T2 映射层（ALIASES + build_domain_rows + ALLOWED_STD）   ← 并行 T3 路由改造
  → T4 flow_config → T5 清洗校验 → T6 勾稽
  → T7 报表种子 → T8 模板导出 → T9.1 前端分组 → T10 文档/样例（已全部落地，v0.6）
```

**阻塞关系**：LD-1/LD-2 未定前勿动 schema；T3.2 依赖 LD-3；T5 依赖 LD-4；T7 SQL 依赖 T1/T2。

---

## 6. 风险与决策点

| # | 风险/决策 | 说明 | 建议 |
|---|---|---|---|
| D1 | 新增列对既有发布的影响 | `writer` 按 release delete-and-replace，列新增不影响旧行 | 新列默认 NULL，旧发布不重建也可；新发布自动填充 |
| D2 | 多 sheet 单文件多域 | 现有 staging/confirm 按 `(file_id, target_domain)` 粒度，4 sheet 需 4 次 confirm | T3 路由产出后按域分批 confirm，不改变单文件状态机 |
| D3 | 数量清洗精度 | "50+"、"1包" 等规则化处理可能误判 | 规则先进 `value_rule`（proposed→人工确认 active），误判落 blocked 而非静默改值 |
| D4 | 报表 SQL 列对齐 | 源台账列序/列名是模板，报表 SQL 需逐列固化 | 以 T7.2 抽样样例锁定列序，评审通过后 seed |
| D5 | `fact_release_rows` 膨胀 | 多域发布镜像增多 | 现有 revoke/supersede 机制覆盖，不新增存储 |

---

*与字段汉化文档冲突时以本文 T1/T2 落库结果为准；LD-1~LD-6 锁定后更新本文。*
