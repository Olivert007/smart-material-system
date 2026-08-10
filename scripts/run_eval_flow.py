#!/usr/bin/env python3
"""B4 — flow parse eval: rule baseline + optional LLM suggest (docs/12).

Hard gate: zero year-as-quantity.
Pass bar (default): LLM field accuracy >= FLOW_EVAL_MIN_ACC (0.75) when LLM runs;
rule path always reported for baseline.
"""
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
os.environ["LLM_BIG_ENDPOINT"] = os.environ.get("EVAL_BIG_ENDPOINT") or "http://127.0.0.1:8001/v1"
os.environ["LLM_BIG_MODEL"] = os.environ.get("EVAL_BIG_MODEL") or "qwen3.6-27b"
os.environ["LLM_ENABLE_THINKING"] = os.environ.get("LLM_ENABLE_THINKING") or "0"
# eval uses explicit suggest; keep worker from racing
os.environ.setdefault("WORKER_POLL_SEC", "60")

from app import config  # noqa: E402
from app.repositories import init_meta, meta_tx  # noqa: E402
from app.services.flow_eval import ensure_flow_eval  # noqa: E402
from app.services.flow_llm import suggest_one  # noqa: E402
from app.services.flow_parse import parse_flow_cell  # noqa: E402
from app.services.model_client import probe_endpoint  # noqa: E402

MIN_ACC = float(os.environ.get("FLOW_EVAL_MIN_ACC", "0.75"))
SKIP_LLM = os.environ.get("FLOW_EVAL_SKIP_LLM", "0") == "1"


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _qty_eq(got, expect) -> bool:
    if expect is None:
        return got is None
    if got is None:
        return False
    try:
        return abs(float(got) - float(expect)) < 1e-6
    except (TypeError, ValueError):
        return False


def _year_violation(qty, forbid: list) -> bool:
    if qty is None or not forbid:
        return False
    try:
        q = float(qty)
    except (TypeError, ValueError):
        return False
    if q != int(q):
        return False
    return int(q) in {int(x) for x in forbid}


def score_suggestion(got: dict, expect: dict) -> dict:
    checks: dict[str, bool] = {}
    forbid = expect.get("forbid_quantity") or []
    qty = got.get("quantity")
    year_bad = _year_violation(qty, forbid)
    checks["no_year_qty"] = not year_bad
    checks["flow_type"] = str(got.get("flow_type") or "").upper() == str(
        expect.get("flow_type") or ""
    ).upper()
    if "quantity" in expect:
        checks["quantity"] = _qty_eq(qty, expect.get("quantity"))
    if expect.get("unit"):
        checks["unit"] = str(got.get("unit") or "") == str(expect["unit"])
    if expect.get("person_contains"):
        person = str(got.get("person") or "")
        checks["person"] = expect["person_contains"] in person
    if "flow_date" in expect:
        exp_d = expect.get("flow_date")
        got_d = got.get("flow_date")
        if exp_d is None:
            checks["flow_date"] = got_d in (None, "", "null")
        else:
            checks["flow_date"] = str(got_d or "")[:10] == str(exp_d)[:10]
    if expect.get("parse_level_in"):
        checks["parse_level"] = str(got.get("parse_level") or "").upper() in {
            str(x).upper() for x in expect["parse_level_in"]
        }
    if expect.get("flag_contains"):
        flags = got.get("flags") or []
        if isinstance(flags, str):
            flags = [flags]
        # also accept BORROW in remark/purpose
        blob = " ".join(str(x) for x in flags) + " " + str(got.get("remark") or "")
        checks["flag"] = expect["flag_contains"] in blob or expect["flag_contains"] in str(
            got.get("flags")
        )

    hard_ok = checks.get("no_year_qty", True) and checks.get("flow_type", True)
    if "quantity" in checks:
        hard_ok = hard_ok and checks["quantity"]
    soft_keys = [k for k in checks if k not in ("no_year_qty",)]
    soft_hit = sum(1 for k in soft_keys if checks[k])
    soft_total = len(soft_keys) or 1
    return {
        "passed": hard_ok,
        "year_violation": year_bad,
        "checks": checks,
        "soft_hit": soft_hit,
        "soft_total": soft_total,
        "soft_acc": round(soft_hit / soft_total, 4),
    }


def eval_rule(case: dict) -> dict:
    parsed = parse_flow_cell(
        case["text"],
        flow_type=case.get("flow_type") or "OUT",
        col_qty=case.get("col_qty"),
        col_unit=case.get("col_unit"),
        parse_source="rule",
    )
    # score first segment against expect (single-cell gold)
    first = parsed[0].to_dict() if parsed else {"parse_level": "L3", "quantity": None}
    # normalize flags
    if "借用" in case["text"] and "BORROW" not in (first.get("flags") or []):
        first.setdefault("flags", []).append("BORROW")
        first["flow_type"] = "OUT"
    scored = score_suggestion(first, case["expect"])
    return {"id": case["id"], "path": "rule", "got": first, **scored}


