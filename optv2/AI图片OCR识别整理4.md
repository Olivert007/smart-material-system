# 数据规整页面借鉴参考项目修改方案（整理）

> **副本位置**：`治理方案/来源/`（供 Docker/Agent 自包含阅读）  
> 来源：宿主机截图 OCR 识别（rapidocr-onnxruntime）；原始 `AI20260813/ocr_out/*.txt` 不随本目录交付  
> 整理日期：2026-08-13  
> 说明：本文档为截图内容的去重、纠错与结构化整理；OCR 难免有个别错字，已尽量修正（如 v1lm/v11m→vllm、1ocal→local、θ→0、丨→|、e→o 等）。截图按拍摄时间前后对应文档逻辑顺序，部分截图存在重复内容，已合并。

---

## 0. 文档信息

- 目标项目：`/workspace/vllm-omni/bugfix/smart-material-system`
- 参考项目：`/workspace/vllm-omni/smart-material-system`
- 日期：2026-08-13
- 本文目的：先写清楚修改方案，后续让低端 agent 按步骤执行。**不要在没有完成本文检查项前直接编码。**

## 1. 执行纪律：先记录问题，再修改代码

后续处理"数据规整"页面问题时，必须遵守以下顺序：

1. 先把用户反馈的问题记录到本文档。
2. 写清楚问题现象、复现步骤、影响范围。
3. 用接口巡检、构建、测试或页面观察确认问题是否真实存在。
4. 写出根因判断或至少列出待验证假设。
5. 写出准备修改的文件和修改方法。
6. 然后再修改代码。
7. 修改后把验证结果补回文档。

禁止：

1. 不记录问题就直接改代码。
2. 没有复现就按猜测大改页面。
3. 只修前端提示而不检查真实 500 接口。
4. 修完不记录验证命令和结果。

## 2. 本次目标

必须完成：

1. "数据规整"页面使用参考项目 `frontend/src/pages/GovernHub.vue` 的组织方式。
2. 删除独立的"治理待办"页面入口。
3. 删除独立的"AI建议审核"页面入口。
4. 所有原来跳转到 `/todos`、`/ai-review`、`/suggestions`、`/govern/todos` 的地方，改为回到 `/govern` 或删除按钮。
5. 页面第一屏要聚焦"当前待处理事项"，不要把治理待办和 AI 审核拆成独立主导航。

不做什么：

1. 不新增新业务功能。
2. 不重写后端接口。
3. 不删除数据库表。
4. 不删除后端 API，除非后续确认完全无引用。本轮只删除前端页面和入口。
5. 不改"数据接入"、"数据成果"、"追溯审计"的主流程，除非只是为了修正跳转路径。

## 3. 参考项目结论

参考项目已经把页面收敛得更简单：

- 主导航只有"数据规整"，没有独立"治理待办"、"AI建议审核"。
- `/govern` 使用 `GovernHub.vue` 作为工作台入口。
- 没有 `AiReviewView.vue` 页面。
- 工作台第一屏展示：待确认字段、待匹配物资、待解析流水、库存对账差异、门禁阻断。
- 用户点击摘要卡片后，在同一页展开 `GovernView` 处理详情。

参考文件：

- `/workspace/vllm-omni/smart-material-system/frontend/src/router/index.ts`
- `/workspace/vllm-omni/smart-material-system/frontend/src/pages/GovernHub.vue`
- `/workspace/vllm-omni/smart-material-system/frontend/src/App.vue`

## 4. bugfix 当前问题

bugfix 项目当前把同一类工作拆得过碎：

| 位置 | 现状 |
|---|---|
| `App.vue` | 主导航同时有："数据规整"、"治理待办"、"AI建议审核" |
| `router/index.ts` | 同时注册：`/todos`、`/govern`、`/ai-review`、`/suggestions`、`/govern/todos` |
| `HomeView.vue` | 有"去处理待办"按钮跳转 `/todos` |
| `GovernHub.vue` / `AiReviewView.vue` | `AiReviewView.vue` 是 bugfix 独有页面，参考项目没有 |
| `BlockedDataPanel.vue` | 跳转 `/todos` |

这些会让用户误以为"数据规整 / 治理待办 / AI建议审核"是三个主流程。实际应该收敛到一个"数据规整工作台"。

## 5. 文件级修改清单

### 5.1 必改文件

#### `frontend/src/pages/GovernHub.vue`

处理方式：用参考项目的 `GovernHub.vue` 作为主实现。

执行要求：

1. 打开参考文件：`/workspace/vllm-omni/smart-material-system/frontend/src/pages/GovernHub.vue`
2. 打开目标文件：`/workspace/vllm-omni/bugfix/smart-material-system/frontend/src/pages/GovernHub.vue`
3. 用参考项目内容替换目标项目内容。
4. 替换后保留目标项目已有的 import 路径风格：`@/pages/GovernView.vue`、`@/api/client`。
5. 不要保留以下 bugfix 专属逻辑：`isTodosHub`、`hubPath`、`/todos`、`/ai-review`、`governTodoSummary`、`governTodoList`、`governTodoDecision`、`AssetsView`、`MetricsView`、`advancedOpen`、`advancedFold`。
6. 保留参考项目的核心数据来源：`listMapPending`、`listFlowPending`、`listMasterPending`、`flowReconcile`、`statsOverview`。
7. 注意目标项目的 `flowReconcile()` 当前没有导出 `FlowReconcileAssist` 类型，也不保证返回 `assist` 字段。实施时**不要直接 import `FlowReconcileAssist`**；改用本文件内的本地类型和兜底文案。

本地类型建议：

```ts
type FlowReconcileAssist = {
  summary?: string;
  primary_reason?: string;
  recommendations?: Array<{ title?: string; impact?: string }>;
};
```

加载对账结果时使用可选读取：

```ts
const assist = (reconcile as { assist?: FlowReconcileAssist }).assist;
reconcileAssist.value = assist ?? null;
```

展示文案必须有兜底：

```ts
hint: reconcileAssist.value?.primary_reason || '库存与流水核对'
```

验收：

