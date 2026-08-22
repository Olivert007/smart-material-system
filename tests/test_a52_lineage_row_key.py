# -*- coding: utf-8 -*-
"""Mid-risk 5 / A5.2: stock_flow publish mirrors lineage into fact_release_rows.row_key."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_a52_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OPS_TOKEN"] = "test-ops"

sys.path.insert(0, str(ROOT))

from app.repositories.db import init_meta, writer_conn  # noqa: E402
from app.repositories.schema import ensure_biz_schema  # noqa: E402
from app.services.govern.mapping import build_stock_flow_bundle, flow_lineage_row_key  # noqa: E402


def main() -> None:
    init_meta()
    con = writer_conn()
    try:
        ensure_biz_schema(con)
        key = flow_lineage_row_key(
            source_file="a.xlsx",
            source_sheet="维护材料",
            source_row=3,
            source_segment=1,
            flow_type="OUT",
        )
        assert key == "a.xlsx|维护材料|3|1|OUT", key

        df = pd.DataFrame(
            {
                "物资名称": ["跳线"],
                "sheet": ["维护材料"],
                "入库记录": ["2025年6月入库2条"],
                "单位": ["条"],
            }
        )
        _t, rows, _p, _s = build_stock_flow_bundle(
            df, file_id="fid1", release_id="rel_a52", source_file="demo.xlsx"
        )
        assert rows, "expected L1 rows"
        assert all(r.get("_row_key") for r in rows), rows[0]

        # simulate writer lineage mirror
        rid = "rel_a52"
        con.execute("DELETE FROM fact_stock_flow WHERE source_release_id=?", [rid])
        con.execute(
            "DELETE FROM fact_release_rows WHERE source_release_id=? AND target_domain='stock_flow'",
            [rid],
        )
        for rec in rows:
            rk = rec["_row_key"]
            con.execute(
                """
                INSERT INTO fact_stock_flow
                (flow_id, material_id, flow_type, quantity, parse_level, parse_source,
                 source_file, source_sheet, source_row, source_segment, source_release_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    rec["flow_id"],
                    rec["material_id"],
                    rec["flow_type"],
                    rec["quantity"],
                    rec["parse_level"],
                    rec["parse_source"],
                    rec["source_file"],
                    rec["source_sheet"],
                    rec["source_row"],
                    rec["source_segment"],
                    rid,
                ],
            )
            con.execute(
                """
                INSERT INTO fact_release_rows
                (source_release_id, file_id, target_domain, row_key, payload_json)
                VALUES (?, 'fid1', 'stock_flow', ?, ?)
                """,
                [rid, rk, json.dumps({"flow_id": rec["flow_id"]}, ensure_ascii=False)],
            )

        n_flow = con.execute(
            "SELECT COUNT(*) FROM fact_stock_flow WHERE source_release_id=?", [rid]
        ).fetchone()[0]
        n_lin = con.execute(
            """
            SELECT COUNT(*) FROM fact_release_rows
            WHERE source_release_id=? AND target_domain='stock_flow'
            """,
            [rid],
        ).fetchone()[0]
        assert n_flow == n_lin == len(rows), (n_flow, n_lin, len(rows))
        sample = con.execute(
            """
            SELECT row_key FROM fact_release_rows
            WHERE source_release_id=? AND target_domain='stock_flow' LIMIT 1
            """,
            [rid],
        ).fetchone()[0]
        assert "|维护材料|" in sample and sample.count("|") == 4, sample
        print("A5_2_OK", {"flows": n_flow, "lineage": n_lin, "sample": sample})
    finally:
        con.close()


if __name__ == "__main__":
    main()
