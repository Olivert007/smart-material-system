# -*- coding: utf-8 -*-
"""Per-release flow_example snapshot for reproducible lineage rebuild (D6 / mid-risk 4)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import config
from app.repositories import meta_conn


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def snapshot_path(release_id: str) -> Path:
    root = config.STAGING / "_flow_example_snapshots"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{release_id}.json"


def load_live_examples() -> dict[str, dict[str, Any]]:
    con = meta_conn()
    try:
        out: dict[str, dict[str, Any]] = {}
        for r in con.execute("SELECT text_norm, flow_json, level FROM flow_example").fetchall():
            out[str(r["text_norm"])] = {
                "flow_json": r["flow_json"],
                "level": r["level"],
            }
        return out
    finally:
        con.close()


def capture_for_release(release_id: str, *, file_id: str | None = None) -> dict[str, dict[str, Any]]:
    """Freeze current flow_example pool for this release_id (call at confirm write)."""
    examples = load_live_examples()
    path = snapshot_path(release_id)
    payload = {
        "release_id": release_id,
        "file_id": file_id,
        "captured_at": _now(),
        "count": len(examples),
        "examples": [
            {
                "text_norm": k,
                "flow_json": v.get("flow_json"),
                "level": v.get("level"),
            }
            for k, v in examples.items()
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return examples


def load_for_release(release_id: str) -> dict[str, dict[str, Any]] | None:
    """Return frozen examples for rebuild; None if snapshot missing."""
    path = snapshot_path(release_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    out: dict[str, dict[str, Any]] = {}
    for item in data.get("examples") or []:
        if not isinstance(item, dict):
            continue
        tn = item.get("text_norm")
        if not tn:
            continue
        out[str(tn)] = {
            "flow_json": item.get("flow_json"),
            "level": item.get("level"),
        }
    return out
