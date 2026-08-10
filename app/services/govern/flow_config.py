# -*- coding: utf-8 -*-
"""Seed / load / apply flow_config (docs/12 A3 — config-driven stock_flow)."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from app import config
from app.repositories import meta_conn, meta_tx

# 仓库级 flow_config 目录：app/services/govern/flow_config.py → parents[3] = 仓库根
DEFAULT_DIR = Path(__file__).resolve().parents[3] / "data" / "flow_config"


def _config_dir() -> Path:
    env = os.environ.get("FLOW_CONFIG_DIR")
    if env:
        return Path(env)
    return Path(getattr(config, "FLOW_CONFIG_DIR", DEFAULT_DIR))


def _norm(s: str) -> str:
    return str(s).strip().lower().replace(" ", "").replace("\n", "").replace("\r", "")


def _canon_header(s: str) -> str:
    t = str(s or "").replace("\n", "").replace("\r", "").strip()
    for sep in ("（", "("):
        if sep in t:
            t = t.split(sep, 1)[0]
    return _norm(t)


def ensure_flow_configs_seed(*, actor: str = "system:seed") -> dict:
    root = _config_dir()
    if not root.exists():
        root = DEFAULT_DIR
    inserted = 0
    updated = 0
    files = sorted(root.glob("*.json")) if root.exists() else []
    with meta_tx() as con:
        for path in files:
            try:
                cfg = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            sheet = str(cfg.get("source_sheet") or "").strip()
            if not sheet:
                continue
            cid = path.stem
            payload = json.dumps(cfg, ensure_ascii=False)
            row = con.execute(
                "SELECT config_id, config_json FROM flow_config WHERE source_sheet=?",
                [sheet],
            ).fetchone()
            if row:
                if row["config_json"] != payload:
                    con.execute(
                        """
                        UPDATE flow_config
                        SET config_json=?, version=version+1, confirmed_by=?,
                            updated_at=datetime('now')
                        WHERE source_sheet=?
                        """,
                        [payload, actor, sheet],
                    )
                    updated += 1
                continue
            con.execute(
                """
                INSERT INTO flow_config (config_id, source_sheet, config_json, version, confirmed_by)
                VALUES (?, ?, ?, 1, ?)
                """,
                [cid, sheet, payload, actor],
            )
            inserted += 1
            for alias in cfg.get("aliases") or []:
                a = str(alias).strip()
                if not a or a == sheet:
                    continue
                exists = con.execute(
                    "SELECT 1 FROM flow_config WHERE source_sheet=?", [a]
                ).fetchone()
                if exists:
                    continue
                con.execute(
                    """
                    INSERT INTO flow_config (config_id, source_sheet, config_json, version, confirmed_by)
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    [f"{cid}__alias_{len(a)}_{abs(sum(ord(ch) for ch in a))}", a, payload, actor],
                )
                inserted += 1
    _load_all_configs.cache_clear()
    return {"ok": True, "inserted": inserted, "updated": updated, "files": len(files)}


@lru_cache(maxsize=1)
def _load_all_configs() -> tuple[tuple[str, str], ...]:
    """Return ((source_sheet, config_json), ...) snapshot for matching."""
    con = meta_conn()
    try:
        rows = con.execute(
            "SELECT source_sheet, config_json FROM flow_config ORDER BY source_sheet"
        ).fetchall()
        return tuple((str(r["source_sheet"]), str(r["config_json"])) for r in rows)
    finally:
        con.close()