- `/govern` 打开后标题是"数据规整工作台"。
- 第一屏是"当前待处理事项"。
- 点击摘要卡片只在本页展开详情，不跳到 `/todos` 或 `/ai-review`。

#### `frontend/src/router/index.ts`

处理方式：对齐参考项目路由。

删除：

```ts
import AiReviewView from '@/pages/AiReviewView.vue'
```

删除 routes：

```ts
{ path: '/todos', name: 'todos', component: GovernHub },
{ path: '/ai-review', name: 'ai-review', component: AiReviewView },
```

修改兼容重定向：

```ts
{ path: '/govern/todos', redirect: (to) => ({ path: '/govern', query: to.query }) },
{ path: '/todos', redirect: (to) => ({ path: '/govern', query: to.query }) },
{ path: '/ai-review', redirect: '/govern' },
{ path: '/suggestions', redirect: '/govern' },
```

注意：如果产品要求"彻底不存在这些路径"，可以直接删除兼容重定向。但建议第一轮保留重定向，避免旧链接白屏。

验收：

- 代码里不再 `import AiReviewView`。
- 访问 `/ai-review`、`/todos` 会回到 `/govern`。
- 主路由里不再有名为 `todos` 或 `ai-review` 的页面组件。

#### `frontend/src/App.vue`

处理方式：对齐参考项目导航。

删除菜单：

```vue
<el-menu-item index="/ai-review">AI建议审核</el-menu-item>
```

以及"治理待办"菜单项。

删除 `activePath` 特判：

```ts
if (p === '/todos' || p === '/govern/todos') return '/todos';
if (p === '/ai-review' || p === '/suggestions') return '/ai-review';
```

新增或保留兼容：

```ts
if (['/todos', '/govern/todos', '/ai-review', '/suggestions'].includes(p)) return '/govern';
```

删除 `titleMap`：

```ts
'/todos': '治理待办',
'/ai-review': 'AI建议审核',
```

把 `/govern` 标题统一为：

```ts
'/govern': '数据规整工作台',
```

验收：

- 左侧主导航不再显示"治理待办"、"AI建议审核"；"数据规整"菜单仍存在。

#### `frontend/src/pages/HomeView.vue`

处理方式：删除独立待办和 AI 审核入口，统一指向 `/govern`。

需要搜索并处理：`/todos`、`/ai-review`、"治理待办"、"AI建议审核"、`showTodosShortcut`、`showAiReviewShortcut`。

修改规则：

1. 原来跳 `/todos` 的卡片，改为跳 `/govern`。
2. 原来跳 `/ai-review` 的卡片，删除该卡片或改为普通"数据规整"提示。
3. 删除 `showAiReviewShortcut`。
4. 文案里不要再出现"治理待办页面"或"AI建议审核页面"。

示例替换：

```ts
return '/todos';
// 改为
return '/govern';
```

验收：

- `HomeView.vue` 中不再出现 `/todos`、`/ai-review`。
- 工作台快捷入口只进入 `/govern`、`/intake`、`/data` 等主页面。

#### `frontend/src/pages/StageView.vue`

处理方式：删除"去处理待办"的说法，统一回到数据规整。

查找：

```vue
<el-button @click="$router.push('/govern')">去处理待办</el-button>
```

改为：

```vue
<el-button @click="$router.push('/govern')">返回数据规整</el-button>
```

验收：页面不再出现"待办页面"的独立入口文案。

#### `frontend/src/components/BlockedDataPanel.vue`

处理方式：跳转路径改为 `/govern`，文案改为"去数据规整"。

查找：

```vue
<el-button @click="$router.push('/todos')">去处理待办</el-button>
```

改为：

```vue
<el-button @click="$router.push('/govern')">去数据规整</el-button>
```

验收：文件中不再出现 `/todos`。

### 5.2 删除文件

删除 `frontend/src/pages/AiReviewView.vue`。

删除条件：

1. `router/index.ts` 已不再 import 它。
2. `rg "AiReviewView|/ai-review|AI建议审核" frontend/src` 没有有效引用。
3. `npm run build` 通过。

暂不删除：

- `frontend/src/components/RowEvidence.vue`：被 `LineageView.vue` 使用，不能删。
- `frontend/src/components/BlockedDataPanel.vue`：被 `DataView.vue` 使用，不能删，只改按钮跳转。

## 6. 推荐执行顺序

低端 agent 必须按这个顺序执行，不要跳步。

### 步骤 1：替换 `GovernHub.vue`

1. 读取参考项目 `GovernHub.vue`。
2. 读取 bugfix 项目 `GovernHub.vue`。
3. 用参考实现替换 bugfix 实现。
4. 不要引入 `/todos`、`/ai-review`。
5. 保存后先不要构建。

### 步骤 2：修改路由

1. 删除 `AiReviewView` import。
2. 删除独立页面路由。
3. 加兼容 redirect：`/govern/todos`→`/govern`、`/todos`→`/govern`、`/ai-review`→`/govern`、`/suggestions`→`/govern`。

### 步骤 3：修改主导航

1. 删除"治理待办"菜单。
2. 删除"AI建议审核"菜单。
3. `activePath` 统一映射到 `/govern`。
4. `titleMap` 删除两个旧标题。

### 步骤 4：修改工作台入口

1. 搜索 `/todos`。
2. 搜索 `/ai-review`。
3. 搜索"治理待办"。
4. 搜索"AI建议审核"。
5. 在 `HomeView.vue` 中把入口统一改成 `/govern` 或删除。

### 步骤 5：修改局部按钮

1. `StageView.vue`：按钮文案改为"返回数据规整"。
2. `BlockedDataPanel.vue`：按钮路径改为 `/govern`，文案改为"去数据规整"。

### 步骤 6：删除独立 AI 审核页面

1. 确认无引用后删除 `frontend/src/pages/AiReviewView.vue`。
2. 不删除后端接口。

### 步骤 7：构建验证

在 `/workspace/vllm-omni/bugfix/smart-material-system/frontend` 执行：

```bash
npm run build
```

构建必须通过。

## 7. 搜索验收命令

在 `/workspace/vllm-omni/bugfix/smart-material-system` 执行：

