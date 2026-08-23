# Smart Material System

English project root for **智能物资数据管理系统** (Phase A implementation).

> Runtime: **Docker container** — use system Python (`/usr/bin/python3`).  
> Do **not** create a project `.venv`; install packages with `pip3` directly.

## Layout

```text
smart-material-system/
├── app/                 # FastAPI backend (Phase A trusted pipeline)
│   ├── api/             # /api/v1 routes
│   ├── services/        # orchestration (evidence, staging, query)
│   ├── repositories/    # SQLite meta + DuckDB access
│   ├── models/          # Pydantic schemas
│   ├── workers/         # intake worker + writer path
│   └── main.py
├── frontend/            # Vue3 + Element Plus (F1)
├── deploy/              # compose.dev / compose.prod / env.example
├── data/                # persistent runtime data (not in image)
│   ├── uploads/
│   ├── raw_evidence/
│   ├── staging/
│   └── backups/
├── scripts/             # backup / ops helpers
├── tests/
├── docs/                # SSOT 方案文档（与 GB10 治理方案仓库同步）
├── requirements.txt
└── README.md
```

## SSOT

Architecture decisions live in [`docs/`](docs/). Canonical governance repo: [Olivert007/GB10](https://github.com/Olivert007/GB10) (keep in sync when方案变更). Code must follow D1–D9 / C1–C14.

## Quick start (Phase A)

```bash
git clone git@github.com:Olivert007/smart-material-system.git
cd smart-material-system
pip3 install -r requirements.txt
export OPS_TOKEN=dev-ops-token-change-me
export PYTHONPATH=$(pwd)
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Smoke:

```bash
PYTHONPATH=/workspace/2026-07/smart-material-system python3 tests/smoke_phase_a.py
```

## Frontend (F1 开发 / F2 MVP / F3 Nginx)

```bash
./scripts/start_api.sh                 # API(+SPA) :8010 回环（需先 npm run build）
cd frontend && npm run build           # 或 ./scripts/build_frontend.sh
# 开发热更新（可选）：
cd frontend && npm run dev             # UI  :5173（代理 /api /events /health）
```

F2 单入口：浏览器打开 **http://127.0.0.1:8010** （FastAPI 托管 `frontend/dist` + `/api/v1`）。  
侧栏按旅程分组：看数（总览/问数/数据中心）· 接入（接入与任务）· 治理（治理中心）· 系统（ops）。  
设置页填写 Ops Token（默认 `dev-ops-token-change-me`）与角色（`X-Ops-Role`）。

### 5 分钟交互演示

1. 打开 http://127.0.0.1:8010 → **总览** 查看表行数与业务指标卡片（点击跳转指标字典）。
2. **接入与任务** 上传样例或运行 `PYTHONPATH=. python3 scripts/run_ledger_sample.py`。
3. **治理中心** 处理映射/流水待确认；**报表快照** 查看流水分析图表。
4. **台账浏览** 分页查看 `fact_inventory` 等 6 表；**自然语言问答** 使用示例问题下拉。
5. **运维面板** 查看模型存活与任务队列；**审计时间线** 查看操作记录。

F3 单入口：`docker compose -f deploy/compose.prod.yml up --build` → http://127.0.0.1:8080（Nginx → api；SSE `/events/tasks/{id}`）。  
写操作带 `version` / `expected_status` / `Idempotency-Key`；冲突返回 **409**。  
OpenAPI 类型：`npm run api:generate` / `npm run api:check`。  
Compose：`deploy/compose.dev.yml`（开发）、`deploy/compose.prod.yml`（F3 PoC）、`deploy/compose-offline.yml`（离线 + vLLM 全栈）。

### Offline Docker deploy (doc 21)

Prepare local build assets once (online machine):

```bash
python3 scripts/prepare_offline_bundle.py          # offline/wheelhouse + offline/npm-cache
PYTHONPATH=. python3 scripts/check_offline_bundle.py --manifest deploy/offline-manifest.example.json
```

Deploy on an air-gapped host (models at `${MODELS_DIR:-/models}`):

```bash
cp deploy/offline.env.example deploy/offline.env
# On a connected machine: pin vLLM digest (requires docker)
./scripts/resolve_vllm_image.sh v0.8.5 --write deploy/offline.env
# Edit OPS_TOKEN, MODELS_DIR
docker compose -f deploy/compose-offline.yml --env-file deploy/offline.env up -d --build
PYTHONPATH=. python3 scripts/check_offline_bundle.py --manifest deploy/offline-manifest.example.json --env-file deploy/offline.env
PYTHONPATH=. python3 scripts/check_docker_runtime.py | python3 -m json.tool
```

Boot persistence (systemd):

```bash
sudo cp -r . /opt/smart-material-system
sudo cp deploy/systemd/smart-material-system.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now smart-material-system.service
```

Image digests: vLLM 通过 `VLLM_IMAGE=repo:tag@sha256:...` 写入 `deploy/offline.env`（`compose-offline.yml` 强制要求）；基础镜像 digest 记录在 `deploy/offline-manifest.example.json`。

## Phase A status

Trusted pipeline closed for rule-based tabular release:

- star schema (`dim_material` / `fact_*`) with `source_release_id`
- upload → evidence (+ `.tabular.parquet`) → **Step1 rule workbook profile** → **Step2 map_pending enqueue** → staging dry-run → ops confirm → idempotent writer
- AST readonly query · backup with writer pause
- tests: `tests/smoke_phase_a.py`, `tests/test_phase_a_accept.py`, `tests/test_profile_step1.py`, `tests/test_map_gov.py`
- profile smoke: `PYTHONPATH=. python3 scripts/smoke_profile_step1.py` → `PROFILE_STEP1_OK`
- map queue smoke: `PYTHONPATH=. python3 scripts/smoke_map_gov.py` → `MAP_GOV_OK`
- quality smoke: `PYTHONPATH=. python3 scripts/smoke_quality_precheck.py` → `QUALITY_PRECHECK_OK`
- plan smoke: `PYTHONPATH=. python3 scripts/smoke_intake_plan.py` → `INTAKE_PLAN_OK`
- metric ask smoke: `PYTHONPATH=. python3 scripts/smoke_metric_template.py` → `METRIC_TEMPLATE_OK`
- Ask：指标 aliases 命中 → `definition_sql`（`source=metric_template`，不调 LLM）；`FLOW_*` draft 返回质量门禁提示
- 种子：`INV_QTY_TOTAL` / `INV_VALUE_TOTAL` / `DEMAND_QTY_TOTAL` / `ASSET_COUNT_TOTAL`（active）；`sql_fewshot` 表 + 种子
- API：`POST /api/v1/metrics/match`
- real sample: `PYTHONPATH=. python3 scripts/run_real_sample.py`
- OpenAPI: `PYTHONPATH=. python3 scripts/export_openapi.py` → `deploy/openapi.json`
- optional seed legacy DB: `PYTHONPATH=. python3 scripts/seed_legacy_bizdb.py`

Not in Phase A: LLM mapping/Text2SQL, cascade/cross-check, full 8-file hardcoded clean_data port.
LLM sheet-profile for `needs_llm` sheets is Stage B+ (not in Step1 rule path).

## Stage 1 (local models)

**设计目标**（`app/config.py`）：fast `:8000`、big `:8001`、embed `:8002`。

**当前验收**以运行态脚本输出为准（区分「设计存在」与「环境可用」）：

```bash
./scripts/start_dev_stack.sh          # 启动顺序指引（不自动拉起进程）
PYTHONPATH=. python3 scripts/check_runtime.py | python3 -m json.tool
```

`runtime_level` 口径：`none`（API 未 ready）→ `dev_ok`（API + Vite 可访问，模型均未起）→ `stage1_degraded`（模型不完整或名称不匹配）→ `full`（三模型在线且名称匹配）。  
embed 不可用时系统可词法 fallback（`EMBED_FALLBACK_LEXICAL=1`）；big 不可用时复杂生成能力受限。

本机 `/models`：
- `Qwen3.6-27B` → big `:8001`（BF16 制品；`LLM_ENABLE_THINKING=0`）
- `Qwen3-Embedding-0.6B` → embed `:8002`
- `Qwen2.5-7B-Instruct` → 过渡基线（已切走时可停）

```bash
./scripts/models.sh status                 # 模型生命周期唯一入口（doc 20）
./scripts/models.sh start big|fast|embed   # 或 start all（big 失败需 ALLOW_DEGRADED_START=1）
./scripts/start_api.sh                     # :8010
./scripts/build_frontend.sh                # F2 dist
PYTHONPATH=. python3 scripts/smoke_f3_sse.py  # F3 SSE → F3_SSE_OK
./scripts/republish_sample.sh        # 真实样例 → fact_inventory
bash ./scripts/harden_real_files.sh  # 多域真实文件压测 → data/eval/results/
PYTHONPATH=. python3 scripts/harden_flow_real.py  # 305B/ZW → fact_stock_flow（FLOW_HARDEN_OK）
PYTHONPATH=. python3 scripts/smoke_stage1.py
PYTHONPATH=. python3 scripts/run_eval_stage1.py   # 基线结果 → data/eval/results/
```

API：
- `GET  /api/v1/models/status`（big/embed 应 ok）
- `POST /api/v1/govern/map-suggest`（candidates.source=`embed`）
- `POST /api/v1/govern/map-confirm`
- `POST /api/v1/ask`
- Module 12 流水：`GET/POST /api/v1/govern/flow/*`、`GET /api/v1/assets/flow-examples`
  - 单测：`PYTHONPATH=. python3 tests/test_flow_parse.py`
  - 冒烟：`PYTHONPATH=. python3 scripts/smoke_flow.py`（`target_domain=stock_flow`）

embed 不可用时自动词法 fallback（`EMBED_FALLBACK_LEXICAL=1`）。**不上** fast/级联/互验。
