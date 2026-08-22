#!/usr/bin/env python3
"""B2 — harden real 305B / ZW ledgers through stock_flow rule path (docs/12)."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "tests" / "sandboxes" / "test_flow_harden"
SAMPLES = [
    Path("/workspace/2026-07/305-CYPC-305-002362-2026-1-B-1.XLSX"),
    Path("/workspace/2026-07/通信部成都区域ZW物资汇总表 (新模板单独）.xlsx"),
]

if TEST_DATA.exists():
    shutil.rmtree(TEST_DATA)
os.environ["DATA_DIR"] = str(TEST_DATA)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["ALLOW_FREE_QUERY"] = "1"
os.environ["WORKER_POLL_SEC"] = "0.3"

from app.main import app  # noqa: E402
from app.services.intake.evidence import load_stock_flow_tabular  # noqa: E402


def _wait_task(client: TestClient, task_id: str | None, timeout: float = 600) -> dict:
    if not task_id:
        return {"status": "done"}
    t0 = time.time()
    last = {}
    while time.time() - t0 < timeout:
        last = client.get(f"/api/v1/tasks/{task_id}").json()
        if last.get("status") in ("done", "failed"):
            return last
        time.sleep(0.5)
    return last


def main() -> None:
    missing = [str(p) for p in SAMPLES if not p.exists()]
    if missing:
        raise SystemExit(f"sample missing: {missing}")

    # Preflight: multi-sheet loader sees expected sheets
    pre = {}
    for p in SAMPLES:
        df = load_stock_flow_tabular(p)
        sheets = sorted(df["sheet"].dropna().unique().tolist()) if len(df) and "sheet" in df.columns else []
        pre[p.name] = {"rows": int(len(df)), "sheets": sheets}
        print("preflight", p.name, pre[p.name])
        assert len(df) > 0, p
        assert "flow_in_text" in df.columns or "flow_out_text" in df.columns

    headers = {"X-Ops-Token": "test-ops"}
    results = []
    with TestClient(app) as client:
        for p in SAMPLES:
            item: dict = {"file": p.name, "ok": False}
            with p.open("rb") as f:
                r = client.post(
                    "/api/v1/files",
                    files={
                        "file": (
                            p.name,
                            f,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    },
                )
            item["upload_status"] = r.status_code
            assert r.status_code == 202, r.text
            body = r.json()
            file_id, task_id = body["file_id"], body.get("task_id")
            item["file_id"] = file_id
            t = _wait_task(client, task_id)
            item["task"] = t.get("status")
            assert t.get("status") == "done", t

            s = client.post(
                f"/api/v1/intake/stage/{file_id}",
                json={"config_version": "v1", "target_domain": "stock_flow"},
            )
            item["stage_status"] = s.status_code
            stg = s.json()
            item["staging"] = {
                k: stg.get(k) for k in ("status", "version", "clean_rows")
            }
            item["flow_parse"] = (stg.get("dry_run") or {}).get("flow_parse")
            item["flow_pending"] = (stg.get("dry_run") or {}).get("flow_pending")
            item["column_mapping"] = (stg.get("dry_run") or {}).get("column_mapping")
            assert stg.get("status") == "STAGED", stg
            assert int(stg.get("clean_rows") or 0) >= 1, stg

            c = client.post(
                f"/api/v1/intake/stage/{file_id}/confirm",
                headers={**headers, "Idempotency-Key": f"harden-flow-{file_id}"},
                json={"version": stg["version"], "expected_status": "STAGED"},
            )
            item["confirm_status"] = c.status_code
            cf = c.json()
            item["rows"] = cf.get("rows")
            item["target_table"] = cf.get("target_table")
            item["release_id"] = (cf.get("release") or {}).get("release_id")
            assert c.status_code == 200, c.text
            assert cf.get("target_table") == "fact_stock_flow"
            assert int(cf.get("rows") or 0) >= 1
            item["ok"] = True
            results.append(item)
            print(json.dumps(item, ensure_ascii=False))

        stats = client.get("/api/v1/govern/flow/stats").json()
        aud = client.get("/api/v1/govern/flow/audit", headers=headers).json()
        year_qty = sum(
            1
            for s in aud.get("suspicious") or []
            if "year_as_quantity" in (s.get("reasons") or [])
        )
        base = client.get("/api/v1/govern/flow/baseline").json()

        # sheet coverage
        sheets = sorted(
            {
                r.get("source_sheet")
                for r in stats.get("by_source_sheet") or []
                if r.get("source_sheet")
            }
        )
        summary = {
            "ok_cases": sum(1 for r in results if r.get("ok")),
            "total_cases": len(results),
            "preflight": pre,
            "results": results,
            "stats": {
                "published_by_level": stats.get("published_by_level"),
                "published_total": stats.get("published_total"),
                "l1_ratio": stats.get("l1_ratio"),
                "l1_over_l1l2": stats.get("l1_over_l1l2"),
                "pending": stats.get("pending"),
                "by_source_sheet": stats.get("by_source_sheet"),
            },
            "sheets": sheets,
            "year_as_quantity": year_qty,
            "gate_missing": (base.get("gate") or {}).get("missing"),
            "metric_values": {
                k: (v or {}).get("value")
                for k, v in (base.get("metric_values") or {}).items()
            },
        }
        out = ROOT / "data" / "eval" / "results"
        out.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        path = out / f"flow_harden_{stamp}.json"
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        # also copy under test data
        (TEST_DATA / "flow_harden.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        print("wrote", path)
        print(
            "sheets",
            sheets,
            "L1/L2/L3",
            stats.get("published_by_level"),
            "pending",
            stats.get("pending"),
            "year_qty",
            year_qty,
        )
        assert summary["ok_cases"] == summary["total_cases"]
        assert year_qty == 0, year_qty
        expect = {"低值易耗", "维护材料", "备品备件", "成都区域ZW物资台账（新模板）"}
        assert expect <= set(sheets), sheets
        print("FLOW_HARDEN_OK")


if __name__ == "__main__":
    main()
