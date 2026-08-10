# 采购订单域接入 · 实施方案（待立项拆解）

> 版本：v0.1（2026-08-09） · 状态：**待立项**（设计稿见 [`../../治理方案/question/04-采购订单接入方案.md`](../../治理方案/question/04-采购订单接入方案.md)；本文件为实施任务拆解）
> 目标：新增第 7 个业务域 `purchase_order`，复用现有可信管线（上传→evidence→staging→confirm→writer 幂等发布→fact_purchase_order），不旁路、不引入新架构。
> 原则：**LLM 只建议、人工确认才写**；**禁原地 UPDATE**；所有变更走现有 meta 表 + 幂等写入范式（与 P1–P4 一致）。

---

## 0. 现状与差距（2026-08-09 复核）

| # | 现状 | 缺口 |
|---|------|------|
| 1 | `schema.py` 无 `fact_purchase_order` | 采购单据实体未建模 |
| 2 | `writer.py` `DOMAIN_FACT_TABLE` 仅 inventory/demand/asset/stock_flow 4 域 | 无 PO 发布路径 |
| 3 | `mapping.ALIASES` / `embed_recall.ALLOWED_STD` 无 purchase 域 | 表头映射无 PO 字段 |
| 4 | `fact_stock_flow` 无 `po_id` 可空列 | 无法做单据级"采购→入库"核销 |
| 5 | 指标字典无 PO_* | 无在途/到货率/采购总额 |

**可复用能力（2026-08-09 已就绪，无需从零开发）**：`value_rule` + staging 接入、`staging_blocked` 逐行明细、`rule_learn` 提案、`release diff / supersede`、`correction_request` 单行修正、`report_definition/report_run` 报表快照、`metric_snapshot` 指标时序、`business_snapshot` 首页快照。

---

## 1. 前置决策（实施前必须锁定，PO-1~PO-5）

| ID | 决策点 | 候选 | 影响面 |
|---|---|---|---|
| PO-1 | 是否做订单级对账（flow 加 `po_id`） | 是（推荐，可逐单核销）/ 否（物料级汇总） | T2 schema、T6 勾稽 |
| PO-2 | 单价含税口径 | 含税 / 不含税 / 双口径字段 | T7 指标 `PO_TOTAL_AMOUNT` |
| PO-3 | status 枚举 | open/partial/received/closed / 按客户实际 | T5 校验规则 |
| PO-4 | 是否解析采购文本单 | 结构化列接入 / 扩展模块 12 原语拆文本 | T4 映射范围 |
| PO-5 | 差异清单落点 | 独立 `po_reconcile_gap` / 并入现有差异清单 | T6 勾稽 |

---

## 2. 任务拆解（按依赖排序）

### T1 · 决策与文档
| 任务 | 落点 | 验收 |
|---|---|---|
| T1.1 锁定 PO-1~PO-5 并回填本文档 | `治理方案/question/04-采购订单接入方案.md` | 五个决策有明确结论 |
| T1.2 立项后将 question/04 升级为正式模块 13 | `治理方案/13-采购订单接入.md` | README 模块索引登记 |

### T2 · 数据模型（schema）
| 任务 | 落点 | 验收 |
|---|---|---|
| T2.1 新建 `fact_purchase_order`（一行一订单行） | `app/repositories/schema.py` | 字段对齐 question/04 §二：po_id/po_no/material_id/supplier/order_date/due_date/quantity/received_qty/unit/unit_price/total_price/buyer/status/source_file/source_release_id |
| T2.2 `fact_stock_flow` 增加可空列 `po_id`（仅 PO-1=是） | 同上 + 旧表迁移策略 | 迁移不炸；无 PO 关联时为空 |
| T2.3 meta 侧差异清单表（仅 PO-5=独立表时） | `app/repositories/db.py` | `po_reconcile_gap` 可建可查 |

