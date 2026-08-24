# -*- coding: utf-8 -*-
"""Local Vanna instance: file-backed retrieval + model_client LLM (no WebUI)."""
from __future__ import annotations

import json
import math
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from app import config
from app.services.llm import embed_recall
from app.services.llm.model_client import chat

_lock = threading.Lock()
_vn_instance: Any | None = None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def _lexical_score(query: str, text: str) -> float:
    q = set(re.findall(r"[\u4e00-\u9fff\w]+", (query or "").lower()))
    t = set(re.findall(r"[\u4e00-\u9fff\w]+", (text or "").lower()))
    if not q or not t:
        return 0.0
    return len(q & t) / len(q)


class _JsonVectorStore:
    """Minimal persistence for Vanna training artifacts (Step2; Step3 expands)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "store.json"
        self._data = self._load()

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return {"ddl": [], "documentation": [], "question_sql": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {
                    "ddl": list(raw.get("ddl") or []),
                    "documentation": list(raw.get("documentation") or []),
                    "question_sql": list(raw.get("question_sql") or []),
                }
        except Exception:
            pass
        return {"ddl": [], "documentation": [], "question_sql": []}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, kind: str, *, text: str, extra: dict | None = None) -> str:
        item_id = uuid.uuid4().hex[:12]
        row = {"id": item_id, "text": text, **(extra or {})}
        self._data.setdefault(kind, []).append(row)
        self._save()
        return item_id

    def top(self, kind: str, question: str, *, n: int = 5) -> list[str]:
        rows = self._data.get(kind) or []
        if not rows:
            return []
        scored: list[tuple[float, str]] = []
        use_embed = embed_recall.embed_endpoint_available()
        q_vec: list[float] | None = None
        if use_embed:
            try:
                q_vec = embed_recall.embed_texts([question])[0]
            except Exception:
                use_embed = False
        for row in rows:
            text = str(row.get("text") or "")
            if use_embed and q_vec:
                try:
                    vec = embed_recall.embed_texts([text])[0]
                    sc = _cosine(q_vec, vec)
                except Exception:
                    sc = _lexical_score(question, text)
            else:
                sc = _lexical_score(question, text)
            if sc > 0:
                scored.append((sc, text))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:n]]


def _build_sms_vanna():
    from vanna.base.base import VannaBase

    store = _JsonVectorStore(Path(config.VANNA_PERSIST_DIR))

    class SmsVanna(VannaBase):
        dialect = "DuckDB"

        def __init__(self) -> None:
            super().__init__(
                config={
                    "dialect": "DuckDB",
                    "language": "Chinese",
                    "max_tokens": 8000,
                    "initial_prompt": (
                        "你是物资管理 DuckDB 只读 SQL 助手。"
                        "最终只输出一条 SELECT 或 WITH 查询，不要解释。"
                    ),
                }
            )
            self._store = store

        def system_message(self, message: str) -> dict:
            return {"role": "system", "content": message}

        def user_message(self, message: str) -> dict:
            return {"role": "user", "content": message}

        def assistant_message(self, message: str) -> dict:
            return {"role": "assistant", "content": message}

        def submit_prompt(self, prompt, **kwargs) -> str:
            messages = []
            for msg in prompt:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    messages.append({"role": "system", "content": content})
                elif role == "assistant":
                    messages.append({"role": "assistant", "content": content})
                else:
                    messages.append({"role": "user", "content": content})
            result = chat(
                role="big",
                task_type="vanna_text2sql",
                messages=messages,
                temperature=0.0,
                max_tokens=512,
            )
            if not result.ok or not result.output_available:
                raise RuntimeError(result.error or result.model_state or "vanna llm failed")
            return result.text

        def generate_embedding(self, data: str, **kwargs) -> list[float]:
            if embed_recall.embed_endpoint_available():
                try:
                    return embed_recall.embed_texts([data])[0]
                except Exception:
                    pass
            return []

        def get_similar_question_sql(self, question: str, **kwargs) -> list:
            rows = store._data.get("question_sql") or []
            out = []
            for row in store.top("question_sql", question, n=5):
                for r in rows:
                    if r.get("text") == row:
                        out.append({"question": r.get("question", ""), "sql": r.get("sql", "")})
                        break
            return out

        def get_related_ddl(self, question: str, **kwargs) -> list:
            return store.top("ddl", question, n=5)

        def get_related_documentation(self, question: str, **kwargs) -> list:
            return store.top("documentation", question, n=5)

        def add_question_sql(self, question: str, sql: str, **kwargs) -> str:
            return store.add("question_sql", text=question, extra={"question": question, "sql": sql})

        def add_ddl(self, ddl: str, **kwargs) -> str:
            return store.add("ddl", text=ddl)

        def add_documentation(self, documentation: str, **kwargs) -> str:
            return store.add("documentation", text=documentation)

        def get_training_data(self, **kwargs):
            import pandas as pd

            rows = []
            for kind, ttype in (("question_sql", "sql"), ("ddl", "ddl"), ("documentation", "documentation")):
                for r in store._data.get(kind) or []:
                    rows.append(
                        {
                            "id": r.get("id"),
                            "training_data_type": ttype,
                            "question": r.get("question"),
                            "content": r.get("sql") or r.get("text"),
                        }
                    )
            return pd.DataFrame(rows)

        def remove_training_data(self, id: str, **kwargs) -> bool:
            changed = False
            for kind in ("question_sql", "ddl", "documentation"):
                before = len(store._data.get(kind) or [])
                store._data[kind] = [r for r in (store._data.get(kind) or []) if r.get("id") != id]
                if len(store._data[kind]) != before:
                    changed = True
            if changed:
                store._save()
            return changed

    return SmsVanna()


def get_sms_vanna():
    global _vn_instance
    with _lock:
        if _vn_instance is None:
            _vn_instance = _build_sms_vanna()
        return _vn_instance


def reset_sms_vanna() -> None:
    """Test helper: drop cached instance."""
    global _vn_instance
    with _lock:
        _vn_instance = None


def vanna_available() -> bool:
    try:
        from vanna.base.base import VannaBase  # noqa: F401

        return True
    except Exception:
        return False
