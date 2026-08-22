# -*- coding: utf-8 -*-
"""API surface audit (doc 19). Does not start worker."""
from __future__ import annotations

import json
import re
import sys
from typing import Any

# Prevent worker side effects during import
import os

os.environ.setdefault("DISABLE_INTAKE_WORKER", "1")

from app.main import app  # noqa: E402

STABLE_PREFIXES = (
    "/health/",
    "/api/v1/files",
    "/api/v1/tasks",
    "/api/v1/intake/",
    "/api/v1/stats/",
    "/api/v1/materials/",
)

OPS_PREFIXES = (
    "/api/v1/ops/",
)

EXPERIMENTAL_PREFIXES = (
    "/api/v1/govern/flow/suggest",
    "/api/v1/govern/flow/opening/seed",
)

LEGACY_PREFIXES = (
    "/api/legacy/",
)

DANGEROUS_PATTERN = re.compile(
    r"(delete|rebuild|supersede|restore|backup|activate|restart)",
    re.I,
)


def classify_route(path: str, methods: set[str]) -> str:
    upper = path.lower()
    if any(upper.startswith(p.lower()) for p in LEGACY_PREFIXES):
        return "legacy"
    if any(upper.startswith(p.lower()) for p in OPS_PREFIXES):
        return "ops"
    if any(upper.startswith(p.lower()) for p in EXPERIMENTAL_PREFIXES):
        return "experimental"
    if any(upper.startswith(p.lower()) for p in STABLE_PREFIXES):
        return "stable"
    if upper.startswith("/api/v1/govern/"):
        return "stable"
    if upper.startswith("/api/v1/"):
        return "stable"
    if upper.startswith("/events/"):
        return "stable"
    return "unclassified"


def is_dangerous(path: str, methods: set[str]) -> bool:
    blob = f"{' '.join(sorted(methods))} {path}"
    return bool(DANGEROUS_PATTERN.search(blob))


def audit_surface() -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    counts = {"stable": 0, "ops": 0, "experimental": 0, "legacy": 0, "unclassified": 0, "dangerous": 0}

    for route in app.routes:
        path = getattr(route, "path", None)
        methods = set(getattr(route, "methods", None) or [])
        if not path or path == "/openapi.json":
            continue
        if "HEAD" in methods:
            methods.discard("HEAD")
        level = classify_route(path, methods)
        dangerous = is_dangerous(path, methods)
        counts[level] = counts.get(level, 0) + 1
        if dangerous:
            counts["dangerous"] += 1
        routes.append(
            {
                "path": path,
                "methods": sorted(methods),
                "level": level,
                "dangerous": dangerous,
            }
        )

    return {
        "counts": counts,
        "routes": sorted(routes, key=lambda r: (r["level"], r["path"])),
    }


def main() -> int:
    print(json.dumps(audit_surface(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
