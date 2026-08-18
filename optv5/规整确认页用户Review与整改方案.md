# 规整确认页用户 Review 与整改方案

> **来源**：`数据规整/` 截图 OCR 识别（rapidocr-onnxruntime，环境 `/workspace/2026-07/.venv`）；原始识别文本见 `ocr_out_数据规整/`
> **整理日期**：2026-08-18
> **说明**：本文档按截图文件名时间戳顺序拼接，并对照画面纠错、去重后整理。截图时间与章节逻辑一致（先 Agent 手册 → Phase A/B → 问题与方案 → 验收与决策）。

**日期**：2026-08-18  
**状态**：**已闭环**（2026-08-18）  
**目标读者**：低能力 Agent — 只读本文，严格按 §0 顺序执行；每步通过门禁后再进下一步。  
**路由**：`/stage/:fileId` → `frontend/src/pages/StageView.vue`  
**范围**：本页 UI、本页文案 SSOT、本页依赖的后端 `quality/detail` 汉化；**不含**全站 disclaimer、报表页、侧栏 IA 改造。  
**仓库根目录**：下文称 **`$ROOT`**（同时含 `frontend/` 与 `app/` 的那一层）。

---

## 0. Agent 复现手册（必读 · 按序执行）

**你要产出什么**：其他开发者打开 `/stage/{fileId}` 时，看到**文件名标题 + 4 数字卡 + 中文摘要 + 预览**，**没有** `file_id` / 指纹 / 接入计划 / 英文 `detail`。

**你是什么角色**：执行型 Agent。本文档 = 唯一规格来源。

**完成标志**：§0.6 全部命令 exit 0 / 无匹配，且 §0.7 手工项全绿。

### 0.1 环境前提（缺一则停）

| 项 | 要求 |
|---|---|
| Node | 能跑 `cd frontend && npm install && npm run build` |
| 后端 | 复现 UI **不必须**起后端；§0.7 手工验收需要 API 在跑（如 `http://127.0.0.1:8010`） |
| 测试 fileId | 至少有一个已上传文件的 `file_id`（如 Demo 台账 `076545f8e95b`） |
| 勿改 | 路由表 `frontend/src/router/index.ts`、侧栏 `App.vue` 菜单项（除非本文明确要求宽度） |

### 0.2 起点自检（先跑，判断要不要做）

在 **`$ROOT`** 执行：

```bash
# 若以下「应不存在」项全部无匹配 → 前端 Phase A 可能已做完，跳到 0.2b
rg '高级信息|接入计划|数据指纹|去治理中心' frontend/src/pages/StageView.vue || true
rg 'el-collapse.*adv|lastRun' frontend/src/pages/StageView.vue || true

# 若以下「应存在」项有匹配 → 核心结构已在
rg 'displayFilename|stageLabels|issueCountsSummary|v-if="!isReleased"' frontend/src/pages/StageView.vue

# 后端 detail 是否仍英文（有匹配则需 Phase B）
rg 'required group blank|key=.*/\|' app/services/intake/quality_precheck.py || true
```

| 结果 | 下一步 |
|---|---|
| 仍有「高级信息 / 接入计划」 | 执行 **§0.4 Phase A** |
| 无高级区，但 quality 仍英文 / 问题数 500+ | 执行 **§0.5 Phase B** |
| 全部自检通过 | 只跑 **§0.6** 确认后结束 |

### 0.3 实施顺序（禁止并行跳步）

```text
Step 1  新建 frontend/src/utils/stageLabels.ts（§3.5）
Step 2  改 frontend/src/pages/StageView.vue（§0.4 清单）
Step 3  cd frontend && npm run build  ← 必须通过，否则不要改后端
Step 4  改 app/services/intake/quality_precheck.py（§0.5）
Step 5  确认 app/api/routers/stats.py 的 blocked 接口支持 target_domain 查询参数
Step 6  再 build + §0.6 grep + §0.7 手工
```

### 0.4 Phase A — 前端 ST-1~ST-12

**只改这些文件**（不要顺手改其它页）：

