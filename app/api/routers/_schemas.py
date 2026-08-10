# -*- coding: utf-8 -*-
"""Shared request schemas + small JSON helpers for /api/v1 routers.

Moved verbatim from app/api/routes.py (A0-1 split) so every domain router
imports its Pydantic bodies from this single module.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class StageBody(BaseModel):
    config_version: str = "v1"
    target_domain: str = "inventory"


class AnalyzeBody(BaseModel):
    target_domain: str = "inventory"
    include_stage: bool = True
    refresh_profile: bool = False
    config_version: str = "v1"
    async_mode: bool = False  # True → enqueue analyze task


class ConfirmBody(BaseModel):
    version: int | None = None
    expected_status: str | None = "STAGED"
    staging_id: str | None = None
    target_domain: str | None = None
    force: bool = False  # bypass quality/plan gate (ops only; still audited)
    supersedes: str | None = None  # optional prior release_id (P1-4)


class PlanConfirmBody(BaseModel):
    note: str = ""
    force: bool = False
    target_domain: str = "inventory"


class GovernBody(BaseModel):
    source: str = ""
    detail: str = ""
    decision: str
    note: str = ""


class MapSuggestBody(BaseModel):
    headers: list[str]
    business_domain: str | None = None


class MapConfirmBody(BaseModel):
    mapping: dict[str, str]
    business_domain: str = "default"
    note: str = ""


class MapEnqueueBody(BaseModel):
    headers: list[str] = Field(default_factory=list)
    file_id: str | None = None
    sheet: str | None = None
    business_domain: str = "default"
    from_file: bool = False  # when True, ignore headers and scan evidence+profile


class MapPendingConfirmBody(BaseModel):
    pending_id: str
    decision: str  # accept | amend | ignore
    std_field: str | None = None
    note: str = ""


class AskBody(BaseModel):
    question: str = Field(..., min_length=1)


class FlowConfirmBody(BaseModel):
    pending_id: str
    decision: str  # accept | amend | ignore
    corrected: dict | None = None
    note: str = ""
    overwrite: bool = False  # update flow_example on text_norm conflict


class FlowRebuildBody(BaseModel):
    release_id: str
    revoke_only: bool = False


class LineageRebuildBody(BaseModel):
    release_id: str
    revoke_only: bool = False


class MetricUpsertBody(BaseModel):
    metric_id: str = Field(..., min_length=1)
    metric_name: str = Field(..., min_length=1)
    definition_sql: str = Field(..., min_length=1)
    aliases: list[str] = Field(default_factory=list)
    unit: str = ""
    definition: str = ""
    source_tables: str = ""
    engine: str = "biz"
    status: str = "draft"


class FlowSuggestBody(BaseModel):
    pending_id: str | None = None
    limit: int = 5
    force_role: str | None = None  # fast|big optional override


class FlowActivateBody(BaseModel):
    metric_ids: list[str] | None = None


class OpeningSeedBody(BaseModel):
    dry_run: bool = False


class MaterialAlignConfirmBody(BaseModel):
    align_id: str | None = None
    from_material_id: str | None = None
    to_material_id: str | None = None
    decision: str  # accept | reject
    note: str = ""
    apply_biz: bool = True


class MaterialAlignBatchBody(BaseModel):
    min_score: float = 0.95
    apply_biz: bool = True


class MasterProposeBody(BaseModel):
    limit: int = 500


class MasterConfirmBody(BaseModel):
    pending_id: str
    decision: str  # approve | reject | merge
    note: str = ""
    merge_to_material_id: str | None = None


class ReleaseDiffBody(BaseModel):
    release_a: str
    release_b: str
    limit: int = 200


class ReleaseSupersedeBody(BaseModel):
    newer_release_id: str
    older_release_id: str


class ValueRuleBody(BaseModel):
    rule_id: str | None = None
    domain: str
    std_field: str
    check_type: str
    params: dict | None = None
    severity: str = "block"
    status: str = "proposed"


class ValueRuleConfirmBody(BaseModel):
    decision: str = "accept"


class ReportCreateBody(BaseModel):
    name: str
    query_sql: str
    report_id: str | None = None
    cron_expr: str = ""
    params: list | dict | None = None


class ReportRunBody(BaseModel):
    params: dict | None = None


class RuleLearnProposeBody(BaseModel):
    limit: int = 50
    min_count: int = 2


class RuleLearnConfirmBody(BaseModel):
    decision: str = "accepted"  # accepted|rejected
    std_field: str | None = None


class CorrectionProposeBody(BaseModel):
    release_id: str
    row_key: str
    field: str
    value_new: str | None = None
    reason: str = ""


class CorrectionDecideBody(BaseModel):
    action: str = "apply"  # apply|decline


def json_dumps_safe(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