```bash
rg "/todos|/ai-review|治理待办|AI建议审核|suggestions|govern/todos" frontend/src
```

允许剩余的内容：

- `router/index.ts` 里的兼容 redirect。

不允许剩余的内容：

- 菜单项"治理待办"、"AI建议审核"。
- `HomeView.vue`、`GovernHub.vue` 里 `isTodosHub`、跳 `/ai-review` 等逻辑。
- `AiReviewView.vue` 文件仍被 import。

继续检查：

```bash
rg "AiReviewView|governTodoSummary|governTodoList|governTodoDecision" frontend/src
```

允许：

- `api/client.ts` 中暂时保留这些 API 函数。

不允许：

- 页面组件继续 import 或调用这些函数。

## 8. 页面验收

启动前后端后人工检查：

### `/govern` 必须看到

- 页面标题：数据规整工作台。
- 第一屏说明：按优先级处理字段、物资、出入库和库存对账问题。
- 摘要卡片：待确认字段、待匹配物资、对账差异、待解析流水、门禁阻断。
- 点击卡片后，在同一页展开处理详情。

### 不能看到

- 独立"治理待办"、"AI建议审核"页面提示、页面入口。
- 跳转 `/todos`、跳转 `/ai-review`。

### 左侧导航

必须看到：工作台、数据接入、数据规整、数据成果、问数助手、追溯审计、系统设置。  
不能看到：治理待办、AI建议审核。

### 旧链接兼容

访问 `/todos`、`/govern/todos`、`/ai-review`、`/suggestions`，预期都进入 `/govern`，页面不白屏。

## 9. 实施后发现的问题（8.x 系列）

### 9.1 字段规整详情无法操作

#### 问题现象

复刻参考项目后，在 `/govern` 页面点击"待确认字段"或待处理列表里的"字段规整"，页面会展开"处理详情：字段规整"，但用户反馈该区域"无法操作"。

具体表现可能包括：

1. 详情标题已经切到"字段规整"，但内部处理组件没有完整按字段规整页面渲染。
2. 从其他卡片切回字段规整时，内部内容可能仍停留在旧 tab 状态。
3. 字段队列表格能看到数据，但用户不知道为什么"接受/修正/忽略"点了不能真正执行。

#### 复现和排查结论

先用真实接口确认不是"没有字段数据"：

```bash
python - <<'PY'
import json, urllib.request
base='http://127.0.0.1:8011'
data=json.load(urllib.request.urlopen(base+'/api/v1/govern/map/pending?limit=5&offset=0&status=pending', timeout=20))
print('total=', data.get('total'), 'items=', len(data.get('items') or []))
print(json.dumps((data.get('items') or [{}])[0], ensure_ascii=False)[:500])
PY
```

当时真实结果：`total=29 items=...`。说明字段规整队列有数据，问题在前端详情渲染和操作提示。

#### 根因

根因有两个：

1. `GovernHub.vue` 嵌入 `GovernView` 时没有强制按当前处理类型重新挂载。复刻参考项目时，如果只写 `<GovernView :initial-tab="activeGovernTab"/>`，在详情已经展开后切换卡片，内部组件可能没有按用户当前点击的处理类型重建，表现为详情标题和内部可操作区域不同步。
2. `GovernView.vue` 的字段规整写操作需要 `ops_token`，但原页面只在点击操作后弹出提示。用户容易理解为"按钮无法操作"，而不是"缺少操作令牌"。

#### 修改方法

修改 `frontend/src/pages/GovernHub.vue`：把嵌入的 `GovernView` 改成带 `key`，并显式显示内部 tabs：

```vue
<GovernView
  :key="activeGovernTab"
  :initial-tab="activeGovernTab"
  :hide-outer-tabs="false"
/>
```

这样做的目的：

1. `activeGovernTab` 变化时，`GovernView` 会重新挂载。
2. `onMounted()` 会重新按当前 tab 加载字段、物资、流水或对账数据。
3. 保持和参考项目更接近的完整页面形态，用户可以看到内部 tabs 和提示。

修改 `frontend/src/pages/GovernView.vue`：在字段规整区域增加显式令牌提示。在字段规整第一个 `el-alert` 后追加：

```vue
<el-alert
  v-if="!opsTokenReady"
  type="error"
  :closable="false"
  show-icon
  title="字段规整操作需要操作令牌"
  description="当前只能查看字段队列。请先在系统设置填写操作令牌，再执行接受、修正或忽略。"
/>
```

在 `<script setup>` 中增加：

```ts
const opsTokenReady = computed(() => Boolean(localStorage.getItem('ops_token')))
```

注意：

- 不要绕过 `ops_token`。
- 不要让字段规整写操作在无令牌时直接执行。
- 这里只是把"为什么不能操作"提前显示出来。

#### 验收标准

进入 `/govern` 后：

1. 点击"待确认字段"卡片。
2. 页面出现"处理详情：字段规整"。
3. 下方能看到完整 `GovernView` 内容和内部 tabs。
4. 字段规整队列显示真实待确认映射。
5. 没有 `ops_token` 时，页面明确显示"字段规整操作需要操作令牌"。
6. 有 `ops_token` 时，接受/修正/忽略可继续走确认弹窗和后端接口。

验证命令：

```bash
npm run build
```

必须通过。

### 9.2 追加问题：用户不知道操作令牌怎么设置

#### 问题现象

字段规整区提示"字段规整操作需要操作令牌"，但用户不知道"操作令牌"是什么，也不知道应该填写什么值。

#### 根因

前端只提示"请先在系统设置填写操作令牌"，但没有解释：

1. 操作令牌来自后端环境变量 `OPS_TOKEN`。
2. 前端设置页只是把令牌保存到浏览器 `localStorage`。
3. 当前开发环境如果没有显式配置 `OPS_TOKEN`，后端默认值是 `dev-ops-token-change-me`。

后端来源（`app/config.py`）：

```python
OPS_TOKEN = os.environ.get("OPS_TOKEN", "dev-ops-token-change-me")
```

前端请求会把本地保存的令牌放到请求头 `X-Ops-Token`（`frontend/src/api/client.ts`）。

