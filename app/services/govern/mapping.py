# -*- coding: utf-8 -*-
"""Map tabular staging frames into star-schema rows (Phase A rule-based)."""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

ALIASES: dict[str, dict[str, list[str]]] = {
    "inventory": {
        "material_name": ["material_name", "name", "物资名称", "名称", "品名", "item_name"],
        "material_code": ["material_code", "code", "物资编码", "编码"],
        "spec": ["spec", "规格", "规格型号", "型号规格", "specification"],
        "stock_qty": ["stock_qty", "qty", "quantity", "现有库存", "现有库存数值", "现有数量", "统一现有数量", "可用数量", "数量"],
        "quota_qty": ["quota_qty", "定额", "定额数量", "定额数量数值", "储备定额", "部门备件储备定额"],
        "unit": ["unit", "单位", "计量单位", "库存计量单位", "统一计量单位"],
        "location": ["location", "存放位置", "库位", "库位号", "位置", "存放货位"],
        "custodian": ["custodian", "保管人", "领用人", "管理员"],
        "region": ["region", "区域", "域", "域描述"],
        "category": ["category", "类别", "物资种类", "物资大类", "物资大类描述"],
        # T2: ledger-export-plan §8.1（LD-1 锁定 2026-08-10）
        "opening_qty": ["opening_qty", "初始库存", "期初数量", "期初库存"],
        "min_qty": ["min_qty", "最低库存阈值", "最低库存"],
        "company_wh_qty": ["company_wh_qty", "公司仓库数量"],
        "remark": ["remark", "备注"],
        "belong_system": ["belong_system", "所属系统"],
        "project_name": ["project_name", "项目名称"],
        "consumption_plan": ["consumption_plan", "消耗计划"],
        "material_source": ["material_source", "物资来源"],
        "group_code": ["group_code", "新集团编码"],
        "is_frame_material": ["is_frame_material", "是否框架物资"],
        "agreement_supplier": ["agreement_supplier", "协议供应商名称"],
        "frame_material_code": ["frame_material_code", "推荐框架物资编码"],
        "frame_material_name": ["frame_material_name", "推荐框架物资名称"],
        "frame_material_spec": [
            "frame_material_spec",
            "推荐框架物资型号规格",
            "推荐框架物资型号",
        ],
        "frame_material_supplier": ["frame_material_supplier", "推荐框架物资供应商"],
        "emergency_supplier": ["emergency_supplier", "应急供应商名称"],
    },
    "demand": {
        "material_name": ["material_name", "name", "物资名称", "名称", "品名"],
        "material_code": ["material_code", "code", "物资编码", "编码", "统一编码", "商品编号"],
        "quantity": ["quantity", "qty", "数量"],
        "unit_price": ["unit_price", "单价", "三峡e购单价", "三峡e购单价（元）"],
        "total_price": ["total_price", "合价", "金额", "合价（元）"],
        "unit": ["unit", "单位"],
        "demand_period": ["demand_period", "period", "期次", "需求期次"],
        "reporter": ["reporter", "填报人"],
        "remark": ["remark", "备注"],
    },
    "asset": {
        "asset_code": ["asset_code", "资产编码", "资产编号", "实物资产编码", "编码"],
        "asset_name": ["asset_name", "资产名称", "实物资产名称", "名称", "name"],
        "company": ["company", "公司"],
        "domain": ["domain", "域"],
        "user_name": ["user_name", "使用人", "使用人姓名"],
        "manager": ["manager", "管理者", "管理者姓名"],
        "location": ["location", "位置", "位置描述"],
        "purchase_date": ["purchase_date", "购买日期"],
        "status": ["status", "状态"],
        "check_result": ["check_result", "核对结果"],
        "spec": ["spec", "规格", "规格型号", "型号规格"],
        "serial_no": ["serial_no", "出厂编号", "序列号", "SN"],
        # T2: ledger-export-plan §8.2（LD-1/LD-2 锁定 2026-08-10）；「备注」优先落 remark
        "remark": ["remark", "备注"],
        "material_code": ["material_code", "物资编码"],
        "asset_qty": ["asset_qty", "数量"],
        "unit": ["unit", "单位", "计量单位"],
        "is_instrument": ["is_instrument", "是否仪器仪表"],
        "replace_cycle": ["replace_cycle", "更换周期（年）"],
        "check_cycle": ["check_cycle", "检测周期（年）"],
        "consumption_plan": ["consumption_plan", "消耗计划"],
        "tool_source": ["tool_source", "工器具来源"],
        "asset_quota_qty": ["asset_quota_qty", "定额数量"],
    },
    "stock_flow": {
        "material_name": ["material_name", "name", "物资名称", "名称", "品名"],
        "material_code": ["material_code", "code", "物资编码", "编码", "物料编码"],
        "unit": ["unit", "单位", "计量单位"],
        "flow_in_text": ["入库记录", "入库文本", "flow_in_text"],
        "flow_out_text": ["出库记录", "出库记录（ZW）", "出库文本", "flow_out_text"],
        "qty_in": ["入库数量", "qty_in"],
        "qty_out": ["出库数量", "qty_out"],
        "source_sheet": ["sheet", "sheet_name", "工作表"],
    },
}


