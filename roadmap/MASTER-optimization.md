# 系统整体优化 · 主路线图

> 版本：v1.0（2026-08-10）· **状态：已落地 Wave 0–4**
> 工程：`smart-material-system` · SSOT 界面文档：`../治理方案/07-界面层设计.md`

---

## 1. 目标信息架构（已实施）

| 旅程 | 页面 |
|---|---|
| 看数 | `/` 总览 → `/ask` → `/browse` → `/reports` |
| 接入 | `/intake` 接入与任务 → `/stage/:id` |
| 治理 | `/govern` → `/learning` → `/metrics` |
| 平台 | `/models` → `/ops` → `/lineage` → `/audit` → `/settings` |

- `/files` 已重定向至 `/intake`
- 流水分析从治理页迁至 `/reports`（`FlowAnalytics` 组件）
- 血缘高级操作迁至 `/lineage`

---

## 2. Wave 完成状态

| Wave | 内容 | 状态 |
|---|---|---|
| W0 | 首页指标绑定、流水分析迁报表、overview 并发探测 | ✅ |
| W1 | 合并接入页、任务列表 API、Lineage 页、侧栏分组 | ✅ |
| W2 | 审计时间线、告警/LLM 成本、角色 Header、401 引导、SSE 降级提示 | ✅ |
| W3 | Ask 示例库、治理向导、Stage 进度条、`run_ledger_sample.py` | ✅ |
| W4 | 模型 activate/restart API、PageSkeleton/RetryBanner、响应式 @media | ✅ |

---

## 3. 新增 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/tasks` | 任务列表（status 筛选） |
| GET | `/api/v1/ops/tasks` | 任务队列计数 |
| GET | `/api/v1/ops/alerts` | 活跃告警 |
| GET | `/api/v1/ops/llm-cost` | LLM 调用统计 |
| GET | `/api/v1/audit/timeline` | 审计时间线 |
| POST | `/api/v1/models/{role}/activate` | 记录模型切换 |
| POST | `/api/v1/models/{role}/restart` | 记录重启请求 |

---

## 4. 本地启动（交互 Review）

```bash
# 构建前端
cd frontend && npm run build

# 启动 API（托管 dist，端口 8010）
cd .. && bash scripts/start_api.sh
```

浏览器打开：**http://127.0.0.1:8010**

开发模式（Vite 热更新）：`cd frontend && npm run dev` → http://127.0.0.1:5173

---

## 5. 归档文档

以下评审文档已吸收进本文，原文见 `roadmap/archive/`：

- `home-govern-review.md`
- `metrics-home-binding.md`
- `assets-ops-user-view.md`
- `user-perspective-analysis.md`

仍活跃的专题：`ledger-export-plan.md`、`field-zh-doc.md`、`examples-plan.md`（样例数据待扩充）

---

## 6. 后续（未纳入本次）

- 采购订单接入（`purchase-order-plan.md`）
- LLM sheet-profile（Stage B+）
- 显存时序 / 验收清单（Ops 二期）
- 四角色后端路由级 403 全覆盖（当前为 Header 约定 + 前端灰显）
