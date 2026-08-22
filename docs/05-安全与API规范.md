# 模块 05 · 安全与 API 规范

> 代码落点：`app/api/routers/*`（分域子路由，聚合入口 `app/api/routes.py`）、`app/repositories/db.py`（meta/biz 连接）、`app/services/llm/*`（模型调用）、`app/main.py`。  
> **本模块是接口与安全 SSOT**；与 [00-总览 §2](00-总览.md) 硬约束冲突时，改实现/他文对齐本文 + 总览。  
> 版本：Phase 2.2（2026-08-08）— 对齐 [00 D1–D9](00-总览.md)；前后端契约见 [11](11-前后端分离与容器化.md)

---

## 0. API 前缀与健康检查（D9）

| 类别 | 路径 | 说明 |
|---|---|---|
| 业务 API | **`/api/v1/*`** | 新接口与 OpenAPI SSOT；实现迁移期可双挂旧 `/api/*` 并标 deprecated |
| 健康 | `/health/live`、`/health/ready` | **不**放在 `/api/v1` 下；见 11 §11 |
| SSE | `/events/*` | 任务进度等；经同源代理；库内任务状态仍为 SSOT |

下文表格中的 `/api/…` 在实现时映射为 `/api/v1/…`（除非注明 legacy）。前端只使用相对 `API_BASE="/api/v1"`（C13）。

---

## 1. 安全机制

### 1.1 SQL 防线（AST 为主，C12）

**主判定**：用 sqlglot（或同等）解析 AST，字符串黑名单/剥注释仅为辅助。

| 规则 | 要求 |
|---|---|
| 单 statement | 禁止多语句 |
| 根节点 | 仅 SELECT 或受约束的 WITH→SELECT |
| 禁止节点/功能 | ATTACH/COPY/PRAGMA/INSTALL/LOAD、写操作、文件/网络 table function |
| 标识符白名单 | 表/列/函数/schema ∈ information_schema ∪ 函数白名单 |
| 连接硬化 | DuckDB 关闭 external access；限制内存、线程、结果行数、执行时间 |
| 产品策略 | 普通用户优先指标模板与受控 `/api/ask`；自由 `/api/query` 收缩（00 §3.3） |

只读 `biz_conn()` 仍是最后兜底。辅助剥注释用例保留在验收清单。

### 1.2 写入防线（唯一 writer，D2）

| 规则 | 说明 |
|---|---|
| 查询永不写 | API/worker 对业务库只用只读连接 |
| 唯一写 | **仅 writer service** 打开业务库读写；API 不直接 `biz_write_conn` |
| 合法路径 | confirm→幂等 release / master_apply / lineage_rebuild（00 §3.1） |
| 审计 | SQLite `write_audit`；`actor` 来自认证主体（§1.5） |
| legacy | `/api/ingest` 默认 403 |
### 1.3 LLM 产出校验（防幻觉驱动）

| 产出物 | 校验规则 | 不通过处理 |
|---|---|---|
| 清洗配置（03 §1.1） | `std_field` ∈ 04 §1；`clean` ∈ 动作库；`adapter` ∈ 适配器清单；`header_row` 合法；`master`/`dedup` 引用存在列；region 边界合法 | 进治理，**不执行** |
| 表头映射（04） | `std_field` ∈ 04 §1 ∪ `ignore` | 非法 → ignore 候选 + 提示 |
| SQL | §1.1 + 标识符白名单（02 §6.3） | 不执行 |
| 指标定义（08） | 仅人工 API 可写字典；`definition_sql` 必须过 §1.1 且为单条 SELECT/WITH | 拒绝保存 |

核心原则：**LLM 输出只是建议**；过白名单/人工确认后才有执行资格（C3）。

### 1.4 上传文件安全校验

**限额配对（实现默认值，环境变量可覆盖；与 [11 §5.3/§8](11-前后端分离与容器化.md) 一致）**：

