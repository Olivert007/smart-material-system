# 前后端分离优化方案（Docker 全容器化讨论稿）

> **副本位置**：`治理方案/来源/`（供 Docker/Agent 自包含阅读）  
> **正式决策**：[`../11-前后端分离与容器化.md`](../11-前后端分离与容器化.md) + [`../00-总览.md`](../00-总览.md) D9 / [`../05`](../05-安全与API规范.md) / [`../06`](../06-运维手册.md) / [`../07`](../07-界面层设计.md)  

> 来源：宿主机截图 OCR；原始 `ocr_out_ai/*.txt` 不随本目录交付  
> 整理日期：2026-08-08  
> 说明：本文档为截图内容的去重、纠错与结构化整理；OCR 难免有个别错字，已尽量修正（如 1ocal→local、v1lm/v11m→vllm、θ→0、丨→| 等）。

---

## 1. 设计结论

前端继续使用 Vue3，后端继续使用 FastAPI，源码、构建、接口和职责保持分离。运行方式按环境区分：

| 环境 | 前端运行方式 | API 访问方式 | Nginx |
|---|---|---|---|
| 开发 | Vite dev server 容器 | Vite 将 /api 代理到 API 容器 | 不使用 |
| MVP 部署 | FastAPI 可临时托管 Vue dist | 同源访问 | 可不使用 |
| 正式部署 | Nginx 容器提供 Vue dist | Nginx 将 /api 代理到 API 容器 | 使用 |

Nginx 不是宿主机服务，而是 Docker Compose 中的前端容器。正式部署只暴露一个入口端口，其余 API、模型和 worker 端口仅在 Docker 内部网络可见。

推荐最终形态：

```text
宿主机浏览器
   │
frontend/nginx:8080   ← 唯一映射到宿主机
   │
   ├─ Vue 静态文件
   ├─ /api/v1/*   → api:8010
   └─ /events/*   → api:8010 (SSE)

Docker 内部网络
   api:8010
   intake-worker
   writer
   vllm-fast:8000
   vllm-big:8001
   embedding:7999
```

## 2. 优化目标与边界

### 2.1 目标

1. 开发与部署全部容器化，不要求宿主机安装 Node、Python 或 Nginx。
2. 保留前后端独立开发、独立测试和独立构建。
3. 浏览器只访问一个同源入口，避免生产环境依赖 CORS。
4. API、vLLM、worker 和数据库不直接暴露给宿主机或局域网。
5. 大文件上传不占满 API 内存，长任务可恢复、可查看进度。
6. 前后端接口通过 OpenAPI 和生成类型保持一致。
7. 写操作支持鉴权、版本检查、幂等和冲突提示。
8. 完全断网后仍可构建、启动、升级和恢复。

### 2.2 非目标

- 不拆成大量微服务。
- 不让前端直接访问 DuckDB、SQLite 或 vLLM。
- 不让 Nginx 承担业务逻辑。
- 不在第一阶段实现不必要的 WebSocket 双向协议。
- 不在运行时从 CDN、npm、pip 或远程模型仓库下载依赖。

## 3. 代码与职责边界

### 3.1 推荐目录

```text
project/
├── app/
│   ├── api/            # FastAPI 后端：路由和 API schema
│   ├── services/       # 业务编排
│   ├── repositories/   # SQLite/DuckDB 数据访问
│   ├── models/         # Pydantic 数据模型
│   ├── workers/        # 异步任务实现
│   └── main.py
├── frontend/           # Vue3 前端
│   ├── src/
│   │   ├── api/        # 自动生成客户端和手写适配层
│   │   ├── components/
│   │   ├── composables/
│   │   ├── pages/
│   │   ├── router/
│   │   ├── public/
│   │   └── stores/
│   ├── package.json
│   ├── vite.config.ts
│   ├── nginx.conf
│   └── Dockerfile
├── deploy/
│   ├── compose.prod.yml
│   ├── compose.dev.yml
│   └── env.example
├── data/               # 宿主机持久化业务数据，不打入镜像
├── models/             # 宿主机模型目录，只读挂载
├── wheelhouse/         # Python 离线包
├── npm-cache/          # 可选 npm 离线缓存
└── Dockerfile.api
```

### 3.2 前端职责

- 页面布局、输入校验和交互状态；
- 调用后端 API；
- 展示任务、模型、治理和发布状态；
- 展示后端返回的权限和冲突信息；
- 不计算业务指标；不持有数据库文件和模型端点；
- 不自行决定表头映射、数据质量或发布资格。

