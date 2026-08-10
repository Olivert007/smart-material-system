# -*- coding: utf-8 -*-
"""Upload size / batch / directory quota checks (docs/05 §1.4)."""
from __future__ import annotations

from pathlib import Path

from app import config


def dir_usage_bytes(root: Path | None = None) -> int:
    """Bytes under uploads/ (formal + tmp), following files only."""
    base = root or config.UPLOAD
    if not base.exists():
        return 0
    total = 0
    for p in base.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def assert_dir_quota(*, incoming_bytes: int) -> None:
    """Raise ValueError with code if uploads dir would exceed quota."""
    used = dir_usage_bytes()
    limit = config.UPLOAD_DIR_QUOTA_BYTES
    if used + max(0, incoming_bytes) > limit:
        raise ValueError(
            f"UPLOAD_DIR_QUOTA: used={used} incoming={incoming_bytes} limit={limit}"
        )


def assert_batch_limits(*, file_count: int, batch_bytes: int) -> None:
    if file_count < 1:
        raise ValueError("UPLOAD_EMPTY_BATCH: no files")
    if file_count > config.UPLOAD_MAX_FILES:
        raise ValueError(
            f"UPLOAD_MAX_FILES: count={file_count} limit={config.UPLOAD_MAX_FILES}"
        )
    if batch_bytes > config.UPLOAD_MAX_BATCH_BYTES:
        raise ValueError(
            f"UPLOAD_MAX_BATCH_BYTES: bytes={batch_bytes} limit={config.UPLOAD_MAX_BATCH_BYTES}"
        )


def parse_limit_error(exc: ValueError) -> tuple[str, str]:
    msg = str(exc)
    code = msg.split(":", 1)[0].strip() if ":" in msg else "UPLOAD_LIMIT"
    return code, msg
