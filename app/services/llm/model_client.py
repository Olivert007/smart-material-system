# -*- coding: utf-8 -*-
"""Stage 1 ModelClient: OpenAI-compatible chat + circuit breaker + llm_call audit."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app import config
from app.repositories import meta_tx


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class CircuitState:
    fails: int = 0
    open_until: float = 0.0


@dataclass
class LlmResult:
    ok: bool
    text: str = ""
    model: str = ""
    endpoint: str = ""
    model_request_attempted: bool = False
    model_invoked: bool = False
    output_available: bool = False
    model_state: str = "not_attempted"
    fallback_reason: str | None = None
    error: str | None = None
    latency_ms: int = 0
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


_circuits: dict[str, CircuitState] = {}


def _circuit(key: str) -> CircuitState:
    if key not in _circuits:
        _circuits[key] = CircuitState()
    return _circuits[key]


def circuit_allow(key: str) -> bool:
    st = _circuit(key)
    if st.open_until and time.time() < st.open_until:
        return False
    return True


def circuit_success(key: str) -> None:
    st = _circuit(key)
    st.fails = 0
    st.open_until = 0.0


def circuit_fail(key: str) -> None:
    st = _circuit(key)
    st.fails += 1
    if st.fails >= config.LLM_CIRCUIT_FAILS:
        st.open_until = time.time() + config.LLM_CIRCUIT_COOLDOWN_SEC


def _http_json(method: str, url: str, payload: dict | None = None, timeout: float = 30) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def probe_endpoint(endpoint: str, timeout: float = 5) -> dict:
    """Return {ok, models[]}."""
    base = endpoint.rstrip("/")
    try:
        data = _http_json("GET", f"{base}/models", timeout=timeout)
        models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
        return {"ok": True, "models": models, "endpoint": endpoint}
    except Exception as e:
        return {"ok": False, "models": [], "endpoint": endpoint, "error": str(e)}


def _audit(
    *,
    call_id: str,
    role: str,
    endpoint: str,
    model: str,
    task_type: str,
    result: LlmResult,
    prompt_chars: int,
) -> None:
    with meta_tx() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_call (
                call_id TEXT PRIMARY KEY,
                role TEXT,
                endpoint TEXT,
                model TEXT,
                task_type TEXT,
                model_state TEXT,
                ok INTEGER,
                latency_ms INTEGER,
                prompt_chars INTEGER,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        con.execute(
            """
            INSERT INTO llm_call (
                call_id, role, endpoint, model, task_type, model_state, ok, latency_ms, prompt_chars, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                call_id,
                role,
                endpoint,
                model,
                task_type,
                result.model_state,
                1 if result.ok else 0,
                result.latency_ms,
                prompt_chars,
                (result.error or "")[:500],
                _now(),
            ],
        )


def chat(
    *,
    role: str,
    messages: list[dict[str, str]],
    task_type: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    model: str | None = None,
    endpoint: str | None = None,
) -> LlmResult:
    """Stage 1: role=big (or fast later). No cascade/cross-check here."""
    if role == "big":
        endpoint = endpoint or config.LLM_BIG_ENDPOINT
        model = model or config.LLM_BIG_MODEL
    elif role == "fast":
        endpoint = endpoint or config.LLM_FAST_ENDPOINT
        model = model or config.LLM_FAST_MODEL
    else:
        raise ValueError(f"unsupported role: {role}")

    key = f"{role}:{endpoint}"
    call_id = uuid.uuid4().hex[:12]
    result = LlmResult(ok=False, model=model or "", endpoint=endpoint, call_id=call_id, model_request_attempted=True)

    if not circuit_allow(key):
        result.model_state = "circuit_open"
        result.fallback_reason = "circuit_open"
        result.error = "circuit open"
        _audit(call_id=call_id, role=role, endpoint=endpoint, model=model or "", task_type=task_type, result=result, prompt_chars=sum(len(m.get("content", "")) for m in messages))
        return result

    # auto-detect model id if empty
    if not model:
        probe = probe_endpoint(endpoint, timeout=5)
        if probe["ok"] and probe["models"]:
            model = probe["models"][0]
            result.model = model
        else:
            result.model_state = "local_model_unavailable"
            result.error = probe.get("error") or "no models"
            circuit_fail(key)
            _audit(call_id=call_id, role=role, endpoint=endpoint, model="", task_type=task_type, result=result, prompt_chars=0)
            return result

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        # Qwen3.6 template: enable_thinking=false skips long reasoning dumps
        "chat_template_kwargs": {"enable_thinking": bool(config.LLM_ENABLE_THINKING)},
    }
    url = endpoint.rstrip("/") + "/chat/completions"
    t0 = time.time()
    attempts = 1 + max(0, int(config.LLM_MAX_RETRIES))
    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            data = _http_json("POST", url, payload, timeout=config.LLM_TIMEOUT_SEC)
            msg = data["choices"][0]["message"]
            text = msg.get("content") or ""
            # Strip leaked <think>...</think> if thinking was partially emitted
            if "</think>" in text:
                text = text.split("</think>", 1)[-1].lstrip("\n")
            result.ok = True
            result.text = text or ""
            result.model_invoked = True
            result.output_available = bool(result.text.strip())
            result.model_state = "llm_analysis_available" if result.output_available else "llm_output_invalid"
            result.latency_ms = int((time.time() - t0) * 1000)
            result.error = None
            circuit_success(key)
            last_err = None
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="ignore")[:300]
            last_err = e
            result.error = f"HTTP {e.code}: {body}"
            result.model_invoked = True
            result.model_state = "llm_invocation_failed"
            result.latency_ms = int((time.time() - t0) * 1000)
            # Do not retry client errors (4xx except 429)
            if 400 <= int(e.code) < 500 and int(e.code) != 429:
                break
            if attempt + 1 < attempts:
                time.sleep(min(2.0, 0.25 * (2**attempt)))
                continue
        except Exception as e:
            last_err = e
            result.error = str(e)
            result.model_state = "local_model_unavailable"
            result.latency_ms = int((time.time() - t0) * 1000)
            if attempt + 1 < attempts:
                time.sleep(min(2.0, 0.25 * (2**attempt)))
                continue
    if not result.ok:
        circuit_fail(key)
        if last_err and not result.error:
            result.error = str(last_err)

    _audit(
        call_id=call_id,
        role=role,
        endpoint=endpoint,
        model=model or "",
        task_type=task_type,
        result=result,
        prompt_chars=sum(len(m.get("content", "")) for m in messages),
    )
    return result


def parse_json_object(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    # greedy object
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None
