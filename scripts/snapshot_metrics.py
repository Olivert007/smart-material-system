#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 分析面：业务指标快照调度（question/03 剩余 2）。

遍历全部 active 指标（BUSINESS_METRICS + FLOW_* 等），evaluate_metric(write_snapshot=True)
写入 metric_snapshot，供趋势曲线/快照对比。建议 cron 每天一次：
  0 2 * * * cd /workspace/2026-07/smart-material-system && python3 scripts/snapshot_metrics.py >> /tmp/metric_snapshot.log 2>&1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.metrics import evaluate_metric, list_metrics  # noqa: E402


def main() -> int:
    metrics = (list_metrics(status="active").get("items") or [])
    written, skipped = 0, 0
    for m in metrics:
        mid = m.get("metric_id")
        if not mid:
            continue
        try:
            out = evaluate_metric(mid, write_snapshot=True)
        except Exception as e:  # noqa: BLE001
            print("SKIP", mid, str(e)[:120])
            skipped += 1
            continue
        if out.get("snapshot_written"):
            written += 1
            print("SNAP", mid, out.get("value"), out.get("unit") or "")
        else:
            skipped += 1
    print(f"SNAPSHOT_DONE total={len(metrics)} written={written} skipped={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