| 顺序 | 文件 | 做什么 |
|---|---|---|
| A1 | `frontend/src/utils/stageLabels.ts` | **新建**；导出 §3.5 全部函数 |
| A2 | `frontend/src/pages/StageView.vue` | **按下面模板结构重写 / 对齐** |
| A3 | `frontend/src/utils/gateLabels.ts` | 若已有则不动；无则保证 `gateLabel` 可用 |

**`StageView.vue` 必须满足的 DOM 结构（缺一项 = 未做完）**：

```text
√ 顶部 1 条 el-alert（结论 title + description），RELEASED 时 type=success
√ el-steps 仅 v-if="!isReleased"（4 步：识别 / 质检 / 预览 / 写入）
√ 标题 displayFilename（文件名），不是 fileId
√ el-select targetDomain：库存 / 资产 / 需求 / 出入库流水
√ 4 数字卡：可用行 / 阻塞行 / 预计写入 / 状态
√ 问题区：仅 1 条 warning alert（issueSummaryText），无 blocked 样本大表
√ 按钮：确认写入 | 查看数据成果（RELEASED）| 开始分析/重新分析 | 去数据规整 | 返回接入
√ 预览表：fieldZh(col) 列头 + visibleFields 过滤
× 不得存在：高级信息折叠、file_id 展示、接入计划表、指纹、run-note
```

**`StageView.vue` 必须满足的数据逻辑**：

```typescript
// 切换域时必须带 target_domain
staging.value = await getStaging(props.fileId, targetDomain.value)
const q = staging.value?.dry_run?.quality
// 质量数据：只从 staging 取，禁止单独调 getQualityReport 填问题数
domainQuality.value = q || null
// RELEASED 时不展示问题摘要
showIssueSummary = !isReleased && (blocked_rows > 0 || issue_total > 0)
// 文件名
listFiles() 或 listTasks() 按 fileId 查 filename → filename ref
```

**按钮文案硬编码**

| 原文（必须删掉） | 改为 |
|---|---|
| Staging / Step1 | 识别 / 质检等中文 |
| 去治理中心 | 去数据规整 |

### 0.5 Phase B — 二次整改 ST-13~ST-16

**触发条件**：切换「库存 / 资产 / 流水」后数字不跟着变；或问题数显示全文件 500+；或 detail 仍含 `key=` 英文。

| 顺序 | 文件 | 做什么 |
|---|---|---|
| B1 | `StageView.vue` | `refresh()` 只用 `getStaging(fileId, targetDomain)` + `dry_run.quality`；**删除**对 `GET /intake/quality/{file_id}` 的依赖 |
| B2 | `StageView.vue` | `showIssueSummary` 在 `status === 'RELEASED'` 时为 false；隐藏步骤条 |
| B3 | `StageView.vue` | 问题区只显示 `issueCountsSummary(issue_counts)` + `sanitizeUserHint(hint)`；**不渲染** blocked 行级样本表 |
| B4 | `app/services/intake/quality_precheck.py` | 所有写入 `detail` / `hint` 的字符串改为中文（如「必填项为空」「主键重复」） |
| B5 | `app/api/routers/stats.py` | `GET /stats/quality/{file_id}/blocked` 已有 `target_domain` 参数则**勿删**；前端本页可不调用此接口 |

**quality_precheck detail 示例（Agent 对照改）**：

| 改前（删） | 改后 |
|---|---|
| `required group blank` | 必填项为空 |
| `key=xxx \| count=82` | 字段「xxx」异常，共 82 行 |
| `blocking=true` | 不要出现在 hint；前端 `sanitizeUserHint` 也会兜底 |

### 0.6 每步必须跑的命令（在 `$ROOT`）

```bash
# 期望：exit 0
cd frontend && npm run build

# 期望：无输出
rg '高级信息|接入计划|数据指纹|去治理中心' frontend/src/pages/StageView.vue

# 期望：无输出
rg 'required group blank|blocking=true' frontend/src/pages/StageView.vue

# 期望：有匹配（说明关键逻辑在）
rg 'displayFilename|issueCountsSummary|sanitizeUserHint' frontend/src/pages/StageView.vue

# 期望：无匹配（不要再用全文件 quality API）
rg 'getQualityReport|/intake/quality/' frontend/src/pages/StageView.vue
```

### 0.7 手工冒烟（需后端 + 浏览器）

