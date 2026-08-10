#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2-3 smoke: rule_learn + report cron (RULE_LEARN_CRON_OK)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_rl_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "smoke-ops"
os.environ["ALLOW_FREE_QUERY"] = "1"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, meta_tx  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.repositories import writer_conn  # noqa: E402
from app.services import rule_learn as rl  # noqa: E402
from app.services.report_runner import (  # noqa: E402
    claim_due_report,
    create_report,
    process_due_report_once,
)


def main() -> int:
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
    finally:
        con.close()

    with meta_tx() as m:
        for i in range(3):
            m.execute(
                """
                INSERT INTO staging_blocked (
                    block_id, staging_id, file_id, target_domain, source_row,
                    header, reason_code, reason_detail, raw_value
                ) VALUES (?, 'st1', 'f1', 'inventory', ?, '怪表头X', 'UNKNOWN_HEADER', 'unknown', 'x')
                """,
                [f"b{i}", i],
            )
            m.execute(
                """
                INSERT INTO staging_blocked (
                    block_id, staging_id, file_id, target_domain, source_row,
                    header, reason_code, reason_detail, raw_value
                ) VALUES (?, 'st1', 'f1', 'inventory', ?, 'stock_qty', 'VALUE_RANGE', 'neg', '-1')
                """,
                [f"v{i}", i + 10],
            )

    out = rl.propose_from_blocked(min_count=2)
    assert out["created"] >= 1, out
    cands = rl.list_candidates()
    assert cands["total"] >= 1
    proposed = [c for c in cands["items"] if c["decision"] == "proposed"]
    assert proposed
    # accept a value_rule candidate if present else map_alias with std_field
    target = next(
        (c for c in proposed if (c.get("proposal") or {}).get("kind") == "value_rule"),
        proposed[0],
    )
    kind = (target.get("proposal") or {}).get("kind")
    conf = rl.confirm_candidate(
        confirm_id=int(target["id"]),
        decision="accepted",
        actor="smoke",
        std_field="material_name" if kind == "map_alias" else None,
    )
    assert conf["ok"] and conf["decision"] == "accepted"

    create_report(
        name="cron smoke",
        query_sql="SELECT 1 AS v",
        actor="smoke",
        report_id="rpt_cron",
        cron_expr="every:1m",
    )
    due = claim_due_report()
    assert due == "rpt_cron", due
    ran = process_due_report_once(actor="smoke")
    assert ran and ran.get("ok"), ran
    # immediate second claim should skip (interval not elapsed)
    assert claim_due_report() is None

    print("RULE_LEARN_CRON_OK")
    print(f"created={out['created']} cron_run={ran['run_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
