# 工作台业务快照整改可执行方案（整理）

> **副本位置**：`治理方案/来源/`（供 Docker/Agent 自包含阅读）  
> 来源：宿主机截图 OCR 识别（rapidocr-onnxruntime）；原始 `AI20260813/ocr_out/*.txt` 不随本目录交付  
> 整理日期：2026-08-13  
> 说明：本文档为截图内容的去重、纠错与结构化整理；OCR 难免有个别错字，已尽量修正（如 1ocal→local、v1lm/v11m→vllm、θ→0、丨→| 等）。截图按拍摄时间前后对应文档逻辑顺序，部分截图存在重复内容，已合并。

---

## 1. 背景

用户在 `bugfix/smart-material-system` 的工作台页面看到一块"业务快照（次级，默认折叠）"区域。截图中该区域展示了库存总量、库存金额、定额利用率、超定额物资、呆滞料行、需求总量、资产台数、入库合计、出库合计，以及按类别、库位、单位的 Top 表格。

当前页面的问题不是"没有数据卡片"，而是：当数据尚未完成规整、发布或可用时，用户看到大量"0"和"-"，不知道这是正常空态、数据未准备好，还是系统异常。

## 2. 本次目标

把工作台首屏改成更符合用户心智的"当前状态 + 下一步动作"。业务快照仍然保留，但必须降级为辅助信息。它只在已有可用业务数据时突出展示；当没有可用数据时，不要展示一堆"0"和"-"干扰用户。

## 3. 本次不做什么

低端 agent 必须严格遵守：

1. 不开发新后端接口。
2. 不改数据库 schema。
3. 不改 `app/services/query/stats_overview.py`：除非现有字段完全无法支持前端判断。
4. 不删除业务快照能力。
5. 不删除治理待办、AI 审核、数据成果、问数助手等入口。
6. 不引入新的 UI 框架或组件库。
7. 不把业务快照改成新的复杂报表页面。
8. 不修改 `smart-material-system` 目录；该目录只作为参考。

## 4. 涉及文件

必须优先检查并修改：

- `frontend/src/pages/HomeView.vue`

可以只读参考：

- `frontend/src/pages/GovernHub.vue`
- `frontend/src/api/client.ts`
- `app/services/query/stats_overview.py`
- `/workspace/vllm-omni/smart-material-system/docs/question/15-数据规整智能协助缺口与整改方案.md`

除非必要，不修改其他文件。

## 5. 当前现状

`HomeView.vue` 当前结构大致如下：

1. 顶部状态提示。
2. "当前数据状态"卡片：展示可用记录、阻塞记录、可用率、待确认字段、待匹配物资、待审核 AI 建议、流水待确认、待办合计、处理后预计释放。
3. "最优先下一步"：展示推荐动作和多个按钮。
4. "最近接入"：展示最近文件。
5. `el-collapse` 中展示"业务快照（次级，默认折叠）"。

问题集中在第 5 部分：

- 标题含有"次级，默认折叠"，这是开发/产品内部语言。
- "0"和"-"没有解释。
- 空数据时仍展示大量指标卡片和空表格。
- 用户无法判断业务快照为空的原因。
- 页面没有强调"业务快照不是当前最该处理的事项"。
- 主数据/库存/资产/需求/流水这组表规模卡与业务指标混在一起，用户会误以为它也是业务快照指标；在宽屏下也容易形成不连续的卡片布局。

## 6. 用户视角判断

用户进入工作台时，第一优先级问题是：

1. 我的数据现在能用吗？
2. 如果不能用，卡在哪里？
3. 我下一步应该处理什么？
4. 处理之后会释放多少数据？
5. 业务指标为什么没有值？

因此首页主信息必须服务这些问题。业务快照只回答"已有业务数据的大概情况"，不能抢占首屏重点。

## 7. 期望页面行为

### 7.1 无数据状态

条件建议：`recent_files.length === 0`，或 `tables` 中核心业务表数量均为 0，且 `quality.blocked_rows === 0` 且 `todos.total === 0`。

页面表现：

- 主按钮只强调"去数据接入"。
- 显示"当前还没有可用业务数据"。
- 不展示业务快照指标卡片。
- 不展示按类别 Top、按库位 Top、按单位 Top。

### 7.2 已上传但未完成规整

条件建议：`recent_files.length > 0`，`quality.clean_rows` 小，且存在待办、阻塞、解析中任务或 staging 未完成迹象。

页面表现：

- 显示"数据正在接入或规整中，业务指标暂不可用"。
- 主按钮优先指向 `nextAction.path` 或 `/todos` 或 `/intake`。
- 业务快照区域显示一条解释，不展示空指标网格。

### 7.3 有阻塞或待办

条件建议：`quality.blocked_rows > 0` 或 `todos.total > 0`。

