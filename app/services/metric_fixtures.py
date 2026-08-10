# -*- coding: utf-8 -*-
"""Compatibility shim (A1-1): re-exports from app.services.metrics.metric_fixtures.

The implementation now lives in app/services/metrics/metric_fixtures.py; this file exists
so existing `from app.services import metric_fixtures` / `from app.services.metric_fixtures import X`
keep working during the A0-1 router-split transition.
"""
from __future__ import annotations

from app.services.metrics import metric_fixtures as _m  # noqa: F401

# Re-export every non-dunder name so attribute access and `from ... import` work.
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
del _m
