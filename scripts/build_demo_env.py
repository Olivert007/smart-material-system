# -*- coding: utf-8 -*-
"""参赛演示环境构建与自检：把脱敏演示台账灌入干净 DATA_DIR 并跑通全链路。

用法（系统 python3，依赖齐备）:
    DATA_DIR 由脚本固定为 demo_data/runtime（每次运行先清空重建）。
    python3 scripts/build_demo_env.py

输出：fact_inventory / fact_stock_flow 发布摘要、flow_pending，
可用于「成果样例（附页）」与演示走查核对。

注意：脚本默认关闭 LLM 兜底（FLOW_LLM_ENABLED=0），纯规则路径；
录演示视频时若本地模型在线，可去掉该环境变量以展示模型 API 建议。
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEMO = ROOT / "demo_data"
RUNTIME = DEMO / "runtime"
SAMPLE = DEMO / "samples" / "通信部成都区域ZW物资汇总表（新模板单独）.xlsx"

if RUNTIME.exists():
    shutil.rmtree(RUNTIME)
os.environ["DATA_DIR"] = str(RUNTIME)
os.environ["OPS_TOKEN"] = "demo-ops"
os.environ["ALLOW_FREE_QUERY"] = "1"
os.environ["WORKER_POLL_SEC"] = "0.3"
os.environ["SPARSE_EVIDENCE_ROWS"] = "5000"
# 纯规则路径自检：关闭 LLM 兜底与 embed 建议（本地模型不参与本次自检）
os.environ["FLOW_LLM_ENABLED"] = "0"
os.environ["EMBED_FALLBACK_LEXICAL"] = "1"

from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def wait_task(client: TestClient, task_id: str, timeout: float = 300) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        t = client.get(f"/api/v1/tasks/{task_id}").json()
        if t.get("status") in ("done", "failed"):
            return t
        time.sleep(0.3)
    raise TimeoutError(f"task {task_id} timeout")


def main() -> int:
    assert SAMPLE.exists(), f"缺失脱敏样例: {SAMPLE}"
    headers = {"X-Ops-Token": "demo-ops"}
    with TestClient(app) as client:
        with SAMPLE.open("rb") as f:
            r = client.post(
                "/api/v1/files",
                files={"file": (SAMPLE.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert r.status_code == 202, r.text
        body = r.json()
        file_id, task_id = body["file_id"], body.get("task_id")
        print("upload:", file_id, "task:", task_id)

        t = wait_task(client, task_id)
        print("analyze task:", t.get("status"), t.get("progress"), t.get("message", ""))
        assert t.get("status") == "done", t
        result = t.get("result") or {}
        steps = result.get("steps") or {}
        for k, v in steps.items():
            if isinstance(v, dict):
                print(f"  step[{k}]:", {kk: vv for kk, vv in v.items() if not isinstance(vv, (list, dict))})
        print("  next_actions:", result.get("next_actions"))

        # 域1：inventory（维护材料/备品备件/应急备汛物资）
        s = client.post(
            f"/api/v1/intake/stage/{file_id}",
            json={"config_version": "v1", "target_domain": "inventory"},
        )
        assert s.status_code == 200, s.text
        stg = s.json()
        print("staging[inventory]:", {k: stg.get(k) for k in ("status", "clean_rows", "version")})
        dry = stg.get("dry_run") or {}
        print("  dry_run.column_mapping:", (dry.get("column_mapping") or {}).get("mapped_count", "-"))
        assert stg["status"] == "STAGED", stg

        c = client.post(
            f"/api/v1/intake/stage/{file_id}/confirm",
            headers={**headers, "Idempotency-Key": "demo-inv"},
            json={"version": stg["version"], "expected_status": "STAGED"},
        )
        assert c.status_code == 200, c.text
        cf = c.json()
        print("release[inventory]:", {k: cf.get(k) for k in ("target_table", "rows")})
        assert cf.get("target_table") == "fact_inventory", cf

        # 域2：stock_flow（出入库流水，维护材料/备品备件）
        s2 = client.post(
            f"/api/v1/intake/stage/{file_id}",
            json={"config_version": "v1", "target_domain": "stock_flow"},
        )
        assert s2.status_code == 200, s2.text
        stg2 = s2.json()
        dry2 = stg2.get("dry_run") or {}
        print("staging[stock_flow]:", {k: stg2.get(k) for k in ("status", "clean_rows", "version")})
        print("  dry_run.flow_parse:", dry2.get("flow_parse"))
        print("  dry_run.flow_pending:", dry2.get("flow_pending"))
        assert stg2["status"] == "STAGED", stg2

        c2 = client.post(
            f"/api/v1/intake/stage/{file_id}/confirm",
            headers={**headers, "Idempotency-Key": "demo-flow"},
            json={"version": stg2["version"], "expected_status": "STAGED", "target_domain": "stock_flow"},
        )
        assert c2.status_code == 200, c2.text
        cf2 = c2.json()
        print("release[stock_flow]:", {k: cf2.get(k) for k in ("target_table", "rows")})
        assert cf2.get("target_table") == "fact_stock_flow", cf2

        # 问数示例（只读查询）
        q = client.post(
            "/api/v1/query",
            headers=headers,
            json={
                "sql": "SELECT location, COUNT(*) AS n, SUM(stock_qty) AS total_qty "
                "FROM fact_inventory GROUP BY location ORDER BY total_qty DESC LIMIT 5"
            },
        )
        assert q.status_code == 200, q.text
        print("query[inventory by location]:", q.json().get("data"))

        q2 = client.post(
            "/api/v1/query",
            headers=headers,
            json={
                "sql": "SELECT flow_type, COUNT(*) AS n, SUM(quantity) AS qty "
                "FROM fact_stock_flow GROUP BY flow_type"
            },
        )
        assert q2.status_code == 200, q2.text
        print("query[flow by type]:", q2.json().get("data"))

        # 治理待确认
        pend = client.get("/api/v1/govern/flow/pending").json()
        print("flow_pending total:", pend.get("total"))

        aud = client.get("/api/v1/audit/events", headers=headers).json()
        if isinstance(aud, dict):
            aud_n = len(aud.get("items") or []) or aud.get("total")
        else:
            aud_n = len(aud or [])
        print("audit events:", aud_n)

    # 补齐趋势分析缺数据板块：区域 / 最低库存 / 资产清查演示行
    # （样例台账没有区域、最低库存列，且资产清查域不在演示管道内，
    #   不补齐则 库存区域分布/低库存TOP/资产三图 无数据）
    import importlib.util

    _spec = importlib.util.spec_from_file_location(
        "backfill_demo_analytics", ROOT / "scripts" / "backfill_demo_analytics.py"
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
    _summary = _mod.backfill_demo_analytics(RUNTIME / "material.duckdb")
    print("backfill[analytics]:", _summary)
    print("DEMO_ENV_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
