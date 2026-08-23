# -*- coding: utf-8 -*-
"""Consistent backup batch (docs/06 §2.1) — meta + biz + evidence + staging."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.repositories import pause_writer, resume_writer, writer_is_paused


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _copy_tree(src: Path, dest: Path, *, label: str) -> dict:
    """Copy directory tree; return manifest entry (sha256 of file listing + total bytes)."""
    if not src.exists():
        return {"path": label, "bytes": 0, "files": 0, "missing": True}
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, symlinks=False, ignore_dangling_symlinks=True)
    n_files = 0
    total = 0
    for p in dest.rglob("*"):
        if p.is_file() and not p.is_symlink():
            n_files += 1
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return {"path": label, "bytes": total, "files": n_files, "missing": False}


def create_backup(tag: str | None = None) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{ts}_{tag}" if tag else ts
    dest = config.BACKUP / name
    dest.mkdir(parents=True, exist_ok=False)

    pause_writer()
    try:
        files: list[dict] = []
        for src in (config.META_DB, config.BIZ_DB):
            if not src.exists():
                continue
            target = dest / src.name
            shutil.copy2(src, target)
            for suffix in ("-wal", "-shm"):
                side = Path(str(src) + suffix)
                if side.exists():
                    shutil.copy2(side, dest / side.name)
            files.append({"path": src.name, "sha256": _sha256(target), "bytes": target.stat().st_size})

        # Evidence + staging parquet trees (needed for A6 rebuild / audit after restore)
        evidence_meta = _copy_tree(config.RAW, dest / "raw_evidence", label="raw_evidence/")
        staging_meta = _copy_tree(config.STAGING, dest / "staging", label="staging/")
        files.append(evidence_meta)
        files.append(staging_meta)

        index = {
            "created_at": ts,
            "files": files,
            "writer_paused": True,
            "includes_evidence": not evidence_meta.get("missing"),
            "includes_staging": not staging_meta.get("missing"),
        }
        manifest = dest / "MANIFEST.json"
        manifest.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"backup_id": name, "path": str(dest), "manifest": index}
    finally:
        resume_writer()
        assert not writer_is_paused()


def list_backups(*, limit: int = 20) -> dict:
    root = config.BACKUP
    root.mkdir(parents=True, exist_ok=True)
    dirs = sorted(
        (p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")),
        key=lambda x: x.name,
        reverse=True,
    )
    total = len(dirs)
    items: list[dict] = []
    for p in dirs[: max(1, min(limit, 100))]:
        manifest_path = p / "MANIFEST.json"
        created_at = None
        files_n = None
        if manifest_path.exists():
            try:
                man = json.loads(manifest_path.read_text(encoding="utf-8"))
                created_at = man.get("created_at")
                files_n = len(man.get("files") or [])
            except Exception:
                pass
        items.append(
            {
                "backup_id": p.name,
                "path": str(p),
                "created_at": created_at or p.name.split("_")[0],
                "files": files_n,
            }
        )
    return {"total": total, "items": items, "backup_root": str(root)}


def _drill_path() -> Path:
    config.BACKUP.mkdir(parents=True, exist_ok=True)
    return config.BACKUP / "restore_drill.json"


def get_restore_drill() -> dict:
    path = _drill_path()
    if not path.exists():
        return {
            "recorded": False,
            "message": "尚未登记恢复演练；未演练前不承诺生产级备份恢复能力。",
            "record": None,
        }
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "recorded": False,
            "message": f"演练记录损坏：{e}",
            "record": None,
        }
    return {
        "recorded": True,
        "message": "已登记恢复演练记录（人工确认，非自动恢复执行）。",
        "record": record,
    }


def record_restore_drill(
    *,
    actor: str,
    note: str = "",
    result: str = "ok",
    backup_id: str | None = None,
) -> dict:
    """Append-only style: overwrite single latest drill record (explicit UI action)."""
    path = _drill_path()
    record = {
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "actor": actor,
        "note": note or "人工确认已完成恢复演练",
        "result": result,
        "backup_id": backup_id,
        "auto_restore": False,
        "disclaimer": "本记录仅证明演练登记，不执行自动全量恢复。",
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "record": record}