#### 用户操作方法

本地开发环境按以下步骤操作：

1. 打开左侧导航"系统设置"。
2. 在"操作令牌"输入框填入 `dev-ops-token-change-me`。
3. 点击"保存到本机"。
4. 回到"数据规整"。
5. 点击"待确认字段"。
6. 在"处理详情：字段规整"中执行"接受/修正/忽略"。

也可以在浏览器控制台临时设置：

```js
localStorage.setItem('ops_token', 'dev-ops-token-change-me')
localStorage.setItem('ops_role', 'ops')
```

然后刷新页面。

#### 注意事项

- 这个默认令牌只适合本地开发。
- 生产或共享环境必须通过环境变量 `OPS_TOKEN` 配置强令牌。
- 不要把生产令牌写入文档、代码或提交记录。
- 如果后端设置了自定义 `OPS_TOKEN`，前端必须填写那个真实值，不能继续用默认值。

### 9.3 追加问题：数据规整页面部分功能提示 500

#### 问题现象

用户反馈"数据规整"页面中很多功能块提示 500。优先检查页面加载接口，而不是先改前端。数据规整页主要包括：

1. 工作台概览。
2. 字段规整。
3. 规则沉淀。
4. 物资规整。
5. 出入库记录处理。
6. 库存对账。

#### 接口巡检方法

在项目根目录执行：

```bash
python - <<'PY'
import json, urllib.request, urllib.error
base='http://127.0.0.1:8011/api/v1'
paths=[
('/stats/overview?recent_limit=1', '工作台概览'),
('/govern/std-fields', '字段规整-标准字段'),
('/govern/rule-learn/candidates?limit=50', '规则沉淀-候选'),
('/assets/rule-dict?limit=50&offset=0', '字段规整-规则字典'),
('/govern/flow/pending?limit=20&offset=0&status=pending', '流水-待确认'),
('/govern/master/pending?limit=100&offset=0&status=pending', '物资规整-待审'),
('/govern/flow/stats', '流水-质量快照'),
('/govern/flow/reconcile', '库存对账'),
('/assets/flow-examples?limit=50&offset=0', '流水-示例池'),
]
for path, name in paths:
    try:
        with urllib.request.urlopen(base+path, timeout=30) as r:
            print('ok', name, path, r.status)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        print('ERR', name, path, e.code, body[:500])
PY
```

当时复现结果：

```text
ERR 字段规整-规则字典：/assets/rule-dict?limit=50&offset=0 -> HTTP 500
其他只读接口当时均为 200
```

#### 真实异常

用 `TestClient` 查看堆栈：

```bash
PYTHONPATH=. python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app, raise_server_exceptions=True)
client.get('/api/v1/assets/rule-dict?limit=50&offset=0')
PY
```

核心异常：

```text
sqlite3.OperationalError: no such column: r.status
```

出错位置：`app/api/routers/assets.py` 的 `assets_rule_dict()`，原因是查询了 `r.status, r.changed_by, r.updated_at`。

#### 根因

这是"旧真实数据表结构 + 新页面/接口字段"的兼容问题。当前从真实项目复制过来的 `meta.sqlite` 中，旧版 `rule_dict` 表只有：

```text
rule_id, header, std_field, business_domain, hits, source, confirmed_by, created_at
```

缺少：

```text
status, changed_by, updated_at
```

仓库里已有部分迁移逻辑，但低端 agent 不能假设启动时一定执行过迁移。页面接口必须能面对旧 `meta.sqlite` 自动补齐缺失列，否则真实数据一接入就会 500。

#### 修改方法

在 `app/services/govern/rule_dict.py` 新增幂等 schema 兜底函数：

```python
def ensure_rule_dict_schema() -> None:
    with meta_tx() as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(rule_dict)").fetchall()}
        if "status" not in cols:
            con.execute("ALTER TABLE rule_dict ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        if "changed_by" not in cols:
            con.execute("ALTER TABLE rule_dict ADD COLUMN changed_by TEXT")
        if "updated_at" not in cols:
            con.execute("ALTER TABLE rule_dict ADD COLUMN updated_at TEXT")
        con.execute("UPDATE rule_dict SET updated_at = datetime('now') WHERE updated_at IS NULL")
```

必须在以下读写路径前调用：`ensure_seed_rules()`、`_fetch_rules()`、`set_rule_status()`、`list_rule_conflicts()`。

同时在 `app/api/routers/assets.py` 的 `assets_rule_dict()` 查询前调用：

```python
from app.services.govern.rule_dict import ensure_rule_dict_schema
ensure_rule_dict_schema()
```

#### 验收方法

先验证实际服务端口：

```bash
python - <<'PY'
import json, urllib.request
base='http://127.0.0.1:8011/api/v1'
for path in [
'/assets/rule-dict?limit=50&offset=0',
'/assets/rule-dict/conflicts',
'/govern/map/pending?limit=100&offset=0&status=pending',
'/govern/flow/reconcile',
]:
    with urllib.request.urlopen(base+path, timeout=20) as r:
        data = json.loads(r.read().decode())
        print(path, r.status, {k: data.get(k) for k in ['total','limit','offset','ok','conflict_count'] if k in data})
PY
```

预期：

```text
/assets/rule-dict?limit=50&offset=0 200
/govern/map/pending?... 200
/assets/rule-dict/conflicts 200
/govern/flow/reconcile 200
```

再跑测试：

```bash
PYTHONPATH=. pytest tests/test_map_gov.py tests/test_rule_dict_learning.py
```

预期：`6 passed`。

最后构建前端：

```bash
cd frontend && npm run build
```

必须通过。

### 9.4 追加问题：系统页面仍存在中英文混杂

#### 问题现象

用户反馈系统页面仍存在中英文混合，例如页面上出现 `ignore` 这类英文状态或动作，会让业务用户难以理解，尤其是在"数据规整、字段规整、出入库记录处理"等需要人工确认的页面。

#### 处理顺序

必须先记录，再修改。执行步骤：

1. 先全局扫描前端页面中的英文状态、动作、按钮和占位值。
2. 区分两类内容：
   - 用户可见文案：必须中文化。
   - 后端协议值、API 参数、枚举值：代码里可以继续用英文，但展示层必须映射成中文。
