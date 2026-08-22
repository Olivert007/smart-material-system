#!/usr/bin/env python3
"""Unit + optional live smoke for flow LLM suggest (docs/12 B1–B2)."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "tests" / "sandboxes" / "test_flow_b1"
if TEST_DATA.exists():
    shutil.rmtree(TEST_DATA)
os.environ["DATA_DIR"] = str(TEST_DATA)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["FLOW_LLM_ENABLED"] = "1"
os.environ["WORKER_POLL_SEC"] = "30"  # avoid background LLM drain during test
os.environ["ALLOW_FREE_QUERY"] = "1"

sys.path.insert(0, str(ROOT))

from app.repositories import init_meta, meta_tx  # noqa: E402
from app.services.flow_llm import process_pending_batch, suggest_one, validate_flow_suggestion  # noqa: E402
from app.services.llm.model_client import LlmResult  # noqa: E402
from app.services.policy_router import route_chat  # noqa: E402


def _seed_pending() -> str:
    init_meta()
    pid = "pend_b1_demo"
    with meta_tx() as con:
        con.execute("DELETE FROM flow_pending")
        con.execute(
            """
            INSERT INTO flow_pending (
                pending_id, file_id, source_sheet, source_row, source_segment,
                flow_type, text_raw, text_norm, parse_level, suggested_json, status, llm_state
            ) VALUES (?, 'f1', '维护材料', 1, 0, 'OUT', ?, ?, 'L2', ?, 'pending', 'none')
            """,
            [
                pid,
                "2025年10月，徐吉领用3个，用于机房音频配线",
                "2025年10月，徐吉领用3个，用于机房音频配线",
                json.dumps(
                    {
                        "flow_type": "OUT",
                        "quantity": 3,
                        "parse_level": "L2",
                        "parse_source": "rule",
                        "person": None,
                        "flow_date": None,
                    },
                    ensure_ascii=False,
                ),
            ],
        )
    return pid


def test_validate_year_qty() -> None:
    bad = LlmResult(ok=True, text='{"flow_type":"IN","quantity":2023,"parse_level":"L1","confidence":0.9}')
    ok, issues = validate_flow_suggestion(bad)
    assert not ok and "year_as_quantity" in issues, issues
    good = LlmResult(
        ok=True,
        text='{"flow_type":"OUT","flow_date":"2025-10-01","quantity":3,"unit":"个",'
        '"person":"徐吉","purpose":"机房音频配线","parse_level":"L1","confidence":0.9,"flags":[]}',
    )
    ok, issues = validate_flow_suggestion(good)
    assert ok, issues
    print("VALIDATE_OK")


def test_disabled() -> None:
    os.environ["FLOW_LLM_ENABLED"] = "0"
    # reload config flag
    from app import config

    config.FLOW_LLM_ENABLED = False
    out = process_pending_batch(limit=1)
    assert out.get("skipped") and out.get("reason") == "FLOW_LLM_DISABLED"
    config.FLOW_LLM_ENABLED = True
    os.environ["FLOW_LLM_ENABLED"] = "1"
    print("DISABLED_OK")


def test_mock_router_writes_pending() -> None:
    pid = _seed_pending()

    fake = LlmResult(
        ok=True,
        text=(
            '{"flow_type":"OUT","flow_date":"2025-10-01","quantity":3,"unit":"个",'
            '"person":"徐吉","purpose":"机房音频配线","remark":"领用",'
            '"parse_level":"L1","confidence":0.88,"flags":[]}'
        ),
        model_state="llm_analysis_available",
        output_available=True,
        model_invoked=True,
    )

    def _fake_route(**kwargs):
        from app.services.policy_router import RouteResult

        # still run validate
        ok, issues = validate_flow_suggestion(fake)
        return RouteResult(
            ok=ok,
            result=fake,
            role_used="big",
            mode="degraded_up",
            attempts=[{"role": "big", "ok": True}],
            issues=issues,
        )

    with patch("app.services.flow_llm.route_chat", side_effect=_fake_route):
        out = suggest_one(pid)
    assert out["ok"], out
    assert out["suggestion"]["parse_source"] == "llm"
    assert out["suggestion"]["quantity"] == 3
    assert out["suggestion"]["person"] == "徐吉"
    with meta_tx() as con:
        row = dict(con.execute("SELECT * FROM flow_pending WHERE pending_id=?", [pid]).fetchone())
        # ensure no biz write path was used — only meta
        assert row["llm_state"] == "done"
        sug = json.loads(row["suggested_json"])
        assert sug["parse_source"] == "llm"
        assert "_rule" in sug
    print("MOCK_WRITE_OK", out["mode"], out["role"])


def test_live_optional() -> None:
    """If big endpoint up, run one real suggest (force big)."""
    from app.services.llm.model_client import probe_endpoint
    from app import config

    probe = probe_endpoint(config.LLM_BIG_ENDPOINT, timeout=3)
    if not probe.get("ok"):
        print("LIVE_SKIP")
        return
    pid = _seed_pending()
    out = suggest_one(pid, force_role="big")
    print("LIVE", json.dumps({k: out.get(k) for k in ("ok", "mode", "role", "suggestion", "issues")}, ensure_ascii=False))
    assert out.get("ok"), out
    assert out["suggestion"]["parse_source"] == "llm"
    # never year qty
    q = out["suggestion"].get("quantity")
    if q is not None:
        assert not (1900 <= float(q) <= 2100 and float(q) == int(float(q)) and int(float(q)) >= 1900 and "年" in (out["suggestion"].get("remark") or "")), q
    print("LIVE_OK")


def main() -> None:
    test_validate_year_qty()
    test_disabled()
    test_mock_router_writes_pending()
    test_live_optional()
    print("FLOW_B1_OK")


if __name__ == "__main__":
    main()