1. 打开 `/intake` → 某文件「进入规整」→ 进入 `/stage/{fileId}`。
2. **标题**是 Excel 文件名，不是 16 进制 id。
3. 下拉切「库存 → 资产 → 出入库流水」：**可用行 / 阻塞行 / 预览**随域变化。
4. 若有阻塞：只看到**中文摘要 alert**，没有英文 detail 大表。
5. 已写入文件：无步骤条、无问题区、主按钮「查看数据成果」。
6. 预览列头为中文（如「物资编码」）。

### 0.8 Agent 常见错误（踩了 = 返工）

| 错误 | 后果 | 正确做法 |
|---|---|---|
| 调用 `GET /intake/quality/{file_id}` 显示问题总数 | 显示 500+ 条全文件问题 | 只用 `staging.dry_run.quality` |
| 在 template 里写 `{{ staging.file_id }}` | 暴露运维字段 | 用 `displayFilename` |
| RELEASED 仍显示「开始分析」 | ST-5 未闭环 | `v-if="!isReleased"` |
| 保留 `<el-collapse>` 高级信息 | ST-1 未闭环 | 整段删除 |
| 裸渲染 `row.detail` | 英文泄漏 | 经 `detailZh()` / 后端中文 |
| 跳过 build 继续改后端 | TS 错误堆积 | 每 Phase 先 build |
| 改 router / 加新页面 | 超出范围 | 只改 §0.4 列出的文件 |

### 0.9 交付自检 Checklist（全部打勾再报完成）

- [ ] `StageView` 无「高级信息」、无 `file_id` 在 template 中展示
- [ ] `frontend/src/utils/stageLabels.ts` 存在且被 `StageView` import
- [ ] 4 数字卡 + 域下拉 + 中文预览列头
- [ ] RELEASED：无 steps、无问题 alert、按钮「查看数据成果」
- [ ] `npm run build` exit 0
- [ ] §0.6 全部 grep 符合「期望」
- [ ] （可选）§0.7 手工 6 条全绿

---

## 1. 用户是谁、来这页干什么

| 角色 | 目标 | 不应看到 |
|---|---|---|
| 评委（演示） | 同一文件分库存 / 资产 / 流水写入，看阻塞与预览 | 运维折叠区、技术状态英文 |
| 库管 / 物资员 | 看规整结果好不好 → 确认写入 → 去浏览数据 | 文件编号、指纹、接入计划、工作表结构 hint、JSON |

**页面定位**：新文件接入旅程的**最后确认门** — 只回答四件事：

1. 规整好了没有？
2. 能写多少行、拦多少行？
3. 有问题吗？什么问题？
4. 确认写入 / 去看成果

### 1.1 站点位置与页面边界

| 项 | 说明 |
|---|---|
| 侧栏 | **无**独立菜单项；从 `/intake` 任务卡或文件台账「进入规整」跳入 |
| 上游 | `/intake`：上传、任务进度、文件台账 |
| 下游 | `/data`：数据成果（明细 / 报表 / 趋势） |
| **唯一职责** | 单文件 staging 评估 → 人工 confirm → 写入业务库 |
| **禁止承担** | 多文件列表、治理队列写操作、模型管理、固定报表、SQL 编辑 |
| 运维排查 | `/system`、`/trace`、OpenAPI、`meta.sqlite` — **不得**占用本页用户路径 |

### 1.2 接入流水线与确认门（后端上下文）

新 Excel 经六步流水线（解析 → 画像 → 映射 → 质量预检 → 清洗 → 核对）产出 **staging 暂存评估**；业务库写入 **唯一**经本页 confirm，不走直接 ingest。

```text
上传（/intake）
  → worker 跑 Step 0–5
  → GET /intake/stage/{file_id} 生成/读取暂存评估（dry-run + gate + 指纹）
  → 用户在本页审阅
  → POST /intake/stage/{file_id}/confirm 确认门 → writer 幂等发布
  → status=RELEASED → 跳转 /data 看成果
```

**staging 状态机（用户可见映射见 §3.2）**：

| 内部值 | 用户可见 | 含义 |
|---|---|---|
| STAGED | 待确认 | 可审阅、可 confirm |
| RELEASING | 写入中 | 短暂中间态 |
| RELEASED | 已写入 | 只读回顾，隐藏问题明细 |
| FAILED | 失败 | 提示重试或联系运维 |

