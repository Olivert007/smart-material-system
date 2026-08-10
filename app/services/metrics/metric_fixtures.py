# -*- coding: utf-8 -*-
"""Fixed metric fixtures for 08 activation gate (docs/08 §3 / 12 §8 #4).

Fixtures run in an isolated DuckDB / SQLite sandbox — never touch live biz/meta data.
"""
from __future__ import annotations

import sqlite3
from typing import Any

import duckdb

# Isolated schema subset matching fact_stock_flow columns used by FLOW_* SQL.
_BIZ_DDL = """
CREATE TABLE fact_stock_flow (
  flow_id VARCHAR,
  material_id VARCHAR,
  flow_type VARCHAR,
  flow_date DATE,
  quantity DOUBLE,
  unit VARCHAR,
  person VARCHAR,
  purpose VARCHAR,
  remark VARCHAR,
  parse_level VARCHAR,
  parse_source VARCHAR,
  source_file VARCHAR,
  source_sheet VARCHAR,
  source_row INTEGER,
  source_segment INTEGER,
  source_release_id VARCHAR
);
"""

FLOW_METRIC_FIXTURES: list[dict[str, Any]] = [
    {
        "metric_id": "FLOW_QTY_TOTAL",
        "version": 1,
        "engine": "biz",
        "definition_sql": (
            "SELECT SUM(quantity) AS v FROM fact_stock_flow WHERE flow_type='IN'"
        ),
        "expect": 15.0,
        "tolerance": 0.01,
        "seed_rows": [
            # IN 4 + 6 + 5 = 15; OUT must not count; year-like numbers only on OUT remark not qty
            ("f1", "m1", "IN", None, 4.0, "包", "L1"),
            ("f2", "m1", "IN", None, 6.0, "包", "L1"),
            ("f3", "m2", "IN", None, 5.0, "个", "L1"),
            ("f4", "m2", "OUT", None, 2.0, "个", "L1"),
        ],
    },
    {
        "metric_id": "FLOW_PARSE_L1_RATIO",
        "version": 1,
        "engine": "biz",
        "definition_sql": (
            "SELECT CASE WHEN COUNT(*) FILTER (WHERE parse_level IN ('L1','L2')) = 0 "
            "THEN NULL ELSE CAST(COUNT(*) FILTER (WHERE parse_level='L1') AS DOUBLE) "
            "/ COUNT(*) FILTER (WHERE parse_level IN ('L1','L2')) END AS v "
            "FROM fact_stock_flow"
        ),
        "expect": 0.75,  # 3 L1 / (3 L1 + 1 L2)
        "tolerance": 0.001,
        "seed_rows": [
            ("a", "m", "IN", None, 1.0, "个", "L1"),
            ("b", "m", "IN", None, 1.0, "个", "L1"),
            ("c", "m", "OUT", None, 1.0, "个", "L1"),
            ("d", "m", "OUT", None, None, "个", "L2"),
            ("e", "m", "OUT", None, None, "个", "L3"),  # excluded from denom
        ],
    },
    {
        "metric_id": "FLOW_RECONCILE_GAP_CNT",
        "version": 1,
        "engine": "meta",
        "definition_sql": "SELECT COUNT(*) AS v FROM flow_reconcile_gap",
        "expect": 2,
        "tolerance": 0,
        "seed_gaps": [
            ("m1", 10.0, 8.0, -2.0),
            ("m2", 5.0, 7.0, 2.0),
        ],
    },
]


def _run_biz_fixture(fx: dict[str, Any]) -> dict[str, Any]:
    con = duckdb.connect(":memory:")
    try:
        con.execute(_BIZ_DDL)
        for i, row in enumerate(fx.get("seed_rows") or []):
            flow_id, mid, ftype, fdate, qty, unit, level = row
            con.execute(
                """
                INSERT INTO fact_stock_flow (
                  flow_id, material_id, flow_type, flow_date, quantity, unit,
                  parse_level, parse_source, source_file, source_sheet,
                  source_row, source_segment, source_release_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'fixture', 'fix.xlsx', 'Sheet1', ?, 0, 'rel_fx')
                """,
                [flow_id, mid, ftype, fdate, qty, unit, level, i + 1],
            )
        got = con.execute(fx["definition_sql"]).fetchone()[0]
    finally:
        con.close()
    return _compare(fx, got)


def _run_meta_fixture(fx: dict[str, Any]) -> dict[str, Any]:
    con = sqlite3.connect(":memory:")
    try:
        con.execute(
            """
            CREATE TABLE flow_reconcile_gap (
              gap_id INTEGER PRIMARY KEY AUTOINCREMENT,
              material_id TEXT,
              stock_qty DOUBLE,
              flow_net DOUBLE,
              gap DOUBLE,
              source_file TEXT
            )
            """
        )
        for g in fx.get("seed_gaps") or []:
            con.execute(
                """
                INSERT INTO flow_reconcile_gap (material_id, stock_qty, flow_net, gap, source_file)
                VALUES (?, ?, ?, ?, 'fixture')
                """,
                [g[0], g[1], g[2], g[3]],
            )
        got = con.execute(fx["definition_sql"]).fetchone()[0]
    finally:
        con.close()
    return _compare(fx, got)


def _compare(fx: dict[str, Any], got: Any) -> dict[str, Any]:
    expect = fx["expect"]
    tol = float(fx.get("tolerance") or 0)
    ok = False
    if got is None and expect is None:
        ok = True
    elif got is not None and expect is not None:
        try:
            ok = abs(float(got) - float(expect)) <= tol
        except (TypeError, ValueError):
            ok = False
    return {
        "metric_id": fx["metric_id"],
        "ok": ok,
        "expect": expect,
        "got": got,
        "tolerance": tol,
        "version": fx.get("version"),
        "engine": fx.get("engine"),
    }


def run_metric_fixtures(*, metric_ids: list[str] | None = None) -> dict[str, Any]:
    """Execute fixed input fixtures; required before FLOW_* status=active."""
    want = set(metric_ids) if metric_ids else {f["metric_id"] for f in FLOW_METRIC_FIXTURES}
    results = []
    for fx in FLOW_METRIC_FIXTURES:
        if fx["metric_id"] not in want:
            continue
        if fx.get("engine") == "meta":
            results.append(_run_meta_fixture(fx))
        else:
            results.append(_run_biz_fixture(fx))
    passed = sum(1 for r in results if r["ok"])
    return {
        "ok": passed == len(results) and len(results) > 0,
        "passed": passed,
        "total": len(results),
        "items": results,
    }