| 度量 | 默认 | 环境变量（建议） | 说明 |
|---|---|---|---|
| 原始上传单文件 | **2 GiB** | `UPLOAD_MAX_BYTES` | Nginx `client_max_body_size` **同值** |
| 单批文件数 | **50** | `UPLOAD_MAX_FILES` | |
| 单批总大小 | **4 GiB** | `UPLOAD_MAX_BATCH_BYTES` | |
| 解压后体积 | **500 MiB** | `UPLOAD_MAX_EXTRACT_BYTES` | 压缩炸弹；与「原始 2g」不同度量 |
| 解压文件数 | **10000** | `UPLOAD_MAX_EXTRACT_FILES` | |
| 上传目录配额 | **200 GiB** | `UPLOAD_DIR_QUOTA_BYTES` | 含临时与正式 |
| 临时文件 TTL | **24h** | `UPLOAD_TMP_TTL_HOURS` | 过期清理 |

| 校验 | 规则 |
|---|---|
| 路径穿越 | `../`、绝对路径、NUL → 400 |
| 越界 symlink | 指向上传目录外 → 400 |
| 压缩炸弹 | 解压体积/文件数超上表 → 400 |
| 宏 | 不执行宏；xlsm 只读数据 |
| 外链 | DDE/外部超链接不跟随，仅记录 |
| 类型伪装 | 扩展名与 magic bytes 不符 → 按实型或拒绝 |
| 流式落盘 | **禁止**整文件 `read()` 进内存；分块写临时文件 + 增量哈希（11 §8） |
| 重复哈希 | 同 SHA256 策略可配置：复用已有 file_id 或拒绝 |

校验在解析前完成；失败删除临时文件并 400。成功 → 原子 rename → **202** + task。

### 1.5 访问控制（D7：单机 / 局域网）

**CORS 不能代替鉴权。** 正式同源入口后仍须防 **CSRF**（11 §9）。

| 模式 | 网络绑定 | 最低控制 |
|---|---|---|
| **单机模式**（Phase A/B 默认） | 入口 **仅 127.0.0.1**（F3 起 ideally 只开前端端口） | 危险操作 `X-Ops-Token`；**勿**长期 token 进 localStorage；`confirmed_by` = 认证主体 |
| **局域网模式**（Phase D / F4） | 指定 LAN + TLS | viewer / operator / admin；HttpOnly Cookie；写 operator+；运维 admin |

**SSOT（评审 P1-1）**：**一切确认 / 生效 / 变更类写（本表清单）均不可匿名**；任务入队、画像/分析触发、暂存评估与 discard 等 **过程性 meta 写** 单机模式可不带 ops（仍受 127.0.0.1 绑定）。LAN 模式对等：清单内 → operator+/admin；过程性写入按角色策略（至少登录）。

单机模式必须 ops 的端点：

| 方法 | 路径 |
|---|---|
| POST | `/api/intake/stage/{file_id}/confirm` |
| POST | `/api/govern/master/pending/confirm`（原 `/api/master/confirm`） |
| POST | `/api/govern/confirm`（字典/映射确认，meta 写） |
| POST | `/api/metrics`（及 `/api/metrics/flow/activate` 等一切指标字典写） |
| POST | 规则回滚 / 规则变更生效类（`/assets/rule-dict/{id}/confirm`、`/govern/rule-learn/*`、`/govern/value-rules*`） |
| POST | `/api/models/{role}/restart`、`/api/models/{role}/activate` |
| POST | `/api/ingest`（legacy） |

过程性 meta 写（单机可 `Auth=none`，**不在**上表）：如 `POST /api/files`、`/files/batch`、`/intake/analyze|profile|plan`、`/intake/stage/{id}`（评估）、`/intake/stage/{id}/discard`。

- 无/错 token → **401**。  
- `confirmed_by` **禁止**请求体随意填写，必须来自认证主体。  
- §2 端点表 Auth 列：上表必须为 ops；过程性写入可为 none；冲突以本表为准。

### 1.6 冲突与 unverified（C4 / D5）

- `conflict: true` / `unverified: true`：不得当作已可执行终局；返回候选供人工。  
- 互验因 fallback 得到的「同模型两次」**禁止**标 `consistent`。
---

## 2. API 端点一览

约定：

- **Auth**：`none` = 单机过程性操作可匿名（仍受绑定限制，§1.5）；`ops` = 确认/生效/变更类，需要 `X-Ops-Token`
- **写库**：`—` 不写；`meta` 元数据；`biz` 仅经 writer（00 §3.1）
- **勿误读**：`Auth=none` 且写 meta ≠ 匿名可做确认/发布；确认类一律见 §1.5 清单

