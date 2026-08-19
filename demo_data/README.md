# 演示数据与一键复现

本目录用于**脱敏演示**：样例台账在 `samples/`，运行库在 `runtime/`（不纳入 git，每次可重建）。

## Pull 后复现步骤

```bash
# 1. 依赖
pip3 install -r requirements.txt
cd frontend && npm install && npm run build && cd ..

# 2. 重建演示库（约 1–3 分钟，纯规则路径，无需 vLLM）
export PYTHONPATH=$(pwd)
python3 scripts/build_demo_env.py
# 成功末尾应打印 DEMO_ENV_OK

# 3. 用演示库启动 API
export DATA_DIR=$(pwd)/demo_data/runtime
export OPS_TOKEN=demo-ops
export ALLOW_FREE_QUERY=1
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

浏览器打开 http://127.0.0.1:8010 ，设置页填写 Ops Token：`demo-ops`。

## 样例文件

| 文件 | 用途 |
|---|---|
| `通信部成都区域ZW物资汇总表（新模板单独）.xlsx` | `build_demo_env.py` 默认灌库输入 |
| `演示用物资台账（脱敏样例）.xlsx` | 小体积合成样例 |
| `演示用物资台账（脱敏样例·通信物资）.xlsx` | 由 `build_desensitized_sample.py` 生成的精简脱敏版 |

## 相关脚本

- `scripts/build_demo_env.py` — 灌库 + 库存/流水双域发布 + 问数自检
- `scripts/build_desensitized_sample.py` — 可选：从样例或 `RAW_SAMPLE` 重生成脱敏 xlsx
- `scripts/build_demo_data.py` — 可选：合成小样例台账

## 注意

- `runtime/`、`demo_stats.json` 为本地生成物，已在 `.gitignore` 中忽略。
- 演示走规则路径时脚本会设 `FLOW_LLM_ENABLED=0`；若需展示大模型建议，启动 vLLM 后去掉该限制即可。