### 3.3 后端职责

- 参数、权限、版本和幂等校验；
- 任务创建、业务编排和状态迁移；
- 数据查询、指标计算、staging 和发布；
- 模型路由与输出校验；
- 审计、告警、备份和恢复接口；
- 对前端隐藏 DuckDB、SQLite、vLLM 和文件系统细节。

## 4. 开发环境方案

### 4.1 开发拓扑

```text
浏览器 http://127.0.0.1:5173
   │
frontend-dev (vite :5173)
   │
   └─ /api → http://api:8010

api（FastAPI :8010）
   └─ worker / writer / model services
```

前端和 API 仍是两个容器。浏览器只访问 Vite，Vite 通过 Docker 内部服务名代理 API，因此开发时也不需要浏览器跨域访问 :8010。

### 4.2 Vite 代理

```ts
// vite.config.ts
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: "http://api:8010",
        changeOrigin: true,
      },
      "/events": {
        target: "http://api:8010",
        changeOrigin: true,
      },
    },
  },
});
```

前端代码只使用相对地址：

```ts
const API_BASE = "/api/v1";
```

不得在业务代码中写死 `localhost:8010`、容器 IP 或 vLLM 端口。

### 4.3 开发 Compose 示例

```yaml
services:
  frontend:
    build:
      target: development
      context: ./frontend
    command: npm run dev -- --host 0.0.0.0
    ports:
      - "127.0.0.1:5173:5173"
    volumes:
      - ./frontend:/app
      - frontend_node_modules:/app/node_modules
    depends_on:
      api:
        condition: service_healthy

  api:
    build:
      dockerfile: Dockerfile.api
      context: .
      target: development
    expose:
      - "8010"
    volumes:
      - .:/workspace/app
      - ./data:/workspace/app/data
      - ./models:/models:ro
    healthcheck:
      test: ["CMD", "curl", "http://127.0.0.1:8010/health/live"]
      interval: 10s
      timeout: 3s
      retries: 6

volumes:
  frontend_node_modules:
```

模型服务可以通过 Compose profile 启用，普通前端开发不强制加载所有大模型：

```bash
docker compose -f deploy/compose.dev.yml up frontend api
docker compose -f deploy/compose.dev.yml --profile models up
```

## 5. 正式部署方案

### 5.1 正式拓扑

正式部署采用 Nginx 前端容器，但所有组件仍在 Docker 内：

```text
浏览器 :8080
   │
frontend/nginx
   ├─ Vue dist
   └─ /api、/events → api:8010

api、worker、writer、vLLM 仅 expose，不 publish
```

宿主机端口映射：

```yaml
ports:
  - "127.0.0.1:8080:8080"
```

需要局域网访问时，才显式改成指定 LAN 地址并启用认证和 TLS。不得无意使用 `0.0.0.0:8080:8080` 将系统暴露到所有网卡。

### 5.2 前端多阶段镜像

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --offline
COPY . .
RUN npm run build

