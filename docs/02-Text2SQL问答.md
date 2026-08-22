# 模块 02 · Text2SQL 问答

> 版本：Phase 2.2（2026-08-08）  
> 接口：`POST /api/v1/ask`（依赖 LLM，未就绪时友好降级）。  
> 代码：`app/services/query/text2sql.py`（`SCHEMA_ZH` / `ask`，含模板优先）+ `app/api/routers/query.py`（`/api/v1/ask`）。  
> 编排：指标模板优先 → PolicyRouter（[09](09-多模型编排策略.md)）→ embed 召回 → `sql_simple`/`sql_complex` → AST 校验；验收见 [10](10-模型评测与验收.md)。

---

## 1. 端到端流程

```
用户中文提问
  │
  ▼
①′ 指标模板 / 规则命中？→ 直接参数化 SQL（不调生成模型，见 08）
  │ 未命中
  ▼
① 生成 Schema 摘要
   information_schema（列名+类型）+ SCHEMA_ZH（6 表列中文注释）拼成 prompt
   + embed 召回相关 few-shot / 历史成功 SQL（可选）
  │
  ▼
② PolicyRouter：简单 → fast；复杂/低置信 → big 或级联（Stage 见 00 §4.2）
   LLM 生成 SQL（system prompt 约束，见 §3）
  │
  ▼
③ 安全校验（见模块 05，AST 为主）
   ├─ 不通过 → 返回错误（含模型原始输出，便于排查），不执行
   └─ 通过
  ▼
④ DuckDB 只读连接执行
   - 结果行数超过 `QUERY_ROW_LIMIT`（默认 200）时返回截断提示（`total_rows` / `truncated`）
  │
  ▼
⑤ LLM 中文总结（问题 + SQL + 结果前几行 → 简洁中文回答；默认 big，见 §5）
  │
  ▼
返回 {question, llm, ok, sql, rows, columns, data, answer, truncated?, total_rows?}
```

**LIMIT 约定**：执行/返回上限默认 `QUERY_ROW_LIMIT`（**200 行**，`app/config.py` 环境变量可覆盖）；超限返回 `total_rows` / `truncated:true`，UI 提示截断（07 §3.2）。

## 2. Schema 注入（为什么这样做）

DuckDB 的 `information_schema.columns` 只有英文列名（如 `stock_qty`），LLM 无法理解含义。
`SCHEMA_ZH`（`app/services/query/text2sql.py`）手工维护 6 张表每列的中文注释，拼进 system prompt：

```
表 fact_inventory:
  - stock_qty (DOUBLE)，现有库存数量
  - material_id (VARCHAR)，物料ID(关联dim_material)
  ...
```

6 张表：`dim_material`（主数据）、`fact_inventory`（库存）、`fact_asset`（资产）、
`fact_demand`（需求）、`fact_quota_adjust`（定额调整）、`fact_stock_flow`（出入流水）。

`fact_stock_flow` 由源头「入库记录/出库记录」自由文本经规则拆解生成（详见 [12](12-出入库流水解析.md)）。schema 注入至少包含：

```
表 fact_stock_flow:
  - flow_type (VARCHAR)，IN/OUT
  - flow_date (DATE)，业务日期
  - quantity (DOUBLE)，数量
  - person (VARCHAR)，经手人/领用人
  - purpose (VARCHAR)，用途
  - material_id (VARCHAR)，物料ID(关联dim_material)
  - parse_level (VARCHAR)，L1/L2/L3（问答默认可优先 L1）
```

「领用/流向/谁领用了」类问题查本表；`FLOW_QTY_TOTAL` 等指标须过 12/08 质量门后再当权威口径。

## 3. System Prompt 要点（`text2sql()`）

- 数据库是 DuckDB；**只输出一条 SELECT/WITH**，无解释、无 markdown 代码块。
- 中文过滤条件用 `LIKE '%关键词%'`（列名为英文）。
- 聚合（SUM/COUNT）必须给出具体分组维度。
- 优先 JOIN `dim_material` 获取物资名称。
- 只能引用上述表与列，禁止写操作。

## 4. 实测结果（Qwen2.5-7B，temperature=0）

| 提问 | 生成 SQL | 结果 |
|---|---|---|
| 库存物资一共多少条记录？总数量多少？ | `SELECT COUNT(DISTINCT material_id) AS record_count, SUM(stock_qty) AS total_quantity FROM fact_inventory` | 723 条 / 31434.0 ✓ |
| 光缆类物资的库存总量是多少？按区域统计 | `SELECT region, SUM(stock_qty) FROM fact_inventory JOIN dim_material ON fact_inventory.material_id = dim_material.material_id WHERE dim_material.category LIKE '%光缆%' GROUP BY region` | 空结果正常返回 ✓ |

对照业务库：`fact_inventory` 共 1689 行、SUM(stock_qty)=31434.0，与模型生成 SQL 的执行结果一致。

## 5. 响应结构示例

