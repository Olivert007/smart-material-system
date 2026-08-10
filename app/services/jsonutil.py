# -*- coding: utf-8 -*-
"""Compatibility shim (A1-1): re-exports from app.services.infra.jsonutil.

The implementation now lives in app/services/infra/jsonutil.py; this file exists
so existing `from app.services import jsonutil` / `from app.services.jsonutil import X`
keep working during the A0-1 router-split transition.
"""
from __future__ import annotations

from app.services.infra import jsonutil as _m  # noqa: F401

# Re-export every non-dunder name so attribute access and `from ... import` work.
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
del _m