3. 优先处理用户已指出的 `ignore`。
4. 修改后运行构建。
5. 把扫描结果、修改点、验证结果补回本文档。

#### 初步修改原则

对用户可见的英文状态做展示层映射，不要直接改后端协议值。示例：

```text
ignore -> 忽略
pending -> 待确认
accepted -> 已接受
ignored -> 已忽略
confirmed -> 已确认
conflict -> 冲突
```

字段下拉中的真实值可以仍然是 `ignore`，但页面 label 必须显示"忽略"。

#### 本次扫描结果

优先扫描：

```bash
rg "ignore|pending|accepted|ignored|confirmed|conflict|accept|amend|reject|enable|disable" frontend/src
```

确认用户可见问题主要集中在 `frontend/src/pages/GovernView.vue`。

具体问题：

1. 字段规整->待确认映射队列->建议直接显示。
2. 候选标签直接显示技术字段，例如 `stock_qty`、`material_`。
3. 字段规整的标准字段下拉直接显示 `ignore`。
4. 映射确认弹窗直接显示 `accept/amend/ignore`。
5. 提示文案出现全为 `ignore`。
6. 流水提示中出现 `example`、`conflict` 状态。

#### 本次修改方法

修改 `frontend/src/pages/GovernView.vue`，新增展示层 helper：

```ts
function stdFieldLabel(field?: string | null): string {
  if (!field) return '未选择'
  if (field === 'ignore') return '忽略'
  return fieldzh(field)
}

function decisionLabel(decision: string): string {
  const map: Record<string, string> = {
    accept: '接受',
    amend: '修正',
    ignore: '忽略',
    accepted: '已接受',
    rejected: '已拒绝',
    proposed: '待确认',
    reject: '拒绝',
    approve: '批准',
    merge: '合并',
  }
  return map[decision] || decision
}

// 引入
import { fieldzh } from '@/utils/fields'
```

修改展示：

1. 建议直接显示 → 用 `decisionLabel`。
2. 候选标签改成 `stdFieldLabel(c.std_field)`；`value` 仍保持原始协议值。
3. 全为 `ignore` 改成"全为忽略"。
4. 映射确认弹窗改成 `decisionLabel(decision)`。
5. `example` 改成"流水拆解示例"。
6. `conflict` 状态改成"冲突状态"。

#### 本次验证结果

```bash
npm run build
```

结果：`√ built`；ReadLints：`No linter errors found.`

### 9.5 追加需求：填充已确认规则字典和自学习示例池数据

#### 需求现象

用户希望在"数据规整->处理详情"中看到这两个区域的实际样子：

1. 已确认规则字典。
2. 自学习示例池（流水拆解示例）。

当前真实数据中：已确认规则字典有少量种子规则，但不够直观；自学习示例池为空。

#### 处理原则

必须先记录，再填数据。填充要求：

1. 使用真实库里的待确认字段和流水待确认数据。
2. 不写纯假数据。
3. 只填少量样例，用于页面查看。
4. 不批量清空或重置业务数据。
5. 填充后记录具体数量和验证方式。

#### 推荐填充方式

规则字典：

1. 从 `map_pending` 中选取有明确业务含义的字段。
2. 写入 `rule_dict`。
3. 保持 `status='active'`。

流水示例池：

1. 从 `flow_pending` 中选取 `pending` 且有可解析方向的记录。
2. 通过治理确认逻辑生成 `flow_example`。
3. 不要随意构造与真实文本无关的流水。

#### 验收方式

接口验证：

```bash
python - <<'PY'
import json, urllib.request
base='http://127.0.0.1:8011/api/v1'
for path in ['/assets/rule-dict?limit=10&offset=0', '/assets/flow-examples?limit=1&offset=0']:
    with urllib.request.urlopen(base+path, timeout=20) as r:
        data = json.loads(r.read().decode())
        print(path, data.get('total'), len(data.get('items') or []))
PY
```

页面验证：

1. 打开 `/govern`。
2. 点击"待确认字段"，查看"已确认规则字典"。
3. 点击"待解析流水"，查看"自学习示例池（流水拆解示例）"。

#### 执行中发现的问题：flow_pending 缺少 version

实际填充时，规则字典样例可以插入，但通过真实治理确认逻辑生成流水拆解示例时报错：

```text
no such column: version
```

触发路径：`app/services/govern/flow_gov.py`。

原因：`confirm_pending()` 会执行：

```sql
UPDATE flow_pending
SET status=?, suggested_json=?, conflict=0, version=version+1, updated_at=datetime('now')
WHERE pending_id=?
```

但当前真实数据复制过来的旧版 `flow_pending` 表没有 `version` 列。

修复方法：

1. 给 `flow_pending` 增加幂等 schema 兜底。
2. 在 `confirm_pending()` 和 `list_pending()` 前调用。
3. 不直接绕过确认逻辑插入 `flow_example`，避免样例格式和真实确认路径不一致。

#### 本次填充结果

已填入：

1. `rule_dict`：新增 5 条来自真实待确认字段的 active 规则。
2. `flow_example`：通过真实 `flow_pending` 确认逻辑生成 3 条流水拆解示例。
3. `flow_pending`：补齐旧库缺失的 `version` 列，避免确认流水时 500。

接口验证结果：

```text
/api/v1/assets/rule-dict?limit=10&offset=0 -> 200, total=7, items=7
/api/v1/assets/flow-examples?limit=10&offset=0 -> 200, total=3, items=3
```

已看到的样例：

```text
规则字典：数量->stock_qty（inventory）
规则字典：商品编号->material_code（demand）
规则字典：项目描述->project_name（asset）
流水示例：建设期至2024年之前采购
流水示例：2025.9.25张艺兴领用1个，2026.3吕玮智领用1个，用于日常设备维护
流水示例：2025.9徐吉领用85台，用于东苑电话安装、三峡大厦电话检修；2026.4.10徐吉领用10台，用于三峡大厦电话检修
```

测试验证：

