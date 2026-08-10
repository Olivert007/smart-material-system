# CSV 导出特殊标记加固 · 实施方案

> 版本：v0.1（2026-08-09） · 状态：待评审
> 目标：补齐 3 条 CSV 导出链路的特殊标记处理——**UTF-8 BOM（Excel 中文兼容）**、**公式注入防护（CSV injection）**、**截断/来源标记**，且不改变库表结构与导出列语义。

---

## 0. 结论摘要（能力判定）

- **系统具备 3 条导出链路**：服务端标准表导出 `/export/table/{table}`、报表产物落盘（parquet+csv）、前端问答结果客户端导出。
- **当前均无特殊标记处理**：无 BOM、无公式注入防护、无截断提示，存在两类风险：
  1. **兼容性**：UTF-8 无 BOM 的 CSV 被 Excel 直接打开时中文乱码；
  2. **安全**：单元格值以 `= + - @` 开头时，Excel 会按公式执行（CSV injection）。
- **结论**：按本文 T1–T3 修改后，导出 CSV 可用 Excel 直接打开不乱码、杜绝公式注入、截断与来源信息可见；`zh=0` 原始列导出与 DuckDB 标准表结构保持不变。

---

## 1. 现状盘点（3 条导出链路）

| # | 链路 | 落点 | 现状 | 问题 |
|---|------|------|------|------|
| L1 | 标准表导出 `GET /export/table/{table}` | [routes.py](file:///workspace/2026-07/smart-material-system/app/api/routes.py#L1522-L1562) | 白名单表名 + sql_guard 只读校验 + 行数上限（`EXPORT_ROW_LIMIT`=100000，[config.py](file:///workspace/2026-07/smart-material-system/app/config.py#L40)）；`df.to_csv(index=False)`，`text/csv; charset=utf-8`；`zh=1` 隐藏技术字段 + 汉化表头 + `flow_type` 枚举汉化 | 无 BOM；无注入防护；截断无提示 |
| L2 | 报表产物 | [report_runner.py](file:///workspace/2026-07/smart-material-system/app/services/report_runner.py#L221-L222) | 报表 SQL 过 AST 只读校验，parquet + csv 双落盘 `df.to_csv(csv_path, index=False)` | 无 BOM；无注入防护 |
| L3 | 前端问答导出 | [client.ts](file:///workspace/2026-07/smart-material-system/frontend/src/api/client.ts#L1288-L1302) `downloadCsv` | 仅转义 `"` `,` `\n`；Blob `text/csv;charset=utf-8`；调用点 [AskView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/AskView.vue#L234-L245) 已做技术字段隐藏 + 表头汉化 | 无 BOM；无注入防护；无来源/截断标记 |

**既有的"标记"处理（保持不动）**：
- 技术字段隐藏 `TECHNICAL_FIELDS`（[field_dict.py](file:///workspace/2026-07/smart-material-system/app/services/field_dict.py#L84-L95)）：仅展示/导出层过滤，`zh=0` 可还原；
- 枚举汉化 `flow_type` IN→入库（[field_dict.py](file:///workspace/2026-07/smart-material-system/app/services/field_dict.py#L98-L100)）；
- `CELL_MARKER` 截断标记（[evidence.py](file:///workspace/2026-07/smart-material-system/app/services/evidence.py#L60-L114) + [staging.py](file:///workspace/2026-07/smart-material-system/app/services/staging.py#L113-L128)）：导入侧 blocked 逻辑，与导出无关，不改。

---

## 2. 问题清单与修改方案

### P1 · UTF-8 BOM（Excel 中文乱码）

**问题**：三条链路均输出无 BOM 的 UTF-8，Excel 双击打开按 ANSI 解析导致中文乱码。

**方案**：导出内容前置 `\ufeff`（BOM）或 pandas 使用 `encoding="utf-8-sig"`。

| 任务 | 落点 | 验收 |
|---|---|---|
| T1.1 `/export/table/{table}` 改为 `df.to_csv(index=False)` → 手动拼 BOM：`content=("\ufeff" + df.to_csv(index=False))`，media_type 保持 `text/csv; charset=utf-8` | [routes.py](file:///workspace/2026-07/smart-material-system/app/api/routes.py#L1558-L1561) | curl 下载首字节为 `EF BB BF`；Excel 打开中文表头正常 |
| T1.2 报表 csv 落盘 `df.to_csv(csv_path, index=False, encoding="utf-8-sig")`（parquet 不受影响） | [report_runner.py](file:///workspace/2026-07/smart-material-system/app/services/report_runner.py#L222) | 产物 csv 首字节 BOM；既有 `reports_file` 下载正常 |
| T1.3 前端 `downloadCsv` 的 Blob 内容前拼接 `\uFEFF` | [client.ts](file:///workspace/2026-07/smart-material-system/frontend/src/api/client.ts#L1301) | 下载文件首字符 BOM，Excel 打开正常 |

### P2 · 公式注入防护（CSV injection）

**问题**：单元格值以 `=` `+` `-` `@`（及制表符/回车等）开头时，Excel 会将其解释为公式/超链接执行，存在注入与数据篡改风险。

**方案**：统一在导出前对单元格值做净化——首字符命中危险前缀时前置 `'`（Excel 视为文本）。注意：**仅命中危险前缀的单元格加 `'`，其余原样**，避免全量污染数据。

| 任务 | 落点 | 验收 |
|---|---|---|
| T2.1 新增共享净化函数（服务端）：`sanitize_csv_cell(v) -> str`，对 `str(v)` 以 `= + - @ \t \r` 开头时前置 `'`，空值保留空串 | 新增 `app/services/csv_safe.py`（导出侧工具，不依赖业务） | 单测覆盖 `=1+1`→`'=1+1`、`+86`→`'+86`、`-5`→`'-5`、`@cmd`→`'@cmd`、普通中文/数字原样 |
| T2.2 `/export/table/{table}` 在 `df.to_csv` 前对全部单元格应用净化（`df = df.map(...)`，注意 pandas 版本差异用 applymap 兜底） | [routes.py](file:///workspace/2026-07/smart-material-system/app/api/routes.py#L1554-L1557) | 导出 CSV 中危险前缀单元格带 `'`，普通数据不变 |
| T2.3 报表 csv 落盘前同样净化（与 T2.2 复用同一函数；parquet 产物不净化，保持原始值） | [report_runner.py](file:///workspace/2026-07/smart-material-system/app/services/report_runner.py#L216-L222) | csv 产物净化、parquet 原始值；下载接口两产物均可用 |
| T2.4 前端 `downloadCsv` 的 `escape` 增加注入净化（与既有引号转义合并） | [client.ts](file:///workspace/2026-07/smart-material-system/frontend/src/api/client.ts#L1293-L1296) | 浏览器导出 CSV 危险前缀单元格带 `'` |

### P3 · 截断/来源标记

**问题**：行数上限截断（`EXPORT_ROW_LIMIT`）无任何提示，使用者无法感知数据被截断；导出文件无来源标记，不利于审计与追溯。

**方案**：
1. 截断提示：导出实际行数 == 上限时，追加一行尾注释 `# TRUNCATED: rows=N, limit=M`（注释行以 `#` 开头，Excel 首行表头不受影响）；
2. 来源标记：可选地在文件名或首行注释中携带表名/时间（L2 报表文件名已含 run_id，可只加注释行说明来源表）。

| 任务 | 落点 | 验收 |
|---|---|---|
| T3.1 `/export/table/{table}`：`len(df)` 达 `cap` 时在 CSV 内容末尾追加 `\n# TRUNCATED: rows={len(df)}, limit={cap}`；文件名已含表名+时间戳，另追加 `# source={table}` 注释 | [routes.py](file:///workspace/2026-07/smart-material-system/app/api/routes.py#L1541-L1562) | 导出 50000 行上限数据时末尾可见 TRUNCATED 注释；未达上限无注释 |
| T3.2 前端 `downloadCsv` 增加可选 `note` 参数（行数/来源），AskView 调用时传入 `已导出 N 行` 信息作为尾注释 | [client.ts](file:///workspace/2026-07/smart-material-system/frontend/src/api/client.ts#L1288-L1302) + [AskView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/AskView.vue#L243) | 导出的 CSV 末尾带注释行 |
| T3.3 报表 csv：`run_report` 已在 meta 表记 run_id/row_count，落盘文件不加注释（保持产物纯净），由报表列表页展示 row_count | 不改（文档确认） | 报表列表页显示行数即可 |

---

## 3. 兼容性约定

1. **`zh=0` 原始导出不受影响**：净化与 BOM 只作用于导出文件内容，不写回 DuckDB 标准表；`zh=0` 仍可拿原始列名与全字段。
2. **parquet 与 csv 分离**：报表 parquet 保持原始值（供程序消费），csv 做展示净化（供人看）。
3. **注释行约定**：`#` 开头行仅出现在 CSV 末尾（表头之后），pandas `read_csv` 默认 `comment=None` 会将其作为数据行——本项目 CSV 仅用于人工查看与下载，不回灌，可接受；如需回灌由导入侧 `_load_csv` 过滤 `#` 行即可（可选增强，不做默认）。

---

## 4. 验收总标准

1. 三条链路导出的 CSV 首字节均为 `EF BB BF`，Excel 直接打开中文不乱码；
2. 危险前缀单元格（`=`/`+`/`-`/`@` 开头）导出为 `'` 前缀文本，普通数据原样；
3. 导出达行数上限时文件末尾出现 `# TRUNCATED` 注释；未达上限无注释；
4. `zh=0` 导出、parquet 产物、DuckDB 标准表数据均保持原始值不变；
5. 全量回归：`tests/` 既有用例（含导出相关 smoke）不回归。

---

## 5. 落地顺序（建议）

```
T1 BOM（L1→L2→L3）
  → T2 注入净化（先建 csv_safe.py 共享函数，再 L1→L2→L3）
  → T3 截断/来源标记（L1 → L3，报表 L2 仅文档确认）
```

**依赖**：T2 依赖 `csv_safe.py` 先落地；T1/T3 彼此独立可并行。

---

## 6. 风险与决策点

| # | 风险/决策 | 说明 | 建议 |
|---|---|---|---|
| D1 | 净化影响数值列 | 数字 `-5` 会被加 `'`，Excel 中显示为文本而非数字 | 可接受（防止公式注入优先级高于数字格式）；如需数字保持数值，可只对字符串列净化、数值列跳过（默认全净化，评审可调） |
| D2 | pandas 版本 `df.map` vs `applymap` | 老版本无 `DataFrame.map` | 用 `getattr` 兜底或统一 `apply` |
| D3 | 注释行回灌问题 | `#` 行被 pandas 当数据读 | 导出 CSV 不回灌；如需回灌在 `_load_csv` 过滤，见 §3 |
| D4 | 前端 Blob BOM | `\uFEFF` 需在 CSV 内容最前，且与后端不重复 | 前端 Blob 直接前置 `\uFEFF` 字节即可 |

---

*与字段汉化文档（field-zh-doc.md）冲突时以本文为准；评审通过后更新本文状态为已实施。*
