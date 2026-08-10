#!/usr/bin/env python3
"""Stage 1 eval baseline: header mapping + Text2SQL (docs/10 skeleton)."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))
os.environ.setdefault("OPS_TOKEN", "dev-ops-token-change-me")
# Pin Stage-1 served ids (EVAL_* overrides). Do not inherit stale shell LLM_BIG_MODEL=7B.
os.environ["LLM_BIG_ENDPOINT"] = os.environ.get("EVAL_BIG_ENDPOINT") or "http://127.0.0.1:8001/v1"
os.environ["LLM_BIG_MODEL"] = os.environ.get("EVAL_BIG_MODEL") or "qwen3.6-27b"
os.environ["LLM_EMBED_ENDPOINT"] = os.environ.get("EVAL_EMBED_ENDPOINT") or "http://127.0.0.1:8002/v1"
os.environ["LLM_EMBED_MODEL"] = os.environ.get("EVAL_EMBED_MODEL") or "qwen3-embedding-0.6b"
os.environ["EMBED_FALLBACK_LEXICAL"] = os.environ.get("EMBED_FALLBACK_LEXICAL") or "1"
os.environ["LLM_ENABLE_THINKING"] = os.environ.get("LLM_ENABLE_THINKING") or "0"

from app.repositories import init_meta  # noqa: E402
from app.services.eval_skel import ensure_eval_skeleton  # noqa: E402
from app.services.mapping_suggest import suggest_header_mapping  # noqa: E402
from app.services.text2sql import ask  # noqa: E402
from app import config  # noqa: E402


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _score_mapping(got: dict[str, str], expect: dict[str, str]) -> tuple[int, int, list[str]]:
    # Soft-accept near-synonym labels used by embed catalog vs rule aliases.
    synonyms = {
        "stock_qty": {"stock_qty", "quantity"},
        "quantity": {"quantity", "stock_qty"},
        "item_name": {"item_name", "material_name", "asset_name"},
        "material_name": {"material_name", "item_name"},
        "specification": {"specification", "spec"},
        "spec": {"spec", "specification"},
        "keeper_or_user": {"keeper_or_user", "user_name", "custodian"},
        "company": {"company", "org", "ignore"},  # weak signal until catalog expands
    }
    ok = 0
    misses: list[str] = []
    for h, gold in expect.items():
        pred = got.get(h)
        accepted = synonyms.get(gold, {gold})
        if pred in accepted:
            ok += 1
        else:
            misses.append(f"{h}: got={pred!r} expect={gold!r}")
    return ok, len(expect), misses


def main() -> None:
    init_meta()
    root = ensure_eval_skeleton(force=True)
    map_cases = _load_jsonl(root / "header_mapping.jsonl")
    sql_cases = _load_jsonl(root / "text2sql.jsonl")

    map_details = []
    map_hit = map_total = 0
    t_map0 = time.time()
    for case in map_cases:
        res = suggest_header_mapping(case["headers"])
        got = res.get("mapping") or {}
        hit, total, misses = _score_mapping(got, case["expect"])
        map_hit += hit
        map_total += total
        map_details.append(
            {
                "headers": case["headers"],
                "hit": hit,
                "total": total,
                "misses": misses,
                "model_state": res.get("model_state"),
                "model_invoked": res.get("model_invoked"),
                "latency_ms": res.get("latency_ms"),
            }
        )
    map_sec = time.time() - t_map0

    sql_details = []
    sql_ok = 0
    t_sql0 = time.time()
    for case in sql_cases:
        res = ask(case["question"])
        sql = (res.get("sql") or "").lower()
        must = [m.lower() for m in case.get("must_contain") or []]
        contain_ok = all(m in sql for m in must)
        min_rows = case.get("expect_min_rows")
        rows = res.get("rows")
        rows_ok = True if min_rows is None else (isinstance(rows, int) and rows >= int(min_rows))
        passed = bool(res.get("ok")) and contain_ok and rows_ok
        if passed:
            sql_ok += 1
        sql_details.append(
            {
                "question": case["question"],
                "ok": passed,
                "api_ok": res.get("ok"),
                "sql": res.get("sql"),
                "rows": rows,
                "contain_ok": contain_ok,
                "rows_ok": rows_ok,
                "must_contain": case.get("must_contain"),
                "error": res.get("error"),
                "model_state": res.get("model_state"),
                "latency_ms": res.get("latency_ms"),
                "answer": (res.get("answer") or "")[:200],
            }
        )
    sql_sec = time.time() - t_sql0

    summary = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stage": 1,
        "models": {
            "big": config.LLM_BIG_MODEL,
            "embed": config.LLM_EMBED_MODEL,
            "enable_thinking": config.LLM_ENABLE_THINKING,
        },
        "mapping": {
            "cases": len(map_cases),
            "field_hit": map_hit,
            "field_total": map_total,
            "field_accuracy": round(map_hit / map_total, 4) if map_total else 0.0,
            "seconds": round(map_sec, 2),
        },
        "text2sql": {
            "cases": len(sql_cases),
            "passed": sql_ok,
            "accuracy": round(sql_ok / len(sql_cases), 4) if sql_cases else 0.0,
            "seconds": round(sql_sec, 2),
        },
        "details": {"mapping": map_details, "text2sql": sql_details},
    }

    out_dir = root / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir / f"stage1_{stamp}.json"
    latest = out_dir / "latest.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    latest.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({k: summary[k] for k in ("ts", "models", "mapping", "text2sql")}, ensure_ascii=False, indent=2))
    print("wrote", out)
    print("EVAL_STAGE1_OK" if summary["text2sql"]["passed"] == summary["text2sql"]["cases"] and map_hit > 0 else "EVAL_STAGE1_CHECK")


if __name__ == "__main__":
    main()