页面表现：

- 业务快照可以折叠保留。
- 首屏强调阻塞行、待办数、AI 建议数、预计可释放行数。
- 如果业务快照没有有效业务数据，显示解释："完成治理待办并形成可用数据后，这里会展示库存、需求、资产和流水概览。"

### 7.4 已有可用业务数据

条件建议：`quality.clean_rows > 0`，或业务指标中至少一个核心指标有非空值且不是全 0。

页面表现：

- 可以展示业务快照。
- 标题改为"业务数据概览"。
- 指标卡片允许展示 0，但必须能区分"真实 0"与"暂无数据"。
- 副说明写清楚："基于已入库可用候选数据；不等于正式发布报表。"

## 8. 具体改动步骤

### 步骤 1：新增前端计算属性

在 `<script setup>` 中增加只读计算属性。推荐命名：

```ts
hasRecentFiles
hasQualityRows
hasPendingWork
hasAnyBusinessMetric
shouldShowBusinessSnapshot
businessSnapshotEmptyReason
businessSnapshotTitle
businessSnapshotDescription
```

判断逻辑必须简单、可读，不要写复杂嵌套。参考规则：

```ts
const hasRecentFiles = computed(() => recentFiles.value.length > 0)

const hasQualityRows = computed(() => {
  return ((quality.value.clean_rows ?? 0) > 0) || ((quality.value.blocked_rows ?? 0) > 0)
})

const hasPendingWork = computed(() => {
  return (todos.value.total ?? 0) > 0
})

const hasAnyBusinessMetric = computed(() => {
  const b = overview.value?.business
  if (!b) return false
  return [
    b.stock_qty_total,
    b.stock_value_total,
    b.quota_fill_ratio,
    b.stale_count,
    b.over_quota_count,
    b.asset_count,
    b.demand_qty_total,
    b.flow_in_qty,
    b.flow_out_qty,
  ].some((v) => v !== null && Number.isFinite(Number(v)) && Number(v) !== 0)
})
```

注意：如果业务上真实允许全 0 代表有效结果，则 `hasAnyBusinessMetric` 不能作为唯一条件，需要结合 `quality.clean_rows`。

### 步骤 2：改业务快照标题

把：

```vue
<el-collapse-item title="业务快照（次级，默认折叠）" name="biz">
```

改成：

- 有可用数据：`业务数据概览`
- 无可用数据：`业务数据概览（暂无可用数据）`

禁止继续使用："次级"、"默认折叠"、"仅供参考"等词，这些词对用户没有帮助。

### 步骤 3：业务快照空态改为"解释 + 行动"

在业务快照折叠区域内部增加分支：

```ts
shouldShowBusinessSnapshot === true
  // 展示指标卡、Top 表格、趋势、小表卡
shouldShowBusinessSnapshot === false
  // 展示空态解释和行动按钮
```

空态建议文案：

> 当前暂无可用业务数据。请先完成数据接入、字段/单位/物资/流水治理，形成可用候选数据后，这里会展示库存、需求、资产和流水概览。

按钮建议：

- 如果 `nextAction.path` 存在：按钮文案用 `nextAction.label`。
- 否则：
  - 有文件或待办："处理治理待办"，跳 `/todos`。
  - 无文件："去数据接入"，跳 `/intake`。

### 步骤 4：减少首屏按钮噪音

"最优先下一步"当前有多个并列按钮：治理待办、AI建议审核、数据规整、查看数据成果、问数助手。这会削弱"最优先"的含义。

建议：

- 保留一个主按钮：`nextAction.label`（或"治理待办"）。
- 保留最多两个次按钮："查看数据成果"、"问数助手"。
- "AI建议审核"只在 `aiSuggestionPending` 时显示，不作为默认下一步，除非已有可用数据。
- 不要删除这些路由，只调整显示条件。

### 步骤 5：业务指标显示规则

修改 `fmt` 或新增 `fmtBusinessMetric`。

目标：

- 未准备好（后端返回 `null` 或 `undefined`）：显示"暂无"。
- 真实数字 0：在已有可用数据时显示 0。

建议不要全局改 `fmt`，避免影响其他区域。新增：

```ts
function fmtBusinessMetric(v: unknown) {
  if (!shouldShowBusinessSnapshot.value) return '暂无'
  return fmt(v)
}
```

然后业务快照卡片使用 `fmtBusinessMetric`。

### 步骤 6：Top 表格空态文案

把业务快照内部 Top 表格的 `empty-text="无"` 改成用户能理解的文案。建议：

- 暂无可用分类数据
- 暂无可用库位数据
- 暂无可用单位数据

如果 `shouldShowBusinessSnapshot === false`，整个 Top 表格区域不展示。

### 步骤 7：保留默认折叠

