# 架构 Review 与结构性债务

- 日期：2026-08-10（第 2 版：P1–P2 全部落地 + 新增 A0-4 发现；第 1 版：架构师视角整体 review）
- 用途：从架构师视角对 `smart-material-system` 做整体 review，登记结构性债务与拓扑差距；编码前先读 [00-交叉分析与解决方案索引](00-交叉分析与解决方案索引.md) §3.7，本文件提供细节
- 维护：每次复核后更新 §6 状态表；新编号 `A-*` 在 [01-项目问题与进展](01-项目问题与进展.md) §七登记
- 范围：Phase A 已交付 + Stage 1 本地模型接入后的实现态，对照 `docs/`（D1–D9 / C1–C14）

---

## 1. 总体判断

**架构决策（D/C 体系）质量远高于代码组织质量。** 治理思路是生产级的，但代码组织已出现"巨型文件"瓶颈，进入 Phase B / Stage B 之前必须做一次结构性收敛，否则债务会随服务数（当前 45 个）增长指数级放大。

| 维度 | 评分 | 依据 |
|------|------|------|
| 治理文档与决策体系 | A | D1–D9 / C1–C14 闭环，文档与代码一致性高于同类 PoC |
| 存储分层与写入安全 | A- | D1/D2 逻辑到位，但 C2 无进程边界强制（见 A0-3） |
| API 层组织 | C | `routes.py` 1604 行 / 70+ 端点 / 全部 Pydantic 内联（见 A0-1） |
| 前端组织 | C- | `GovernView.vue` 1514 行 / `client.ts` 1307 行 / `components/` 空目录（见 A0-2） |
| 服务层组织 | B- | 45 模块平铺、职责重叠、无子包（见 A1-1） |
| 测试覆盖 | B | intake/govern 流程覆盖好，LLM/OCR/routes/writer 缺单测（见 A1-2） |
| 拓扑实现 | C | 单容器 PoC，与 D3 目标拓扑背离（见 A0-3） |
| 运维可观测 | B+ | 50+ smoke、heartbeat 恢复、writer pause、vLLM watchdog |
| CI/CD | D | 仓库无 CI 配置（见 A1-3） |

---

## 2. 值得肯定的架构决策（重构中不要破坏）

| 项 | 实现 | 价值 |
|----|------|------|
| D1 存储分层 | `db.py` SQLite WAL（meta/tasks/治理队列）+ DuckDB（星型分析） | 职责清晰、读写路径分离 |
| D2 唯一 writer + 幂等发布 | `writer.py` 持锁 + `source_release_id` 幂等 + `version/expected_status/Idempotency-Key` + 409 | 可信流水线正确范式 |
| Crash 一致性 | `compensate_releasing()` 启动回收 + heartbeat 超时恢复 | 对崩溃态有考虑 |
| C3 LLM 无执行权 | LLM 只产建议，写入必经 staging dry-run → ops confirm | AI 辅助治理的安全边界 |
| C4/C5 人工门 | `*_pending` 治理队列是人与模型边界 | 冲突不静默 |
| C14 OpenAPI SSOT | `export_openapi.py` → `openapi.json` → `api:generate` → `api:check` | 前后端契约闭环 |
| C12 AST 防护 | `sql_guard.py` 用 sqlglot | SQL 注入护栏 |
| 运维闭环 | smoke 脚本群 + writer pause for backup + vLLM 内存 watchdog | 运维意识强 |

---

## 3. 架构风险详表（A-*）

### 3.1 P0 级（结构性瓶颈，进入 Phase B 前必须收敛）

#### A0-1 · `routes.py` 巨型文件（1604 行 / 70+ 端点 / 全部 Pydantic 内联）

**现象**

- `app/api/routes.py` 单文件 1604 行，包含全部 `/api/v1` 端点（约 70 个）+ 全部 Pydantic `BaseModel` 内联在文件顶部。
- `app/models/__init__.py` 是空占位符，schema 无独立落点。
- 文件直接 import 15+ service 模块。