```json
{
  "question": "库存物资一共多少条记录？总数量多少？",
  "llm": "qwen2.5-7b",
  "ok": true,
  "sql": "SELECT COUNT(DISTINCT material_id) …",
  "rows": 1,
  "columns": ["record_count", "total_quantity"],
  "data": [{"record_count": 723, "total_quantity": 31434.0}],
  "answer": "库存物资共有723条记录，总数量为31434.0。"
}
```

失败场景（模型生成未通过校验 / SQL 执行报错 / LLM 未就绪）：
- `ok: false` + `error` 字段，含可排查信息；不抛 500。

## 6. 已知局限与调优落地

**落地决策（2026-08-06）**：四个局限均有落地方案（6.1~6.4），原则同 04 自学习——**人工修正的 SQL 回写扩展 few-shot 池，越用越准**。

| 局限 | 说明 | 落地（见下） |
|---|---|---|
| 复杂 SQL 偶发错误 | 多表嵌套、窗口函数、时间范围等小模型易写歪 | 6.1 换 big + embed/规则 few-shot |
| 空结果不解释原因 | 只提示"查询结果为空" | 6.2 表画像注入 |
| 中文列名幻觉 | 偶发把中文名当列名 | 6.3 列名白名单二次检查 |
| 单次输出不稳 | temperature=0 仍有小概率漂移 | 6.4 采样 2 次仲裁 |
| 执行结果无验证 | SQL 合法但语义错（求和口径错/过滤过严）执行后无提示 | 6.5 执行后结果校验 |

### 6.1 复杂 SQL：few-shot（含 embed 召回）+ big 路由

- **few-shot 池**按问题类型分桶：聚合统计 / 多表 JOIN / 时间范围 / 模糊过滤 / 空值处理。
- 实测通过的 SQL（见 §4 已验证 2 例）沉淀为示例，落 `meta.sqlite.sql_fewshot` 表：

  | 列 | 说明 |
  |---|---|
  | `question_type` | 问题类型桶 |
  | `question_zh` / `sql` | 示例问题与已验证 SQL |
  | `model` / `verified_by` | 验证模型与确认人（审计） |
  | `created_at` | 时间戳 |

- 提问时先规则分类（关键词："汇总/多少/平均"→聚合；含时间词→时间范围…）；**Stage 1+ 可用 embed 在池内召回 Top-K**，再注入 1~2 条示例（09）。
- 与 04 规则字典同思路：**人工修正过的 SQL 回写扩展 few-shot 池**，越用越准。
- 简单 → `sql_simple`(fast)；复杂 → `sql_complex`(big)；低置信 escalate；见 01 §4 / 09。

### 6.2 空结果解释：表/字段画像注入

**画像体系（四级）**：与模块 03 §1.2 的 workbook/sheet profile 同一方法论，从"文件"一路贯彻到"字段"：

| 层级 | 画像 | 来源 | 计算时机 |
|---|---|---|---|
| 文件级 | workbook/sheet profile：sheet 角色 / 表头 / 数据区 / 异常 | 证据层（规则全量算） | 接入前（03 §1.2） |
| 表级 | 表画像：行数 / 主键唯一率 / 空值率 / 更新时间 | 业务库（DuckDB 全量算） | 入库后 / 定期刷新 |
| 字段级 | 列画像：类型 / 空值率 / 枚举 topN / 数值 min-max-mean / 日期范围 / 单位 | 业务库 | 同上 |

**表/字段画像内容**（规则引擎全量算，LLM 只解读——与"识别用样本、计算用全量"一致）：

| 对象 | 画像项 |
|---|---|
| 表 | 行数、主键唯一率、必填列空值率、最后更新时间 |
| 列（数值） | min / max / mean、空值率、非零占比 |
| 列（枚举/文本） | topN 值及计数（`category`/`region`/`status`…）、去重数 |
| 列（日期） | min / max、跨度 |

**存储**：`meta.sqlite` 新增 `table_profile` / `column_profile` 缓存表——入库后生成、可手动刷新；查询优先读缓存，行数变化超阈值自动重算。DuckDB 全量统计秒级完成，不依赖 LLM。

**用途**（画像不只为空结果解释，是全链路共享能力）：

- **空结果解释**（本节）：总结阶段注入表画像，LLM 区分两种情况：
  - **条件过严**（分布中有该值但被过滤掉）→ 建议放宽条件；
  - **确实无数据**（分布中无该类别）→ 明说"该类别无数据"，而非模糊的"查询结果为空"。
- **schema 注入增强**（§2）：把枚举 topN / 常见值注入 system prompt，WHERE 条件更贴真实数据。
- **few-shot 采样**（6.1）：按问题类型与数据分布选示例。
- **结果校验基准**（6.5）：数值范围 / 行数合理性对比基准。
- **预聚合触发**（6.6）：行数 >50 万 → 路由走预聚合表。
- **质量预检（03 Step3）与主数据匹配（04）**：空值率 / 枚举分布直接复用。