```bash
PYTHONPATH=. pytest tests/test_map_gov.py tests/test_rule_dict_learning.py tests/test_rule_dict_status.py
```

结果：`11 passed, 1 warning`。

### 9.6 页面提示层级与详情标题不同步问题

#### 问题现象

在"数据规整->处理详情"中切换子 Tab 时，页面存在以下问题：

1. 外层标题一直显示"处理详情：出入库记录处理"，但内部实际已经切到"字段规整"、"规则沉淀"、"物资规整"或"库存对账"。
2. "数据规整待确认"作为大块提示在每个子页面重复出现。
3. 多个页面把流程说明显示成黄色告警，容易让用户误以为系统异常。
4. `POST /govern/flow/opening/seed` 等技术文案，不适合业务用户。

#### 根因

1. 只在点击上方待处理事项时更新 `activeGovernTab`。
2. `GovernView` 内部 Tab 切换后没有向外层同步当前 Tab。
3. 顶部全局说明使用 `el-alert` 常驻显示，和各子页说明叠加。
4. 库存对账接口返回的技术 note 被前端原样展示。

#### 修改方案

1. `GovernView` 增加 `tab-change` 事件。
2. `GovernHub` 监听该事件，同步 `activeGovernTab`，保证详情标题与内部 Tab 一致。
3. 将全局"数据规整待确认"大块 alert 降级为普通说明文字。
4. 将普通流程说明从黄色告警调整为信息说明；只对真正需要处理的风险保留 warning。
5. 对库存对账说明做前端业务化文案映射，避免 `PoC`、接口路径、英文内部字段直接暴露。

#### 验收方式

1. 打开 `/govern`。
2. 点击"待解析流水"进入详情。
3. 在详情内依次切换"字段规整"、"规则沉淀"、"物资规整"、"出入库记录处理"、"库存对账"。
4. 验证标题分别显示：处理详情：字段规整 / 处理详情：规则沉淀 / 处理详情：物资主数据 / 处理详情：出入库记录处理 / 处理详情：库存对账。
5. 验证非异常说明不再以重复黄色大块告警出现。
6. 验证库存对账说明中不再出现 `PoC`、`missing opening_qty`、接口路径等技术文案。

#### 本次修改结果

已修改：

- `frontend/src/pages/GovernView.vue`：增加 `tab-change` 事件；将全局"数据规整待确认"alert 降级为普通说明文字；将字段规整、物资规整说明从 warning 调整为 info。
- `frontend/src/pages/GovernHub.vue`：对库存对账接口返回的技术 note 做业务化中文映射；监听 `GovernView` 的 `tab-change` 事件，内部 Tab 切换时同步外层 `activeGovernTab`，保证"处理详情标题正确"；移除对子组件 `key` 的强制重建依赖，避免内部 Tab 切换时整块详情重复挂载。

验证：

```bash
npm run build
```

结果：`vue-tsc -b && vite build` 通过。Vite 仍提示 `chunk > 500kB`，此为既有打包体积提示，非本次修改引入的编译错误。

### 9.7 数据规整页面前后端功能扫描问题

#### 扫描范围

本次只读扫描范围：

1. `frontend/src/pages/GovernHub.vue`
2. `frontend/src/pages/GovernView.vue`
3. `frontend/src/api/client.ts`
4. `app/api/routers/govern.py`
5. `app/services/govern/flow_gov.py`
6. 页面只读接口：`/govern/map/pending`、`/govern/master/pending`、`/govern/flow/stats`、`/govern/flow/pending`、`/govern/flow/reconcile`、`/assets/rule-dict`、`/assets/flow-examples`、`/stats/overview`

#### 已复现/已确认的问题

1. **流水级别筛选分页错误**：前端 `flowLevelFilter` 只过滤当前页返回数据。当前真实数据中 pending 流水为 L2=424、L3=4，第一页只有 L3=3，选择 L3 会漏掉后续页数据。
2. **主数据待审无法处理全部数据**：页面显示总数，但没有分页，后 480 条无法在页面处理。
3. **工作台摘要抗失败能力不足**：`GovernHub.loadSummary()` 使用 `Promise.all`，这会放大单点 500 对页面的影响；任一摘要接口失败，会导致整个工作台摘要失败。
4. **操作令牌提示不是响应式**：`opsTokenReady` 直接读取 `localStorage`，用户在设置页补充令牌后，当前详情组件可能仍显示"只能查看"。
5. **个别成功提示的验证入口不精确**：字段映射确认后提示进入 `fact_inventory` 验证；字段映射本质是规则字典变更，不一定对应库存事实表，容易误导。

#### 修改方案

1. `flow_gov.list_pending()` 在 SQL 层按 `parse_level` 过滤，并返回过滤后的 total。
2. 前端 `listFlowPending()` 透传 `parse_level`。
3. `GovernView` 删除流水当前页本地筛选，改为后端分页筛选。
4. `GovernHub.loadSummary()` 改为局部容错：摘要接口失败时保留其他成功结果，并给出错误提示。
5. 操作令牌状态改为可刷新状态，在页面 focus/storage 变化时重新读取。
6. 字段映射确认成功提示改为"已写入规则字典"。

#### 验收方式

1. 流水处理页选择 L3：翻页不应丢数据；总数应为真实 L3 数量。
2. 主数据待审页：能看到分页控件；总数为后端返回总数；可切换页码处理后续记录。
3. 工作台摘要：单个接口失败不应让整个工作台变成空状态。
4. 操作令牌：填写令牌并回到页面后，令牌提示应刷新。

#### 本次修改结果

已修改：

- `app/services/govern/flow_gov.py`：`list_pending()` 增加 `parse_level` 参数，在 SQL 层过滤流水级别，并返回过滤后的 total。
- `app/api/routers/govern.py`：`/govern/flow/pending` 增加 `parse_level` 查询参数。
- `frontend/src/api/client.ts`：`listFlowPending()` 支持透传 `parse_level`。
- `frontend/src/pages/GovernView.vue`：流水级别筛选改为后端分页筛选；主数据待审接入 `PagedTable`，支持分页处理全部记录；字段映射确认成功提示改为"已写入规则字典"；操作令牌提示改为可刷新状态，监听 focus 和 storage。
- `frontend/src/pages/GovernHub.vue`：摘要加载改用 `Promise.allSettled`，单个摘要接口失败时，其余成功结果仍展示，并给出局部失败提示。