**clean / blocked**：清洗后质量合格行 vs 被规则拦截行；二者在 confirm 前均为「治理候选」，只有 confirm 后 clean 随 release 正式发布。

---

## 2. 现状问题（2026-08-18 Review）

### 2.1 信息架构

| 编号 | 问题 | 严重度 |
|---|---|---|
| ST-1 | 「高级信息（运维 / 排查用）」对业务用户零价值，却占整页底部 | P0 |
| ST-2 | 标题展示 `file_id` 十六进制，而非文件名 | P0 |
| ST-3 | 「接入计划 / 工作表识别 / 数据指纹」属运维面，不应出现在用户路径 | P0 |
| ST-4 | 操作按钮偏多（分析 / 刷新 / 确认 / 返回 / 治理），主次不清 | P1 |
| ST-5 | 已写入（RELEASED）仍展示「开始分析」，易误导 | P1 |

### 2.2 中英文混杂（用户可见路径）

| 编号 | 位置 | 现状 | 目标 |
|---|---|---|---|
| ST-6 | 阻塞 / 质量 `detail` | `required group blank` | 必填项为空 |
| ST-7 | 阻塞 `reason_detail` | `material_name required` | 物资名称不能为空 |
| ST-8 | 质量 `hint` | 含 `blocking=true` / confirm / LLM | 全中文业务句 |
| ST-9 | 预览列值 | 部分仍显示英文字段名（未走 `fieldZh`） | 列头中文；单元格为业务值 |
| ST-10 | 按钮「去治理中心」 | 与侧栏「数据规整」不一致 | 统一为「去数据规整」 |

### 2.3 布局

| 编号 | 问题 | 目标 |
|---|---|---|
| ST-11 | 窄屏表格撑破、步骤条描述冗余 | 表格横向滚动；步骤仅四字标题 |
| ST-12 | 指标卡 6+4 仍偏多 | 保留：可用行 / 阻塞行 / 预计写入 / 状态 |

---

## 3. 整改方案

### 3.1 页面结构（整改后）

```text
步骤条（识别 → 质检 → 预览 → 写入）  ← RELEASED 时隐藏
结论条（一句话：能确认 / 已写入 / 有问题）
规整结果卡
  + 文件名 + 数据类型（库存 / 资产 / 流水）
  + 4 个数字卡：可用行 / 阻塞行 / 预计写入 / 状态
  + 主操作：确认写入 | 查看数据成果 | 返回接入 |（有问题时）去数据规整
需要处理的问题（仅 STAGED 且 blocked>0 或 quality>0；RELEASED 隐藏）
规整后预览（业务列，visibleFields 过滤 source_* 等技术列）
```

**删除整块**：高级折叠区（工作表识别、接入计划、指纹、版本号、`file_id`）。

### 3.2 中文术语（本页 SSOT）

改本页用户可见文案时 **只改本节**，不在其他文档重复维护。

| 英文 / 内部 | 用户可见 | 备注 |
|---|---|---|
| STAGED / RELEASED / RELEASING / FAILED | 待确认 / 已写入 / 写入中 / 失败 | `stagingStatusZh()` |
| `file_id` | **不展示**；标题用文件名 | 从 `GET /tasks?file_id=` |
| inventory / asset / stock_flow / demand | 库存 / 资产 / 出入库流水 / 需求 | 下拉 label；`:value` 可保留英文 |
| material_name required | 物资名称不能为空 | |
| MISSING_COL / MISSING_REQUIRED | 缺少必填字段 / 必填项为空 | |
| required group blank | 必填项为空 | |
| 治理中心 | **数据规整** | 与侧栏一致 |
| gate ready / blocked | 就绪 / 阻塞 | 若出现则汉化 |
| LLM | 大模型 | hint 清洗 |
| blocking=true | 存在阻塞项 | `sanitizeUserHint()` |
| OpsToken | 操作令牌 | 本页一般不展示 |
| confirm | 确认写入 | |

### 3.3 API（只读 + 已实现约束）

