# -*- coding: utf-8 -*-
"""Governance endpoints under /api/v1 (A0-1 split from routes.py).

Endpoint registration order is preserved verbatim from the original
app/api/routes.py (static paths before param paths in each prefix space).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import config
from app.api.auth import require_ops
from app.repositories import meta_conn
from app.services import flow_gov as flow_gov_svc
from app.services import flow_lineage as flow_lineage_svc
from app.services import flow_llm as flow_llm_svc
from app.services import map_gov as map_gov_svc
from app.services import mapping_suggest as map_svc
from app.services import metrics as metrics_svc
from app.services import writer as writer_svc

from app.api.routers._schemas import (
    CorrectionDecideBody,
    CorrectionProposeBody,
    FlowConfirmBody,
    FlowRebuildBody,
    FlowSuggestBody,
    GovernBody,
    LineageRebuildBody,
    MapConfirmBody,
    MapEnqueueBody,
    MapPendingConfirmBody,
    MapSuggestBody,
    MasterConfirmBody,
    MasterProposeBody,
    MaterialAlignBatchBody,
    MaterialAlignConfirmBody,
    OpeningSeedBody,
    ReleaseDiffBody,
    ReleaseSupersedeBody,
    RuleLearnConfirmBody,
    RuleLearnProposeBody,
    TodoDecisionBody,
    ValueRuleBody,
    ValueRuleConfirmBody,
    json_dumps_safe,
)

router = APIRouter(prefix=config.API_V1_PREFIX)


@router.post("/govern/confirm")
def govern_confirm(body: GovernBody, actor: str = Depends(require_ops)):
    con = meta_conn()
    try:
        cur = con.execute(
            """
            INSERT INTO govern_confirm (source, detail, decision, note, actor)
            VALUES (?, ?, ?, ?, ?)
            """,
            [body.source, body.detail[:200], body.decision, body.note[:200], actor],
        )
        con.commit()
        return {"ok": True, "id": cur.lastrowid, "decision": body.decision, "actor": actor}
    finally:
        con.close()


@router.post("/govern/map-suggest")
def map_suggest(body: MapSuggestBody):
    if not body.headers:
        raise HTTPException(400, detail={"code": "HEADERS_REQUIRED", "message": "headers required"})
    return map_svc.suggest_header_mapping(body.headers, business_domain=body.business_domain)


@router.post("/govern/map-confirm")
def map_confirm(body: MapConfirmBody, actor: str = Depends(require_ops)):
    """Persist confirmed header→std_field into rule_dict (meta only; no biz write)."""
    if not body.mapping:
        raise HTTPException(400, detail={"code": "MAPPING_REQUIRED", "message": "mapping required"})
    con = meta_conn()
    try:
        n = 0
        for header, std_field in body.mapping.items():
            con.execute(
                """
                INSERT INTO rule_dict (header, std_field, business_domain, hits, source, confirmed_by)
                VALUES (?, ?, ?, 1, 'human_confirm', ?)
                ON CONFLICT(header, business_domain, std_field) DO UPDATE SET
                    hits = hits + 1,
                    confirmed_by = excluded.confirmed_by
                """,
                [str(header)[:120], str(std_field)[:64], body.business_domain[:64], actor],
            )
            n += 1
        con.execute(
            """
            INSERT INTO govern_confirm (source, detail, decision, note, actor)
            VALUES ('map_confirm', ?, 'accepted', ?, ?)
            """,
            [json_dumps_safe(body.mapping)[:200], body.note[:200], actor],
        )
        con.commit()
        return {"ok": True, "saved": n, "actor": actor}
    finally:
        con.close()


@router.post("/govern/map/enqueue")
def map_enqueue(body: MapEnqueueBody):
    """Enqueue low-confidence / multi-candidate / conflict headers into map_pending."""
    try:
        if body.from_file:
            if not body.file_id:
                raise HTTPException(400, detail={"code": "FILE_REQUIRED", "message": "file_id required"})
            return map_gov_svc.enqueue_from_file(
                body.file_id, business_domain=body.business_domain
            )
        if not body.headers:
            raise HTTPException(400, detail={"code": "HEADERS_REQUIRED", "message": "headers required"})
        return map_gov_svc.enqueue_headers(
            body.headers,
            file_id=body.file_id,
            sheet=body.sheet,
            business_domain=body.business_domain,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": str(e)})
    except KeyError as e:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": str(e)})


@router.get("/govern/map/pending")
def map_pending_list(limit: int = 50, offset: int = 0, status: str = "pending", file_id: str | None = None):
    return map_gov_svc.list_pending(limit=limit, offset=offset, status=status, file_id=file_id)


@router.post("/govern/map/pending/confirm")
def map_pending_confirm(body: MapPendingConfirmBody, actor: str = Depends(require_ops)):
    try:
        return map_gov_svc.confirm_pending(
            pending_id=body.pending_id,
            decision=body.decision,
            std_field=body.std_field,
            note=body.note,
            actor=actor,
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "pending not found"})
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_REQUEST", "message": str(e)})
    except RuntimeError as e:
        raise HTTPException(409, detail={"code": "STATUS_CONFLICT", "message": str(e)})


@router.get("/govern/flow/pending")
def flow_pending(limit: int = 50, offset: int = 0, status: str = "pending"):
    return flow_gov_svc.list_pending(limit=limit, offset=offset, status=status)


@router.post("/govern/flow/confirm")
def flow_confirm(body: FlowConfirmBody, actor: str = Depends(require_ops)):
    try:
        return flow_gov_svc.confirm_pending(
            pending_id=body.pending_id,
            decision=body.decision,
            actor=actor,
            corrected=body.corrected,
            note=body.note,
            overwrite=body.overwrite,
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "pending not found"})
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_DECISION", "message": str(e)})


@router.post("/govern/flow/suggest")
def flow_suggest(body: FlowSuggestBody, actor: str = Depends(require_ops)):
    """B1/B2 — LLM structured suggest on pending only (no DuckDB write)."""
    if body.force_role and body.force_role not in ("fast", "big"):
        raise HTTPException(400, detail={"code": "BAD_ROLE", "message": "force_role must be fast|big"})
    try:
        if body.pending_id:
            return flow_llm_svc.suggest_one(body.pending_id, force_role=body.force_role)
        return flow_llm_svc.process_pending_batch(limit=body.limit, force_role=body.force_role)
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "pending not found"})


@router.get("/govern/flow/reconcile")
def flow_reconcile():
    """Read-only gap list (does not rewrite flow_reconcile_gap)."""
    return flow_gov_svc.reconcile(persist=False)


@router.post("/govern/flow/reconcile")
def flow_reconcile_persist(actor: str = Depends(require_ops)):
    """Explicit rewrite of flow_reconcile_gap (ops)."""
    out = flow_gov_svc.reconcile(persist=True)
    out["persisted"] = True
    out["actor"] = actor
    return out


@router.post("/govern/flow/opening/seed")
def flow_opening_seed(body: OpeningSeedBody, actor: str = Depends(require_ops)):
    """Seed opening_qty=stock_qty for inventory rows with no stock_flow (writer-only)."""
    from app.services import writer as writer_svc

    return writer_svc.seed_opening_from_snapshot(actor=actor, dry_run=body.dry_run)


@router.post("/govern/material/align/propose")
def material_align_propose(actor: str = Depends(require_ops)):
    """Scan flow-only materials; write unique/ambiguous proposals to material_align."""
    from app.services import material_align as align_svc

    out = align_svc.propose_alignment()
    out["actor"] = actor
    return out


@router.get("/govern/material/align")
def material_align_list(status: str | None = "proposed", limit: int = 100, offset: int = 0):
    from app.services import material_align as align_svc

    return align_svc.list_alignments(status=status, limit=limit, offset=offset)


@router.post("/govern/material/align/confirm")
def material_align_confirm(body: MaterialAlignConfirmBody, actor: str = Depends(require_ops)):
    from app.services import material_align as align_svc

    try:
        return align_svc.confirm_alignment(
            align_id=body.align_id,
            from_material_id=body.from_material_id,
            to_material_id=body.to_material_id,
            decision=body.decision,
            actor=actor,
            note=body.note,
            apply_biz=body.apply_biz,
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "alignment not found"})
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_DECISION", "message": str(e)})


@router.post("/govern/material/align/accept-unique")
def material_align_accept_unique(body: MaterialAlignBatchBody, actor: str = Depends(require_ops)):
    """Batch-accept non-ambiguous proposals (default score>=0.95) and remap flows."""
    from app.services import material_align as align_svc

    return align_svc.accept_unique_proposed(
        actor=actor, min_score=body.min_score, apply_biz=body.apply_biz
    )


@router.post("/govern/master/propose")
def master_propose(body: MasterProposeBody = MasterProposeBody(), actor: str = Depends(require_ops)):
    """Scan L3 dim_material → master_pending (meta only)."""
    from app.services import master_gov as master_gov_svc

    out = master_gov_svc.propose_from_dim(limit=body.limit)
    out["actor"] = actor
    return out


@router.get("/govern/master/pending")
def master_pending_list(limit: int = 50, offset: int = 0, status: str = "pending"):
    from app.services import master_gov as master_gov_svc

    return master_gov_svc.list_pending(limit=limit, offset=offset, status=status)


@router.post("/govern/master/pending/confirm")
def master_pending_confirm(body: MasterConfirmBody, actor: str = Depends(require_ops)):
    from app.services import master_gov as master_gov_svc

    try:
        return master_gov_svc.confirm_pending(
            pending_id=body.pending_id,
            decision=body.decision,
            actor=actor,
            note=body.note,
            merge_to_material_id=body.merge_to_material_id,
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "pending not found"})
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_REQUEST", "message": str(e)})
    except RuntimeError as e:
        raise HTTPException(409, detail={"code": "STATUS_CONFLICT", "message": str(e)})


@router.get("/govern/flow/stats")
def flow_stats():
    return flow_gov_svc.parse_stats()


@router.get("/govern/flow/baseline")
def flow_baseline():
    """A9 — quality baseline + FLOW_* draft values (acceptance record)."""
    return metrics_svc.flow_quality_baseline()


@router.get("/govern/flow/gate")
def flow_gate():
    """08/12 activation gate checklist for FLOW_* (must stay draft until ready).

    Read-only: does not persist reconcile gaps (use POST /govern/flow/reconcile).
    """
    return metrics_svc.flow_activation_gate()


@router.get("/govern/flow/audit")
def flow_audit(limit: int = 5000, actor: str = Depends(require_ops)):
    """A6.1 — flag year-as-quantity / missing parse_level (docs/12 FL7)."""
    return flow_lineage_svc.audit_stock_flow(limit=limit)


@router.post("/govern/flow/rebuild")
def flow_rebuild(body: FlowRebuildBody, actor: str = Depends(require_ops)):
    """A6.2 — revoke+rebuild by release_id; never UPDATE quantity.

    Thin alias of /govern/lineage/rebuild for stock_flow (backward compatible).
    """
    try:
        if body.revoke_only:
            return writer_svc.lineage_revoke(body.release_id, actor=actor)
        return writer_svc.lineage_rebuild(body.release_id, actor=actor)
    except KeyError as e:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": str(e)})
    except FileNotFoundError as e:
        raise HTTPException(404, detail={"code": "STAGING_MISSING", "message": str(e)})
    except RuntimeError as e:
        raise HTTPException(400, detail={"code": "REBUILD_REFUSED", "message": str(e)})
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_REQUEST", "message": str(e)})


@router.get("/govern/lineage/releases")
def lineage_releases(limit: int = 50, offset: int = 0, domain: str | None = None):
    """List release_manifest for Ops lineage UI (all domains)."""
    return writer_svc.list_releases(limit=limit, offset=offset, domain=domain)


@router.get("/govern/lineage/row")
def govern_lineage_row(release_id: str, row_key: str):
    """行级证据：发布结果行 → 来源原始值 + 规整值 + 血缘链条（optv1/05 Q11）。"""
    from app.services.govern import row_evidence as row_ev

    try:
        return row_ev.row_evidence(release_id=release_id, row_key=row_key)
    except KeyError as e:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": str(e)})


@router.post("/govern/lineage/rebuild")
def lineage_rebuild(body: LineageRebuildBody, actor: str = Depends(require_ops)):
    """D6 generic lineage revoke/rebuild for inventory|demand|asset|stock_flow."""
    try:
        if body.revoke_only:
            return writer_svc.lineage_revoke(body.release_id, actor=actor)
        return writer_svc.lineage_rebuild(body.release_id, actor=actor)
    except KeyError as e:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": str(e)})
    except FileNotFoundError as e:
        raise HTTPException(404, detail={"code": "STAGING_MISSING", "message": str(e)})
    except RuntimeError as e:
        raise HTTPException(400, detail={"code": "REBUILD_REFUSED", "message": str(e)})
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_REQUEST", "message": str(e)})


@router.get("/govern/std-fields")
def govern_std_fields():
    from app.services.embed_recall import ALLOWED_STD, STD_FIELDS

    return {
        "fields": sorted(ALLOWED_STD),
        "aliases": {k: v[:5] for k, v in STD_FIELDS.items()},
    }


@router.post("/govern/release/diff")
def govern_release_diff(body: ReleaseDiffBody):
    from app.services import release_diff as diff_svc

    try:
        return diff_svc.diff_releases(body.release_a, body.release_b, limit=body.limit)
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_REQUEST", "message": str(e)})


@router.post("/govern/release/supersede")
def govern_release_supersede(body: ReleaseSupersedeBody, actor: str = Depends(require_ops)):
    from app.services import release_diff as diff_svc

    try:
        return diff_svc.mark_supersede(
            newer_release_id=body.newer_release_id,
            older_release_id=body.older_release_id,
            actor=actor,
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "release not found"})
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_REQUEST", "message": str(e)})


@router.get("/govern/value-rules")
def govern_value_rules(status: str | None = None, domain: str | None = None):
    from app.services import value_validator as vv

    vv.ensure_value_rule_seed()
    return vv.list_value_rules(status=status, domain=domain)


@router.post("/govern/value-rules")
def govern_value_rules_upsert(body: ValueRuleBody, actor: str = Depends(require_ops)):
    from app.services import value_validator as vv

    return vv.upsert_value_rule(
        rule_id=body.rule_id,
        domain=body.domain,
        std_field=body.std_field,
        check_type=body.check_type,
        params=body.params,
        severity=body.severity,
        status=body.status,
        actor=actor,
    )


@router.post("/govern/value-rules/{rule_id}/confirm")
def govern_value_rules_confirm(
    rule_id: str, body: ValueRuleConfirmBody | None = None, actor: str = Depends(require_ops)
):
    from app.services import value_validator as vv

    body = body or ValueRuleConfirmBody()
    try:
        return vv.confirm_value_rule(rule_id, actor=actor, decision=body.decision)
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "rule not found"})


@router.post("/govern/rule-learn/propose")
def govern_rule_learn_propose(
    body: RuleLearnProposeBody | None = None, actor: str = Depends(require_ops)
):
    from app.services import rule_learn as rl

    body = body or RuleLearnProposeBody()
    return rl.propose_from_blocked(limit=body.limit, min_count=body.min_count)


@router.get("/govern/rule-learn/candidates")
def govern_rule_learn_candidates(limit: int = 50):
    from app.services import rule_learn as rl

    return rl.list_candidates(limit=limit)


@router.post("/govern/rule-learn/{confirm_id}/confirm")
def govern_rule_learn_confirm(
    confirm_id: int, body: RuleLearnConfirmBody, actor: str = Depends(require_ops)
):
    from app.services import rule_learn as rl

    try:
        return rl.confirm_candidate(
            confirm_id=confirm_id,
            decision=body.decision,
            actor=actor,
            std_field=body.std_field,
            dry_run=bool(body.dry_run),
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "candidate not found"})
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, detail={"code": "BAD_REQUEST", "message": str(e)})


@router.get("/govern/corrections")
def govern_corrections(status: str | None = None, limit: int = 50):
    from app.services import correction_gov as cg

    return cg.list_corrections(status=status, limit=limit)


@router.post("/govern/corrections")
def govern_corrections_propose(body: CorrectionProposeBody, actor: str = Depends(require_ops)):
    from app.services import correction_gov as cg

    try:
        return cg.propose(
            release_id=body.release_id,
            row_key=body.row_key,
            field=body.field,
            value_new=body.value_new,
            reason=body.reason,
            actor=actor,
        )
    except KeyError as e:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": str(e)})
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_REQUEST", "message": str(e)})


@router.post("/govern/corrections/{correction_id}/decide")
def govern_corrections_decide(
    correction_id: str, body: CorrectionDecideBody, actor: str = Depends(require_ops)
):
    from app.services import correction_gov as cg

    try:
        if body.action == "decline":
            return cg.decline(correction_id, actor=actor)
        return cg.apply(correction_id, actor=actor)
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "correction not found"})
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, detail={"code": "BAD_REQUEST", "message": str(e)})


@router.get("/govern/todo-summary")
def govern_todo_summary():
    """Unified govern todo counts for workbench / 数据规整 (optv1 P3/4)."""
    from app.services import todo_board as todo_board_svc

    return todo_board_svc.todo_summary()


@router.get("/govern/todo-list")
def govern_todo_list(
    limit: int = 50,
    offset: int = 0,
    todo_type: str | None = None,
    sort: str = "impact",
):
    """Unified pending queue sorted by impact (optv1 P3/4)."""
    from app.services import todo_board as todo_board_svc

    _ = sort  # currently only impact ordering
    return todo_board_svc.todo_list(limit=limit, offset=offset, todo_type=todo_type)

@router.get("/govern/standardization/summary")
def govern_standardization_summary():
    """optv1/08 contract alias → todo_summary."""
    return govern_todo_summary()


@router.get("/govern/todos")
def govern_todos(
    limit: int = 50,
    offset: int = 0,
    todo_type: str | None = None,
    sort: str = "impact",
):
    """optv1/08 contract alias → todo_list."""
    return govern_todo_list(limit=limit, offset=offset, todo_type=todo_type, sort=sort)


@router.post("/govern/todos/{todo_id}/decision")
def govern_todo_decision(
    todo_id: str,
    body: TodoDecisionBody,
    actor: str = Depends(require_ops),
):
    """Unified todo decision facade (optv1/08). Supports dry_run preview."""
    from app.services import todo_board as todo_board_svc

    try:
        return todo_board_svc.decide_todo(
            todo_id=todo_id,
            decision=body.decision,
            actor=actor,
            amended_value=body.amended_value,
            note=body.note or "",
            expected_version=body.expected_version,
            idempotency_key=body.idempotency_key,
            dry_run=bool(body.dry_run),
        )
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "todo not found"})
    except RuntimeError as e:
        msg = str(e)
        if "todo_conflict" in msg or "invalid status" in msg:
            raise HTTPException(409, detail={"code": "CONFLICT", "message": msg})
        raise HTTPException(400, detail={"code": "BAD_REQUEST", "message": msg})
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_REQUEST", "message": str(e)})