`bizOpen` 继续默认为空数组，不要让业务快照默认展开。原因：工作台首屏应优先展示状态、待办、下一步。业务快照是辅助判断，不是当前主流程。

### 步骤 8：移除业务快照内的表规模卡

业务快照内部不要再展示：主数据、资产、库存、需求、流水。

原因：

1. 这组卡展示的是底层表规模，不是业务经营指标。
2. 它和上方库存、需求、资产、流水业务指标容易混淆。
3. 它在宽屏下只有 5 个小卡，视觉上不连续，看起来不像自适应布局。
4. 工作台用户更关心"能不能用、卡在哪里、下一步做什么"，不关心底层表行数。

处理方式：

- 删除 `HomeView.vue` 业务快照里的 `tableCards` 渲染区域。
- 不删除后端 `tables` 字段；它可以留给系统页、调试页或后续诊断使用。
- 如果 `tableCards` 计算属性只服务这个区域，也一并删除。
- 不把这组卡挪到首屏，避免继续制造重复信息。

## 9. 建议最终页面顺序

`HomeView.vue` 页面顺序保持：

1. 顶部状态提示。
2. 当前数据状态卡片。
3. 最优先下一步。
4. 最近接入。
5. 业务数据概览，默认折叠。

- 不要把业务快照移动到顶部。
- 不要在业务快照中展示底层表规模卡。

## 10. 文案规范

使用业务用户能理解的文案。推荐：

- 当前暂无可用业务数据
- 完成规整后展示业务概览
- 基于可用候选数据，不等于正式发布报表
- 处理治理待办
- 审核AI建议

禁止：

- 次级
- 默认折叠
- `debug`、`NaN`、内部口径、`null`、`undefined` 等技术词汇

## 11. 验收标准

### 验收 1：无数据

准备状态：无上传文件、无 staging、无业务表数据。

期望：

- 页面主行动是"去数据接入"。
- 业务快照不展示一堆"0"或"-"。
- 业务快照区域说明为什么暂无业务数据。

### 验收 2：有文件但未规整

准备状态：存在最近接入文件、没有可用业务数据。

期望：

- 页面提示数据仍需接入/规整。
- 业务快照不展示空表格。
- 主行动指向接入、规整或待办。

### 验收 3：有待办/阻塞

准备状态：`todos.total > 0` 或 `quality.blocked_rows > 0`。

期望：

- 首屏能看到待办数量、阻塞行数、预计可释放行数。
- 业务快照继续默认折叠。
- AI建议审核只在 AI 建议数量大于 0 时出现。

### 验收 4：已有可用数据

准备状态：`quality.clean_rows > 0`，或至少一个业务指标有有效值。

期望：

- 业务快照可以展开查看。
- 标题是"业务数据概览"。
- 指标可以正常显示 0。
- 空 Top 表格显示明确文案，不显示单字"无"。

## 12. 测试命令

在 `/workspace/vllm-omni/bugfix/smart-material-system` 下执行。

后端 smoke：

```bash
pytest tests/test_routes_smoke.py
```

前端类型检查：

```bash
cd frontend && npm run type-check
```

如果项目没有 `type-check` 脚本，则执行：

```bash
cd frontend && npm run build
```

手工检查：

1. 打开首页 `/`。
2. 无数据时没有大面积 0/-。
3. 展开业务快照后空态解释清楚。
4. 有待办时下一步按钮明确。
5. 有可用数据时业务指标正常展示。
6. 业务快照默认折叠。

## 13. 失败处理

如果前端编译失败：

1. 优先检查新增计算属性是否引用了未定义变量。
2. 检查模板里是否访问了 `.value`；模板中不需要 `.value`。
3. 不要通过删除业务快照来绕过错误。

如果页面显示空白：

1. 打开浏览器控制台查看 Vue 模板错误。
2. 回退最近一次模板分支改动。
3. 保留原有 `load()`、`statsOverview()`、`flowMonthly()` 调用逻辑。

如果用户仍然看到大量 0 和 -：

1. 检查 `shouldShowBusinessSnapshot` 是否只控制了部分区域。
2. 确认业务指标卡、Top 表格、tableCards 都在同一个展示分支内。
3. 确认空态分支没有继续渲染旧卡片。

## 14. 完成定义

本任务完成必须同时满足：

1. `HomeView.vue` 中业务快照标题不再出现"次级，默认折叠"。
2. 无可用业务数据时，不显示业务指标卡片网格。
3. 无可用业务数据时，有明确解释和下一步按钮。
4. 有可用业务数据时，业务快照仍可展开查看。
5. 治理待办和 AI 审核入口没有丢失。
6. 业务快照中不再出现主数据/库存/资产/需求/流水表规模卡。
7. 前端构建或类型检查通过。
8. 后端 smoke 测试通过，或明确说明失败原因与本次改动无关。
