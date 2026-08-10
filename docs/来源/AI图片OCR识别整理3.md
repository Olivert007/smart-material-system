# 多模型编排优化方案（讨论稿）整理

> **副本位置**：`治理方案/来源/`（供 Docker/Agent 自包含阅读；正式决策以 `../09-多模型编排策略.md` / `../10-模型评测与验收.md` 为准）  
> 来源：宿主机截图 OCR；原始 `ocr_out_ai/*.txt` 不随本目录交付  
> 整理日期：2026-08-08  
> 说明：本文档为截图内容的去重、纠错与结构化整理；OCR 难免有个别错字，已尽量修正（如 1ocal→local、v1lm/v11m→vllm、00M→OOM、阔值→阈值、丨→| 等）。

---

## 1. 优化目标

本方案不以"调用更多模型"为目标，而是让不同能力和成本的模型承担合适的任务，并保证模型失败、冲突或输出非法时不会产生错误的高置信结果。

**优化目标：**

1. 简单、高频、低风险任务优先使用小模型，降低延迟和内存压力。
2. 复杂、低置信、高风险任务升级到主模型。
3. 规则、指标模板和历史资产能够处理的任务不调用生成模型。
4. 模型生成结果必须经过结构、权限和业务规则校验。
5. 普通任务允许服务降级，关键互验禁止用降级结果冒充独立模型结果。
6. 所有调用记录真实模型、制品版本、prompt 版本、证据范围和降级原因。
7. 双模型是否长期常驻由业务评测决定，而不是预设为硬约束。

**非目标：**

- 不让多个模型对每个请求固定轮流生成。
- 不用模型投票代替业务校验或人工确认。
- 不在第一阶段同时常驻三个大生成模型。
- 不把模型自报置信度直接当作执行依据。

## 2. 推荐模型池

### 2.1 常驻模型

| 角色 | 推荐模型 | 主要职责 | 说明 |
|---|---|---|---|
| embed | Qwen3-Embedding-0.6B 或 BAAI/bge-m3 | 表头、指标、主数据、few-shot 候选召回 | 只召回，不直接决策 |
| fast | Qwen/Qwen3.5-9B | 摘要、常规画像、普通映射、简单 SQL | 第二阶段启用 |
| big | Qwen/Qwen3.6-27B-FP8 | 复杂 SQL、低置信修正、质量解释、接入建议 | 主模型候选 |

模型制品必须固定：

- 完整仓库或本地目录标识；
- BF16、FP8、GPTQ 或 GGUF 等格式；
- revision/commit；
- 文件 SHA256 清单；
- 实际加载峰值、稳态内存和评测结果；
- vLLM 和容器镜像版本。

### 2.2 SQL 专项候选模型

`Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8` 作为 A/B 测试候选，与 `Qwen3.6-27B-FP8` 比较复杂 SQL 的执行正确率。初期不与 9B、27B 三大模型同时常驻。测试后只能选择以下一种定位：

1. 替换 big，成为统一主模型；或
2. 在 SQL 专项批处理窗口按需切换；或
3. 评测收益不足，不进入生产模型池。

### 2.3 暂不推荐作为长期模型

| 模型 | 定位 |
|---|---|
| Qwen3-32B-BF16 | 旧一代且内存占用较高，不作为新部署首选 |
| Qwen2.5-7B-Instruct | 已有资产，可用于过渡和基线对照，不作为长期 fast 主选 |
| Qwen3.6-27B-BF16 | 单模型可测试；双模型常驻优先使用官方 FP8 制品 |
| GGUF-Q8_0 | 属于 llama.cpp 路线，不与 vLLM FP8 参数和体积混用 |

## 3. 编排总体架构

```text
业务请求
   ↓
PolicyRouter（确定性规则，不使用 LLM 路由）
   ├─ 规则/指标模板直接处理
   ├─ Embedding 候选召回
   ├─ fast 生成 → 校验 → 低置信/失败 → big 修正
   └─ big 直接生成
   ↓
Schema/SQL/业务规则校验器
   ├─ 可执行
   └─ 待人工 / 拒绝
```

核心组件：

