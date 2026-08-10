#!/usr/bin/env python3
"""A6.1 — audit fact_stock_flow for year-as-quantity and other bad rows (docs/12 FL7)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))

from app.repositories import init_meta  # noqa: E402
from app.services.flow_lineage import audit_stock_flow  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit fact_stock_flow suspicious rows")
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--json-out", type=str, default="")
    args = ap.parse_args()

    init_meta()
    report = audit_stock_flow(limit=args.limit)
    print(json.dumps(
        {
            "ok": report.get("ok"),
            "total_rows": report.get("total_rows"),
            "suspicious_count": report.get("suspicious_count"),
            "by_release": report.get("by_release"),
            "sample": (report.get("suspicious") or [])[:10],
        },
        ensure_ascii=False,
        indent=2,
    ))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print("wrote", out)
    if not report.get("ok"):
        raise SystemExit(1)
    print("AUDIT_OK" if report.get("suspicious_count", 0) == 0 else "AUDIT_HAS_SUSPICIOUS")


if __name__ == "__main__":
    main()
