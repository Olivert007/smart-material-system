# 标准字段汉化与技术字段隐藏 · 维护说明

> 版本：v1.1（2026-08-10） · 状态：已实现（T1/T2 台账新列 + T8 台账模板导出已同步）
> 目的：把系统数据呈现从「技术视角」转向「业务分析视角」——导出与业务表格默认展示中文表头、隐藏溯源/解析类技术字段，业务用户不接触库级字段名。标准表结构（DuckDB）不变。

---

## 1. 实现位置（**两端字典必须同步维护**）

| 端 | 文件 | 内容 |
|---|---|---|
| 后端 | [`app/services/field_dict.py`](../app/services/field_dict.py) | `TABLE_ZH` 表中文名、`FIELD_ZH` 字段中文名、`TECHNICAL_FIELDS` 技术字段集；`table_zh / field_zh / is_technical / visible_fields / zh_columns` |
| 前端 | [`frontend/src/utils/fields.ts`](../frontend/src/utils/fields.ts) | 与后端同名的字典与函数（Ask 结果表头汉化用） |

> ⚠️ 新增或修改字段映射时，**必须同时改两端**，否则导出与 Ask 展示会不一致。

---

## 2. 应用点

| 应用点 | 行为 |
|---|---|
| `GET /api/v1/export/table/{table}?zh=1`（默认） | 表头中文 + 隐藏技术列 |
| `GET /api/v1/export/table/{table}?zh=0` | 原始列名 + 全字段（逃生通道，供程序/排障使用） |
| `GET /api/v1/export/ledger/{sheet}?zh=1`（T8 台账模板导出） | 4-sheet 台账模板：固定列序（LD-5）+ 台账模板列名（LEDGER_SHEETS，与 §1.1–§1.4 台账列名一致） |
| `GET /api/v1/export/ledger/{sheet}?zh=0` | 原始英文列名（同种子报表 SELECT 列序） |
| AskView 结果表格 | 列名显示用 `fieldZh()`，并隐藏技术列（`displayCols`） |
| AskView「导出 CSV」 | 中文表头 + 隐藏技术列 |
| HomeView「标准表导出」卡 | 按钮为中文域标签（物资主数据/库存台账/…），点击调 `tableExportUrl(table)` |

> ⚠️ 台账模板列名（`LEDGER_SHEETS`，[reports.py](../app/api/routers/reports.py)）是独立于 `FIELD_ZH` 的导出层映射，按台账模板语义命名（如 `现有库存/存放位置/保管人`），与 `FIELD_ZH` 的通用中文名（如 `库存数量/库位/库管员`）可不同——改报表种子 SELECT 列序时必须同步 LEDGER_SHEETS。

**技术字段隐藏是「展示/导出层」处理**：DuckDB 标准表列不变、数据不丢，`zh=0` 可取回全字段。

---

## 3. 字段中文映射表（6 张标准表）

### 通用字段
| 字段 | 中文 | 字段 | 中文 |
|---|---|---|---|
| material_id | 物资ID | material_code | 物资编码 |
| material_name | 物资名称 | unit | 单位 |
| category | 类别 | spec | 规格型号 |
| source_file | 来源文件 | | |

### dim_material（物资主数据）
| 字段 | 中文 | 字段 | 中文 |
|---|---|---|---|
| name_alias | 名称别名 | spec_alias | 规格别名 |
| code_source | 编码来源 | | |

### fact_inventory（库存台账）
| 字段 | 中文 | 字段 | 中文 |
|---|---|---|---|
| inventory_id | 库存ID | region | 区域 |
| stock_qty | 库存数量 | opening_qty | 期初数量 |
| quota_qty | 定额数量 | min_qty | 最低数量 |
| temp_qty | 临时数量 | company_wh_qty | 公司仓数量 |
| age_days | 库龄(天) | unit_cost | 单价 |
| stock_value | 库存金额 | location | 库位 |
| custodian | 库管员 | remark | 备注 |
| belong_system | 所属系统 | project_name | 项目名称 |
| consumption_plan | 消耗计划 | material_source | 物资来源 |
| group_code | 新集团编码 | is_frame_material | 是否框架物资 |
| agreement_supplier | 协议供应商 | emergency_supplier | 应急供应商 |
| frame_material_code | 推荐框架物资编码 | frame_material_name | 推荐框架物资名称 |
| frame_material_spec | 推荐框架物资型号 | frame_material_supplier | 推荐框架物资供应商 |

