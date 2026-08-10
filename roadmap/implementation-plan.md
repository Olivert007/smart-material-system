# 规整/清洗后数据处理 · 实施方案

> 版本：v0.1（2026-08-09） · 状态：待评审
> 目标：补齐系统在"观察端"（清洗质量监控、二次加工）与"演进端"（发布生命周期、规则增强）的能力。
> 原则：**LLM 只建议、人工确认才写**；**禁止原地 UPDATE 事实行**；所有变更走现有 meta 表 + 幂等写入范式。

---

## 0. 现状与差距

当前数据链路（已实现）：

```
上传 → raw_evidence(*.parquet) → tabular → Staging(规整清洗) → Ops 确认 → writer 幂等写入 DuckDB 星型模型
                                                          │                                │
                                                          └─ blocked 仅计数（无明细）       ├─ 查询/问答（AST 只读）
                                                                                          ├─ FLOW_* 指标（实时求值，不留历史）
                                                                                          ├─ 勾稽对账
                                                                                          └─ 血缘审计 / release 重建吊销
```

差距（按依赖排序）：

| # | 差距 | 后果 |
|---|------|------|
| 1 | blocked 行无明细（[staging.py](file:///workspace/2026-07/smart-material-system/app/services/staging.py#L145-L155) 只写 `blocked_rows` 计数） | 无法回答"被拒的是什么、为什么拒" |
| 2 | 清洗规则仅表头→标准字段映射（[rule_dict.py](file:///workspace/2026-07/smart-material-system/app/services/rule_dict.py#L62-L159)），无值域/格式校验 | 坏数据只能"拒"不能"审" |
| 3 | 发布无版本语义（[writer.py](file:///workspace/2026-07/smart-material-system/app/services/writer.py#L152-L271) delete-and-replace by release_id） | 无增量更新、无新旧对比、无单行修正通道 |
| 4 | 消费侧仅临时拉取（查询/指标实时算） | 无报表产物、无指标时间序列 |

---

## 1. 总体架构

四个阶段，按依赖排序（后一阶段可复用前一阶段的表与函数）：

```
P1 清洗可观测 ──┬─→ P2 规则增强（自学习依赖 blocked 明细）
                │
                └─→ P3 发布生命周期（supersede 语义 + 版本 diff）
P4 二次加工（报表快照 + 指标时序）  ← 与 P2/P3 并行，P4.2 依赖现有 evaluate 引擎
```

里程碑：
- **M1 = P1 + P2**：清洗质量闭环（明细 → 报告 → 规则 → 再清洗）
- **M2 = P3**：发布生命周期（版本标记 + diff + 修正）
- **M3 = P4**：消费侧（报表产物 + 指标历史）

---

## 2. P1 清洗可观测（Blocked 明细 + 质量报告）

### 2.1 数据模型（meta.sqlite，[db.py](file:///workspace/2026-07/smart-material-system/app/repositories/db.py#L90-L130) `init_meta` 追加）

```sql
CREATE TABLE IF NOT EXISTS staging_blocked (
    block_id      TEXT PRIMARY KEY,
    staging_id    TEXT NOT NULL,          -- 关联 staging_record.staging_id
    file_id       TEXT NOT NULL,
    target_domain TEXT NOT NULL,
    source_row    INTEGER,                -- 原始行号（0 基）
    header        TEXT,                   -- 触发字段（可为空=整行）
    reason_code   TEXT NOT NULL,          -- MISSING_COL/TYPE_ERROR/VALUE_RANGE/
                                          -- UNKNOWN_HEADER/FORMAT_INVALID/CELL_MARKER/OTHER
    reason_detail TEXT,                   -- 规则说明、期望值
    raw_value     TEXT,                   -- 原值（截断 200 字符）
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_staging_blocked_sid ON staging_blocked(staging_id);
CREATE INDEX IF NOT EXISTS idx_staging_blocked_code ON staging_blocked(reason_code);
```

### 2.2 后端改动

- [staging.py](file:///workspace/2026-07/smart-material-system/app/services/staging.py#L26-L225) `create_staging`：
  - tabular 路径：对 blocked 行逐行定位原因（缺列/类型/值域/未知表头），调用新校验器产出明细（见 P2.1）；
  - cell_evidence 路径：`value_type == 'marker'` 的行统一 `reason_code=CELL_MARKER`；
  - 明细在**同一 meta 事务**内写入，`INSERT ... ON CONFLICT(staging_id) DO` 保证 staging 重建时刷新明细（旧明细按 staging_id 先 DELETE）；
  - **命中缓存（status=STAGED/RELEASING 复用）时不重算**，避免重复工作。
- 新增 `app/services/quality.py`：
  - `quality_report(file_id)` → 聚合：clean/blocked、blocked 按 reason_code 分布、按 header 分布 top10、关键列非空率/非法值率；
  - `quality_report_by_release(release_id)` → 发布质量快照（经 release_manifest 反查 staging_id）。
- [routes.py](file:///workspace/2026-07/smart-material-system/app/api/routes.py) 新增端点（只读，无需 Ops Token）：
  - `GET /api/v1/stats/quality/{file_id}`
  - `GET /api/v1/stats/quality/release/{release_id}`
  - `GET /api/v1/stats/quality/{file_id}/blocked?limit&offset`（明细分页，供前端查看）

### 2.3 质量基线指标（复用 [metrics.py](file:///workspace/2026-07/smart-material-system/app/services/metrics.py#L213-L255) 引擎）

- 新增 seed 指标（engine=**meta**，新增 evaluate 分支，不连 DuckDB 业务库）：
  - `INTAKE_BLOCK_RATE` = blocked / (clean + blocked)
  - `INTAKE_CLEAN_RATE` = clean / total
  - `INTAKE_UNKNOWN_HEADER_CNT` = 按 reason_code=UNKNOWN_HEADER 计数
- 激活沿用 08 门禁流程（draft → gate → active），与 FLOW_* 一致；**只改 meta，不写业务库**。

### 2.4 前端

- [StageView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/StageView.vue)：新增"质量摘要"卡（clean/blocked + 分布条形 + 明细表分页）。
- [HomeView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/HomeView.vue)：概览卡片追加 `INTAKE_BLOCK_RATE`（复用现有 FLOW_* 求值逻辑）。
- `client.ts / generated.ts` 补类型与调用。

### 2.5 验收

1. 上传含坏行的文件 → staging 生成后 `staging_blocked` 有逐行明细；
2. 质量接口返回分布且与计数一致；
3. 同一文件二次 staging（version+1）→ 明细刷新而非累积；
4. `INTAKE_BLOCK_RATE` 可激活、可求值。

---

## 3. P2 清洗规则增强（值域校验 + 自学习原料）

### 3.1 校验规则模型

新增独立表（避免 rule_dict 语义混杂）：

```sql
CREATE TABLE IF NOT EXISTS value_rule (
    rule_id       TEXT PRIMARY KEY,
    domain        TEXT NOT NULL,          -- inventory/asset/demand/stock_flow
    std_field     TEXT NOT NULL,          -- 作用于标准字段
    check_type    TEXT NOT NULL,          -- required / numeric_positive / date_iso /
                                          -- enum / regex / max_length
    params_json   TEXT,                   -- {"values":[...],"pattern":"...","max":100}
    severity      TEXT NOT NULL DEFAULT 'block',  -- block（拒行）/ warn（仅标记）
    status        TEXT NOT NULL DEFAULT 'proposed', -- proposed/active/disabled
    confirmed_by  TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 3.2 校验器

- 新增 `app/services/value_validator.py`：`apply_checks(df, domain, rules) -> (clean_df, blocked_details)`
  - 按 `std_field` 从已映射 DataFrame 取列 → 逐行校验 → 产出 `reason_code` + `reason_detail` + `raw_value`；
  - **block** 行进 blocked 明细（P1 表）；**warn** 行标记但放行（clean_df 加 `_warn` 列，不进明细）。
- [staging.py](file:///workspace/2026-07/smart-material-system/app/services/staging.py) 集成顺序：`normalize_tabular → resolve_columns → apply_checks`。

### 3.3 治理中心「校验规则」子页

- 复用 [GovernView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/GovernView.vue) 的"建议 → 人工确认"模式：
  - `GET /api/v1/govern/value-rules`（列表，按 status 过滤）
  - `POST /api/v1/govern/value-rules`（新建 proposed，需 Ops Token）
  - `POST /api/v1/govern/value-rules/{id}/confirm`（proposed → active，写 govern_confirm 留痕）

### 3.4 规则自学习（只产候选，不自动回写）

- 新增 `app/services/rule_learn.py`：
  - 从 `staging_blocked` 聚合：UNKNOWN_HEADER 高频表头 → 复用 [mapping_suggest.py](file:///workspace/2026-07/smart-material-system/app/services/mapping_suggest.py) 的 embed/lexical 候选 → 生成**候选映射**；
  - 高 block 率的 `(domain, std_field)` → 生成**候选校验规则**（如"该列 80% 为空，建议 required"）；
  - 候选统一写入 `govern_confirm(source='rule_learn')`，治理中心待确认列表可见，确认后回写 rule_dict / value_rule。
- 新增端点：`GET /api/v1/govern/rule-learn/candidates?limit`（只读，展示候选）。

### 3.5 验收

1. 新建"数量>0"校验规则并激活；上传违反规则的文件 → 对应行进 blocked 明细且 `reason_code=VALUE_RANGE`；
2. 未激活规则不影响 staging（默认只读 active）；
3. 学习接口能对高频未知表头产出候选映射清单，且**未自动写入**。

---

## 4. P3 发布生命周期（supersede + 版本 diff）

### 4.1 supersede 关系（元数据层，物理行不动）

```sql
ALTER TABLE release_manifest ADD COLUMN supersedes TEXT;   -- 被本 release 替代的 release_id
ALTER TABLE release_manifest ADD COLUMN superseded_by TEXT; -- 替代本 release 的 release_id
-- 迁移：旧行默认 NULL（表示当前有效）
```

- [routes.py](file:///workspace/2026-07/smart-material-system/app/api/routes.py) `POST /intake/stage/{file_id}/confirm` 的 body 增加可选 `supersedes: str | null`；
- [writer.py](file:///workspace/2026-07/smart-material-system/app/services/writer.py) `confirm_release` 写入 release_manifest 时一并记录 supersedes，并**事务内**把被替代 release 的 `superseded_by` 回填；
- **决策点 D1**（需评审）：查询层是否自动排除 superseded release。
  - 方案 A（推荐首期不做）：只标记 + 管理界面展示，查询语义不变——不破坏现有 LLM SQL/AST；
  - 方案 B：`v_material_inventory` 等视图改为"最新非 superseded release"，需同步 [schema.py](file:///workspace/2026-07/smart-material-system/app/repositories/schema.py#L218-L227) 视图与 stats/勾稽逻辑，风险面大，放后续迭代。

### 4.2 版本 diff

- **数据源直接用 `fact_release_rows`**（[schema.py](file:///workspace/2026-07/smart-material-system/app/repositories/schema.py#L119-L128)：按 `source_release_id` + `row_key` + `payload_json` 全量快照），无需新增存储。
- 新增 `app/services/release_diff.py`：`diff(release_a, release_b)` 按 row_key 对比 payload_json → 分组为 added / removed / changed（字段级差异前 N 个）。
- 新增端点：`POST /api/v1/govern/release/diff {release_a, release_b}` → 汇总 + 明细（limit 200）。
- 前端 [OpsView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/OpsView.vue)：新增"发布生命周期"卡：
  - release 列表（状态含 superseded 标记、supersede 链）；
  - 选择两版 → diff 表格；"标记 supersede"操作（需 Ops Token）。

### 4.3 单行修正通道（可选，依赖 4.1）

```sql
CREATE TABLE IF NOT EXISTS correction_request (
    correction_id TEXT PRIMARY KEY,
    release_id    TEXT NOT NULL,
    row_key       TEXT NOT NULL,
    field         TEXT NOT NULL,
    value_new     TEXT,
    reason        TEXT,
    status        TEXT NOT NULL DEFAULT 'proposed',  -- proposed/applied/declined
    actor         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- **applied = 以修正后的完整 payload 生成新 release + supersede 原 release**（复用 4.1 与幂等 writer），**绝不原地 UPDATE**。

### 4.4 验收

1. 同一文件发布两版库存 → release 列表可见 supersede 关系，双方字段互指正确；
2. diff 对数量/字段变化行给出 added/removed/changed 分组；
3. 全程无 `UPDATE fact_*` 原地修改（write_audit 可查）。

---

## 5. P4 二次加工（报表快照 + 指标时序）

### 5.1 报表定义与执行

```sql
CREATE TABLE IF NOT EXISTS report_definition (
    report_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    query_sql   TEXT NOT NULL,           -- 只读 SQL，经 AST 校验
    params_json TEXT,                    -- 可选参数模板
    cron_expr   TEXT,                    -- 空 = 仅手动触发
    active      INTEGER DEFAULT 1,
    created_by  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS report_run (
    run_id        TEXT PRIMARY KEY,
    report_id     TEXT NOT NULL,
    status        TEXT NOT NULL,          -- pending/running/done/failed
    started_at    TEXT,
    finished_at   TEXT,
    artifact_path TEXT,                   -- data/reports/{report_id}/{run_id}.parquet(+csv)
    row_count     INTEGER,
    error         TEXT
);
```

- 新增 `app/services/report_runner.py`：参数绑定 → 复用 [query.py](file:///workspace/2026-07/smart-material-system/app/services/query.py#L29-L37) 的 AST 只读校验 + 行数上限（`QUERY_ROW_LIMIT` 同类约束）→ DuckDB 执行 → 落盘 `data/reports/` → 更新 run 状态。
- **调度**：并入现有 [intake_worker.py](file:///workspace/2026-07/smart-material-system/app/workers/intake_worker.py#L46-L64) 轮询循环（`claim_next_report`，按 cron 到期或手动触发入队），不新增线程；与 intake 任务共用 claim/心跳/恢复模式。
- 端点：
  - `GET /api/v1/reports`（定义列表）
  - `POST /api/v1/reports`（建定义，Ops Token；SQL 过 AST 校验）
  - `POST /api/v1/reports/{report_id}/run`（手动触发，返回 run_id）
  - `GET /api/v1/reports/{run_id}/file`（下载 parquet/csv）
- 前端：新增 `ReportsView.vue`（报表定义 + 运行历史 + 下载），并入路由与菜单。

### 5.2 指标时间序列

```sql
CREATE TABLE IF NOT EXISTS metric_snapshot (
    snapshot_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_id    TEXT NOT NULL,
    value        DOUBLE,
    unit         TEXT,
    status       TEXT,
    evaluated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [metrics.py](file:///workspace/2026-07/smart-material-system/app/services/metrics.py) `evaluate_metric` 增加 `write_snapshot`（默认 True 或按 metric 配置），结果落库；
- 前端 [MetricsView.vue](file:///workspace/2026-07/smart-material-system/frontend/src/pages/MetricsView.vue)：「求值」列加"近 N 次"展开（简单表格/迷你趋势，不引图表库）。

### 5.3 验收

1. 创建报表定义 → 手动运行 → artifact 落盘且可下载，SQL 非只读被拒；
2. FLOW_* 连续求值 → `metric_snapshot` 有历史，MetricsView 可看趋势；
3. worker 空闲时 cron 报表按时触发，与 intake/flow-LLM 队列互不阻塞。

---

## 6. 涉及文件清单

**后端**
- [app/repositories/db.py](file:///workspace/2026-07/smart-material-system/app/repositories/db.py)（init_meta 追加 4 张新表 + 索引）
- [app/repositories/schema.py](file:///workspace/2026-07/smart-material-system/app/repositories/schema.py)（P4 视图像改仅在决策点 D1=方案 B 时）
- [app/services/staging.py](file:///workspace/2026-07/smart-material-system/app/services/staging.py)（blocked 明细写入 + 校验器集成）
- 新增 `app/services/quality.py`、`app/services/value_validator.py`、`app/services/rule_learn.py`、`app/services/release_diff.py`、`app/services/report_runner.py`
- [app/services/metrics.py](file:///workspace/2026-07/smart-material-system/app/services/metrics.py)（engine=meta 分支 + snapshot 落库 + 新 seed 指标）
- [app/services/writer.py](file:///workspace/2026-07/smart-material-system/app/services/writer.py)（supersedes 记录）
- [app/services/query.py](file:///workspace/2026-07/smart-material-system/app/services/query.py)（报表 SQL 校验复用）
- [app/workers/intake_worker.py](file:///workspace/2026-07/smart-material-system/app/workers/intake_worker.py)（report claim 轮询）
- [app/api/routes.py](file:///workspace/2026-07/smart-material-system/app/api/routes.py)（新增约 10 个端点）

**前端**（[frontend/src/pages/](file:///workspace/2026-07/smart-material-system/frontend/src/pages)）
- StageView / HomeView / GovernView / OpsView / MetricsView 增量改动
- 新增 ReportsView.vue + [router/index.ts](file:///workspace/2026-07/smart-material-system/frontend/src/router/index.ts) 注册
- [api/client.ts](file:///workspace/2026-07/smart-material-system/frontend/src/api/client.ts) / generated.ts 补类型

**测试**
- `tests/test_staging_blocked.py`（明细正确性、重建刷新）
- `tests/test_value_rules.py`（校验器 block/warn 行为）
- `tests/test_release_diff.py`（diff 分组正确性、supersede 关系）
- `tests/test_reports.py`（只读校验、落盘、下载）

---

## 7. 风险与决策点

| # | 风险/决策 | 说明 | 建议 |
|---|-----------|------|------|
| D1 | superseded release 是否自动退出查询视图 | 影响 LLM SQL / stats / 勾稽 | 首期只标记+diff，视图语义后续再改 |
| R1 | `staging_blocked` 膨胀 | 明细随 staging 重建刷新，但仍累计 | 保留最近 N 份 staging 的明细，超出按 staging_id 清理 |
| R2 | 报表 SQL 误用 | 非只读 / 超大结果 | 复用 AST 校验 + 行数上限 + cron 防重入（run 状态锁） |
| R3 | worker 队列互相饿死 | intake/flow-LLM/report 共用循环 | 每轮各类型至多 1 个任务，保留现有 poll 节拍 |
| R4 | 指标 engine=meta 与 biz 语义混淆 | `definition_sql` 执行库不同 | metric_dict 增加 `engine` 已存在，evaluate 按 engine 分派，测试覆盖 |

---

## 8. 落地顺序建议

1. **P1（blocked 明细 + 质量报告 + INTAKE_* 指标）**——最独立、收益最直接；
2. **P2（校验规则 + 规则学习候选）**——依赖 P1 明细；
3. **P4（报表快照 + 指标时序）**——可与 P2 并行，独立性强；
4. **P3（supersede + diff + 修正）**——涉及 writer 与决策点 D1，放最后收口。

每个阶段独立可交付、可回滚（仅新增表/端点，不改既有语义）。
