# -*- coding: utf-8 -*-
"""Header mapping Copilot: rule_dict → embed recall → big suggest (Stage 1, no auto-publish)."""
from __future__ import annotations

import json

from app.services.embed_recall import ALLOWED_STD, STD_FIELDS, recall_candidates, validate_mapping
from app.services.model_client import chat, parse_json_object
from app.services.rule_dict import dict_prefill

LOW_SCORE = 0.75
MULTI_SCORE = 0.92


def classify_queue_items(
    headers: list[str],
    suggest: dict,
) -> list[dict]:
    """Uncertain headers that must enter map_pending (docs/04 §6.4)."""
    mapping = suggest.get("mapping") or {}
    candidates = suggest.get("candidates") or {}
    multi = suggest.get("multi_candidate_headers") or {}
    conflicts = set(suggest.get("dict_conflicts") or [])
    dict_hits = suggest.get("dict_hits") or {}
    items: list[dict] = []

    for h in headers:
        cands = candidates.get(h) or []
        top = cands[0] if cands else None
        top_score = float(top["score"]) if top else 0.0
        suggested = mapping.get(h) or (top["std_field"] if top else None)
        reason = None

        if h in conflicts:
            reason = "conflict"
        elif h in multi:
            reason = "multi_candidate"
        elif h not in dict_hits and top and top_score < LOW_SCORE:
            reason = "low_confidence"
        elif h not in dict_hits and (suggested in (None, "ignore")) and top_score < MULTI_SCORE:
            reason = "unmapped"
        elif h not in dict_hits and not top and suggested == "ignore":
            reason = "unmapped"

        if not reason:
            continue
        items.append(
            {
                "header": h,
                "suggested_field": suggested,
                "candidates": cands[:5],
                "reason": reason,
                "top_score": top_score,
            }
        )
    return items


def suggest_header_mapping(headers: list[str], *, business_domain: str | None = None) -> dict:
    if not headers:
        return {"ok": False, "error": "empty headers", "model_state": "not_attempted"}

    # 04 §6.2 layers ①/② — dictionary before embed/LLM
    dict_map, dict_hits, dict_conflicts = dict_prefill(headers, business_domain=business_domain)

    recalls = {h: recall_candidates(h, top_k=5) for h in headers}
    prefill = dict(dict_map)
    for h, cands in recalls.items():
        if h in prefill:
            continue
        if cands and cands[0]["score"] >= 0.92:
            prefill[h] = cands[0]["std_field"]

    # All headers settled by dict (+ ignore) and no open conflicts → skip LLM
    uncovered = [h for h in headers if h not in prefill]
    if not uncovered and not dict_conflicts:
        clean, illegal = validate_mapping(prefill)
        out = {
            "ok": True,
            "mapping": clean,
            "candidates": recalls,
            "multi_candidate_headers": {},
            "unmapped_columns": [h for h, f in clean.items() if f == "ignore"],
            "illegal_columns": illegal,
            "prefill": prefill,
            "dict_hits": dict_hits,
            "dict_conflicts": dict_conflicts,
            "hint": "规则字典命中预填；仍须人工 confirm 后回写，不可自动发布",
            "model_request_attempted": False,
            "model_invoked": False,
            "output_available": False,
            "model_state": "rule_dict_hit",
            "fallback_reason": None,
            "model": None,
            "latency_ms": 0,
            "error": None,
        }
        out["queue_items"] = classify_queue_items(headers, out)
        return out

    # High-confidence embed/lexical path when every remaining header is strongly matched
    if len(prefill) == len(headers) and not dict_conflicts:
        clean, illegal = validate_mapping(prefill)
        out = {
            "ok": True,
            "mapping": clean,
            "candidates": recalls,
            "multi_candidate_headers": {},
            "unmapped_columns": [h for h, f in clean.items() if f == "ignore"],
            "illegal_columns": illegal,
            "prefill": prefill,
            "dict_hits": dict_hits,
            "dict_conflicts": dict_conflicts,
            "hint": "字典/高置信召回直接预填；仍须人工 confirm 后回写，不可自动发布",
            "model_request_attempted": False,
            "model_invoked": False,
            "output_available": False,
            "model_state": "embed_high_confidence",
            "fallback_reason": None,
            "model": None,
            "latency_ms": 0,
            "error": None,
        }
        out["queue_items"] = classify_queue_items(headers, out)
        return out

    fields_desc = ", ".join(sorted(ALLOWED_STD))
    alias_hint = {k: v[:3] for k, v in STD_FIELDS.items()}
    sys_msg = (
        "你是物资数据治理专家。把表头映射到标准字段枚举。"
        f"标准字段（含 ignore）：{fields_desc}\n"
        f"常见别名参考：{json.dumps(alias_hint, ensure_ascii=False)}\n"
        "只输出 JSON 对象：{\"列名\": \"标准字段\"}，无法映射用 ignore。"
        "已由规则字典给出的映射请尽量保留，除非明显错误。"
    )
    usr = (
        f"表头：{json.dumps(headers, ensure_ascii=False)}\n"
        f"规则字典预填：{json.dumps(dict_map, ensure_ascii=False)}\n"
        f"词法召回预填（可修改）：{json.dumps(prefill, ensure_ascii=False)}\n"
        f"各列表头候选：{json.dumps(recalls, ensure_ascii=False)}"
    )

    result = chat(
        role="big",
        task_type="map_headers",
        messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": usr}],
        temperature=0.0,
        max_tokens=800,
    )

    mapping: dict = {}
    if result.ok and result.output_available:
        parsed = parse_json_object(result.text)
        if isinstance(parsed, dict):
            mapping = {str(k): str(v) for k, v in parsed.items()}
        else:
            repair = chat(
                role="big",
                task_type="map_headers_repair",
                messages=[
                    {"role": "system", "content": sys_msg + " 上次输出不是合法 JSON，请只输出 JSON 对象。"},
                    {"role": "user", "content": usr},
                    {"role": "assistant", "content": result.text[:1000]},
                    {"role": "user", "content": "请重新只输出 JSON。"},
                ],
                temperature=0.0,
                max_tokens=800,
            )
            result = repair
            parsed = parse_json_object(repair.text) if repair.ok else None
            mapping = {str(k): str(v) for k, v in parsed.items()} if parsed else dict(prefill)
    else:
        mapping = dict(prefill)

    # Dictionary always wins over LLM for non-conflicted hits (04 §6.2)
    for h, f in dict_map.items():
        mapping[h] = f

    clean, illegal = validate_mapping(mapping)
    for h in headers:
        clean.setdefault(h, "ignore")

    unmapped = [h for h, f in clean.items() if f == "ignore"]
    multi = {h: cands for h, cands in recalls.items() if len(cands) >= 2 and cands[0]["score"] < 0.92}

    draft = {
        "ok": bool(clean),
        "mapping": clean,
        "candidates": recalls,
        "multi_candidate_headers": multi,
        "unmapped_columns": unmapped,
        "illegal_columns": illegal,
        "prefill": prefill,
        "dict_hits": dict_hits,
        "dict_conflicts": dict_conflicts,
        "hint": "字典优先；多候选仅预填，不可自动发布；请人工 confirm 后回写规则字典",
        "model_request_attempted": result.model_request_attempted,
        "model_invoked": result.model_invoked,
        "output_available": result.output_available,
        "model_state": result.model_state,
        "fallback_reason": result.fallback_reason,
        "model": result.model,
        "latency_ms": result.latency_ms,
        "error": result.error,
    }
    draft["queue_items"] = classify_queue_items(headers, draft)
    return draft