| 用途 | HTTP | 前端函数 | 要点 |
|---|---|---|---|
| 暂存评估 | `GET /api/v1/intake/stage/{file_id}?target_domain=` | `getStaging()` | 切换库存 / 资产 / 流水时 **必须**带 `target_domain` |
| 确认写入 | `POST /api/v1/intake/stage/{file_id}/confirm` | `confirmStaging()` | 需 ops / govern token |
| 丢弃暂存 | `POST /api/v1/intake/stage/{file_id}/discard` | — | 运维路径 |
| 文件名 | `GET /api/v1/tasks?file_id=` | `listTasks()` | 用 `filename` 作标题 |
| 阻塞明细（本页通常不调用） | `GET /api/v1/stats/quality/{file_id}/blocked?target_domain=` | `listQualityBlocked()` | 若做行级表须带域；**当前实现只用摘要，不拉样本表** |
| 质量（**禁止本页使用**） | `GET /api/v1/intake/quality/{file_id}` | `getQualityReport()` | 全文件聚合；**会导致 ST-13** |

**数据绑定规则（二次整改 ST-13~ST-16）**：

1. 质量条数 / 摘要：优先 `staging.dry_run.quality`（与所选域一致）。
2. 阻塞：`list_blocked` 带 `target_domain`；**RELEASED 时整段隐藏**。
3. 未确认且有阻塞：只展示 `issue_counts` 中文摘要，**不展示**原始英文样本表。
4. RELEASED：隐藏步骤条 + 问题双表；主按钮「查看数据成果」。

### 3.4 代码落点

| 任务 | 文件 |
|---|---|
| 删高级区 + 精简 fetch + 按域切换 | `frontend/src/pages/StageView.vue` |
| 状态 / 域 / hint / detail 汉化 | `frontend/src/utils/stageLabels.ts` |
| 门禁 label | `frontend/src/utils/gateLabels.ts` |
| 预览列头 / 单元格 | `@/utils/fields` 的 `fieldZh`、`valueZh`、`visibleFields` |
| 文件名展示 | `StageView.vue` + `listTasks` |
| 质量 detail 中文模板 | `app/services/intake/quality_precheck.py` |
| 主内容区宽度 | `App.vue`（100% 宽，本页配合表格横滑） |
| 阻塞按域 | `app/api/routers/intake.py`（`list_blocked` 参数） |

### 3.5 `stageLabels.ts` 规格（本页文案工具）

**路径**：`frontend/src/utils/stageLabels.ts`

**必须导出**：

| 函数 | 用途 |
|---|---|
| `domainZh(domain)` | inventory → 库存 |
| `stagingStatusZh(status)` | STAGED / RELEASED → 待确认 / 已写入 |
| `targetTableZh(table)` | 物理表名 → 中文表名 |
| `sanitizeUserHint(text)` | 去掉 blocking / LLM / confirm 等英文碎片 |
| `fieldsListZh(fields)` | 字段名数组 → 中文顿号列表 |
| `issueCountsSummary(counts)` | `issue_counts` →「必填项为空 82 行；…」 |
| `detailZh(detail)` | 兜底解析 `key=` / `value=` / blank / required 英文模板 |

**禁止**：在 `StageView.vue` 模板中裸染后端 `detail` / `hint` / `reason_detail`，须经上述函数之一。

### 3.6 已写入态与 disclaimer 边界

本页 **不**展示「非正式发布 / 可用候选」类 disclaimer — 该类说明全站只允许出现在 **首页顶栏一处**。本页结论条只用业务态文案，例如「已写入，可查看数据成果」。

---

## 4. 验收标准

> Agent 自动化验收以 **§0.6** 为准；本节供人工复核。

### 4.1 手工

1. 业务用户路径 **零**「高级信息」折叠区、零 `file_id` / 指纹 / 接入计划表。
2. 标题为 **文件名**；数据类型下拉切换后数字与预览随域变化。
3. 质量 / 阻塞区域 **无裸英文** detail（`required group blank` 等已汉化）。
4. 已写入状态：主按钮为「查看数据成果」，无「确认写入」、无步骤条、无问题表。
5. 375px 宽屏：无整页横向滚动；表格区域可横滑。

### 4.2 构建与 grep

与 **§0.6** 相同：

