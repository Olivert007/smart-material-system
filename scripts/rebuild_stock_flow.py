#!/usr/bin/env python3
"""A6.2 — lineage rebuild stock_flow by release_id (docs/12 FL7). No in-place UPDATE."""
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
from app.services.flow_lineage import (  # noqa: E402
    audit_stock_flow,
    rebuild_stock_flow_release,
    revoke_stock_flow_release,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Rebuild fact_stock_flow by release lineage")
    ap.add_argument("--release-id", required=False, help="specific release to rebuild")
    ap.add_argument("--all-suspicious", action="store_true", help="rebuild every release with year-as-qty")
    ap.add_argument("--revoke-only", action="store_true", help="only delete derived rows")
    ap.add_argument("--actor", default="ops:cli")
    args = ap.parse_args()

    init_meta()
    if not args.release_id and not args.all_suspicious:
        ap.error("need --release-id or --all-suspicious")

    targets: list[str] = []
    if args.release_id:
        targets = [args.release_id]
    else:
        report = audit_stock_flow()
        targets = sorted(k for k, n in (report.get("by_release") or {}).items() if k and n > 0)
        print("suspicious releases", targets)

    results = []
    for rid in targets:
        if args.revoke_only:
            results.append(revoke_stock_flow_release(rid, actor=args.actor))
        else:
            results.append(rebuild_stock_flow_release(rid, actor=args.actor))
        print(json.dumps(results[-1], ensure_ascii=False, indent=2))

    post = audit_stock_flow()
    print(json.dumps(
        {
            "post_suspicious_count": post.get("suspicious_count"),
            "post_by_release": post.get("by_release"),
        },
        ensure_ascii=False,
        indent=2,
    ))
    year_left = sum(
        1
        for s in post.get("suspicious") or []
        if "year_as_quantity" in (s.get("reasons") or [])
    )
    print("REBUILD_OK" if year_left == 0 else "REBUILD_CHECK")


if __name__ == "__main__":
    main()