验证结果：

```text
/api/v1/govern/flow/pending?status=pending -> total=428, items=20
/api/v1/govern/flow/pending?status=pending&parse_level=L3 -> total=4, items=4, levels=['L3']
/api/v1/govern/master/pending?limit=20&offset=20&status=pending -> total=500, items=20
```

测试：

```bash
PYTHONPATH=. pytest tests/test_routes_smoke.py tests/test_map_gov.py tests/test_rule_dict_learning.py tests/test_rule_dict_status.py
```

结果：`24 passed, 1 warning`。

前端构建：

```bash
npm run build
```

结果：`vue-tsc -b && vite build` 通过。Vite 仍提示 `chunk > 500kB`，此为既有打包体积提示。

### 9.8 并行前后端审查补充问题

#### 补充发现

前后端并行只读审查补充确认以下问题：

1. **"规则沉淀"Tab 会同时渲染"库存对账"面板**：根因是 `rulelearn` 是独立 `v-if`，后面的 `map/master/flow/reconcile` 是另一条 `v-if/v-else` 链，第二条链的 `v-else` 会命中"库存对账"。
2. **深链未接入**：多处旧入口和业务入口带 query 跳转 `/govern?tab=`；`GovernHub` 未读取 `route.query.tab`，详情区不会自动展开。
3. **库存对账 total 与 items 口径不一致**：后端返回完整差异总数 total，items 只返回前 200 条；前端标题和导出没有说明"当前只展示/导出前 200 条"。
4. **字段待确认队列也存在固定 `limit=100` 无分页的问题**。
5. **写相邻接口鉴权不完整**：`POST /govern/map/enqueue` 会写 `map_pending`，但未要求操作令牌；`POST /govern/map-suggest` 可能调用模型，建议也按治理操作加令牌。
6. **写 rule_dict 的路径需要统一 schema 兜底**：读路径已经调用 `ensure_rule_dict_schema()`；写路径仍可能在旧库上遇到缺列风险。

#### 修改方案

1. "规则沉淀"与"字段规整"、"物资规整"、"出入库记录处理"、"库存对账"改为互斥渲染。
2. `GovernHub` 读取并监听 `route.query.tab`，合法 Tab 自动展开详情。
3. 字段待确认队列接入 `PagedTable`。
4. 库存对账标题和导出按钮明确"当前展示/导出行数"，避免误解为全量导出。
5. `map-suggest`、`map/enqueue` 增加 `require_ops`。
6. `map-confirm`、`map/pending/confirm`、`rule-learn confirm` 写规则字典前调用 `ensure_rule_dict_schema()`。

#### 验收方式

1. 切到"规则沉淀"，只出现规则学习候选，不出现库存对账。
2. 访问 `/govern?tab=master`，详情自动展开且标题为"处理详情：物资主数据"。
3. 字段待确认超过一页时可以翻页。
4. 库存对账页面明确显示当前展示数量，CSV 按当前展示导出。
5. 未带操作令牌调用 `POST /govern/map/enqueue` 应返回 401。
6. 旧库写规则字典路径不应因缺 `status/updated_at/changed_by` 列返回 500。

#### 本次补充修改结果

已修改：

- `frontend/src/pages/GovernView.vue`："规则沉淀"、"字段规整"、"物资规整"、"出入库记录处理"改为互斥渲染，修复规则沉淀下方误出库存对账的问题；字段待确认队列接入分页；库存对账标题显示"共 N 行，当前展示 M 行"；导出按钮改为"导出当前展示 CSV"，避免误解为全量导出；字段治理写操作按钮在无令牌时禁用。
- `frontend/src/pages/GovernHub.vue`：接入 `route.query.tab`，`/govern?tab=master`、`/govern?tab=flow` 等合法深链会自动展开详情。
- `app/api/routers/govern.py`：`POST /govern/map-suggest`、`POST /govern/map/enqueue` 增加 `require_ops`。
- `app/services/govern/map_gov.py`：`confirm_pending()` 写规则字典前调用 `ensure_rule_dict_schema()`。
- `app/services/govern/rule_learn.py`：`confirm_candidate()` 写规则字典前调用 `ensure_rule_dict_schema()`。
- `tests/test_routes_smoke.py`：更新 map-suggest 鉴权测试。

验证结果：

```text
POST /api/v1/govern/map-suggest 无令牌 -> 401
POST /api/v1/govern/map/enqueue 无令牌 -> 401
POST /api/v1/govern/map-suggest 配置令牌 -> 200
POST /api/v1/govern/map/enqueue 配置令牌 -> 200
```

测试：

```bash
PYTHONPATH=. pytest tests/test_routes_smoke.py tests/test_map_gov.py tests/test_rule_dict_learning.py tests/test_rule_dict_status.py
```

结果：`25 passed, 1 warning`。

构建：

```bash
npm run build
```

结果：`vue-tsc -b && vite build` 通过。Vite 仍提示 `chunk > 500kB`，此为既有打包体积提示。

### 9.9 数据成果页 Top 物资流水展示口径调整

#### 需求

用户要求：

> 数据成果页面，Top 物资流水（IN/OUT）还是以中文物资展示，内部按照资产编码对齐。

#### 当前问题

Top 物资流水（IN/OUT）的数据链路为：

1. 前端组件：`frontend/src/components/FlowAnalytics.vue`
2. 前端接口：`frontend/src/api/client.ts` 的 `flowTop()`
3. 后端接口：`GET /api/v1/analytics/flow-top`
4. 后端服务：`app/services/query/analytics.py`

现状：后端只返回 `material_id`、`flow_type`、`qty`，前端图表 x 轴直接展示 `material_id`。对业务用户来说，`M-...` 这类内部 ID 不直观。前端 Top 排序表达式也存在小错误，出库量没有正确参与总量排序。

#### 修改方案

