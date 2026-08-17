# -*- coding: utf-8 -*-
"""Embedding recall + lexical fallback (Stage 1; no auto-publish)."""
from __future__ import annotations

import json
import math
import re
import threading
import urllib.error
import urllib.request
from collections import Counter

from app import config

# docs/04 §1
STD_FIELDS: dict[str, list[str]] = {
    "asset_code": ["资产编号", "资产编码", "资产号"],
    "material_code": ["物资编号", "物资编码", "物料编码", "物料号", "编码"],
    "item_name": ["名称", "物资名称", "资产名称", "品名", "物料名称"],
    "specification": ["规格", "型号", "规格型号"],
    "quantity": ["数量", "库存数量", "需求数量", "现有数量"],
    "unit": ["单位", "计量单位"],
    "location": ["存放地点", "库位", "位置", "存放位置", "库位号"],
    "department": ["部门", "所属部门"],
    "keeper_or_user": ["保管人", "使用人", "领用人", "管理员", "填报人", "填报人姓名"],
    "status": ["状态", "资产状态"],
    "serial_or_factory_no": ["序列号", "出厂编号", "SN"],
    "purchase_date": ["购买日期", "购置日期"],
    "remark": ["备注", "说明"],
    "region": ["区域", "地区", "仓库区域"],
    "category": ["分类", "物资类别", "品类", "物资大类", "物资种类"],
    "stock_qty": ["现有库存", "账面数量", "现有库存数值", "现有数量"],
    "stock_value": ["金额", "库存金额", "总价", "库存值", "单价", "合价"],
    "flow_type": ["入库", "出库", "流向"],
    "flow_date": ["出入库日期", "业务日期"],
    "flow_in_text": ["入库记录", "入库文本", "flow_in_text"],
    "flow_out_text": ["出库记录", "出库记录（ZW）", "出库文本", "flow_out_text"],
    "qty_in": ["入库数量", "qty_in"],
    "qty_out": ["出库数量", "qty_out"],
    "demand_period": ["期次", "计划期", "年度", "需求期次"],
    "quota_qty": ["定额", "调整数量", "定额数量"],
    # T2: ledger-export-plan §8.4（LD-1/LD-2 锁定 2026-08-10）
    "opening_qty": ["初始库存", "期初数量", "期初库存"],
    "min_qty": ["最低库存阈值", "最低库存"],
    "company_wh_qty": ["公司仓库数量"],
    "belong_system": ["所属系统"],
    "project_name": ["项目名称"],
    "consumption_plan": ["消耗计划"],
    "material_source": ["物资来源"],
    "group_code": ["新集团编码"],
    "is_frame_material": ["是否框架物资"],
    "agreement_supplier": ["协议供应商名称"],
    "frame_material_code": ["推荐框架物资编码"],
    "frame_material_name": ["推荐框架物资名称"],
    "frame_material_spec": ["推荐框架物资型号"],
    "frame_material_supplier": ["推荐框架物资供应商"],
    "emergency_supplier": ["应急供应商名称"],
    "is_instrument": ["是否仪器仪表"],
    "replace_cycle": ["更换周期（年）"],
    "check_cycle": ["检测周期（年）"],
    "tool_source": ["工器具来源"],
    "asset_qty": ["数量", "资产数量"],
    "asset_quota_qty": ["定额数量"],
}

ALLOWED_STD = set(STD_FIELDS) | {"ignore"}

_lock = threading.Lock()
_field_vecs: dict[str, list[tuple[str, list[float]]]] | None = None
_field_alias_meta: dict[str, str] = {}  # field -> display alias


def _grams(text: str, n: int = 2) -> Counter:
    s = re.sub(r"\s+", "", str(text).lower())
    if not s:
        return Counter()
    if len(s) < n:
        return Counter([s])
    return Counter(s[i : i + n] for i in range(len(s) - n + 1))


