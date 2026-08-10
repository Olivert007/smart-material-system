#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 分析面：预置受控只读报表种子（幂等 upsert，question/03 建议 5 / UI-5）。

种子定义收敛于 app/services/report_runner.SEED_REPORTS，此处仅为手工触发入口；
服务启动时由 main.py lifespan 的 ensure_report_seed() 自动执行（幂等）。

用法：python3 scripts/seed_reports.py [--run]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.report_runner import (  # noqa: E402
    SEED_REPORTS,
    ensure_report_seed,
    run_report,
)


def main() -> int:
    out = ensure_report_seed(actor="seed:p2")
    print("SEED", out)
    if "--run" in sys.argv:
        for s in SEED_REPORTS:
            try:
                r = run_report(s["report_id"], actor="seed:p2")
                print("  RUN", s["report_id"], r["status"], "rows=", r["row_count"])
            except Exception as e:  # noqa: BLE001
                print("  RUN FAIL", s["report_id"], str(e)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
