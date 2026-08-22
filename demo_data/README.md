# 演示数据（本地）

本目录用于本地演示环境。**样例台账不入 git**（涉密/内网原件请仅保存在本机 `samples/`）。

| 路径 | 说明 |
|---|---|
| `samples/` | 本地放置演示用 xlsx（已 `.gitignore`） |
| `runtime/` | `build_demo_env.py` 生成的运行库（已 `.gitignore`） |

## 复现步骤

```bash
# 1. 将本地脱敏台账放入 samples/，或导出环境变量
export DEMO_SAMPLE=/path/to/your-desensitized-ledger.xlsx

# 2. 依赖与前端
pip3 install -r requirements.txt
cd frontend && npm install && npm run build && cd ..

# 3. 重建演示库（纯规则路径，无需 vLLM）
export PYTHONPATH=$(pwd)
python3 scripts/build_demo_env.py
# 成功末尾应打印 DEMO_ENV_OK

# 4. 启动 API
export DATA_DIR=$(pwd)/demo_data/runtime
export OPS_TOKEN=demo-ops
export ALLOW_FREE_QUERY=1
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

浏览器打开 http://127.0.0.1:8010 ，设置页填写 Ops Token：`demo-ops`。

## 相关脚本

- `scripts/build_demo_env.py` — 灌库 + 双域发布 + 问数自检（读取 `DEMO_SAMPLE` 或 `samples/*.xlsx`）
- `scripts/build_demo_data.py` — 可选：合成虚构小样例台账
- `scripts/build_desensitized_sample.py` — 可选：从 `RAW_SAMPLE` 生成脱敏版（需本地原件）