**风险**

- 单文件耦合 15+ service，任何 service 改动都要在此文件内定位；
- Pydantic 模型与路由混排，OpenAPI（C14 依赖）全部来自此文件，难以做 schema 复用与版本化；
- 多人协作冲突高发区；
- 无法对单个域做独立测试；
- 拆分风险随时间增长（每多一个端点，拆分成本上升）。

**建议**

按域拆分为 `app/api/routers/`，schema 抽到 `app/api/schemas/`：

```
app/api/
├── routers/
│   ├── files.py        # tasks, sse
│   ├── intake.py       # analyze/profile/quality/plan/stage
│   ├── govern_map.py   # map-*
│   ├── govern_flow.py  # flow-*
│   ├── govern_master.py
│   ├── metrics.py
│   ├── ask.py
│   ├── reports.py
│   ├── ops.py          # backup, models/status
│   ├── export.py
│   └── legacy.py       # query/ingest（见 A2-1）
├── schemas/            # 从 routes.py 抽出的 BaseModel
└── auth.py
```

每个 router 文件目标 < 300 行；`main.py` 用 `include_router` 聚合。

**验收**

- 每个 router 文件 < 300 行；
- `deploy/openapi.json` 字段级 diff = 0（API 契约不变）；
- `npm run api:check` 通过；
- 现有 smoke 全绿。

**关联**：A1-2（拆分前需补端到端测试网）、A1-3（拆分后需 CI 守护）。

---

#### A0-2 · 前端巨型页面 + 无共享组件

**现象**

- `frontend/src/pages/GovernView.vue` **1514 行**，同时承担 mapping / flow / reconcile / master / corrections 五个治理子域 UI；
- `frontend/src/api/client.ts` **1307 行**，单文件聚合所有 API 调用；
- `frontend/src/components/` **空目录**，无共享组件抽取；
- 无 Pinia/Vuex，跨页状态靠 `localStorage`（ops token）与 props。

**风险**

- `GovernView.vue` 可维护性极差，单文件改动易引入回归；
- `client.ts` 与后端域拆分解耦背道而驰，后端拆 router 后前端仍聚在一处；
- 无状态管理 → ops token / 当前 task / 全局错误状态只能靠 localStorage 与 props 传递，刷新即丢；
- 409 冲突处理散落各页，无统一 `ConflictDialog`。

**建议**

1. `GovernView` 拆为 `views/govern/MapPanel.vue` / `FlowPanel.vue` / `ReconcilePanel.vue` / `MasterPanel.vue` / `CorrectionPanel.vue` 子组件，`GovernView` 仅做 tab 容器；
2. `client.ts` 按域拆分：`api/metrics.ts` / `api/govern.ts` / `api/intake.ts` / `api/ops.ts`，与后端 router 拆分对齐；
3. 引入 Pinia：`stores/auth.ts`（ops token）、`stores/task.ts`（当前 task 进度）、`stores/error.ts`（全局错误）；
4. `components/` 至少抽出：`FileUploader`、`ConfirmGate`、`MetricCard`、`ConflictDialog`（409 处理）、`EmptyData`（U-3 unavailable 态）。

**验收**

- 单个 `.vue` 文件 < 400 行；
- `components/` 至少 5 个共享件；
- Pinia store 接管 ops token，刷新不丢；
- `npm run build` 通过，`api:check` drift = 0。

**关联**：A0-1（前后端域拆分对齐）、03 UI-*（前端整改项）。

---

#### A0-3 · 实现拓扑与目标拓扑背离（D3 / C11）

**现象**

- `docs/06` 目标 = Compose 多容器（api / worker / writer 分离）；
- `compose.prod.yml` 注释明确写"worker runs in-process"；
- `app/workers/intake_worker.py` 是同进程 daemon 线程（121 行）；
- `writer.py` 是同进程模块，`writer_conn()` 在 `db.py` 中可被任意 import 方调用。

