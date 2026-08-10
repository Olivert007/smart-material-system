# -*- coding: utf-8 -*-
"""Compatibility shim (A1-1): re-exports from app.services.govern.mapping_suggest.

The implementation now lives in app/services/govern/mapping_suggest.py; this file exists
so existing `from app.services import mapping_suggest` / `from app.services.mapping_suggest import X`
keep working during the A0-1 router-split transition.
"""
from __future__ import annotations

from app.services.govern import mapping_suggest as _m  # noqa: F401

# Re-export every non-dunder name so attribute access and `from ... import` work.
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
del _m