```bash
cd frontend && npm run build

# 本页不应再出现运维折叠与 file_id 展示
rg '高级信息|file_id|接入计划|数据指纹|去治理中心' frontend/src/pages/StageView.vue
# 期望：无匹配（file_id 仅出现在 script/API 参数，不在 template 文案）

rg 'required group blank|blocking=true|LLM.*跳过' frontend/src/pages/StageView.vue
# 期望：无匹配
```

---

## 5. 不在本轮（本页不解决）

| 项 | 说明 |
|---|---|
| 低值易耗 / 个人工器具 sheet 未路由 | 接入编排配置缺口；需在 adapter / 路由表扩展，非 UI 文案 |
| 305 等源数据 `material_name` 为空导致 block | 源数据 + 治理队列；本页只如实展示阻塞摘要 |
| 全站顶栏 disclaimer 重复 | 首页顶栏 SSOT 处理；本页不重复 |
| 运维 JSON / 原始 quality API 全量 | SystemView、OpenAPI、meta 库 |

---

## 6. 二次 Review（2026-08-18 晚）

### 6.1 仍暴露的问题

| 编号 | 现象 | 根因 |
|---|---|---|
| ST-13 | 「需要处理的问题」显示 513 项 | 误用 `GET /intake/quality/{file}`（全文件），未用当前域 `staging.dry_run.quality` |
| ST-14 | 「未入库明细」与当前域无关 | `list_blocked` 取最新 staging（常为 stock_flow），未按 `target_domain` |
| ST-15 | 说明列出现 `key=… \| count=82` | 后端 `quality_precheck.py` detail 为英文模板 |
| ST-16 | 已写入仍展示问题双表 | RELEASED 态应只保留顶部数字卡，不展示明细表 |

### 6.2 二次整改（已全部落地）

1. **质量数据**：优先 `staging.dry_run.quality`（与所选库存 / 资产 / 流水一致）。
2. **阻塞**：`list_blocked` / 摘要带 `target_domain`；RELEASED 隐藏。
3. **问题区**：只展示 `issue_counts` 中文摘要，不渲染英文样本表。
4. **后端**：`detail` / `hint` 改为中文；前端 `detailZh` 兜底解析 `key=` / `value=` / blank 模式。
5. **前端**：RELEASED 隐藏步骤条 + 问题区；主按钮「查看数据成果」。

---

## 7. 实施记录

| 日期 | 内容 | 关键文件 |
|---|---|---|
| 2026-08-18 | ST-1~ST-12：删高级区、文件名标题、4 数字卡、术语汉化 | `StageView.vue`、`stageLabels.ts`、`gateLabels.ts` |
| 2026-08-18 晚 | ST-13~ST-16：按域质量 / 阻塞、RELEASED 隐藏问题区、后端 detail 中文 | `StageView.vue`、`quality_precheck.py`、`intake.py` |

**构建**：`cd frontend && npm run build` exit 0。

---

## 8. 决策记录（本页锁定）

| ID | 决策 |
|---|---|
| ST-D1 | 用户路径零 `file_id` / 指纹 / 接入计划；运维信息走 `/system`、`/trace` |
| ST-D2 | 标题用文件名；域切换必须驱动 staging + 阻塞 + 预览 |
| ST-D3 | RELEASED 只读：无 confirm、无步骤条、无问题明细表 |
| ST-D4 | 阻塞 / 质量文案 SSOT 在本文件 §3.2 + `stageLabels.ts` |

---

## 截图索引（时间戳 ↔ 章节）

| 截图 | 对应内容 |
|---|---|
| `ScreenShot_2026-08-18_205923_552` | 文首元数据 + §0.1~§0.3 |
| `ScreenShot_2026-08-18_205949_060` | §0.4 Phase A |
| `ScreenShot_2026-08-18_210006_124` | §0.5~§0.7 Phase B / 命令 / 冒烟 |
| `ScreenShot_2026-08-18_210026_087` | §0.8~§1.1 |
| `ScreenShot_2026-08-18_210048_260` | §1.2~§2.3 |
| `ScreenShot_2026-08-18_210110_823` | §3.1~§3.3 |
| `ScreenShot_2026-08-18_210130_072` | §3.4~§4.1 |
| `ScreenShot_2026-08-18_210149_642` | §4.2~§7 |
| `ScreenShot_2026-08-18_210201_940` | §8 决策记录 |