def list_flow_configs() -> list[dict[str, Any]]:
    con = meta_conn()
    try:
        rows = con.execute(
            """
            SELECT config_id, source_sheet, config_json, version, confirmed_by, updated_at
            FROM flow_config
            ORDER BY source_sheet
            """
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["config"] = json.loads(item.pop("config_json"))
            except Exception:
                item["config"] = None
            out.append(item)
        return out
    finally:
        con.close()


def get_flow_config(source_sheet: str | None) -> dict[str, Any] | None:
    """Lookup by exact source_sheet / alias row, then canon / contains match."""
    sheet = str(source_sheet or "").strip()
    if not sheet:
        return None
    try:
        rows = _load_all_configs()
    except Exception:
        return None
    if not rows:
        return None

    def _parse(payload: str) -> dict | None:
        try:
            cfg = json.loads(payload)
            return cfg if isinstance(cfg, dict) else None
        except Exception:
            return None

    for name, payload in rows:
        if name == sheet:
            return _parse(payload)
    ckey = _canon_header(sheet)
    nkey = _norm(sheet)
    for name, payload in rows:
        if _canon_header(name) == ckey or _norm(name) == nkey:
            return _parse(payload)
    # substring: workbook sheet "台账305B_维护材料" vs config "维护材料"
    for name, payload in rows:
        nn = _norm(name)
        if len(nn) >= 2 and (nn in nkey or nkey in nn):
            return _parse(payload)
    return None


def flow_column_for(cfg: dict[str, Any] | None, flow_type: str) -> dict[str, Any] | None:
    if not cfg:
        return None
    ft = (flow_type or "").upper()
    for col in cfg.get("flow_columns") or []:
        if str(col.get("flow_type") or "").upper() == ft:
            return col if isinstance(col, dict) else None
    return None


# --- T3.1: 4-sheet 台账 sheet→域路由（ledger_route.json，LD-3 锁定 2026-08-10）---
_ledger_route_cache: dict | None = None


def _ledger_route_path() -> Path:
    """T3.1: ledger_route.json 静态资产与 flow_config 同源（env FLOW_CONFIG_DIR 优先，
    否则仓库 data/flow_config）。不依赖运行时 config.DATA（可能指向独立数据卷）。"""
    return _config_dir() / "ledger_route.json"


def _load_ledger_route() -> dict:
    """Load sheet→domain route table (static config, cached)."""
    global _ledger_route_cache
    if _ledger_route_cache is not None:
        return _ledger_route_cache
    path = _ledger_route_path()
    if not path.exists():
        _ledger_route_cache = {"version": "0", "sheets": []}
        return _ledger_route_cache
    try:
        _ledger_route_cache = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _ledger_route_cache = {"version": "0", "sheets": []}
    return _ledger_route_cache


def _reload_ledger_route() -> None:
    global _ledger_route_cache
    _ledger_route_cache = None


def get_ledger_route(sheet_name: str | None) -> dict[str, Any] | None:
    """T3.1: map workbook sheet name → {domain, flow}. Exact/canon/contains match.

    Returns e.g. {"sheet": "维护材料", "domain": "inventory", "flow": True}
    """
    sheet = str(sheet_name or "").strip()
    if not sheet:
        return None
    route = _load_ledger_route()
    for item in route.get("sheets") or []:
        s = str(item.get("sheet") or "").strip()
        if not s:
            continue
        if s == sheet:
            return dict(item)
    ckey = _canon_header(sheet)
    nkey = _norm(sheet)
    for item in route.get("sheets") or []:
        s = str(item.get("sheet") or "").strip()
        if _canon_header(s) == ckey or _norm(s) == nkey:
            return dict(item)
    for item in route.get("sheets") or []:
        s = str(item.get("sheet") or "").strip()
        if len(s) >= 2 and (_norm(s) in nkey or nkey in _norm(s)):
            return dict(item)
    for item in route.get("sheets") or []:
        for alias in item.get("aliases") or []:
            a = str(alias or "").strip()
            if not a:
                continue
            if a == sheet or _norm(a) == nkey or _canon_header(a) == ckey:
                return dict(item)
            if len(a) >= 2 and (_norm(a) in nkey or nkey in _norm(a)):
                return dict(item)
    return None


def ledger_sheet_names(domain: str) -> list[str]:
    """T3.1: sheet names routed to a target domain (for staging sheet filtering)."""
    out: list[str] = []
    for item in _load_ledger_route().get("sheets") or []:
        if str(item.get("domain") or "").strip() == domain:
            out.append(str(item.get("sheet") or "").strip())
    return out


def _pick_col(columns: list[str], wanted: str | None) -> str | None:
    if not wanted:
        return None
    by_norm = {_norm(c): c for c in columns}
    by_canon = {_canon_header(c): c for c in columns}
    key = _norm(wanted)
    if key in by_norm:
        return by_norm[key]
    ckey = _canon_header(wanted)
    if ckey in by_canon:
        return by_canon[ckey]
    for c in columns:
        cc = _canon_header(c)
        if cc == ckey or (len(ckey) >= 2 and ckey in cc):
            return c
    return None


def apply_flow_config_columns(
    columns: list[str],
    source_sheet: str | None,
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Overlay flow_config headers/qty/unit onto stock_flow column map (docs/12 A3)."""
    mapping = dict(base or {})
    cfg = get_flow_config(source_sheet)
    if not cfg:
        return mapping
    for fc in cfg.get("flow_columns") or []:
        if not isinstance(fc, dict):
            continue
        ft = str(fc.get("flow_type") or "").upper()
        text_field = "flow_in_text" if ft == "IN" else "flow_out_text" if ft == "OUT" else None
        qty_field = "qty_in" if ft == "IN" else "qty_out" if ft == "OUT" else None
        if not text_field:
            continue
        header = fc.get("header")
        hit = _pick_col(columns, str(header) if header else None)
        if hit:
            mapping[text_field] = hit
        qty_hit = _pick_col(columns, str(fc.get("qty_column") or "") or None)
        if qty_hit and qty_field:
            mapping[qty_field] = qty_hit
        unit_hit = _pick_col(columns, str(fc.get("unit_column") or "") or None)
        if unit_hit:
            mapping["unit"] = unit_hit
    # always retain sheet tag if present
    if "sheet" in {_norm(c): c for c in columns} or any(_canon_header(c) == "sheet" for c in columns):
        for c in columns:
            if _canon_header(c) == "sheet" or _norm(c) == "sheet":
                mapping.setdefault("source_sheet", c)
                break
    return mapping