FROM nginx:alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
```

离线构建必须提前准备 npm cache 或内部固定基础镜像。部署现场不执行远程 `npm install`。

### 5.3 Nginx 配置基线

```nginx
server {
    listen 8080;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;
    client_max_body_size 2g;

    location /assets/ {
        try_files $uri =404;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location / {
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache";
    }

    location /api/ {
        proxy_pass http://api:8010;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
        proxy_connect_timeout 5s;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location /events/ {
        proxy_pass http://api:8010;
        proxy_buffering off;
        proxy_http_version 1.1;
        proxy_cache off;
        proxy_set_header Connection "";
        proxy_read_timeout 1h;
    }
}
```

- `/events/` 必须关闭 proxy_buffering 与 proxy_cache，读超时拉长到 1h。
- 上传是否关闭 `proxy_request_buffering` 应通过大文件测试决定：关闭后可直接流向 API；开启时 Nginx 会先使用临时磁盘，需要明确临时目录容量。

### 5.4 正式 Compose 示例

```yaml
services:
  frontend:
    image: local/intelligent-data-frontend:1.0.0
    ports:
      - "127.0.0.1:8080:8080"
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped

  api:
    image: local/intelligent-data-api:1.0.0
    expose:
      - "8010"
    environment:
      META_DB_PATH: /data/meta.sqlite3
      BIZ_DB_PATH: /data/material.duckdb
      LLM_FAST_ENDPOINT: http://vllm-fast:8000/v1
      LLM_BIG_ENDPOINT: http://vllm-big:8001/v1
    volumes:
      - ./data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "http://127.0.0.1:8010/health/ready"]
      timeout: 5s
      interval: 15s
      retries: 8

  worker:
    image: local/intelligent-data-api:1.0.0
    command: python -m app.workers.intake
    volumes:
      - ./data:/data
    restart: unless-stopped

  writer:
    image: local/intelligent-data-api:1.0.0
    command: python -m app.writer
    volumes:
      - ./data:/data
    restart: unless-stopped

  vllm-fast:
    image: local/vllm-aarch64:validated
    expose:
      - "8000"
    volumes:
      - ./models:/models:ro
    restart: unless-stopped

  vllm-big:
    image: local/vllm-aarch64:validated
    expose:
      - "8001"
    volumes:
      - ./models:/models:ro
    restart: unless-stopped
```

示例只描述网络和服务边界。GPU 参数、writer 通信方式、SQLite/DuckDB 所有权和 vLLM 命令以最终基础架构方案为准。

## 6. MVP 简化部署

如果第一阶段希望减少一个容器，可以由 FastAPI 托管已经构建好的 Vue dist：

```python
from fastapi.staticfiles import StaticFiles

app.mount(
    StaticFiles(directory="frontend/dist", html=True),
    name="frontend",
)
```

MVP 拓扑：

```text
浏览器 :8010
   │
FastAPI
   ├─ /api/v1/*
   └─ Vue dist
```

适用条件：

- 单用户本机验证；
- 页面和 API 可一起重启；
- 目标是尽快验证业务闭环；
- 暂不需要独立静态缓存策略；
- 迁移到 Nginx 时前端仍使用相对 `/api/v1`，因此不需要修改业务代码，只调整镜像和 Compose。

MVP 不建议使用 `python -m http.server` 或长期运行 `vite preview` 作为正式静态服务。

## 7. API 契约优化

### 7.1 API 版本

所有业务接口统一放在 `/api/v1/*`，例如：

```text
POST /api/v1/files
GET  /api/v1/tasks/{task_id}
POST /api/v1/ask
POST /api/v1/intake/stages/{stage_id}/confirm
GET  /api/v1/metrics
POST /api/v1/models/{model_id}/activate
```

健康检查不放在业务版本下：

```text
GET /health/live
GET /health/ready
```

### 7.2 OpenAPI 生成前端类型

FastAPI 是接口 schema 的唯一来源：

```text
FastAPI OpenAPI
   ↓ openapi-typescript / orval
frontend/src/api/generated
```

建议提供构建命令：

```bash
npm run api:generate
npm run api:check
```

CI 或离线验收中，如果生成结果与仓库内容不一致则失败，防止前后端契约漂移。自动生成层不直接承载页面逻辑，前端在 `src/api/` 增加薄适配层，处理统一错误、认证和数据格式。

### 7.3 通用响应

成功响应不强制再包一层 `{ ok: true }`，资源本身就是响应。错误统一使用：

```json
{
  "error": "...",
  "message": "暂存版本已变化，请刷新后重试",
  "code": "STAGE_VERSION_CONFLICT",
  "details": {},
  "request_id": "req_01..."
}
```

前端按稳定的 `code` 处理，不解析中文 `message` 判断逻辑。

### 7.4 HTTP 状态码

| 场景 | 状态码 |
|---|---|
| 创建资源 | 201 |
| 查询或操作成功 | 200 |
| 创建异步任务 | 202 |
| 未认证 | 401 |
| 参数、文件或 SQL 非法 | 400 |
| 无权限 | 403 |
| 资源不存在 | 404 |
| 版本、状态或互验冲突 | 409 |
| 结构/业务规则校验失败 | 422 |
| 请求过多或配额耗尽 | 429 |
| 模型或依赖暂时不可用 | 503 |

LLM 输出非法、互验冲突等业务失败不再统一伪装成 HTTP 200。

## 8. 同步、异步与流式交互

### 8.1 交互选择

| 业务 | 推荐方式 |
|---|---|
| 列表、详情、指标查询 | 普通 HTTP |
| 文件解析、接入分析、规则重放 | 202 + task_id |
| 任务进度、告警变化 | SSE |
| LLM 问答 | 普通 HTTP 起步；需要逐步展示时使用 SSE |
| 模型加载和切换 | 异步任务 + SSE |
| 双向协同编辑 | 当前不需要 WebSocket |

### 8.2 异步任务响应

```json
{
  "task_id": "task_01...",
  "resource_id": "file_01...",
  "status": "pending",
  "events_url": "/events/tasks/task_01...",
  "status_url": "/api/v1/tasks/task_01..."
}
```

前端先订阅 SSE；断线或浏览器恢复后调用状态接口重新同步。SSE 是体验优化，数据库中的任务状态仍是 SSOT。

### 8.3 SSE 事件

```text
event: task.progress
data: {"task_id": "..."}

event: task.completed
data: {"task_id": "...", "resource_id": "..."}

event: task.failed
data: {"task_id": "...", "error_code": "MODEL_UNAVAILABLE"}
```

事件中不发送完整敏感数据或模型 prompt。

## 9. 大文件上传

### 9.1 上传流程

```text
浏览器 multipart 上传
   ↓
Nginx/Vite proxy
   ↓
FastAPI 分块写临时文件 + 增量 SHA256
   ↓
大小、扩展名、magic bytes、安全校验失败 → 删除临时文件
   ↓
校验成功 → 原子 rename → 创建任务 → 返回 202
```

后端不得使用一次性 `await file.read()` 读取整个大文件。应按固定块写入磁盘，并设置：

- 单文件大小上限；
- 单批文件数量和总大小上限；
- 上传目录配额；
- 临时文件过期清理；
- 同一文件哈希的重复策略；
- 客户端断开后的清理；
- 文件名与存储路径分离，内部使用随机 ID。

### 9.2 上传进度

浏览器上传进度由 axios/XHR 的上传事件展示；文件落盘后的解析进度由任务 SSE 展示。两者是不同阶段，UI 不应混成一个不透明进度条。

### 9.3 断点续传

一期不实现。只有在文件经常超过约 1GB、网络不稳定或局域网远程上传成为常态时，再引入分片上传协议。

## 10. 鉴权与权限

### 10.1 单机模式

- 入口只绑定 127.0.0.1；
- 读操作可以按产品需要简化；
- 不将长期 ops token 保存到 localStorage；
- 发布、主数据审批、模型重启和规则回滚仍需操作凭证。

### 10.2 局域网模式

角色建议：

| 角色 | 权限 |
|---|---|
| viewer | 查看数据、指标和已发布结果 |
| operator | 上传、治理确认、指标维护、接入发布 |
| admin | 模型切换、服务重启、规则回滚、恢复操作 |

使用服务端 session 或短期令牌，浏览器通过 HttpOnly、SameSite=Strict Cookie 持有会话。前端按钮权限只改善体验，后端必须再次校验。

### 10.3 CSRF 与同源

正式环境采用同源入口后，Cookie 写接口应增加 CSRF token 或严格的 Origin/Referer 校验。Nginx 同源代理解决 CORS，不自动解决 CSRF。

## 11. 写操作一致性

所有有副作用的 API 需要：

- `Idempotency-Key`；
- 当前资源 `version`；
- 预期状态 `expected_status`；
- 认证操作者；
- `request_id` 和审计记录。

确认示例：

```text
POST /api/v1/intake/stages/stage_01/confirm
Idempotency-Key: release-stage_01-v3
```

```json
{
  "expected_status": "ready",
  "version": 3,
  "note": "确认发布"
}
```

只有版本和状态同时匹配时才能进入发布。旧页面提交返回 `409`，前端提示刷新并重新查看影响评估。模型切换、规则回滚和主数据合并也采用相同机制。

## 12. 前端状态管理

### 12.1 状态分类

| 状态 | 推荐位置 |
|---|---|
| API 列表、详情、任务、模型状态 | Vue Query |
| 当前用户、权限、界面偏好 | Pinia |
| 分页、搜索、筛选、当前 Tab | URL query |
| 服务端任务真实状态 | 后端数据库，不保存在前端作为 SSOT |
| 表单编辑草稿 | 组件或表单库 |

不得将相同 API 数据同时复制到 VueQuery、Pinia 和多个组件状态，避免刷新时出现不同版本。

### 12.2 页面恢复

- 通过 `task_id` 从后端恢复任务进度；
- 刷新页面后通过 URL 恢复分页和筛选；
- SSE 断线后先重新读取任务状态，再继续订阅；
- 页面不依赖内存中的"上一步结果"才能进入下一步；
- 写表单显示当前资源版本和最后更新时间。

### 12.3 构建与加载

- 路由级懒加载 8 个页面；
- Element Plus 和 ECharts 按需引入；
- 静态资源使用内容哈希；
- index.html 不长期缓存；
- 图标使用项目已打包的图标库；
- 禁止使用公网字体、图标、CDN 和远程脚本。

## 13. 健康检查与可观测性

### 13.1 健康端点

```text
/health/live
/health/ready
```

- `/health/live`：进程存活，不检查所有外部依赖。
- `/health/ready`：检查 meta、业务库只读连接和必要内部服务。
- big 模型不可用不一定让整个 API ready=false；应按功能降级。writer 或元数据存储不可用则 API 不应接受写任务。

### 13.2 链路标识

所有响应包含或通过响应头返回：

| ID | 用途 |
|---|---|
| trace_id | 全链路 |
| X-Request-ID | 请求 |
| task_id | 异步任务 |
| release_id | 发布任务 |

这些 ID 应贯穿：

```text
Nginx access log / FastAPI log / 任务表 / LLM 调用审计 / 发布清单 / 前端错误详情
```

### 13.3 前端错误展示

用户默认看到简明错误和可执行动作；可展开技术详情查看 `error_code`、`request_id` 和失败步骤。不得把完整堆栈、数据库路径或敏感 prompt 返回浏览器。

## 14. 离线构建与交付

离线交付包至少包含：

1. Docker Compose 与环境变量模板；
2. frontend、api、vllm 等镜像 tar 和 SHA256；
3. Vue 已构建产物或 npm 离线 cache；
4. Python wheelhouse 和锁定依赖；
5. 模型制品与校验清单；
6. 数据库初始化和迁移脚本；
7. 启动、停止、备份、恢复和自检脚本；
8. OpenAPI 文件和生成的前端客户端；
9. 第三方许可证清单。

镜像应在有网络的构建环境完成并导出。DGX Spark 部署现场使用：

```bash
docker load -i images/frontend.tar
docker load -i images/api.tar
docker load -i images/vllm.tar
docker compose -f deploy/compose.prod.yml up -d
```

运行容器不执行 `apt install`、`pip install`、`npm install` 或模型下载。

## 15. 测试与验收

### 15.1 前端

- 8 个页面路由和权限；
- 上传、任务进度和 SSE 重连；
- 列表分页、筛选与 URL 恢复；
- 409 版本冲突和 503 模型不可用；
- 页面刷新后任务状态恢复；
- 断网情况下无远程资源请求；
- 桌面和目标浏览器视口无布局重叠。

### 15.2 API

- OpenAPI 与生成客户端一致；
- 正确使用 200/201/202/4xx/5xx；
- 幂等键重复请求返回同一业务结果；
- 上传流式落盘，超限和中断可清理；
- 旧版本写入返回 409；
- SSE 断开不影响任务执行；
- 前端无法直接访问 vLLM 或数据库；
- Nginx 超时不导致后台任务重复执行。

### 15.3 Docker

- 宿主机只暴露预期入口端口；
- API、writer、worker 和模型只在内部网络可达；
- 容器重启后任务和页面可恢复；
- 数据和模型均来自持久化挂载；
- 前端/API/worker/model 日志可按 request_id 串联；
- 无网络时可完整启动和运行。

## 16. 分阶段实施

### Phase F1：开发环境统一

- 建立 compose.dev.yml；
- Vite 容器代理 /api；
- FastAPI 输出 OpenAPI，生成 TypeScript 类型；
- 前端统一使用相对 /api/v1；
- 暂不加入 Nginx。

### Phase F2：MVP 交付

- 构建 Vue dist；
- 完成文件上传、任务状态、错误码、版本和幂等机制；
- 可先由 FastAPI 托管静态文件；
- 只绑定回环地址。

### Phase F3：正式容器部署

- 使用 Nginx 前端容器；
- API、worker、writer、vLLM 独立容器；
- 只暴露 127.0.0.1:8080；
- 启用 SSE、健康检查、统一 request_id 和静态缓存；
- 完成离线镜像导入和恢复演练。

### Phase F4：局域网访问（按需）

- Nginx 增加 TLS；
- 启用用户、角色、session 和 CSRF 防护；
- 限制访问源和上传配额；
- 不改变前后端业务代码和内部 API 地址。
