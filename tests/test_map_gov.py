# -*- coding: utf-8 -*-
"""PR2: map_pending queue — low-conf/multi/conflict → human → rule_dict."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_map_gov_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"
os.environ["EMBED_FALLBACK_LEXICAL"] = "1"
os.environ["LLM_BIG_ENDPOINT"] = ""  # force no live LLM
os.environ["LLM_FAST_ENDPOINT"] = ""

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, meta_tx  # noqa: E402
from app.services.map_gov import confirm_pending, enqueue_headers, list_pending  # noqa: E402
from app.services.mapping_suggest import classify_queue_items, suggest_header_mapping  # noqa: E402
from app.services.rule_dict import dict_prefill  # noqa: E402


def _seed_conflict() -> None:
    init_meta()
    with meta_tx() as con:
        con.execute("DELETE FROM rule_dict")
        con.execute("DELETE FROM map_pending")
        con.execute(
            """
            INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
            VALUES ('模糊列', 'location', 'default', 2, 'human_confirm', 't')
            """
        )
        con.execute(
            """
            INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
            VALUES ('模糊列', 'region', 'default', 2, 'human_confirm', 't')
            """
        )


def test_conflict_enters_queue() -> None:
    _seed_conflict()
    headers = ["模糊列", "xyz_unknown_col_zz"]
    sug = suggest_header_mapping(headers, business_domain="default")
    items = classify_queue_items(headers, sug)
    reasons = {i["header"]: i["reason"] for i in items}
    assert reasons.get("模糊列") == "conflict", reasons
    assert "xyz_unknown_col_zz" in reasons, reasons

    out = enqueue_headers(headers, file_id="f1", sheet="S1", business_domain="default", suggest=sug)
    assert out["enqueued"] >= 2, out
    listed = list_pending(status="pending")
    assert listed["total"] >= 2
    headers_pending = {i["header"] for i in listed["items"]}
    assert "模糊列" in headers_pending


def test_confirm_writes_rule_dict_not_silent() -> None:
    _seed_conflict()
    headers = ["外部追踪号ZZ99"]
    sug = suggest_header_mapping(headers, business_domain="default")
    out = enqueue_headers(headers, file_id="", sheet="", suggest=sug)
    assert out["enqueued"] == 1, out
    pid = out["pending_ids"][0]

    # Before confirm: conflicted headers stay out of silent prefill
    prefill, _, conflicts = dict_prefill(["模糊列"])
    assert "模糊列" in conflicts or "模糊列" not in prefill

    res = confirm_pending(
        pending_id=pid, decision="amend", std_field="remark", actor="tester", note="ok"
    )
    assert res["ok"] and res["status"] == "accepted"
    prefill2, hits2, _ = dict_prefill(["外部追踪号ZZ99"])
    assert prefill2.get("外部追踪号ZZ99") == "remark", (prefill2, hits2)

    listed = list_pending(status="pending")
    assert all(i["pending_id"] != pid for i in listed["items"])


def test_ignore_records_ignore_field() -> None:
    init_meta()
    with meta_tx() as con:
        con.execute("DELETE FROM map_pending")
        con.execute("DELETE FROM rule_dict WHERE header='外部ID列'")
    sug = {
        "mapping": {"外部ID列": "ignore"},
        "candidates": {"外部ID列": []},
        "multi_candidate_headers": {},
        "dict_conflicts": [],
        "dict_hits": {},
    }
    out = enqueue_headers(["外部ID列"], suggest=sug)
    assert out["enqueued"] == 1
    pid = out["pending_ids"][0]
    confirm_pending(pending_id=pid, decision="ignore", actor="tester")
    prefill, hits, _ = dict_prefill(["外部ID列"])
    assert prefill.get("外部ID列") == "ignore", (prefill, hits)


def main() -> None:
    test_conflict_enters_queue()
    print("OK conflict_enters_queue")
    test_confirm_writes_rule_dict_not_silent()
    print("OK confirm_writes_rule_dict")
    test_ignore_records_ignore_field()
    print("OK ignore_records")
    print("MAP_GOV_OK")


if __name__ == "__main__":
    main()