def _norm(s: str) -> str:
    return str(s).strip().lower().replace(" ", "").replace("\n", "").replace("\r", "")


def _canon_header(s: str) -> str:
    """Strip parenthetical notes / newlines so '入库记录（…）' → '入库记录'."""
    t = str(s or "").replace("\n", "").replace("\r", "").strip()
    for sep in ("（", "("):
        if sep in t:
            t = t.split(sep, 1)[0]
    return _norm(t)


def resolve_columns(
    df: pd.DataFrame,
    domain: str,
    *,
    source_sheet: str | None = None,
) -> dict[str, str]:
    alias = ALIASES.get(domain, {})
    cols = list(df.columns)
    by_norm = {_norm(c): c for c in cols}
    by_canon = {_canon_header(c): c for c in cols}
    mapping: dict[str, str] = {}
    for target, names in alias.items():
        for n in names:
            key = _norm(n)
            if key in by_norm:
                mapping[target] = by_norm[key]
                break
            ckey = _canon_header(n)
            if ckey in by_canon:
                mapping[target] = by_canon[ckey]
                break
            # prefix / contains for long Excel headers (305B / ZW)
            hit = None
            for c in cols:
                cn = _norm(c)
                cc = _canon_header(c)
                if cn.startswith(key) or cc == ckey or (len(ckey) >= 2 and ckey in cc):
                    hit = c
                    break
            if hit:
                mapping[target] = hit
                break
    # Infer sheet from a uniform `sheet` column when caller omitted source_sheet
    sheet = source_sheet
    if not sheet and "sheet" in by_norm:
        try:
            vals = {str(v).strip() for v in df[by_norm["sheet"]].dropna().unique().tolist() if str(v).strip()}
            if len(vals) == 1:
                sheet = next(iter(vals))
        except Exception:
            sheet = None
    if domain == "stock_flow":
        try:
            from app.services.flow_config import apply_flow_config_columns

            mapping = apply_flow_config_columns(cols, sheet, mapping)
        except Exception:
            pass
    # docs/04 §6: rule_dict overrides ALIASES (confirmed human mappings)
    try:
        from app.services.rule_dict import apply_rule_overrides

        mapping = apply_rule_overrides(cols, domain, mapping)
    except Exception:
        # meta unavailable in some unit contexts — keep ALIASES-only map
        pass
    return mapping


# LD-4 (2026-08-10)：台账「50+ / 150+」等去后缀写法 → 解析为数值，避免静默 NULL
_NUM_SUFFIX_RE = re.compile(r"^([-+]?\d+(?:\.\d+)?)\s*[+＋]\s*$")


def _num(v: Any) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().replace(",", "").replace("，", "")
    if not s:
        return None
    m = _NUM_SUFFIX_RE.match(s)
    if m:
        return float(m.group(1))
    try:
        return float(s)
    except (TypeError, ValueError):
        # 解析失败：返回 None 由调用方处理；T5 完整版将此类值进 staging_blocked（VALUE_RANGE）
        return None