### 2.1 已实现（含 Phase 2.1 行为变更；路径均为 `/api/v1`，见 §0）

| 方法 | 路径 | 功能 | LLM | Auth | 写库 | 入参 / 返回要点 |
|---|---|---|---|---|---|---|
| POST | `/api/files` | 上传 → 入队解析（**202 + task_id**，03 §3.1） | 否 | none | meta | multipart `file` |
| GET | `/api/files` | 文件批次列表 | 否 | none | — | 分页 §3.4 |
| DELETE | `/api/files/{file_id}` | 删除批次（含任务） | 否 | none | meta | |
| POST | `/api/ingest` | **legacy** 历史 8 文件全量刷新 | 否 | ops | biz | 见下方闸门 |
| GET | `/api/query/tables` | 业务库表清单 | 否 | none | — | |
| POST | `/api/ask` | Text2SQL（指标模板优先） | 是 | none | — | LIMIT 见 02 |
| GET | `/api/govern/pending` | 待确认清单 | 否 | none | — | 分页 |
| POST | `/api/govern/confirm` | 映射/清洗决策回写字典 | 否 | **ops** | meta | 不直接写业务库 |
| POST | `/api/govern/map-suggest` | 表头映射建议（字典→embed→LLM） | 是 | none | — | |
| POST | `/api/govern/map-confirm` | 映射确认（含 queue 方式） | 否 | **ops** | meta | |
| GET | `/api/tasks` / `/api/tasks/{task_id}` | 任务列表 / 状态 | 否 | none | — | |

> 说明：自由 `POST /api/query`（legacy）在 `app/api/legacy.py` 挂载但默认闸门关闭；`ALLOW_LEGACY_INGEST` / `ALLOW_FREE_QUERY` 均默认 0（见下方收缩）。

**`POST /api/query` 收缩（00 §3.3，Phase A 起）**：

| 条件 | 行为 |
|---|---|
| `ALLOW_FREE_QUERY=0`（默认）或普通用户 | **403**；引导指标模板 / `POST /api/ask` |
| 单机 + ops token 且 `ALLOW_FREE_QUERY=1` | 允许，仍过 §1.1 AST |
| LAN viewer | 禁止；operator+ 可按产品开关开放 |

**`POST /api/ingest` 闸门（C5）**：

```
若 ALLOW_LEGACY_INGEST != "1"  → 403 {"detail":"legacy ingest disabled; use staging confirm"}
若缺少/错误 X-Ops-Token       → 401
否则执行历史全量管道，响应必须含:
  {"status":"ok","deprecated":true,"tables":{...}}
```

新文件接入**禁止**依赖此接口；文档与 UI 标注 Deprecated。

### 2.2 接入与任务（多数已实现，路径见 03 §5；未实现项标注"规划"）

> 下表原为规划清单；截至 2026-08-17，`files/tasks/intake/analyze|profile|quality|plan|report|conclusion|stage` 均已落地（`app/api/routers/{files,intake}.py`，前缀 `/api/v1`）。

| 方法 | 路径 | 功能 | LLM | Auth | 写库 |
|---|---|---|---|---|---|
| POST | `/api/files/batch` | 批量上传入队 | 否 | none | meta |
| GET | `/api/tasks` | 任务列表（status 筛选） | 否 | none | — |
| GET | `/api/tasks/{task_id}` | 任务进度 | 否 | none | — |
| POST | `/api/intake/analyze/{file_id}` | 画像+映射+质量+建议 | fast/big | none | meta |
| GET | `/api/intake/profile/{file_id}` | 文件画像结论（规则优先） | 否 | none | — |
| GET | `/api/intake/quality/{file_id}` | 质量预检结论 | 否 | none | — |
| POST | `/api/intake/plan/{file_id}` | 接入建议（含质量，走队列） | big | none | meta |
| POST | `/api/intake/plan/{file_id}/confirm` | 计划确认（staging 前置） | 否 | **ops** | meta |
| GET | `/api/intake/report/{file_id}` | 接入报告 | 否 | none | — |
| GET | `/api/intake/conclusion/{file_id}` | 结论摘要 | 否 | none | — |
| POST | `/api/intake/stage/{file_id}` | 暂存评估（dry-run，不写 biz） | 否 | none | meta |
| GET | `/api/intake/stage/{file_id}` | 暂存报告 | 否 | none | — |
| POST | `/api/intake/stage/{file_id}/confirm` | **确认门 → intake_release** | 否 | ops | **biz** |
| POST | `/api/intake/stage/{file_id}/discard` | 丢弃暂存 | 否 | none | meta |

