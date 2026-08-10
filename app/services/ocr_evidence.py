# -*- coding: utf-8 -*-
"""Compatibility shim (A1-1): re-exports from app.services.intake.ocr_evidence.

The implementation now lives in app/services/intake/ocr_evidence.py; this file exists
so existing `from app.services import ocr_evidence` / `from app.services.ocr_evidence import X`
keep working during the A0-1 router-split transition.
"""
from __future__ import annotations

from app.services.intake import ocr_evidence as _m  # noqa: F401

# Re-export every non-dunder name so attribute access and `from ... import` work.
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
del _m
