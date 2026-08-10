# -*- coding: utf-8 -*-
"""sql_fewshot pool seed (docs/04 Assets / 02)."""
from __future__ import annotations

import uuid

from app.repositories import meta_tx

_SEED = [
    {
        "question_type": "count",
        "question": "库存表有多少行",
        "sql_gold": "SELECT COUNT(*) AS row_count FROM fact_inventory",
    },
    {
        "question_type": "metric",
        "question": "库存总数量是多少",
        "sql_gold": "SELECT SUM(stock_qty) AS v FROM fact_inventory",
    },
    {
        "question_type": "metric",
        "question": "需求总量是多少",
        "sql_gold": "SELECT SUM(quantity) AS v FROM fact_demand",
    },
]


def ensure_sql_fewshot_seed(*, actor: str = "system:seed") -> dict:
    inserted = 0
    skipped = 0
    with meta_tx() as con:
        # table may be new on upgrade
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sql_fewshot (
                fewshot_id TEXT PRIMARY KEY,
                question_type TEXT,
                question TEXT NOT NULL,
                sql_gold TEXT NOT NULL,
                hits INTEGER DEFAULT 0,
                source TEXT,
                confirmed_by TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        for row in _SEED:
            exists = con.execute(
                "SELECT fewshot_id FROM sql_fewshot WHERE question=? AND sql_gold=?",
                [row["question"], row["sql_gold"]],
            ).fetchone()
            if exists:
                skipped += 1
                continue
            con.execute(
                """
                INSERT INTO sql_fewshot (
                    fewshot_id, question_type, question, sql_gold, hits, source, confirmed_by
                ) VALUES (?, ?, ?, ?, 0, 'seed', ?)
                """,
                [
                    uuid.uuid4().hex[:12],
                    row["question_type"],
                    row["question"],
                    row["sql_gold"],
                    actor,
                ],
            )
            inserted += 1
    return {"ok": True, "inserted": inserted, "skipped": skipped}