| 组件 | 职责 |
|---|---|
| ModelRegistry | 保存模型角色、端点、制品版本、能力和健康状态 |
| TaskPolicy | 定义每类任务的 primary、升级模型、预算和超时 |
| PolicyRouter | 根据任务类型、复杂度、风险和健康状态选择执行路径 |
| ModelClient | 统一 OpenAI 兼容调用、结构化输出、超时和调用审计 |
| OutputValidator | Pydantic/schema、SQL AST、标识符和动作白名单 |
| ConfidenceScorer | 综合规则命中、召回相似度、校验结果和历史通过率 |
| EscalationEngine | 判断是否从 fast 升级到 big |
| ConflictResolver | 只识别一致、冲突或不可验证；不自动选择冲突侧 |
| CircuitBreaker | 按模型和任务维度熔断，避免重复调用故障端点 |

## 4. 任务路由策略

### 4.1 策略表

```python
TASK_POLICY = {
    "summary":        {"primary": "fast", "escalate": "big",   "risk": "low",    "max_calls": 2},
    "profile":        {"primary": "fast", "escalate": "big",   "risk": "medium", "max_calls": 2},
    "map_headers":    {"primary": "fast", "escalate": "big",   "risk": "medium", "max_calls": 2},
    "sql_simple":     {"primary": "fast", "escalate": "big",   "risk": "medium", "max_calls": 2},
    "sql_complex":    {"primary": "big",  "escalate": None,    "risk": "high",   "max_calls": 2},
    "quality_explain":{"primary": "fast", "escalate": "big",   "risk": "medium", "max_calls": 2},
    "ingest_plan":    {"primary": "big",  "escalate": None,    "risk": "high",   "max_calls": 1},
}
```

- `max_calls` 是单次业务任务的生成调用上限，不包含 embedding。
- 结构化输出解析失败最多允许同模型修复一次；达到预算后转人工，不允许无限重试。

### 4.2 路由优先级

```text
规则/模板命中
  > 历史确认资产
  > Embedding 唯一候选
  > big
  > fast
  > 人工
```

- 模型不能覆盖明确的人工确认规则。
- Embedding 高相似候选只能预填，是否允许自动采用由任务风险决定；业务写入配置仍经过 staging confirm。

## 5. 分场景编排

### 5.1 表头映射

```text
原始表头 + sheet 上下文
   ↓
规则字典：精确/归一化/业务域匹配
   ├─ 未命中
   ↓
Embedding：召回 Top-K 历史确认映射
   ├─ 唯一高相似候选 → 预填 + 标记来源
   └─ 无候选/多候选 → fast 输出结构化建议
   ↓
std_field 白名单校验
   ├─ 高综合置信          → staging
   ├─ 低置信/冲突          → big 完整修正 → staging + 人工确认
```

发送给模型的上下文应包含：表头、相邻表头、sheet 角色、样本值、业务域、Embedding 候选及来源。不得只发送孤立列名。

### 5.2 Text2SQL

```text
用户问题
   ↓
指标名/别名/历史问法匹配
   ├─ 命中唯一指标 → SQL 模板填参 → AST 校验 → 返回结果
   └─ 未命中 → 复杂度分类
        ├─ simple → fast
        └─ complex → big
   ↓
AST + 表列函数白名单 → 只读 dry-run
   ├─ 通过 → 数值口径校验 → 返回结果
   └─ 失败/异常 → fast 结果升级 big 修正
```

复杂度信号：

- JOIN、子查询、窗口函数、排名、占比、环比；
- 涉及两张及以上业务表；
- 时间范围或时间粒度推断；
- 指标匹配存在多个候选；
- 历史同类 SQL 通过率低；
- 问题中的业务实体无法唯一映射到 schema；
- 用户明确要求审计级或关键口径结果。

模型一致不等于 SQL 正确。最终判据以 AST、只读执行、指标口径和业务测试为准。

### 5.3 新文件接入

```text
文件
   ↓
规则解析 + Workbook/Sheet Profile + 全量统计
   ↓
Embedding 匹配历史格式指纹和确认配置
   ├─ 高置信复用 → staging 对照，不直接发布
   └─ 常规新格式 → fast：角色/表头/区域建议
        ├─ 校验通过 → staging
        ├─ 低置信 → big 完整修正版
        └─ 多级表头/区域堆叠/schema drift → big
   ↓
配置 schema + 动作白名单 → staging → confirm
```

模型只读取表头、头中尾样本、规则统计和异常摘要，不读取全量数据。全量清洗、质量统计和发布由规则引擎完成。

### 5.4 数据质量解释