### 2.3 治理 / 主数据 / 指标 / 资产（均已实现，路径见下与 04/07/08/12 §7.1）

> 主数据路由实际落在 `/govern/master/*`；治理流水/对齐等见 [12 §7.1](12-出入库流水解析.md)。

| 方法 | 路径 | 功能 | Auth | 写库 |
|---|---|---|---|---|
| GET | `/api/stats/overview` | 概览统计 | none | — |
| GET | `/api/assets/rule-dict` | 规则字典（含 conflicts/preview/confirm） | none | — |
| GET | `/api/assets/fewshot` | few-shot 池 | none | — |
| GET | `/api/assets/history` | 确认历史 | none | — |
| GET | `/api/govern/master/pending` | 主数据待审 | none | — |
| POST | `/api/govern/master/pending/confirm` | 主数据审批生效 | ops | **biz**（approved/merged 时） |
| GET | `/api/metrics` | 指标列表（含 fixtures/snapshots/evaluate） | none | — |
| POST | `/api/metrics` | 指标新增/修改 | **ops** | meta |
| POST | `/api/metrics/flow/activate` | 流水指标激活（12 §8 门禁） | **ops** | meta |
| POST | `/api/metrics/check` | 口径冲突检测 | none | — |
| POST | `/api/metrics/match` | 问题 → 候选指标 | none | — |

指标写仅人工 + ops（与 §1.5 一致）；**禁止** LLM/自动编排代写；UI 不暴露无鉴写入口。

### 2.4 运维与模型（已实现子集；模型导入仍为规划）

| 方法 | 路径 | 功能 | Auth | 写库 |
|---|---|---|---|---|
| GET | `/api/models/status` | 模型健康/存活 | none | — |
| POST | `/api/models/{role}/activate` | 切换 fast/big | ops | meta（配置） |
| POST | `/api/models/{role}/restart` | 重启容器内 vLLM | ops | — |
| GET | `/api/ops/tasks` | 任务队列概览 | none | — |
| GET | `/api/ops/alerts` | 告警列表 | none | — |
| GET | `/api/ops/llm-cost` | LLM 调用统计 | none | — |
| POST | `/api/ops/backup` · GET | `/api/ops/backups` | 备份/列表 | ops / none | meta |
| GET/POST | `/api/ops/restore-drill` | 恢复演练 | none/ops | meta |
| ~~GET~~ | ~~`/api/models/import`~~ | **离线包导入（规划未落地）** | ops | meta |

**模型导入约束（Phase A/B）**：

- **禁止**在线拉取 HuggingFace/ModelScope 等远程仓；仅接受预置目录或离线 tar + SHA256 校验。  
- 导入为异步任务：卡片状态 `importing` → 成功 `deployed`/`configured`；失败可查 `job` 错误码。  
- **无** `POST /api/models/download` 类端点。

**`restart` 实现约束（全套在容器内）**：

- API 与 vLLM **同容器**：restart 调用预置脚本（如 `scripts/vllm_restart_fast.sh`），脚本内仅 `pkill` + `vllm serve …`（对应 01 §3 / 06 §1.1），**不**经 Docker socket 套娃。
- **禁止**把请求体/路径参数拼进 shell；`{id}` 只能映射到白名单枚举（`fast` / `big` / `dual`）。
- restart **只杀 vLLM**，不杀 uvicorn/前端，避免治理会话中断。
- 缺 ops token → 401（§1.5）。
---

## 3. 通用行为规范

### 3.1 降级行为

- LLM 未就绪：`/api/ask`、`/api/govern/map-suggest` 等 → HTTP 200 + `ok:false` + `llm:"unavailable"`，不抛 500。
- SQL 校验失败 / 执行报错 → `ok:false` + `error`。
- 配置未过白名单 → `ok:false` + 字段级错误；不执行。
- 互验冲突 → `conflict:true`，不自动选侧（§1.6）。
- LLM 任务统一带回：`model_request_attempted` / `model_invoked` / `output_available` / `fallback_reason` / `model_state`（01 §5.5）。

