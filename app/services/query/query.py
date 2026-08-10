# -*- coding: utf-8 -*-
"""Read-only query via AST guard."""
from __future__ import annotations

from fastapi import HTTPException

from app import config
from app.repositories import biz_conn
from app.services.jsonutil import json_safe
from app.services.sql_guard import validate_readonly_sql


def list_tables() -> list[str]:
    con = biz_conn()
    try:
        df = con.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='main'
            ORDER BY table_name
            """
        ).fetchdf()
    finally:
        con.close()
    return df["table_name"].tolist()


def run_readonly_query(sql: str, *, allow_free: bool | None = None, row_limit: int | None = None) -> dict:
    if allow_free is None:
        allow_free = config.ALLOW_FREE_QUERY
    if not allow_free:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "message": "free query disabled; set ALLOW_FREE_QUERY=1 for ops",
                "code": "FREE_QUERY_DISABLED",
            },
        )
    guard = validate_readonly_sql(sql)
    if not guard.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_sql",
                "message": guard.error,
                "code": guard.code,
            },
        )
    con = biz_conn()
    try:
        df = con.execute(guard.sql).fetchdf()
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "sql_exec", "message": str(e), "code": "SQL_EXEC_ERROR"})
    finally:
        con.close()
    # row_limit=None：不截断（报表/导出等需全量）；调用方如需封顶显式传 QUERY_ROW_LIMIT
    data = df if row_limit is None else df.head(row_limit)
    return {
        "rows": int(len(df)),
        "columns": list(df.columns),
        "data": json_safe(data.to_dict(orient="records")),
    }