```text
DuckDB 全量计算确定性指标
   ├─ 空值率、重复率、主键冲突
   ├─ 汇总与明细差异
   ├─ 数量/金额范围、单位异常
   └─ 数据分布漂移
   ├─ fast 生成普通中文说明
   └─ 严重异常/多种可能原因/涉及发布阻断 → big 生成解释与治理建议
```

模型不负责计算质量数值，也不能改变质量 gate 的规则结论。

## 6. 置信度与升级机制

### 6.1 综合置信度

不直接使用模型输出的 `confidence`，建议综合分数：

| 因子 | 权重 |
|---|---|
| 规则命中质量 | 30% |
| Embedding 相似度 | 20% |
| Schema/白名单校验 | 20% |
| 历史同类通过率 | 15% |
| 上下文完整度 | 10% |
| 模型自报置信度 | 5% |

具体权重通过历史确认数据校准，不在编码中写死为永久业务规则。

### 6.2 升级条件

满足任一条件即从 fast 升级到 big：

1. 综合置信度低于阈值；
2. schema、枚举或 SQL AST 校验失败；
3. 存在多个同等级候选；
4. sheet 存在多区域、多级表头或结构漂移；
5. SQL 涉及多表、复杂聚合或指标歧义；
6. 结果触发数值或质量异常；
7. 任务被标记为高风险；
8. 历史同类型任务的人工修正率超过阈值。

### 6.3 big 的输入

big 不应只看到 fast 的答案，应同时收到：

- 原始问题或证据摘要；
- fast 输出及校验错误；
- 候选规则和指标定义；
- 要求输出的完整 schema；
- 明确指令：输出完整修正版，不输出增量补丁。

## 7. 级联、互验与降级

### 7.1 推荐级联

```text
fast 草稿 → big 审查并输出完整最终稿 → 确定性校验器
```

取消"7B 初稿 → 27B 复审 → 7B 定稿"。小模型不应在最后一步重写大模型的修正结果。

### 7.2 独立互验

互验只用于少量关键任务。两侧必须独立调用指定模型：

```text
fast（禁止 fallback） → 结构化比较 → 一致/冲突/不可验证
big（禁止 fallback）
```

规则：

- 任一模型不可用：`unverified`；
- 输出结构非法：`invalid`，不能参与一致性判断；
- 两侧冲突：进入人工，不按模型大小自动选择；
- 两侧一致：仍需确定性校验，不直接获得执行权；
- 审计记录真实 model_id、revision 和调用端点。

### 7.3 普通任务降级

| 原任务 | 故障 | 处理 |
|---|---|---|
| big 摘要/解释任务 | big 不可用 | 可转 fast，标记 `degraded_down` |
| fast 低风险任务 | fast 不可用 | 可转 big，标记 `degraded_up` |
| big 复杂 SQL | big 不可用 | fast 可生成候选，但必须 `needs_confirm=true` |
| big 接入决策 | big 不可用 | 规则结果 + 待人工，不自动发布 |
| 独立互验 | 任一不可用 | `unverified`，禁止 fallback |

降级用于维持服务，不得提升结果置信等级。

## 8. 模型状态和调用审计

### 8.1 模型实例状态

```text
loading → configured → ready → degraded → unreachable → circuit_open → stopping
```

### 8.2 单次调用状态

```text
not_invoked / ok / degraded_up / degraded_down / timeout / transport_failed
/ output_invalid / policy_blocked / conflict / unverified / quota_exhausted
```

### 8.3 llm_call 建议字段

| 字段 | 说明 |
|---|---|
| call_id / trace_id | 单次调用与业务链路标识 |
| task_type / mode | 任务类型与 direct/cascade/verify |
| requested_role / actual_role | 请求角色与实际角色 |
| model_id / model_revision | 真实模型制品 |
| endpoint | 实际端点 |
| prompt_version | prompt 版本 |
| evidence_digest | 模型看到的证据摘要 |
| input_tokens / output_tokens | token 数量 |
| latency_ms | 调用延迟 |
| status / fallback_reason | 状态与原因 |
| schema_valid | 输出是否通过结构校验 |
| created_at | 时间戳 |

审计日志不默认保存完整敏感 prompt；可保存脱敏摘要和内容哈希。需要问题回放时，将受控原文放在独立审计存储并设置保留期。

## 9. 推理引擎策略

### 9.1 默认引擎

第一选择为标准 vLLM，原因是：

- 支持 OpenAI 兼容 API；
- 具备连续批处理和结构化输出能力；
- 适合 API 与批量任务并发；
- 支持 FP8 safetensors 路线；
- 当前应用编排接口改动较小。