### T3 · Writer 发布路径
| 任务 | 落点 | 验收 |
|---|---|---|
| T3.1 `DOMAIN_FACT_TABLE` 加 `purchase_order` 分支 | `app/services/writer.py` | 幂等、release_id 审计、重复 confirm 不双写 |
| T3.2 血缘键镜像（row_key 含 po 段） | 同上 + `flow_lineage` | 可对账、可重建吊销 |

### T4 · 映射层
| 任务 | 落点 | 验收 |
|---|---|---|
| T4.1 `mapping.ALIASES` 加 purchase_order 域中文别名 | `app/services/mapping.py` | po_no/supplier/order_date/… 可命中 |
| T4.2 `ALLOWED_STD` 加 `po_*` 标准字段 | `app/services/embed_recall.py` | 治理中心表头映射页可生成建议 |
| T4.3 结构化列映射走 flow_config JSON（若 PO-4=结构化） | `data/flow_config/*.json` + `app/services/flow_config.py` | 不硬编码映射分支 |
| T4.4 若 PO-4=文本单：扩展模块 12 原语 | `app/services/flow_parse.py` | 文本拆解单测绿 |

### T5 · 校验与拦截
| 任务 | 落点 | 验收 |
|---|---|---|
| T5.1 种子校验规则（unit_price>0、supplier 非空、quantity>0、po_no 唯一） | `app/services/value_validator.py` | 违反规则的行落 `staging_blocked`，`reason_code` 正确 |
| T5.2 staging 接入顺序扩展（normalize→resolve→apply_checks） | `app/services/staging.py` | 坏行不整批回滚 |

### T6 · 勾稽扩展
| 任务 | 落点 | 验收 |
|---|---|---|
| T6.1 到货勾稽（订单级 ΣIN(po_id) vs received_qty，或物料级） | `app/services/flow_gov.py` | 差异可见、可导出、不阻塞发布 |
| T6.2 差异落点（按 PO-5） | 独立表或并入现有清单 | 可查询 |

### T7 · 指标
| 任务 | 落点 | 验收 |
|---|---|---|
| T7.1 新增 `PO_OPEN_QTY` 在途量、`PO_RECEIVE_RATE` 到货率、`PO_TOTAL_AMOUNT` 采购总额 | `app/services/metrics.py`（metric_dict seed） | 复用 evaluate_metric，**无 FLOW_* 式门禁**，可直接 active |
| T7.2 首页快照卡（采购汇总） | `app/services/stats_overview.py` | HomeView 可见 |

### T8 · 报表与展示
| 任务 | 落点 | 验收 |
|---|---|---|
| T8.1 预置采购报表定义（在途、到货率、按供应商/月份聚合） | 种子 `report_definition` | 可运行、可下载 parquet/csv |
| T8.2 治理中心「采购订单」页签 | `frontend/src/pages/GovernView.vue` | 待确认/差异可见 |
| T8.3 首页快照 + 可选 Assets 展示 | `frontend/src/pages/HomeView.vue` | 与 T7.2 配套 |

---

## 3. 验收总标准

1. 上传含采购订单的文件 → staging → confirm → `fact_purchase_order` 有数据、幂等可查；
2. 坏行（负单价/空供应商）落 `staging_blocked` 明细，不整批回滚；
3. 到货勾稽可导出差异清单（按 PO-1 精度）；
4. `PO_*` 三指标可求值、可快照时序；
5. 全程无 `UPDATE fact_purchase_order` 原地修改（write_audit 可查）。

---

## 4. 落地顺序（建议）

```
T1 决策锁定（PO-1~PO-5，阻塞 T2.2/T4.4/T6）
  → T2 schema → T3 writer → T4 映射（并行 T5 校验）
  → T6 勾稽 → T7 指标 → T8 报表/展示
```

**风险提示**：PO-1/PO-4/PO-5 未定前勿动 schema（`po_id` 列与差异表结构取决于决策）；PO-2 未定前勿固化 `PO_TOTAL_AMOUNT` 口径。

---

*与 question/04 冲突时以锁定后的决策为准；本文档随 PO-1~PO-5 结论更新。*
