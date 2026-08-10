# -*- coding: utf-8 -*-
"""SQL AST guard (docs/05 §1.1, C12)."""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp


_FORBIDDEN_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Copy,
    exp.Grant,
    exp.Set,
    exp.Use,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Attach,
    exp.Detach,
    exp.Pragma,
)


@dataclass
class SqlGuardResult:
    ok: bool
    sql: str
    error: str | None = None
    code: str | None = None


def validate_readonly_sql(sql: str, *, max_statements: int = 1) -> SqlGuardResult:
    text = (sql or "").strip().rstrip(";")
    if not text:
        return SqlGuardResult(False, text, "empty sql", "SQL_EMPTY")
    try:
        statements = sqlglot.parse(text, read="duckdb")
    except Exception as e:
        return SqlGuardResult(False, text, f"parse error: {e}", "SQL_PARSE_ERROR")
    if not statements or any(s is None for s in statements):
        return SqlGuardResult(False, text, "unable to parse sql", "SQL_PARSE_ERROR")
    if len(statements) > max_statements:
        return SqlGuardResult(False, text, "multiple statements forbidden", "SQL_MULTI_STATEMENT")

    root = statements[0]
    if isinstance(root, _FORBIDDEN_TYPES):
        return SqlGuardResult(False, text, f"forbidden statement: {type(root).__name__}", "SQL_FORBIDDEN")

    # Must be SELECT or WITH->SELECT
    if not isinstance(root, (exp.Select, exp.Union)):
        # WITH wraps Select as With
        if isinstance(root, exp.With):
            if not isinstance(root.this, (exp.Select, exp.Union)):
                return SqlGuardResult(False, text, "WITH must resolve to SELECT", "SQL_NOT_SELECT")
        else:
            return SqlGuardResult(False, text, "only SELECT/WITH allowed", "SQL_NOT_SELECT")

    for node in root.walk():
        if isinstance(node, _FORBIDDEN_TYPES):
            return SqlGuardResult(False, text, f"forbidden node: {type(node).__name__}", "SQL_FORBIDDEN")
        if isinstance(node, exp.Anonymous):
            name = (node.name or "").lower()
            if name in {"read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto", "httpfs"}:
                return SqlGuardResult(False, text, f"forbidden table function: {name}", "SQL_FORBIDDEN_FN")
        if isinstance(node, exp.Table) and node.this and str(node.this).lower().startswith("read_"):
            return SqlGuardResult(False, text, "forbidden table function", "SQL_FORBIDDEN_FN")

    return SqlGuardResult(True, text)