### 3.2 JSON 安全

- `_json_safe()`：`NaN/Inf → null`，非基础类型 → str。

### 3.3 错误码与通用错误体

新客户端优先稳定字段（11 §6.3）：

```json
{"error":"…","message":"…","code":"STAGE_VERSION_CONFLICT","details":{},"request_id":"req_…"}
```

| 场景 | HTTP | 说明 |
|---|---|---|
| 创建资源 | **201** | |
| 成功 | 200 | 资源本身即可，不强制 `{ok:true}` |
| 异步任务已接受 | **202** | 含 `task_id` / `status_url` / `events_url` |
| 参数非法 / 上传不安全 / 非法 SQL | 400 | |
| 未认证 | **401** | |
| 无权限 / legacy 关闭 | **403** | |
| 不存在 | 404 | |
| 版本/状态/互验冲突 | **409** | 含 `code`；前端刷新后重试 |
| 结构/业务规则校验失败 | **422** | 字段级 |
| 配额耗尽 | **429** | |
| 模型或依赖暂不可用 | **503** | 功能可降级，勿一律伪装 200 |
| 兼容旧软失败 | 200+`ok:false` | 仅迁移期非关键路径 |

**禁止**将互验冲突、LLM 输出非法统一伪装成 HTTP 200（新路径）。

### 3.3.1 写操作头与乐观锁（11 §6.4）

副作用请求携带：`Idempotency-Key`、资源 `version`、`expected_status`、认证、`X-Request-ID`（或由网关注入）。不匹配 → 409。与 03 `release_id` 幂等互补。

### 3.4 分页

列表端点统一：

```json
{
  "limit": 20,
  "offset": 0,
  "total": 156,
  "next_offset": 20,
  "filters": {"status": "pending", "search": "光缆"},
  "items": []
}
```

- `limit` 默认 20、上限 100；先过滤再分页；稳定排序 `created_at DESC, id DESC`。

---

## 4. 连接管理（D1 / D2）

| 连接 | 存储 | 模式 | 谁可调用 |
|---|---|---|---|
| `meta_conn()` | **meta.sqlite**（WAL） | 读写 | API、worker（短事务） |
| `biz_conn()` | 物资库.duckdb | 只读 | API 查询/问答/dry-run |
| writer 写连接 | 物资库.duckdb | **唯一读写** | 仅 writer 进程 |

- **禁止** API 与多 worker 进程并发写同一 DuckDB（含 meta 若误用 DuckDB）。  
- 若 PoC 坚持 meta 暂用 DuckDB：API 必须单进程且 worker 同进程线程 + 单写队列——**不作为长期方案**（00 D1）。  
- `init_meta()` 建 SQLite 表（`app/repositories/db.py`）：`file_batch`、`intake_task`、`intake_report`、`staging_record`、`staging_blocked`、`release_manifest`、`write_audit`、`govern_confirm`、`rule_dict`、`map_pending`、`idempotency_record`、`llm_call`、`ask_log`、`flow_pending`、`flow_example`、`flow_config`、`flow_reconcile_gap`、`material_align`、`master_pending`、`metric_dict`、`metric_snapshot`、`sql_fewshot`、`value_rule`、`report_definition`、`report_run`、`correction_request` 等。  
- 文档 §1/§5.6 提及的 `prompt_template`（提示词集中管理）与 `alert` 表**尚未落地**，属规划。

---

## 5. 与前端 / 运维的契约摘要

| 调用方 | 必须遵守 |
|---|---|
| 07 / 11 界面 | 相对 `/api/v1`；不直连 DuckDB/vLLM；正式单入口；写操作鉴权+version |
| 06 运维 | Compose 目标见 11；PoC 单容器可多端口映射；宿主机不双开 API |
| 03 接入 | 发布只走 staging confirm；上传 202+任务 |
| OpenAPI | schema SSOT；`npm run api:check` 防漂移（C14） |
| models/restart | 预置脚本只重启 vLLM；PoC 同容器约束见 §2.4 |