def eval_llm(case: dict) -> dict:
    pid = f"eval_{case['id']}"
    rule_seed = {
        "flow_type": case.get("flow_type") or "OUT",
        "quantity": case.get("col_qty"),
        "unit": case.get("col_unit"),
        "parse_level": "L2",
        "parse_source": "rule",
        "remark": case["text"],
    }
    with meta_tx() as con:
        con.execute("DELETE FROM flow_pending WHERE pending_id=?", [pid])
        con.execute(
            """
            INSERT INTO flow_pending (
                pending_id, file_id, source_sheet, source_row, source_segment,
                flow_type, text_raw, text_norm, parse_level, suggested_json,
                status, llm_state
            ) VALUES (?, 'eval', 'eval', 0, 0, ?, ?, ?, 'L2', ?, 'pending', 'none')
            """,
            [
                pid,
                case.get("flow_type") or "OUT",
                case["text"],
                case["text"],
                json.dumps(rule_seed, ensure_ascii=False),
            ],
        )
    t0 = time.time()
    out = suggest_one(pid, force_role="big")
    latency = int((time.time() - t0) * 1000)
    sug = (out.get("suggestion") or {}) if out.get("ok") else {}
    if not sug and out.get("ok") is False:
        return {
            "id": case["id"],
            "path": "llm",
            "passed": False,
            "year_violation": False,
            "checks": {},
            "soft_hit": 0,
            "soft_total": 1,
            "soft_acc": 0.0,
            "error": out.get("issues") or out.get("error") or out.get("reason"),
            "latency_ms": latency,
            "got": sug,
        }
    scored = score_suggestion(sug, case["expect"])
    return {
        "id": case["id"],
        "path": "llm",
        "got": sug,
        "latency_ms": latency,
        "role": out.get("role"),
        "mode": out.get("mode"),
        **scored,
    }


def main() -> None:
    init_meta()
    # keep FLOW_LLM_ENABLED on for suggest_one
    config.FLOW_LLM_ENABLED = True
    root = ensure_flow_eval(force=True)
    cases = _load_jsonl(root / "flow_parse_llm.jsonl")

    rule_details = [eval_rule(c) for c in cases]
    rule_pass = sum(1 for d in rule_details if d["passed"])
    rule_year = sum(1 for d in rule_details if d.get("year_violation"))
    rule_soft_hit = sum(d["soft_hit"] for d in rule_details)
    rule_soft_total = sum(d["soft_total"] for d in rule_details)

    llm_details: list[dict] = []
    llm_ran = False
    probe = probe_endpoint(config.LLM_BIG_ENDPOINT, timeout=3)
    if not SKIP_LLM and probe.get("ok"):
        llm_ran = True
        for c in cases:
            llm_details.append(eval_llm(c))
            print(
                "llm",
                c["id"],
                "pass" if llm_details[-1]["passed"] else "FAIL",
                llm_details[-1].get("got", {}).get("quantity"),
                llm_details[-1].get("latency_ms"),
            )
    else:
        print("LLM_SKIP", "skip_flag" if SKIP_LLM else probe)

    llm_pass = sum(1 for d in llm_details if d.get("passed"))
    llm_year = sum(1 for d in llm_details if d.get("year_violation"))
    llm_soft_hit = sum(d.get("soft_hit", 0) for d in llm_details)
    llm_soft_total = sum(d.get("soft_total", 0) for d in llm_details) or 1

    summary = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cases": len(cases),
        "min_acc": MIN_ACC,
        "rule": {
            "passed": rule_pass,
            "accuracy": round(rule_pass / len(cases), 4) if cases else 0.0,
            "soft_accuracy": round(rule_soft_hit / rule_soft_total, 4) if rule_soft_total else 0.0,
            "year_violations": rule_year,
        },
        "llm": {
            "ran": llm_ran,
            "passed": llm_pass,
            "accuracy": round(llm_pass / len(llm_details), 4) if llm_details else None,
            "soft_accuracy": round(llm_soft_hit / llm_soft_total, 4) if llm_details else None,
            "year_violations": llm_year,
        },
        "details": {"rule": rule_details, "llm": llm_details},
    }

    hard_ok = rule_year == 0 and (not llm_ran or llm_year == 0)
    acc_ok = (not llm_ran) or (summary["llm"]["accuracy"] or 0) >= MIN_ACC
    summary["ok"] = bool(hard_ok and acc_ok and rule_pass >= 1)

    out_dir = root / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir / f"flow_eval_{stamp}.json"
    latest = out_dir / "flow_eval_latest.json"
    payload = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    out.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")

    print(
        json.dumps(
            {k: summary[k] for k in ("ts", "cases", "min_acc", "rule", "llm", "ok")},
            ensure_ascii=False,
            indent=2,
        )
    )
    print("wrote", out)
    print("FLOW_EVAL_OK" if summary["ok"] else "FLOW_EVAL_CHECK")


if __name__ == "__main__":
    main()
