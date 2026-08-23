# -*- coding: utf-8 -*-
"""行级证据：发布结果行 → 来源原始值 + 规整值 + 血缘链条（optv1/05 Q11）。

从「数据成果」某一行进入：定位 fact_release_rows 的 row_key，
用发布时保留的来源快照（raw parquet，旧发布回退到 payload parquet）重建
「来源列/来源值 → 标准字段/规整值」对照，并汇总发布版本、字段映射、
规则依据、物资匹配、人工确认与处理任务。
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from app.repositories import biz_conn, meta_conn
from app.services import field_dict as fd
from app.services.govern.mapping import resolve_columns
from app.services.intake.staging import staging_payload_path
from app.services.infra.writer import DOMAIN_FACT_TABLE

_TECH_SKIP = {
    "row_key",
    "file_id",
    "target_domain",
    "source_release_id",
    "source_file",
    "source_sheet",
    "source_row",
    "source_segment",
    "source_era",
    "color_flag",
    "parse_level",
    "parse_source",
}


def _json_safe(v: Any) -> Any:
    if v is None:
        return None
    # numpy 标量（fetchdf 读取）：统一转 python 标量
    if hasattr(v, "item"):
        try:
            v = v.item()
        except Exception:
            pass
    if isinstance(v, float) and v != v:
        return None
    if isinstance(v, (int, float, str, bool)):
        return v
    try:
        return str(v)[:500]
    except Exception:
        return None


def _values_equal(a: Any, b: Any) -> bool:
    """规整前后值比较：容忍类型差异（Excel 原始值常为 str，规整值为数值）。"""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    # 数字字符串与数值（如 "0" vs 0、1.0 vs 1）按数值比较
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def _cell(df: pd.DataFrame, idx: int, col: str | None) -> Any:
    if col is None or col not in df.columns:
        return None
    if idx < 0 or idx >= len(df):
        return None
    return _json_safe(df.iloc[idx][col])


def _row_index(df: pd.DataFrame, row_key: str, payload: dict, domain: str) -> int:
    """把 row_key / payload 定位到来源帧行号（与发布时枚举一致，1 基转 0 基）。"""
    if domain == "stock_flow":
        try:
            return max(0, int(payload.get("source_row") or 1) - 1)
        except (TypeError, ValueError):
            pass
    if row_key.startswith("r") and row_key[1:].isdigit():
        return int(row_key[1:])
    tail = row_key.rsplit("|", 1)[-1]
    if tail.isdigit():
        return max(0, int(tail) - 1)
    # 兜底：按物资名称/编码匹配来源行
    try:
        mapping = resolve_columns(df, domain)
    except Exception:
        mapping = {}
    name_col = mapping.get("material_name") or mapping.get("asset_name")
    code_col = mapping.get("material_code") or mapping.get("asset_code")
    for i, rec in enumerate(df.to_dict(orient="records")):
        if name_col and rec.get(name_col):
            want = payload.get("material_name") or payload.get("asset_name")
            if want and str(rec.get(name_col)) != str(want):
                continue
        if code_col and rec.get(code_col):
            want = payload.get("material_code")
            if want and str(rec.get(code_col)) != str(want):
                continue
        return i
    return 0


def row_evidence(release_id: str, row_key: str) -> dict[str, Any]:
    if not release_id or not row_key:
        raise KeyError("release_id and row_key required")

    con = biz_conn()
    try:
        df = con.execute(
            """
            SELECT source_release_id, file_id, target_domain, row_key, payload_json
            FROM fact_release_rows
            WHERE source_release_id=? AND row_key=?
            """,
            [release_id, row_key],
        ).fetchdf()
    finally:
        con.close()
    if df is None or len(df) == 0:
        raise KeyError("release row not found")
    row = df.iloc[0].to_dict()

    payload = json.loads(row["payload_json"] or "{}")
    if not isinstance(payload, dict):
        payload = {}
    domain = str(row["target_domain"] or "")
    file_id = str(row["file_id"] or "")
    source_file = str(payload.get("source_file") or file_id)
    source_sheet = payload.get("source_sheet")
    source_row = payload.get("source_row")

    release: dict[str, Any] = {}
    staging: dict[str, Any] = {}
    task: dict[str, Any] | None = None
    confirms: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    config_version = "v1"
    with meta_conn() as mcon:
        rm = mcon.execute(
            "SELECT * FROM release_manifest WHERE release_id=?", [release_id]
        ).fetchone()
        if rm:
            release = {k: _json_safe(v) for k, v in dict(rm).items()}
        st = mcon.execute(
            """
            SELECT config_version, status, version
            FROM staging_record
            WHERE file_id=? AND target_domain=?
            ORDER BY updated_at DESC LIMIT 1
            """,
            [file_id, domain],
        ).fetchone()
        if st:
            staging = {k: _json_safe(v) for k, v in dict(st).items()}
            config_version = str(staging.get("config_version") or config_version)
        else:
            config_version = str(release.get("config_version") or config_version)
        for r in mcon.execute(
            """
            SELECT source, detail, decision, note, actor, created_at
            FROM govern_confirm
            WHERE detail LIKE ? OR note LIKE ?
            ORDER BY created_at DESC LIMIT 20
            """,
            [f"%{release_id}%", f"%{release_id}%"],
        ).fetchall():
            confirms.append({k: _json_safe(v) for k, v in dict(r).items()})
        for r in mcon.execute(
            """
            SELECT action, actor, detail_json, created_at
            FROM write_audit
            WHERE release_id=?
            ORDER BY created_at DESC LIMIT 20
            """,
            [release_id],
        ).fetchall():
            audit.append({k: _json_safe(v) for k, v in dict(r).items()})
        if file_id:
            t = mcon.execute(
                """
                SELECT task_id, task_type, status, progress, message, created_at, finished_at
                FROM intake_task
                WHERE file_id=?
                ORDER BY created_at DESC LIMIT 1
                """,
                [file_id],
            ).fetchone()
            if t:
                task = {k: _json_safe(v) for k, v in dict(t).items()}

    # 来源行：优先 raw 快照（接入时读取的原始列/值），回退发布载荷 parquet
    payload_path = staging_payload_path(file_id, config_version, domain)
    raw_path = payload_path.with_name(f"{payload_path.stem}_raw{payload_path.suffix}")
    raw_df: pd.DataFrame | None = None
    try:
        src = raw_path if raw_path.exists() else payload_path
        if src.exists():
            raw_df = pd.read_parquet(src)
    except Exception:
        raw_df = None

    mapping: dict[str, str] = {}
    if raw_df is not None and len(raw_df) > 0:
        try:
            mapping = resolve_columns(raw_df, domain)
        except Exception:
            mapping = {}
    idx = 0
    if raw_df is not None and len(raw_df) > 0:
        idx = _row_index(raw_df, row_key, payload, domain)

    table = DOMAIN_FACT_TABLE.get(domain, "fact_release_rows")
    compare: list[dict[str, Any]] = []
    for field, val in payload.items():
        if field in _TECH_SKIP:
            continue
        header = mapping.get(field) if mapping else None
        raw_val = _cell(raw_df, idx, header) if raw_df is not None else None
        clean_val = _json_safe(val)
        compare.append(
            {
                "field": field,
                "field_zh": fd.table_field_zh(table, field),
                "source_header": header,
                "raw_value": raw_val,
                "clean_value": clean_val,
                "changed": (not _values_equal(raw_val, clean_val)) if raw_val is not None else None,
            }
        )

    material: dict[str, Any] = {}
    mid = payload.get("material_id")
    if mid:
        con2 = biz_conn()
        try:
            mdf = con2.execute(
                """
                SELECT material_code, material_name, spec, unit, category,
                       match_level, code_source, name_alias, spec_alias, source_release_id
                FROM dim_material WHERE material_id=?
                """,
                [mid],
            ).fetchdf()
            if mdf is not None and len(mdf) > 0:
                material = {k: _json_safe(v) for k, v in mdf.iloc[0].to_dict().items()}
                material["material_id"] = mid
        finally:
            con2.close()

    rule_hits: list[dict[str, Any]] = []
    if mapping:
        with meta_conn() as mcon:
            for std_field, header in mapping.items():
                r = mcon.execute(
                    """
                    SELECT header, std_field, business_domain, source, confirmed_by, status, updated_at
                    FROM rule_dict WHERE header=? AND std_field=?
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    [header, std_field],
                ).fetchone()
                if r:
                    rule_hits.append({k: _json_safe(v) for k, v in dict(r).items()})

    return {
        "ok": True,
        "release_id": release_id,
        "row_key": row_key,
        "domain": domain,
        "source_file": source_file,
        "source_sheet": source_sheet,
        "source_row": source_row,
        "source_file_id": file_id,
        "release": release,
        "staging": staging,
        "task": task,
        "material": material,
        "mapping": [
            {"std_field": k, "source_header": v} for k, v in mapping.items()
        ],
        "rule_hits": rule_hits,
        "confirms": confirms,
        "audit": audit,
        "compare": compare,
        "note": (
            "来源值为接入时读取的原始列/单元格值（raw 快照，旧发布回退到发布载荷）；"
            "规整值为发布版本中的值。"
        ),
    }
