# -*- coding: utf-8 -*-
"""Compatibility shim (A1-1): re-exports from app.services.llm.embed_recall.

The implementation now lives in app/services/llm/embed_recall.py; this file exists
so existing `from app.services import embed_recall` / `from app.services.embed_recall import X`
keep working during the A0-1 router-split transition.
"""
from __future__ import annotations

from app.services.llm import embed_recall as _m  # noqa: F401

# Re-export every non-dunder name so attribute access and `from ... import` work.
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
del _m
