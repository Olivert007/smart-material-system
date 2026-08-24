# 问数助手 Vanna 接入执行方案

> **识别说明**：本文件由文件夹 `19/` 中 7 张截图 OCR 识别并整理而成。
> 问数助手第一阶段接入 VannaAI 作为外部 NL2SQL 引擎：决策、目标、vLLM 影响、代码落点、配置、接口、训练、实施步骤与验收标准。

---

> 状态：执行中。**Step1 已完成**（2026-08-24）。结论：第一阶段只接 **VannaAI**。

## Step1 实施记录（2026-08-24）

已完成：

- `app/services/query/ask_engine.py` — `AskEngineResult` + `get_ask_engine()`
- `app/services/query/legacy_text2sql_engine.py` — 原 big 模型 text2sql + repair
- `app/config.py` — `ASK_ENGINE` / `VANNA_PERSIST_DIR` / `VANNA_AUTO_TRAIN`
- `app/services/query/text2sql.py` — 指标模板 → AskEngine → 守卫 → 执行 → 总结
- `tests/test_ask_engine_legacy.py` — Step1 单元测试

验收（34 passed）：

```bash
PYTHONPATH=. python3 -m pytest tests/test_ask_engine_legacy.py \
  tests/test_routes_smoke.py tests/test_phase_a_accept.py \
  tests/test_metric_template_ask.py tests/test_ask_degraded.py tests/test_ask_insights.py
```

`ASK_ENGINE=vanna` 暂仍走 legacy（Step2 接入 VannaEngine + 回退）。

---

## 1. 决策

选择 VannaAI 作为问数助手的第一阶段外部 NL2SQL 引擎。

不选择：WrenAI、DB-GPT、Chat2DB、直接换 DuckDB-NSQL/SQLCoder。

## 2. 目标

```
指标模板 + Vanna 引擎生成 SQL + 现有 SQL 守卫 → DuckDB 查询 → 当前前端展示
```

保留 `/api/v1/ask`，不替换前端，不引入 Vanna WebUI。

## 3. 不做什么

- 不允许 Vanna 直接执行 SQL
- 不绕过 `validate_readonly_sql()`
- 不替换 `AskView.vue` 主 UI
- 指标模板仍可离线回答

## 4. 对 vLLM 的影响

- vLLM 仍是推理服务；Vanna 通过 `model_client.chat` 适配（Step2）
- `ASK_ENGINE` 默认 `legacy`
- embed 复用 `LLM_EMBED_ENDPOINT`（:8002）
- 单次 Vanna 生成 + 失败回退 legacy；保留熔断

## 5. 代码落点

### 5.1 新增文件

| 文件 | 状态 |
|------|------|
| `app/services/query/ask_engine.py` | ✅ Step1 |
| `app/services/query/legacy_text2sql_engine.py` | ✅ Step1 |
| `app/services/query/vanna_engine.py` | Step2 |
| `scripts/train_vanna_ask.py` | Step3 |
| `tests/test_ask_engine_vanna_fallback.py` | Step2 |
| `tests/test_ask_engine_legacy.py` | ✅ Step1 |

### 5.2 已修改

- `app/config.py` — 三项环境变量
- `app/services/query/text2sql.py` — 接入 AskEngine

## 6. 配置

```python
ASK_ENGINE = os.environ.get("ASK_ENGINE", "legacy")  # legacy | vanna
VANNA_PERSIST_DIR = os.environ.get("VANNA_PERSIST_DIR", str(DATA / "vanna"))
VANNA_AUTO_TRAIN = os.environ.get("VANNA_AUTO_TRAIN", "1") == "1"
```

## 7. 接口设计

AskEngine 只生成候选 SQL；`text2sql._ask` 负责守卫、执行、总结。

流程：空问题 → 指标模板 → `AskEngine.generate_sql` → `validate_readonly_sql` → DuckDB → 返回。

## 8. Vanna 训练内容（Step3）

schema summary、active 指标、SCHEMA_ZH、sql_fewshot、10–20 条领域样例。

## 9. 实施步骤

### Step1：引入可切换 AskEngine ✅

- AskEngine 接口 + legacy 实现
- `ASK_ENGINE=legacy` 行为不变

### Step2：接入 VannaEngine，但默认关闭

- 安装 vanna 依赖
- `ASK_ENGINE=vanna` 时调用 Vanna，失败回退 legacy

### Step3：训练 Vanna 上下文

### Step4：前端标注来源

### Step5：真实问题对比（`data/eval/results/ask_engine_compare.json`）

## 10. 成功标准

指标模板不调 LLM；Vanna 不可用不崩；SQL 全过守卫；前端显示来源；不影响接入/规整/发布。

## 11. Agent 执行提示

```
只执行 docs/19-问数助手Vanna接入执行方案.md 的 Step2。
不要一次做完 Step2 到 Step5。
```