### 6.3 中文列名幻觉：列名白名单二次检查

在既有 SELECT/WITH 白名单基础上，`_validate_sql` 增加**标识符白名单**：

- SQL 中出现的标识符必须 ∈ 业务库表名/列名（information_schema）∪ SQL 函数白名单（`SUM/COUNT/AVG/MAX/MIN/LIKE/COALESCE/CASE/CAST/EXTRACT`…）∪ 字面量。
- 正则提取标识符时避开字符串/数字字面量与 `AS` 别名（别名不在检查范围，需排除 `AS 别名` 与 `GROUP BY 别名` 场景）。
- 命中非白名单标识符（如中文列名）→ 拦截，返回 `ok:false + error`（含原始 SQL 便于排查），不执行。
- 这是模块 05"LLM 产出校验"在 SQL 侧的具体化。

### 6.4 单次输出不稳：2 次采样仲裁

- 关键/复杂查询：`temperature=0.2` 采样 2 次生成 SQL（可与 01 级联叠加：对各侧定稿再比）。
- 仲裁规则（对齐 00 §2.2 / C4，**禁止按行数自动选**）：

  ```
  2 次 SQL 规范化后一致     → 执行
  不一致
      ├─ 任一侧未过白名单 → 丢弃非法侧；仅一侧合法 → 执行合法侧并 warning
      ├─ 两侧都合法且结果集在抽样上一致 → 执行任一侧（记录两侧 sql）
      └─ 两侧都合法但结果不一致 / 无法判定 → conflict，落「待人工」
         （返回两侧 sql + 预览，不自动选「行数多者」）
  ```

- 与降级链联动：普通生成失败可 big→fast→规则；**互验路径禁止 fallback**（01 §5.2 / 09）。语义冲突只进人工。
- 结果正确性最终靠**指标模板、AST 约束与固定评测集**，不能主要依赖「双模型一致」（评审 P2-5）。

### 6.5 执行后结果验证（规则校验，不依赖 LLM）

生成前/生成时防线保证"SQL 合法且尽量正确"，但**执行结果是否正确**还需一道规则校验（全部 DuckDB 级，不耗 LLM）：

| 校验 | 规则实现 | 触发提示 |
|---|---|---|
| 结果集上限 | 超过 `QUERY_ROW_LIMIT`（默认 200）截断 | 超限截断 + "结果超 N 行，已截断，可缩小条件"（`total_rows`/`truncated`） |
| 空结果复核 | 空结果时自动跑"去掉 WHERE 的版本"对比 | 全表有数据 → "过滤条件过严"；全表也空 → "确实无数据"（与 6.2 表画像衔接） |
| 数值范围检查 | SUM/AVG 与表画像列 min/max/历史总量对比，偏差 >N 倍 | "疑似口径错误（如求和列选错）" |
| 行数合理性 | 结果行数 vs 表画像行数 | 0 行 → 过严；≈全量行 → 提示"可能漏过滤" |
| 结果级互验升级 | 互验除 SQL 文本规范化外，加**抽样执行结果一致**（10% 抽样结果集相同才算一致；不一致 → 待人工，不自动选） | 降低「文本不同但结果各异」误收 |

**全链路校验闭环**：

```
生成前（schema 注入 + few-shot）→ 生成时（白名单/互验/仲裁）
→ 生成后（EXPLAIN 可执行性）→ 执行后（本节规则校验）→ 作答（6.2 表画像解释）
→ 兜底（只读连接 + 人工）
```

- 校验结果随响应返回（`warnings` 数组），模块 07 问答页以黄色警告条展示。
- 与 05 的"LLM 产出校验"衔接：本节是**执行结果**校验，05 是**LLM 产出配置**校验，互不替代。

### 6.6 大表查询优化（百万行规模）

DuckDB 列式聚合在百万行上可跑，但复杂 JOIN/窗口函数仍需专项优化：

| 优化 | 实现 |
|---|---|
| **预聚合表** | 高频维度物化表，如 `agg_material_by_category(分类, 数量总和, 记录数, source_release_id, refreshed_at)` |
| **确定性刷新** | **writer 侧任务**（非 LLM）：release 成功后或定时触发全量/增量重建；失败告警，不静默用脏缓存 |
| **源数据版本** | 每张预聚合表记录 `source_release_id`（或等价批次水位）；问答/校验可核对与当前已发布 release 是否一致 |
| **schema 注入标注** | 注入时注明「预聚合；含 GROUP BY 优先」及当前 `source_release_id` |
| **兜底全表** | 预聚合无法满足或版本落后 → 回退主表全量 |
| **触发条件** | 表画像行数 >50 万 且 查询含 `GROUP BY`/聚合 → 路由提示走预聚合 |

- 预聚合清单随表画像维护（§6.2 / 07 概览页）；**禁止**仅在 prompt 里口头要求模型「优先用预聚合」而不落刷新任务。  
- 与 6.5 结果校验配合；版本落后时 `warnings` 提示「预聚合未跟上最近 release」。