当前业务没有音频、视频生成需求，原则上不要求 vLLM-Omni。若继续复用 `vllm-omni` 镜像，应只使用标准模型服务能力，并单独验证 Qwen3.5/Qwen3.6、FP8、aarch64 和结构化输出。

### 9.2 对照引擎

| 引擎 | 进入对照测试的条件 |
|---|---|
| SGLang | 大量请求共享 schema、指标和 few-shot 前缀，需要测试前级缓存收益 |
| llama.cpp | 并发长期为 1，双模型常驻内存压力高，考虑 GGUF Q6/Q8 路线 |
| TensorRT-LLM | 模型已固定且需要进一步压榨 NVIDIA 平台性能 |

引擎选择使用同一业务评测集和相同输出约束比较，不能只比较 tokens/s。

## 10. DGX Spark 初始资源预算

以下参数只作为首轮压测起点：

| 服务 | 初始建议 |
|---|---|
| Embedding | 独立小服务，低并发；约 1-2GB 量级，以实测为准 |
| max-model-len | 8192 |
| max-num-seqs | 每个生成实例从 1 开始 |
| 模型调用并发 | 全局从 2 开始，fast/big 各 1 |
| 文件分析并发 | 从 1 开始 |

128GB 为统一内存，必须给操作系统、容器、DuckDB、Excel 解析、Parquet 和 page cache 留出空间。验收至少记录：

1. 空载；
2. 单 big；
3. fast + big 双常驻；
4. 双模型同时生成；
5. 双模型生成并行处理百万行文件；
6. 连续运行 24 小时。

若双常驻导致内存或延迟不可接受，降级策略为：

1. 保留 big 单模型；
2. Embedding 放 CPU 或按需运行；
3. fast 改为按需启动，或取消 fast；
4. 不优先通过降低主模型量化质量来维持形式上的多模型。

## 11. 分阶段落地

### Stage 1：单主模型基线

- 常驻 big 和 Embedding；
- 所有生成任务先由 big 处理；
- 完成统一调用、结构校验、审计、熔断和业务评测；
- 暂不实现级联和互验。
- 目的：得到准确率、延迟和内存基线，先验证数据闭环。

### Stage 2：加入 fast 路由

- 部署 Qwen3.5-9B；
- 只迁移摘要、常规画像和普通映射；
- 对比迁移前后的准确率、人工修正率和延迟；
- 开启 fast → big 升级，不开启固定双模型调用。

### Stage 3：关键任务互验

- 验证 unverified、冲突和模型故障状态；
- 只对经过业务确认的少量高风险任务启用独立互验；
- 统计互验发现的真实错误数与新增人工工作量。

### Stage 4：SQL 专项 A/B

- 用 Qwen3-Coder-30B-A3B-Instruct-FP8 替换式测试 big；
- 根据复杂 SQL 执行正确率决定是否替换或放弃；
- 不与 27B 同时常驻作为常规生产配置。

## 12. 评测与验收

### 12.1 业务评测集

| 类型 | 最低规模 |
|---|---|
| 简单单表查询 | 50 |
| 多表、时间、排名、占比查询 | 50 |
| 指标口径歧义问题 | 20 |
| 多级表头、区域堆叠、异常格式 | 20 个文件 |
| 常规文件表头/角色识别 | 30 个文件 |
| 主数据候选匹配 | 100 组 |
| 模型不可用、超时、非法 JSON | 每类至少 10 个故障用例 |

### 12.2 核心指标

- SQL 执行正确率，而非仅语法合法率；
- 指标口径正确率；
- 表头映射 precision/recall；
- 文件角色和区域识别准确率；
- 人工介入率和人工修正率；
- p50/p95 延迟；
- 峰值统一内存；
- 降级、冲突和伪高置信结果数量；
- 每业务任务生成调用次数。

### 12.3 启用双模型的门槛

只有同时满足以下条件才长期启用 fast + big：

1. fast 承接目标任务后，整体 p95 延迟有明确下降；
2. 人工修正率没有超过约定阈值；
3. fast → big 升级能够覆盖大部分低质量结果；
4. 双常驻不影响百万行文件处理和系统稳定性；
5. 24 小时运行无 OOM、锁死或模型端点频繁重启。

互验只有在"发现的真实错误收益"高于"新增调用和人工冲突处理成本"时保留。
