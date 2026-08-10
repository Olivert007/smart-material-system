#!/usr/bin/env python3
"""Wave 3: 一键样例接入（上传→等待→staging 提示）。

用法: python3 scripts/run_ledger_sample.py [xlsx路径]
默认查找 data/samples/ 下第一个 xlsx；若无则自 fixture 生成。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from ledger_xlsx_util import build_ledger_xlsx_from_fixture  # noqa: E402


def main() -> int:
    sample = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if sample is None:
        samples = sorted((ROOT / "data" / "samples").glob("*.xlsx"))
        if samples:
            sample = samples[0]
        else:
            out = ROOT / "data" / "samples" / "ce84beaa91ca.xlsx"
            sample = build_ledger_xlsx_from_fixture(out_path=out)
            print(f"已从 fixture 生成: {sample}")
    if not sample.is_file():
        print(f"文件不存在: {sample}")
        return 1

    client = TestClient(app)
    with sample.open("rb") as f:
        res = client.post(
            "/api/v1/files",
            files={"file": (sample.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    if res.status_code not in (200, 202):
        print(res.status_code, res.text)
        return 1
    body = res.json()
    print("upload:", body)
    task_id = body.get("task_id")
    file_id = body.get("file_id")
    if not task_id:
        print("无 task_id（可能复用已有文件）")
        return 0
    for _ in range(120):
        t = client.get(f"/api/v1/tasks/{task_id}").json()
        print("task:", t.get("status"), t.get("progress"), t.get("message", ""))
        if t.get("status") in ("done", "failed", "pending_govern"):
            break
        time.sleep(1)
    print(f"下一步: 浏览器打开 /stage/{file_id} 完成 Staging 确认")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
