"""metrics services - see README.md.

Re-exports the same-name module's public API so existing
`from app.services.metrics import X` keeps working (the package shadows the
old flat module of the same name).
"""
from __future__ import annotations

from app.services.metrics import metrics as _m  # noqa: F401
globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
del _m