def _str(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    t = str(v).strip()
    return "" if t.lower() in {"nan", "none", "/", "-", "--"} else t


def flow_lineage_row_key(
    *,
    source_file: str,
    source_sheet: str,
    source_row: int | str,
    source_segment: int | str,
    flow_type: str,
) -> str:
    """A5.2 stable lineage key: source_file|sheet|row|segment|flow_type."""
    return (
        f"{source_file}|{source_sheet}|{source_row}|{source_segment}|{flow_type}"
    )


def _get(data: dict, mapping: dict[str, str], field: str) -> Any:
    col = mapping.get(field)
    if not col:
        return None
    return data.get(col)


def build_domain_rows(
    df: pd.DataFrame,
    *,
    domain: str,
    file_id: str,
    release_id: str,
    source_file: str,
    examples: dict[str, dict] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    if domain == "generic" or domain not in ALIASES:
        rows = []
        for i, rec in enumerate(df.to_dict(orient="records")):
            rows.append(
                {
                    "source_release_id": release_id,
                    "file_id": file_id,
                    "target_domain": domain,
                    "row_key": f"r{i}",
                    "_payload": rec,
                }
            )
        return "fact_release_rows", rows

    mapping = resolve_columns(df, domain)
    rows: list[dict[str, Any]] = []

    if domain == "inventory":
        for i, data in enumerate(df.to_dict(orient="records"), 1):
            name = _str(_get(data, mapping, "material_name"))
            code = _str(_get(data, mapping, "material_code"))
            if not name and not code:
                continue
            mid = code or f"M-{file_id}-{i}"
            rows.append(
                {
                    "inventory_id": f"INV-{release_id}-{i}",
                    "material_id": mid,
                    "region": _str(_get(data, mapping, "region")) or "未知",
                    "category": _str(_get(data, mapping, "category")) or "未分类",
                    "source_file": source_file,
                    "source_era": "",
                    "color_flag": "",
                    "stock_qty": _num(_get(data, mapping, "stock_qty")),
                    "opening_qty": _num(_get(data, mapping, "opening_qty")),
                    "quota_qty": _num(_get(data, mapping, "quota_qty")),
                    "min_qty": _num(_get(data, mapping, "min_qty")),
                    "temp_qty": None,
                    "company_wh_qty": _num(_get(data, mapping, "company_wh_qty")),
                    "age_days": None,
                    "unit_cost": None,
                    "stock_value": None,
                    "unit": _str(_get(data, mapping, "unit")),
                    "location": _str(_get(data, mapping, "location")),
                    "custodian": _str(_get(data, mapping, "custodian")),
                    # T2: ledger-export-plan §8.1（LD-1 锁定 2026-08-10）
                    "remark": _str(_get(data, mapping, "remark")),
                    "belong_system": _str(_get(data, mapping, "belong_system")),
                    "project_name": _str(_get(data, mapping, "project_name")),
                    "consumption_plan": _str(_get(data, mapping, "consumption_plan")),
                    "material_source": _str(_get(data, mapping, "material_source")),
                    "group_code": _str(_get(data, mapping, "group_code")),
                    "is_frame_material": _str(_get(data, mapping, "is_frame_material")),
                    "agreement_supplier": _str(_get(data, mapping, "agreement_supplier")),
                    "frame_material_code": _str(_get(data, mapping, "frame_material_code")),
                    "frame_material_name": _str(_get(data, mapping, "frame_material_name")),
                    "frame_material_spec": _str(_get(data, mapping, "frame_material_spec")),
                    "frame_material_supplier": _str(
                        _get(data, mapping, "frame_material_supplier")
                    ),
                    "emergency_supplier": _str(_get(data, mapping, "emergency_supplier")),
                    # T7: source_sheet 优先取映射列，回退到台账 sheet 标记列（T3.2）
                    "source_sheet": _str(_get(data, mapping, "source_sheet"))
                    or _str(data.get("sheet")),
                    "source_release_id": release_id,
                    "_material_name": name,
                    "_material_code": code,
                    "_spec": _str(_get(data, mapping, "spec")),
                }
            )
        return "fact_inventory", rows

    if domain == "demand":
        for i, data in enumerate(df.to_dict(orient="records"), 1):
            name = _str(_get(data, mapping, "material_name"))
            code = _str(_get(data, mapping, "material_code"))
            if not name and not code and "quantity" not in mapping:
                continue
            mid = code or f"M-{file_id}-{i}"
            rows.append(
                {
                    "demand_id": f"DEM-{release_id}-{i}",
                    "material_id": mid,
                    "demand_period": _str(_get(data, mapping, "demand_period")) or "unknown",
                    "quantity": _num(_get(data, mapping, "quantity")),
                    "unit_price": _num(_get(data, mapping, "unit_price")),
                    "total_price": _num(_get(data, mapping, "total_price")),
                    "unit": _str(_get(data, mapping, "unit")),
                    "reporter": _str(_get(data, mapping, "reporter")),
                    "remark": _str(_get(data, mapping, "remark")),
                    "source_file": source_file,
                    "source_release_id": release_id,
                    "_material_name": name,
                    "_material_code": code,
                }
            )
        return "fact_demand", rows

    if domain == "asset":
        for i, data in enumerate(df.to_dict(orient="records"), 1):
            code = _str(_get(data, mapping, "asset_code")) or f"A-{file_id}-{i}"
            name = _str(_get(data, mapping, "asset_name"))
            if not name and "asset_code" not in mapping:
                continue
            rows.append(
                {
                    "asset_code": code,
                    "asset_name": name,
                    "company": _str(_get(data, mapping, "company")),
                    "domain": _str(_get(data, mapping, "domain")),
                    "user_name": _str(_get(data, mapping, "user_name")),
                    "manager": _str(_get(data, mapping, "manager")),
                    "location": _str(_get(data, mapping, "location")),
                    "purchase_date": _str(_get(data, mapping, "purchase_date")),
                    "status": _str(_get(data, mapping, "status")),
                    "check_result": _str(_get(data, mapping, "check_result")),
                    # T2: ledger-export-plan §8.2（LD-1/LD-2 锁定 2026-08-10）
                    "material_code": _str(_get(data, mapping, "material_code")),
                    "asset_qty": _num(_get(data, mapping, "asset_qty")),
                    "unit": _str(_get(data, mapping, "unit")),
                    "is_instrument": _str(_get(data, mapping, "is_instrument")),
                    "replace_cycle": _num(_get(data, mapping, "replace_cycle")),
                    "check_cycle": _num(_get(data, mapping, "check_cycle")),
                    "consumption_plan": _str(_get(data, mapping, "consumption_plan")),
                    "tool_source": _str(_get(data, mapping, "tool_source")),
                    "asset_quota_qty": _num(_get(data, mapping, "asset_quota_qty")),
                    "remark": _str(_get(data, mapping, "remark")),
                    "source_file": source_file,
                    "color_flag": "",
                    # T7: source_sheet 优先取映射列，回退到台账 sheet 标记列（T3.2）
                    "source_sheet": _str(_get(data, mapping, "source_sheet"))
                    or _str(data.get("sheet")),
                    "source_release_id": release_id,
                }
            )
        return "fact_asset", rows

    if domain == "stock_flow":
        table, rows, _pending, _stats = build_stock_flow_bundle(
            df,
            file_id=file_id,
            release_id=release_id,
            source_file=source_file,
            examples=examples,
        )
        return table, rows

    return "fact_release_rows", []


def build_stock_flow_bundle(
    df: pd.DataFrame,
    *,
    file_id: str,
    release_id: str,
    source_file: str,
    examples: dict[str, dict] | None = None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Return (table, l1_rows, pending, stats) for stock_flow domain.

    examples: optional frozen flow_example map (release snapshot). When None, load live meta.
    """
    mapping = resolve_columns(df, "stock_flow")
    from app.services.flow_parse import FlowFields, parse_flow_cell, text_norm
    from app.services.flow_config import flow_column_for, get_flow_config
    from app.repositories import meta_conn
    import json as _json

    if examples is None:
        examples = {}
        con = meta_conn()
        try:
            for r in con.execute("SELECT text_norm, flow_json, level FROM flow_example").fetchall():
                examples[r["text_norm"]] = {"flow_json": r["flow_json"], "level": r["level"]}
        finally:
            con.close()

    rows: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    stats = {"L1": 0, "L2": 0, "L3": 0, "segments": 0, "config_hits": 0, "material_aligned": 0}
    seq = 0
    cfg_cache: dict[str, dict | None] = {}
    from app.services.material_align import accepted_maps, resolve_material_id, _inventory_universe

    align_maps = accepted_maps()
    inv_universe = _inventory_universe()
    for i, data in enumerate(df.to_dict(orient="records"), 1):
        name = _str(_get(data, mapping, "material_name"))
        code = _str(_get(data, mapping, "material_code"))
        if not name and not code:
            continue
        spec = _str(_get(data, mapping, "spec"))
        mid, align_hit = resolve_material_id(
            code=code,
            name=name,
            spec=spec,
            file_id=file_id,
            row_index=i,
            universe=inv_universe,
            maps=align_maps,
        )
        if align_hit and (
            align_hit.get("unique") or align_hit.get("match_kind") == "accepted_map"
        ):
            stats["material_aligned"] = int(stats.get("material_aligned") or 0) + 1
        unit_col = _str(_get(data, mapping, "unit")) or None
        sheet = _str(_get(data, mapping, "source_sheet")) or "Sheet1"
        if sheet not in cfg_cache:
            cfg_cache[sheet] = get_flow_config(sheet)
        cfg = cfg_cache[sheet]
        if cfg:
            stats["config_hits"] = int(stats.get("config_hits") or 0) + 1
        src_row = i
        for direction, field, qty_field in (
            ("IN", "flow_in_text", "qty_in"),
            ("OUT", "flow_out_text", "qty_out"),
        ):
            text = _str(_get(data, mapping, field))
            if not text:
                continue
            col_qty = _num(_get(data, mapping, qty_field))
            fcol = flow_column_for(cfg, direction)
            seps = list(fcol.get("separators") or []) if fcol else None
            if fcol and not unit_col and fcol.get("unit_column"):
                unit_col = _str(data.get(str(fcol["unit_column"]))) or unit_col
            if fcol and col_qty is None and fcol.get("qty_column"):
                col_qty = _num(data.get(str(fcol["qty_column"])))
            tn = text_norm(text)
            parsed: list[FlowFields] = []
            if tn in examples:
                try:
                    cached = _json.loads(examples[tn]["flow_json"])
                    if isinstance(cached, list):
                        for item in cached:
                            if not isinstance(item, dict):
                                continue
                            parsed.append(
                                FlowFields(
                                    flow_type=item.get("flow_type", direction),
                                    flow_date=item.get("flow_date"),
                                    quantity=item.get("quantity"),
                                    unit=item.get("unit") or unit_col,
                                    person=item.get("person"),
                                    purpose=item.get("purpose"),
                                    remark=item.get("remark") or text,
                                    parse_level=item.get("parse_level")
                                    or examples[tn].get("level")
                                    or "L2",
                                    parse_source="example",
                                    source_segment=int(item.get("source_segment") or 0),
                                    flags=list(item.get("flags") or []),
                                )
                            )
                except Exception:
                    parsed = []
            if not parsed:
                parsed = parse_flow_cell(
                    text,
                    flow_type=direction,
                    col_qty=col_qty,
                    col_unit=unit_col,
                    separators=seps or None,
                    parse_source="rule",
                )
            for ff in parsed:
                stats["segments"] += 1
                stats[ff.parse_level] = stats.get(ff.parse_level, 0) + 1
                suggested = ff.to_dict()
                suggested.update(
                    {
                        "material_id": mid,
                        "source_sheet": sheet,
                        "source_row": src_row,
                        "text_raw": text,
                        "text_norm": tn,
                        "flow_config_sheet": (cfg or {}).get("source_sheet") if cfg else None,
                    }
                )
                if ff.parse_level == "L1":
                    seq += 1
                    rows.append(
                        {
                            "flow_id": f"FL-{release_id}-{seq}",
                            "material_id": mid,
                            "flow_type": ff.flow_type,
                            "flow_date": ff.flow_date,
                            "quantity": ff.quantity,
                            "unit": ff.unit or unit_col or "",
                            "person": ff.person or "",
                            "purpose": ff.purpose or "",
                            "remark": ff.remark,
                            "parse_level": ff.parse_level,
                            "parse_source": ff.parse_source,
                            "source_file": source_file,
                            "source_sheet": sheet,
                            "source_row": src_row,
                            "source_segment": ff.source_segment,
                            "source_release_id": release_id,
                            "_material_name": name,
                            "_material_code": code,
                            "_row_key": flow_lineage_row_key(
                                source_file=source_file,
                                source_sheet=sheet,
                                source_row=src_row,
                                source_segment=ff.source_segment,
                                flow_type=ff.flow_type,
                            ),
                        }
                    )
                else:
                    pending.append(
                        {
                            "file_id": file_id,
                            "source_sheet": sheet,
                            "source_row": src_row,
                            "source_segment": ff.source_segment,
                            "flow_type": ff.flow_type,
                            "text_raw": text,
                            "text_norm": tn,
                            "parse_level": ff.parse_level,
                            "suggested_json": suggested,
                        }
                    )
    return "fact_stock_flow", rows, pending, stats