1. 后端 `flow_top()` 继续按内部编码聚合，保证 IN/OUT 对齐不靠中文名称。
2. 查询 `fact_stock_flow` 后左连接 `dim_material`。
3. 返回字段增加：`material_id`（内部对齐主键）、`asset_code`（展示/对齐编码，优先用 `dim_material.material_code`，为空时回退 `material_id`）、`spec`（规格型号）、`material_name`（中文物资名称）、`display_name`（前端 x 轴中文展示名）。
4. 前端聚合仍以 `asset_code || material_id` 作为 key，不以中文名合并。
5. 前端 x 轴展示 `display_name`。
6. tooltip 中展示中文名、编码、入库量、出库量。
7. 修正 Top 排序表达式，按入库+出库总量排序。

#### 验收方式

1. 请求接口：`GET /api/v1/analytics/flow-top?limit=5`，返回 200。
2. 返回项应同时包含：`asset_code`、`material_id`、`material_name`、`flow_type`、`display_name`、`qty`。
3. 页面图表 x 轴应显示中文物资名称或中文名称+规格。
4. tooltip 应可看到内部编码，确认图表展示名和内部对齐 key 分离。

#### 本次修改结果

已修改：

- `app/services/query/analytics.py`：`/analytics/flow-top` 继续以内部 `material_id` 聚合流水，后左连接 `dim_material`，返回 `asset_code`、`display_name` 等字段。
- `frontend/src/api/client.ts`：优先取 `dim_material.material_code`，为空时回退 `material_id`；`FlowTopItem` 增加中文展示和编码字段。
- `frontend/src/components/FlowAnalytics.vue`：Top 图表内部按 `asset_code/material_id` 聚合；tooltip 展示完整中文名和内部编码；x 轴展示中文 `display_name`，长名称做短截断；修正 Top 排序，按入库+出库总量排序。

接口验证结果示例：

```text
GET /api/v1/analytics/flow-top?limit=5 -> 200
material_id=M-6ae1956bab9d-46
material_name=光缆
asset_code=M-6ae1956bab9d-46
flow_type=IN
display_name=光缆·山泽G1-2410024芯单模室内束状软光缆9/125100米/卷黄色（卷）
qty=200.0
```

测试与构建：

```bash
PYTHONPATH=. pytest tests/test_routes_smoke.py
npm run build
```

结果：`14 passed, 1 warning`；构建通过。

### 9.10 数据成果页流水分析图表字体重叠

#### 问题现象

用户反馈数据成果页中流水分析图表存在字体重叠：

1. 出入库按月趋势图：x 轴月份、图例、tooltip 在窄宽度下容易挤在一起。
2. Top 物资流水图：中文物资名较长，x 轴标签旋转后与图例/坐标轴区域重叠。
3. 发布级别占比图：饼图外部标签与底部图例重叠。

#### 根因

1. `FlowAnalytics.vue` 三个图共用较紧的图表高度。
2. ECharts `grid.bottom` 预留空间不足。
3. Top 图 x 轴中文标签变长后，原来的 `rotate + fontSize` 不足以避免重叠。
4. 饼图使用外部标签，单项或少项数据时标签容易落到底部图例区域。

#### 修改方案

1. 月趋势图增大底部空间并启用 `containLabel`。
2. Top 图增大底部空间，启用 `hideOverlap`、`interval=0`、固定标签宽度和裁断。
3. Top 图 tooltip 保留完整中文名和编码。
4. 饼图标签改为内部展示，图例保留底部，避免外部 label line 与图例重叠。
5. 适当增加图表高度。

#### 验收方式

1. 打开数据成果页。
2. 查看三个流水分析图：
   - 月趋势月份不应压到图例。
   - Top 物资中文名不应与图例重叠。
   - 发布级别占比标签不应压到底部图例。
3. 鼠标悬浮 Top 图柱子，tooltip 仍应显示完整中文物资名和编码。

#### 本次修改结果

已修改 `frontend/src/components/FlowAnalytics.vue`：

1. 月趋势图：增大 `grid.bottom`，开启 `containLabel`。
2. Top 物资流水图：增大底部空间；x 轴标签缩短到 10 个字符后加省略号、固定标签宽度和截断；tooltip 仍显示完整中文名和编码。
3. 发布级别占比图：饼图中心上移；标签改为扇区内部展示；避免外部 label line 与底部图例重叠。
4. 图表高度：普通图从 280px 调整为 320px；小图从 220px 调整为 240px。

验证：

```bash
npm run build
```

结果：构建通过；ReadLints：`No linter errors found`。

## 10. 风险与注意事项

1. `GovernHub.vue` 直接替换后，可能发现 `api/client.ts` 缺少参考项目用到的类型或函数。不要自己发明接口，先检查目标项目 `api/client.ts` 是否已有：`flowReconcile`、`listFlowPending`、`listMapPending`、`listMasterPending`、`statsOverview`。
2. 已确认目标项目当前没有 `FlowReconcileAssist` 导出，且 `/api/v1/govern/flow/reconcile` 当前返回里没有 `assist` 字段。实施时按第 5.1 节写本地可选类型和兜底，不要为此改后端。
3. 如果函数名不同，只做薄适配，不改后端。
4. 不要删除 `GovernView.vue`，参考项目 `GovernHub.vue` 依赖它。
5. 不要删除 `RowEvidence.vue`，它属于追溯审计。
6. 不要删除 `BlockedDataPanel.vue`，它属于数据成果里的阻塞数据查看。
7. 如果 `npm run build` 报 unused import，优先删除未使用 import，不要改业务逻辑。
8. 如果 `/govern` 页面数据为空，要确认真实数据是否已经填充，不要为了通过页面验收写假数据。

## 11. 完成定义

本任务完成时必须满足：

1. 修改方案本文已存在。
2. 代码实施后，`/govern` 是唯一的数据规整主入口。
3. 独立"治理待办"页面从导航和路由组件中删除。
4. 独立"AI建议审核"页面从导航和路由组件中删除。
5. 旧链接兼容跳转到 `/govern`。
6. `npm run build` 通过。
7. `rg "/todos|/ai-review|治理待办|AI建议审核" frontend/src` 没有非兼容路由残留。