**风险**

- **C2"只有 writer 写 DuckDB"目前是纪律约束而非进程边界约束**。任何被引入 `routes.py` 的服务只要 `from app.repositories.db import writer_conn` 就能绕过 writer。随着服务数增长（已 45 个），这种约束会失效。
- API 进程崩溃 = worker + writer 一起崩溃，无独立重启语义；
- 备份 `pause_writer()` 只能暂停本进程内的写，未来独立 worker 容器无法被暂停；
- 横向扩展（多 API 副本）不可能，因为 worker + writer 是单例。

**建议**

分两步收敛：

**Step 1（短期，1–2 周）**：worker 进程剥离
- 独立容器 `worker`，复用 `app/workers/intake_worker.py`，通过 SQLite `tasks` 表轮询（已是 C9 设计）；
- API 只负责入队 + SSE 推送，不跑业务逻辑；
- `compose.prod.yml` 增 `worker` service。

**Step 2（中期，Phase B）**：writer 进程剥离
- writer 独立服务，API/worker 通过 HTTP/IPC 调用；
- `writer_conn()` 移出 `db.py`，仅在 writer 服务内可用；
- API/worker 进程物理上无法直连 DuckDB 写。

**短期兜底**（Step 1 之前）：
- `db.py` 加 `writer_conn()` 调用方审计（`_writer_caller_allowlist`），非白名单 import 抛错；
- CI 静态扫描违规 `from app.repositories.db import writer_conn` 的非白名单文件。

**验收**

- Step 1：`docker compose up` 起 api + worker 两容器，杀 api 不影响 worker；
- Step 2：API 进程内 `grep -r writer_conn app/api app/services` 无命中；
- 短期兜底：CI 扫描 0 违规。

**关联**：A1-3（CI 守护）、A2-2（health/ready 真实探测依赖 worker 独立）。

---

#### A0-4 · DuckDB 读写混合连接竞态（worker 线程 vs writer）— P0 新发现

**现象**（2026-08-10 在 A1-4 验证 smoke 时暴露）

- `tests/smoke_phase_a.py` 及所有走 release 路径的 smoke 脚本稳定报错：
  `Connection Error: Can't open a connection to same database file with a different configuration than existing connections`
- 复现条件：worker 线程的 report cron / metric snapshot 调 `biz_conn()`（只读）期间，API 的 confirm/release 调 `writer_conn()`（读写）→ DuckDB 拒绝同文件上只读 + 读写连接共存。
- 已验证为**先于本次 P1/P2 改动存在**（回退 db/config/main 后仍复现）。

**根因**

- `biz_conn()`（只读）不持 `_writer_lock`，与 `writer_conn()`（读写，持锁）无互斥；DuckDB 不允许同文件混合只读/读写连接。
- `_bootstrap_biz()` 每次 `biz_conn()`/`writer_conn()` 都开一个读写连接做 schema ensure，进一步放大竞态窗口。
- 这是 A0-3（worker/writer 同进程）的直接后果：同进程内 worker 与 API 并发访问同一 DuckDB 文件，无连接级互斥。

**影响**

- 所有 smoke 脚本（release 路径）不可用；pytest 因 worker 时序差异暂未触发，但属潜在 flake。
- 阻塞 A1-4 的 smoke 验证（已用 pytest 63 passed 作为验证门）。

**建议**（与 A0-3 合并实施）

- 短期：引入读写锁（readers-writer），`biz_conn()` 取共享、`writer_conn()` 取独占，连接生命周期内持锁；或单连接复用。
- 中期：随 A0-3 Step1 把 worker 剥离为独立进程，进程间不再共享连接，竞态自然消失。
- `_bootstrap_biz()` 改一次性（已尝试但需配合读写锁，单独改会破坏现有连接时序，故回退）。

**验收**

- `tests/smoke_phase_a.py` 在 worker 启用下稳定 `PHASE_A_OK`（当前阻塞）。
- pytest 63 全绿且无新增 flake。

