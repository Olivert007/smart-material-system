# -*- coding: utf-8 -*-
"""Reports & export endpoints under /api/v1 (A0-1 split from routes.py)."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app import config
from app.api.auth import require_ops, require_ops_or_seed_report
from app.services import csv_safe, query as query_svc

from app.api.routers._schemas import ReportCreateBody, ReportRunBody

router = APIRouter(prefix=config.API_V1_PREFIX)


# T8: ledger-export-plan §7 台账 4-sheet 模板导出（LD-5 固定列序；表头=台账模板列名 §1.1–§1.4）
# report_id 对应 report_runner.SEED_REPORTS 的种子报表；headers 为该 sheet 的台账模板列名。
LEDGER_SHEETS: dict[str, dict] = {
    "维护材料": {
        "report_id": "rpt_ledger_weihu",
        "headers": {
            "material_name": "名称",
            "spec": "品牌型号规格",
            "stock_qty": "现有库存",
            "opening_qty": "初始库存",
            "quota_qty": "定额数量",
            "min_qty": "最低库存阈值",
            "unit": "单位",
            "location": "存放位置",
            "custodian": "保管人",
            "belong_system": "所属系统",
            "project_name": "项目名称",
            "material_source": "物资来源",
            "group_code": "新集团编码",
            "remark": "备注",
            "qty_in": "入库数量",
            "qty_out": "出库数量",
            "flow_times": "流水次数",
        },
    },
    "备品备件": {
        "report_id": "rpt_ledger_beipin",
        "headers": {
            "material_name": "物资名称",
            "spec": "品牌规格型号",
            "stock_qty": "现有库存量",
            "opening_qty": "初始库存",
            "quota_qty": "定额数量",
            "min_qty": "最低数量",
            "unit": "单位",
            "location": "存放位置",
            "custodian": "保管人",
            "belong_system": "所属系统",
            "project_name": "项目名称",
            "material_source": "物资来源",
            "group_code": "新集团编码",
            "remark": "备注",
            "qty_in": "入库数量",
            "qty_out": "出库数量",
            "flow_times": "流水次数",
        },
    },
    "应急备汛物资": {
        "report_id": "rpt_ledger_yjbm",
        "headers": {
            "material_name": "物资名称",
            "spec": "型号规格",
            "stock_qty": "现有数量",
            "opening_qty": "期初数量",
            "quota_qty": "定额数量",
            "min_qty": "最低数量",
            "unit": "计量单位",
            "location": "存放货位",
            "custodian": "管理员",
            "belong_system": "所属系统",
            "project_name": "项目名称",
            "material_source": "物资来源",
            "group_code": "新集团编码",
            "remark": "备注",
            "qty_in": "入库数量",
            "qty_out": "出库数量",
            "flow_times": "流水次数",
        },
    },
    "公用工器具": {
        "report_id": "rpt_ledger_gongju",
        "headers": {
            "asset_code": "资产编码",
            "asset_name": "资产名称",
            "material_code": "物资编码",
            "asset_qty": "数量",
            "unit": "单位",
            "replace_cycle": "更换周期（年）",
            "check_cycle": "检测周期（年）",
            "status": "状态",
            "user_name": "使用人",
            "location": "存放位置",
            "tool_source": "工器具来源",
            "asset_quota_qty": "定额数量",
            "consumption_plan": "消耗计划",
            "remark": "备注",
        },
    },
}


@router.get("/reports")
def reports_list():
    from app.services import report_runner as rr

    return rr.list_reports()


@router.post("/reports")
def reports_create(body: ReportCreateBody, actor: str = Depends(require_ops)):
    from app.services import report_runner as rr

    try:
        return rr.create_report(
            name=body.name,
            query_sql=body.query_sql,
            actor=actor,
            report_id=body.report_id,
            cron_expr=body.cron_expr,
            params=body.params,
        )
    except ValueError as e:
        raise HTTPException(400, detail={"code": "BAD_SQL", "message": str(e)})


@router.post("/reports/{report_id}/run")
def reports_run(
    report_id: str,
    body: ReportRunBody | None = None,
    actor: str = Depends(require_ops_or_seed_report),
):
    from app.services import report_runner as rr

    try:
        return rr.run_report(report_id, actor=actor, params=(body.params if body else None))
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "report not found"})
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, detail={"code": "REPORT_FAILED", "message": str(e)})


@router.get("/reports/runs")
def reports_runs(report_id: str | None = None, limit: int = 50):
    from app.services import report_runner as rr

    return rr.list_runs(report_id, limit=limit)


@router.get("/reports/{run_id}/file")
def reports_file(run_id: str):
    from fastapi.responses import FileResponse
    from app.services import report_runner as rr

    try:
        run = rr.get_run(run_id)
    except KeyError:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "run not found"})
    path = run.get("artifact_path")
    if not path or not Path(path).exists():
        raise HTTPException(404, detail={"code": "ARTIFACT_MISSING", "message": "artifact missing"})
    return FileResponse(path, filename=Path(path).name)


# DT-W1/W5: 业务明细视图映射 — browse/export 默认 mode=business 时按事实表映射宽表。
BROWSE_VIEWS = {
    "fact_inventory": "v_browse_inventory",
    "fact_stock_flow": "v_browse_stock_flow",
    "fact_demand": "v_browse_demand",
    "fact_asset": "v_browse_asset",
}


@router.get("/export/table/{table}")
def export_table(table: str, limit: int = 50000, zh: int = 1, mode: str = "business"):
    """只读导出标准表为 CSV（表名白名单 + AST 校验 + 行数上限）。

    供「规整后数据」导出使用：表名必须存在于业务库目录（防注入），
    SQL 仍走 sql_guard 只读校验，行数受 EXPORT_ROW_LIMIT 约束。
    mode=business（默认）：事实表走 v_browse_* 业务明细视图；mode=raw：物理表直出。
    默认 zh=1：表头汉化、隐藏技术/溯源字段；zh=0 返回原始列名与全字段。
    """
    from datetime import datetime

    from fastapi.responses import Response
    from app.repositories import biz_conn
    from app.services import field_dict as fd
    from app.services.sql_guard import validate_readonly_sql

    if mode not in ("business", "raw"):
        raise HTTPException(400, detail={"code": "BAD_MODE", "message": "mode must be business or raw"})
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise HTTPException(400, detail={"code": "BAD_TABLE", "message": "invalid table name"})
    if table not in query_svc.list_tables():
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "table not found"})
    target = BROWSE_VIEWS.get(table, table) if mode == "business" else table
    cap = max(1, min(int(limit), config.EXPORT_ROW_LIMIT))
    guard = validate_readonly_sql(f'SELECT * FROM "{target}" LIMIT {cap}')
    if not guard.ok:
        raise HTTPException(400, detail={"code": guard.code or "SQL_REJECTED", "message": guard.error})
    con = biz_conn()
    try:
        df = con.execute(guard.sql).fetchdf()
    finally:
        con.close()
    if zh:
        keep = fd.visible_fields(list(df.columns))
        if keep:
            df = df[keep]
        # 值域汉化须在列改名之前（否则 "flow_type" 已不存在，映射永不生效）
        if "flow_type" in df.columns:
            df["flow_type"] = df["flow_type"].map(lambda v: fd.value_zh("flow_type", v))
        df.columns = fd.zh_columns_for_table(table, list(df.columns))
    # csv-export-harden T2.2: 公式注入防护（仅命中危险前缀的单元格加 `'`）
    df = csv_safe.sanitize_df(df)
    # csv-export-harden T1.1: UTF-8 BOM（Excel 中文不乱码）
    content = csv_safe.csv_bom() + df.to_csv(index=False)
    # csv-export-harden T3.1: 行数达上限时追加截断/来源注释
    if len(df) >= cap:
        content += f"\n# source={table}\n# TRUNCATED: rows={len(df)}, limit={cap}"
    filename = f"{table}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/ledger/{sheet}")
def export_ledger(sheet: str, zh: int = 1):
    """T8: 台账 4-sheet 模板导出（LD-5 固定列序 + 台账模板列名）。

    实时执行对应 report_definition 种子 SQL（只读校验），列序以种子 SELECT 顺序为准
    （LD-5 固定列序单一来源）；zh=1 表头汉化为台账模板列名（LEDGER_SHEETS），
    zh=0 返回原始英文列名。
    """
    from datetime import datetime
    from urllib.parse import quote

    from fastapi.responses import Response
    from app.repositories import biz_conn, meta_tx
    from app.services.sql_guard import validate_readonly_sql

    spec = LEDGER_SHEETS.get(sheet)
    if not spec:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "unknown ledger sheet"})
    with meta_tx() as con:
        row = con.execute(
            "SELECT query_sql FROM report_definition WHERE report_id=?", [spec["report_id"]]
        ).fetchone()
    if not row:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "report seed missing"})
    guard = validate_readonly_sql(row["query_sql"])
    if not guard.ok:
        raise HTTPException(400, detail={"code": guard.code or "SQL_REJECTED", "message": guard.error})
    con = biz_conn()
    try:
        df = con.execute(guard.sql).fetchdf()
    finally:
        con.close()
    if zh:
        headers = spec["headers"]
        df.columns = [headers.get(c, c) for c in df.columns]
    # csv-export-harden T1/T2: 台账导出同样加 BOM + 注入防护（与 /export/table 同口径）
    df = csv_safe.sanitize_df(df)
    content = csv_safe.csv_bom() + df.to_csv(index=False)
    filename = f"台账_{sheet}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/browse/{table}")
def browse_table(table: str, limit: int = 100, offset: int = 0, zh: int = 1, mode: str = "business"):
    """台账在线分页浏览（ledger-browse LB-1 / question/14 DT-W1）：JSON 分页 + 汉化列名/枚举 + 隐藏技术字段。

    mode=business（默认）：事实表走 v_browse_* 业务明细视图（JOIN dim_material，
    名称/规格/单位前置，material_id 置后列供溯源）；mode=raw：物理表直出原始列。
    与 /export/table 同源（表名白名单 + AST 只读校验 + 字段汉化），区别：
    limit 上限 500（单页），不触发 EXPORT_ROW_LIMIT；返回 JSON 分页数据供前端列表展示。
    """
    import json

    from app.repositories import biz_conn
    from app.services import field_dict as fd
    from app.services.sql_guard import validate_readonly_sql

    if mode not in ("business", "raw"):
        raise HTTPException(400, detail={"code": "BAD_MODE", "message": "mode must be business or raw"})
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise HTTPException(400, detail={"code": "BAD_TABLE", "message": "invalid table name"})
    if table not in query_svc.list_tables():
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "table not found"})
    target = BROWSE_VIEWS.get(table, table) if mode == "business" else table
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    con = biz_conn()
    try:
        guard = validate_readonly_sql(f'SELECT * FROM "{target}" LIMIT {limit} OFFSET {offset}')
        if not guard.ok:
            raise HTTPException(400, detail={"code": guard.code or "SQL_REJECTED", "message": guard.error})
        df = con.execute(guard.sql).fetchdf()
        cnt_guard = validate_readonly_sql(f'SELECT COUNT(*) AS n FROM "{target}"')
        if not cnt_guard.ok:
            raise HTTPException(400, detail={"code": cnt_guard.code or "SQL_REJECTED", "message": cnt_guard.error})
        total = int(con.execute(cnt_guard.sql).fetchone()[0])
    finally:
        con.close()
    if zh:
        keep = fd.visible_fields(list(df.columns))
        if keep:
            df = df[keep]
        # 值域汉化须在列改名之前（否则 "flow_type" 已不存在，映射永不生效）
        if "flow_type" in df.columns:
            df["flow_type"] = df["flow_type"].map(lambda v: fd.value_zh("flow_type", v))
        df.columns = fd.zh_columns_for_table(table, list(df.columns))
    # NaN → null、时间 → ISO 字符串，直接可 JSON 序列化
    rows = json.loads(df.to_json(orient="records"))
    return {
        "table": table,
        "mode": mode,
        "columns_zh": list(df.columns),
        "rows": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
