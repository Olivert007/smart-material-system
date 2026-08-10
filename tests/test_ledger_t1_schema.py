# -*- coding: utf-8 -*-
"""T1: ledger-export-plan schema columns exist after ensure_biz_schema (LD-1/LD-2)."""
from __future__ import annotations

from app.repositories import biz_conn, writer_conn
from app.repositories.schema import ensure_biz_schema

INV_T1_COLS = (
    "remark",
    "belong_system",
    "project_name",
    "consumption_plan",
    "material_source",
    "group_code",
    "is_frame_material",
    "agreement_supplier",
    "frame_material_code",
    "frame_material_name",
    "frame_material_spec",
    "frame_material_supplier",
    "emergency_supplier",
)

ASSET_T1_COLS = (
    "material_code",
    "asset_qty",
    "unit",
    "is_instrument",
    "replace_cycle",
    "check_cycle",
    "consumption_plan",
    "tool_source",
    "asset_quota_qty",
    "remark",
)


def _table_cols(con, table: str) -> set[str]:
    rows = con.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='main' AND table_name=?
        """,
        [table],
    ).fetchall()
    return {r[0] for r in rows}


def test_ledger_t1_inventory_columns():
    con = writer_conn()
    try:
        ensure_biz_schema(con)
    finally:
        con.close()
    con = biz_conn()
    try:
        cols = _table_cols(con, "fact_inventory")
        for c in INV_T1_COLS:
            assert c in cols, f"missing fact_inventory.{c}"
    finally:
        con.close()


def test_ledger_t1_asset_columns():
    con = writer_conn()
    try:
        ensure_biz_schema(con)
    finally:
        con.close()
    con = biz_conn()
    try:
        cols = _table_cols(con, "fact_asset")
        for c in ASSET_T1_COLS:
            assert c in cols, f"missing fact_asset.{c}"
    finally:
        con.close()