> 注：以上 12 个台账扩展列（remark 起）为 T1/T2（ledger-export-plan §7.1，LD-1 锁定 2026-08-10）新增。

### fact_asset（资产台账）
| 字段 | 中文 | 字段 | 中文 |
|---|---|---|---|
| asset_code | 资产编号 | asset_name | 资产名称 |
| company | 所属单位 | domain | 业务域 |
| user_name | 使用人 | manager | 管理人 |
| purchase_date | 购置日期 | status | 状态 |
| check_result | 盘点结果 | material_code | 物资编码 |
| asset_qty | 资产数量 | unit | 单位 |
| is_instrument | 是否仪器仪表 | replace_cycle | 更换周期(年) |
| check_cycle | 检测周期(年) | consumption_plan | 消耗计划 |
| tool_source | 工器具来源 | asset_quota_qty | 资产定额数量 |
| remark | 备注 | | |

> 注：asset_qty 起为 T1/T2（ledger-export-plan §7.2，LD-1/LD-2 锁定 2026-08-10）新增。

### fact_demand（需求明细）
| 字段 | 中文 | 字段 | 中文 |
|---|---|---|---|
| demand_id | 需求ID | demand_period | 需求期间 |
| quantity | 数量 | unit_price | 单价 |
| total_price | 需求金额 | reporter | 申报人 |
| remark | 备注 | | |

### fact_quota_adjust（定额调整记录）
| 字段 | 中文 | 字段 | 中文 |
|---|---|---|---|
| quota_id | 调整ID | adjust_type | 调整类型 |
| installed_qty | 装机数量 | accident_quota | 事故定额 |
| reserve_quota | 储备定额 | verified_quota | 核定定额 |
| device_name | 设备名称 | reason | 原因 |

### fact_stock_flow（出入库流水）
| 字段 | 中文 | 字段 | 中文 |
|---|---|---|---|
| flow_id | 流水ID | flow_type | 出入类型 |
| flow_date | 日期 | quantity | 数量 |
| person | 经手人 | purpose | 用途 |
| remark | 备注 | | |

---

## 4. 技术字段清单（业务展示/导出时隐藏）

| 字段 | 所在表 | 隐藏原因 |
|---|---|---|
| source_release_id | 全部事实表 | 发布血缘技术字段 |
| source_era | fact_inventory | 数据期别标记（内部） |
| color_flag | fact_inventory / fact_asset | 颜色标记（内部） |
| delete_flag | fact_quota_adjust | 删除标记（内部） |
| parse_level / parse_source | fact_stock_flow | LLM 流水解析级别/来源 |
| source_sheet / source_row / source_segment | fact_stock_flow | 溯源定位（表页/行/段落） |
| match_level | dim_material | 主数据匹配级别（规则/人工/LLM） |

---

## 5. 维护规则（Checklist）

1. **新增业务表/字段**：先改 `app/repositories/schema.py` → 再同步 `field_dict.py` + `utils/fields.ts`；
2. **新字段判定**：属于「来源/解析/治理/内部标记」→ 加入 `TECHNICAL_FIELDS`（后端）与 `TECHNICAL_FIELDS`（前端）；否则加 `FIELD_ZH`；
3. **同一字段跨表语义不同**（如 `quantity` 在 demand 与 flow 中含义不同）：当前用通用中文名（"数量"）规避歧义；若需区分，需把字典升级为按表映射（`TABLE_FIELD_ZH`），属已知局限；
4. **导出行为回归**：`zh=1` 中文表头且不含技术列；`zh=0` 与原始 schema 一致；
5. **不要在字典里删后端字段**——`zh=0` 依赖原始列名，字典只负责映射。

---

## 6. 验证方式

```bash
# 后端 smoke（临时 DATA_DIR，参考 tests/test_intake_analyze.py 的流程）
#   zh=1 → 表头中文、不含 source_release_id/color_flag/parse_level 等
#   zh=0 → inventory_id,...source_release_id 全字段
curl -s 'http://127.0.0.1:8080/api/v1/export/table/fact_inventory?limit=5'      # zh=1
curl -s 'http://127.0.0.1:8080/api/v1/export/table/fact_inventory?limit=5&zh=0' # zh=0

# 前端构建
cd frontend && npm run build   # vue-tsc + vite，两个字典的 TS 类型会兜底
```

---

*配套改动：规整后数据预览与导出见 2026-08-09「数据展示与导出」最小集（staging dry_run.clean_sample、/export/table 端点）。*