def _cosine_counter(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _cosine_vec(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def lexical_recall(header: str, top_k: int = 5) -> list[dict]:
    hg = _grams(header)
    scored: list[tuple[float, str, str]] = []
    for field, aliases in STD_FIELDS.items():
        best = _cosine_counter(hg, _grams(field))
        best_alias = field
        for al in aliases:
            sc = _cosine_counter(hg, _grams(al))
            if header.strip() == al or al in header or header in al:
                sc = max(sc, 0.99)
            if sc > best:
                best, best_alias = sc, al
        scored.append((best, field, best_alias))
    scored.sort(reverse=True)
    out = []
    for sc, field, alias in scored[:top_k]:
        if sc <= 0:
            continue
        out.append({"std_field": field, "score": round(sc, 4), "matched_alias": alias, "source": "lexical"})
    return out


def embed_endpoint_available() -> bool:
    try:
        req = urllib.request.Request(config.LLM_EMBED_ENDPOINT.rstrip("/") + "/models", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _detect_embed_model() -> str:
    if config.LLM_EMBED_MODEL:
        return config.LLM_EMBED_MODEL
    try:
        req = urllib.request.Request(config.LLM_EMBED_ENDPOINT.rstrip("/") + "/models", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
        return models[0] if models else "qwen3-embedding-0.6b"
    except Exception:
        return "qwen3-embedding-0.6b"


def embed_texts(texts: list[str], timeout: float = 60) -> list[list[float]]:
    if not texts:
        return []
    model = _detect_embed_model()
    payload = {"model": model, "input": texts}
    req = urllib.request.Request(
        config.LLM_EMBED_ENDPOINT.rstrip("/") + "/embeddings",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    items = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
    return [it.get("embedding") or [] for it in items]


def _ensure_field_vecs() -> dict[str, list[tuple[str, list[float]]]]:
    """field -> [(alias_text, vector), ...]"""
    global _field_vecs
    with _lock:
        if _field_vecs is not None:
            return _field_vecs
        texts: list[str] = []
        meta: list[tuple[str, str]] = []  # (field, alias)
        for field, aliases in STD_FIELDS.items():
            opts = [field] + list(aliases)
            for t in opts:
                texts.append(t)
                meta.append((field, t))
            _field_alias_meta[field] = aliases[0] if aliases else field
        vecs = embed_texts(texts)
        out: dict[str, list[tuple[str, list[float]]]] = {}
        for (field, alias), vec in zip(meta, vecs):
            out.setdefault(field, []).append((alias, vec))
        _field_vecs = out
        return _field_vecs


def reset_field_vec_cache() -> None:
    global _field_vecs
    with _lock:
        _field_vecs = None


def vector_recall(header: str, top_k: int = 5) -> list[dict]:
    field_vecs = _ensure_field_vecs()
    hv = embed_texts([header])[0]
    scored: list[tuple[float, str, str]] = []
    h = header.strip()
    for field, pairs in field_vecs.items():
        best = -1.0
        best_alias = _field_alias_meta.get(field, field)
        for alias, fv in pairs:
            sc = _cosine_vec(hv, fv)
            if h == alias or alias in h or h in alias:
                sc = max(sc, 0.99)
            if sc > best:
                best, best_alias = sc, alias
        scored.append((best, field, best_alias))
    scored.sort(reverse=True)
    out = []
    for sc, field, alias in scored[:top_k]:
        out.append(
            {
                "std_field": field,
                "score": round(float(sc), 4),
                "matched_alias": alias,
                "source": "embed",
            }
        )
    return out


def recall_candidates(header: str, top_k: int = 5) -> list[dict]:
    """Prefer remote embed when available; else lexical fallback."""
    if embed_endpoint_available():
        try:
            return vector_recall(header, top_k=top_k)
        except Exception:
            if config.EMBED_FALLBACK_LEXICAL:
                cands = lexical_recall(header, top_k=top_k)
                for c in cands:
                    c["source"] = "lexical_fallback"
                return cands
            raise
    if config.EMBED_FALLBACK_LEXICAL:
        return lexical_recall(header, top_k=top_k)
    return []


def validate_mapping(mapping: dict) -> tuple[dict[str, str], list[str]]:
    """Keep only allowed std fields; illegal → ignore candidate list."""
    clean: dict[str, str] = {}
    illegal: list[str] = []
    for col, field in mapping.items():
        f = str(field).strip()
        if f in ALLOWED_STD:
            clean[str(col)] = f
        else:
            clean[str(col)] = "ignore"
            illegal.append(str(col))
    return clean, illegal