**处置（2026-08-10 已修复，短期方案落地）**

- [db.py](file:///workspace/2026-07/smart-material-system/app/repositories/db.py) 引入 `_RWLock`（reader-writer，writer-preferring + 每线程可重入）：`biz_conn()` 取共享锁、`writer_conn()` 取独占锁，**锁持有期为连接生命周期**（`_LockedConn` 代理在 `close()` 释放），确保同文件只读/读写连接永不并存。
- `_bootstrap_biz()` 改为按路径一次性缓存（`_bootstrapped_paths` + 双重检查），消除每次连接前额外读写连接的放大窗口；bootstrap 使用裸 `duckdb.connect(path)` 且只在无锁区执行。
- 健康探针改 `readonly_probe()`（持共享锁、无 bootstrap 副作用），与写路径互斥（[main.py](file:///workspace/2026-07/smart-material-system/app/main.py)）。
- 验证：真实 4-sheet 台账三域 confirm 连续通过、连接峰值 open=1、零混合模式冲突；pytest 63 passed 无死锁/重入问题。
- 中期方案（A0-3 Step 2 writer 进程剥离）仍为最终收敛路径，本修复为其争取时间。

**关联**：A0-3（根因同源，建议合并实施）、A1-4（被阻塞的 smoke 验证）。

---

### 3.2 P1 级（影响可维护性与质量门）

#### A1-1 · 服务层扁平化 + 职责重叠

**现象**

`app/services/` 45 模块平铺，无子包。职责重叠明显：

| 重叠组 | 模块 |
|--------|------|
| 质量 | `quality.py` + `quality_precheck.py` |
| 流水 | `flow_gov.py` / `flow_parse.py` / `flow_llm.py` / `flow_lineage.py` / `flow_config.py` / `flow_example_snapshot.py` / `flow_eval.py`（7 个） |
| 接入 | `intake.py` / `intake_analyze.py` / `intake_plan.py` |
| 指标 | `metrics.py` / `metric_fixtures.py` |
| 映射 | `mapping.py` / `mapping_suggest.py` / `map_gov.py` / `material_align.py` |

**风险**

- 新人定位困难，命名边界模糊（`mapping.py` 与 `mapping_suggest.py` 谁负责什么？）；
- 易出现重复实现（两个质量模块各写一套校验）；
- import 路径扁平，无法按域做权限/可见性控制。

**建议**

按子域分包：

```
app/services/
├── intake/        # evidence, profile, quality, quality_precheck, plan, staging, ocr_evidence, upload_limits
├── govern/        # map, mapping_suggest, map_gov, flow_*, master, material_align, correction, rule_dict, rule_learn, value_validator, release_diff, field_dict
├── query/         # query, sql_guard, text2sql, analytics, stats_overview, report_runner
├── metrics/       # metrics, metric_fixtures, fewshot
├── llm/           # model_client, embed_recall, policy_router
├── eval/          # eval_skel
└── infra/         # writer, backup, idempotency, jsonutil
```

迁移用 re-export 兼容（`app/services/metrics.py` → `from app.services.metrics.metrics import *`），避免一次性改 15+ import 点。

**验收**

- 每个子包有 `__init__.py` 与 README 说明职责；
- 无重复实现（quality 合并为一个模块或明确分工）；
- 现有 smoke 全绿。

**关联**：A0-1（router 拆分后 import 路径需同步调整）。

---

#### A1-2 · 测试覆盖结构性缺失

**现象**

22 个 pytest 模块主要覆盖 intake/govern 流程，但**无**针对：

| 缺失层 | 风险 |
|--------|------|
| `routes.py`（API 层） | 1604 行无单测，A0-1 拆分缺安全网 |
| `writer.py` | 仅集成测试间接覆盖，D2 核心逻辑无直接断言 |
| `text2sql.py` / `embed_recall.py` / `model_client.py` | Stage 1 核心新增能力，最少测试 |
| `ocr_evidence.py` | OCR 路径无单测 |
| 前端 | 0 测试 |
| analytics / reports 端点 | 大部分无端到端 |

**风险**

- LLM 与 OCR 是 Stage 1 核心新增能力，却是最少测试的部分（最该测的没测）；
- `routes.py` 拆分（A0-1）无安全网，重构即赌运气；
- writer 是数据安全核心，无直接测试意味着幂等/补偿逻辑回归无门禁。

**建议**

1. **拆分前补网**：用 FastAPI TestClient 给 `routes.py` 每个域至少 1 个 happy + 1 个 409 端到端测试（先于 A0-1）；
2. **LLM 契约测试**：用 `vcr.py` 或自建 cassette 录制 vLLM 响应，回放验证 `text2sql` / `embed_recall` / `flow_llm` 的 prompt 构造与响应解析；
3. **writer 单测**：直接断言 `writer.confirm_release()` 的幂等性（同 `source_release_id` 二次调用不重复写）、`compensate_releasing()` 的状态回收；
4. **OCR 单测**：固定样例图 → 期望文本，防 OCR 引擎升级回归；
5. **前端**：至少加 Vitest 组件 smoke（`ConfirmGate`、`ConflictDialog` 渲染）。

**验收**

- `routes.py` 端到端测试覆盖每个 router ≥ 2 用例；
- LLM 路径有 cassette 回放测试；
- writer 幂等单测存在；
- `pytest --cov app/services/llm app/services/writer.py` 覆盖率 > 60%。

**关联**：A0-1（拆分前置）、A1-3（CI 守护）。

---

#### A1-3 · 无 CI 配置

**现象**

仓库根无 `.github/`、`.gitlab-ci.yml`、`Jenkinsfile`。所有验证靠手动跑 smoke。

**风险**

- C14 `api:check` 不会在 PR 上自动执行，OpenAPI drift 无门禁；
- pytest 不会自动跑，回归无门禁；
- smoke 脚本（50+）不会自动跑，运维契约无门禁；
- 多人协作时 PR 合并即赌单测是否通过。

**建议**

最小 CI（GitHub Actions）：

```yaml
# .github/workflows/ci.yml
jobs:
  backend:
    - pip install -r requirements.txt
    - PYTHONPATH=. python3 -m pytest tests/ -q
    - PYTHONPATH=. python3 scripts/smoke_phase_a.py
  frontend:
    - cd frontend && npm ci && npm run api:check && npm run build
```

`api:check` 失败应 block merge；pytest 失败 block merge。

**验收**

- PR 合并前 CI 必跑；
- `api:check` drift ≠ 0 时 CI 红；
- pytest 失败时 CI 红。

**关联**：A0-1（拆分后回归门禁）、A1-2（测试投入才有回报）。

---

#### A1-4 · 测试数据污染生产数据目录

**现象**

`data/` 下混存：

| 类型 | 内容 | 大小 |
|------|------|------|
| 生产运行 | `meta.sqlite` / `material.duckdb` / `uploads/` / `raw_evidence/` / `staging/` / `backups/` | ~40 MB |
| 测试沙盒 | `test_run/` / `test_flow/` / `test_flow_a6/` / `test_flow_a9/` / `test_flow_b1/` / `test_flow_d4/` / `test_flow_harden/`（25 MB）/ `test_f3_sse/` / `real_sample_run/` | ~70 MB |

**风险**

- 环境变量配错（`DATA_DIR` 指错）就会让测试写入生产 DB；
- 备份脚本若 glob `data/` 会把测试沙盒一起备份，膨胀备份体积；
- `.gitignore` 已忽略 `data/`，但 `backup.py` 未显式排除 `test_*`。

**建议**

- 测试沙盒统一迁到 `tests/sandboxes/` 或 `tmp/`，`conftest.py` 强制 `DATA_DIR=tmp/test_data`；
- `backup.py` 显式排除 `test_*` 目录（glob 模式 `data/[!t]` 或显式 allowlist）；
- `config.py` 启动时若 `DATA_DIR` 名以 `test_` 开头则打 warning。

**验收**

- `data/` 下无 `test_*` 目录；
- `backup.py` 备份产物不含测试沙盒；
- `conftest.py` 强制隔离。

**关联**：05 测试工程问题（已闭环，但本项是新发现的污染面）。

---

### 3.3 P2 级（可靠性细节，可排期收敛）

#### A2-1 · 遗留端点与开关管理

**现象**

- `/api/v1/query`（自由 SQL）、`/api/v1/ingest`（遗留写入）仍在 `routes.py`，靠 `ALLOW_FREE_QUERY` / `ALLOW_LEGACY_INGEST` 默认 `0` 关闭。

**风险**

- 开关默认关闭但代码常驻，未来误开即暴露写入口；
- C12 的 AST 防护只覆盖 query，ingest 无类似护栏；
- 拆分 `routes.py`（A0-1）时这两个端点应单独管理。

**建议**

- 遗留端点移到 `app/api/routers/legacy.py`，在 `main.py` 按 env 条件 `include_router`（`if config.ALLOW_LEGACY_INGEST`）；
- ingest 路径补 AST 白名单校验，与 query 同等防护；
- 文档明确遗留端点的下线时间表（Phase B 是否删除？）。

**验收**

- 默认部署 `ALLOW_LEGACY_INGEST=0` 时 `/api/v1/ingest` 返回 404；
- ingest 有 AST 校验单测。

---

#### A2-2 · `health/ready` 过于乐观

**现象**

`app/main.py:147` 中 `biz_db` 检查是 `Path(config.BIZ_DB).exists() or True` —— `or True` 让它永远返回 `True`；worker 也直接硬编码 `True`。

**风险**

- readiness 失去意义，k8s/Compose 探针无法据此判断是否就绪；
- DuckDB 文件被锁/损坏时 readiness 仍绿；
- worker 线程死掉时 readiness 仍绿。

**建议**

- `biz_db` 探测：尝试 `biz_conn()` 跑 `SELECT 1`，失败返回 `False`；
- worker 探测：检查 `worker.is_alive()`（需 `intake_worker.py` 暴露线程句柄）；
- `/health/ready` 失败时返回 503，让 Compose `healthcheck` 据此重启。

**验收**

- DuckDB 文件锁时 `/health/ready` 返回 503；
- worker 线程 kill 后 `/health/ready` 返回 503。

**关联**：A0-3（worker 独立后探测更直接）。

---

#### A2-3 · `config.py` 全局副作用

**现象**

`config.py:93` 在 import 时 `mkdir`，导致任何 `import app.config` 都会创建目录，测试隔离性受损。

**风险**

- 测试中 `DATA_DIR` 设到临时路径后，import 即创建目录，无法验证"目录不存在"分支；
- `config.py` 被多模块 import，副作用顺序不可控。

**建议**

- 把目录初始化移到显式 `ensure_dirs()` 函数，在 `init_meta()` 或 `lifespan` 中调用；
- `config.py` 只做常量定义，无副作用。

**验收**

- `import app.config` 不创建任何目录；
- `ensure_dirs()` 在 lifespan 中显式调用。

---

## 4. 与治理文档的一致性核对

| 治理项 | 代码一致性 | 备注 |
|--------|-----------|------|
| D1 SQLite+DuckDB | ✅ | `db.py` 实现到位 |
| D2 唯一 writer | ⚠️ | 逻辑到位，但无进程边界强制（A0-3） |
| D3 多容器拓扑 | ❌ | 仍单容器，文档自承 PoC（A0-3） |
| D6 lineage 回滚 | ✅ | `flow_lineage.py` / `rebuild_stock_flow.py` |
| C2 仅 writer 写 | ⚠️ | 纪律约束，非物理隔离（A0-3） |
| C7 数据本地 | ✅ | 无外部调用 |
| C12 AST 防护 | ✅ | `sql_guard.py` 用 sqlglot |
| C14 OpenAPI SSOT | ✅ | 但缺 CI 强制（A1-3） |

整体一致性高于同类项目，但 D3/C2 的"实现滞后于文档"需要在 Phase B 路线图中明确收敛计划，否则会形成"文档说一套、代码做一套"的长期债务。

---

## 5. 收敛路线图

| 优先级 | 工作 | 估时 | 价值 | 依赖 |
|--------|------|------|------|------|
| P0 | A1-2 拆分前补 `routes.py` 端到端测试网 | 2–3 天 | 重构安全网 | 无 |
| P0 | A0-1 拆分 `routes.py` 为 `routers/` + `schemas/` | 3–5 天 | 解锁后续所有改动 | A1-2 |
| P0 | A1-3 引入 CI（pytest + api:check + 关键 smoke） | 1 天 | 防回归 | A1-2 |
| P0 | A1-4 测试沙盒迁出 `data/` | 0.5 天 | 消除数据污染风险 | 无 |
| P1 | A0-2 前端 `GovernView` + `client.ts` 拆分 + 引入 Pinia | 5 天 | 前端可维护性 | A0-1 |
| P1 | A1-1 services 子包化 | 2 天 | 服务定位 | A0-1 |
| P1 | A0-3 Step 1 worker 进程剥离（独立容器） | 5–7 天 | 兑现 D3 | A1-3 |
| P2 | A0-3 Step 2 writer 进程剥离 / `writer_conn` 调用审计 | 7–10 天 | 物理兑现 C2 | A0-3 Step1 |
| P2 | A1-2 LLM 路径契约测试 | 3 天 | Stage 1 质量门 | A1-3 |
| P2 | A2-1/A2-2/A2-3 遗留端点 + health + config 清理 | 1–2 天 | 运维可靠性 | 无 |

**关键路径**：A1-2 → A0-1 → A1-3 → A0-3 Step1。建议在 Phase B 新功能开工前完成 P0 四项（约 1.5 周）。

---

## 6. 状态表

| ID | 问题 | 优先级 | 状态 | 验收 |
|----|------|--------|------|------|
| A0-1 | `routes.py` 1604 行巨型文件 | P0 | 🔶 待开工 | 每 router < 300 行 + OpenAPI diff = 0 |
| A0-2 | 前端巨型页面 + 无共享组件 | P0 | 🔶 待开工 | 单 .vue < 400 行 + Pinia 接管 token |
| A0-3 | 实现拓扑与 D3 背离（worker/writer 同进程） | P0 | 🔶 待开工 | Step1: api+worker 双容器；Step2: writer 独立 |
| A0-4 | DuckDB 读写混合连接竞态（worker vs writer） | P0 | 🔶 待开工（随 A0-3） | smoke_phase_a 在 worker 启用下稳定 OK |
| A1-1 | services 45 模块扁平 + 职责重叠 | P1 | ✅ 已落地（2026-08-10） | 子包化 + 无重复实现 |
| A1-2 | 测试覆盖结构性缺失（routes/writer/LLM/OCR/前端） | P1 | ✅ 已落地（2026-08-10） | routes 端到端 + LLM cassette + writer 幂等单测 |
| A1-3 | 无 CI 配置 | P1 | ✅ 已落地（2026-08-10） | PR 合并前 CI 必跑 + api:check block |
| A1-4 | 测试沙盒污染 `data/` | P1 | ✅ 已落地（2026-08-10） | `data/` 无 `test_*` + backup 排除 |
| A2-1 | 遗留端点（query/ingest）开关管理 | P2 | ✅ 已落地（2026-08-10） | 默认 404 + ingest AST 校验 |
| A2-2 | `health/ready` 过于乐观 | P2 | ✅ 已落地（2026-08-10） | DuckDB 锁/worker 死时返回 503 |
| A2-3 | `config.py` import 时 mkdir 副作用 | P2 | ✅ 已落地（2026-08-10） | import 无副作用 + 显式 ensure_dirs |

---

## 7. 落地记录（2026-08-10 P1–P2 收敛）

本轮按 §5 路线图依次落地 P1–P2 全部 7 项 + 顺带修复 2 个前端构建阻塞。验证门：`pytest tests/` 63 passed + OpenAPI/frontend 类型 drift = 0 + frontend `npm run build` 通过 + `data/` 无 `test_*`。

| ID | 改动 | 验证 |
|----|------|------|
| A2-3 | `app/config.py` 移除 import 时 `mkdir` 循环，改 `ensure_dirs()`；由 `meta_conn()` / `_bootstrap_biz()` 懒调用 | `import app.config` 不创建目录；`ensure_dirs()` 后目录就绪 |
| A2-2 | `app/main.py` `/health/ready` 真实探测 DuckDB `SELECT 1` + `worker.is_alive()`；`app/workers/intake_worker.py` 增 `is_alive()` | fresh/已 bootstrap 两态均 200；worker stop 后 503 |
| A1-3 | 新增 `.github/workflows/ci.yml`：backend（pytest + OpenAPI drift + smoke）+ frontend（api:check + build），失败 block merge | 本地 `export_openapi.py` + `api:generate` drift = 0 |
| A1-4 | 9 个 `data/test_*` + `real_sample_run` 迁至 `tests/sandboxes/`；10 个脚本/测试改路径；`config._warn_test_data_dir()`（仅 DATA 在 `tests/sandboxes` 下告警）；`backup.py` 仅拷特定文件本就不含沙盒 | `data/` 无 `test_*`；pytest 无新增告警 |
| A2-1 | 新增 `app/api/legacy.py`（`/query`、`/ingest`），从 `routes.py` 抽出；`main.py` 始终挂载（OpenAPI 稳定），handler 在 flag off 时返回 404；`/query/tables` 留 `routes.py`；ingest 注释要求未来 AST 白名单 | flag off → 404；flag on → /query 200、/ingest 501；`test_legacy_endpoints.py` 4 用例 |
| A1-2 | 新增 3 个测试文件 23 用例：`test_routes_smoke.py`（13 端点，禁 worker 避 A0-4 flake）、`test_writer_idempotent.py`（RELEASED 短路 + 版本冲突）、`test_llm_client_cassette.py`（mock `_http_json` 验响应解析/思维标签剥离/熔断器/审计） | pytest 40 → 63 |
| A1-1 | `app/services/` 45 模块按 7 子包重组（intake/govern/query/metrics/llm/eval/infra），每个原路径留 re-export shim（复制所有非 dunder 名）；`intake`/`metrics`/`query` 同名包由 `__init__.py` re-export 同名模块；移除被包遮蔽的 3 个死 shim；2 个 LLM 测试改 import 真实子包模块 | 45 模块 import OK；pytest 63 全绿；OpenAPI + 前端类型 drift = 0 |
| 附带 | 修 `AskView.vue` 未用 `valueZh` 导入、`fields.ts` `table` 未用参（vue-tsc 阻塞 build） | `npm run build` 通过 |

**未做（明确留待 P0）**：A0-1（`routes.py` 拆 `routers/`）、A0-2（前端巨型页面拆分 + Pinia）、A0-3（worker/writer 进程剥离）、A0-4（DuckDB 读写竞态，随 A0-3）。A1-1 的"无重复实现"（quality/quality_precheck 等语义合并）留作后续，本轮仅做结构分包。

---

## 8. 一句话总结

**架构决策（D/C 体系）质量远高于代码组织质量**——治理思路是生产级的，但 `routes.py` 1604 行、`GovernView.vue` 1514 行、worker/writer 同进程这三处是当前架构债务的"三座大山"，建议在投入 Phase B 新功能前先做一次结构性收敛（P0 四项约 1.5 周），否则债务会随服务数增长指数级放大。

