#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: map_pending queue (MAP_GOV_OK)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repositories import init_meta, meta_tx  # noqa: E402
from app.services.govern.map_gov import confirm_pending, enqueue_headers, list_pending  # noqa: E402


def main() -> int:
    init_meta()
    with meta_tx() as con:
        con.execute("DELETE FROM map_pending WHERE header IN ('模糊列','外部追踪号ZZ99')")
        con.execute("DELETE FROM rule_dict WHERE header IN ('模糊列','外部追踪号ZZ99')")
        con.execute(
            """
            INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
            VALUES ('模糊列', 'location', 'default', 1, 'seed', 'smoke')
            """
        )
        con.execute(
            """
            INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
            VALUES ('模糊列', 'region', 'default', 1, 'seed', 'smoke')
            """
        )

    sug = {
        "mapping": {"模糊列": "location", "外部追踪号ZZ99": "ignore"},
        "candidates": {
            "模糊列": [
                {"std_field": "location", "score": 0.5},
                {"std_field": "region", "score": 0.5},
            ],
            "外部追踪号ZZ99": [],
        },
        "multi_candidate_headers": {},
        "dict_conflicts": ["模糊列"],
        "dict_hits": {},
    }
    out = enqueue_headers(
        ["模糊列", "外部追踪号ZZ99"], file_id="smoke", sheet="S1", suggest=sug
    )
    assert out["enqueued"] == 2, out
    pending = list_pending(status="pending", file_id="smoke")
    assert pending["total"] >= 2

    # confirm one
    pid = next(i["pending_id"] for i in pending["items"] if i["header"] == "外部追踪号ZZ99")
    confirm_pending(pending_id=pid, decision="amend", std_field="remark", actor="smoke")
    print("MAP_GOV_OK")
    print(f"enqueued={out['enqueued']} remaining={list_pending(status='pending', file_id='smoke')['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
