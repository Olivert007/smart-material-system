# -*- coding: utf-8 -*-
"""Offline bundle integrity checks (doc 21 §13.1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_DOCKERIGNORE = {".git", "data/", "node_modules", ".env"}


def check_dockerignore(root: Path) -> dict:
    path = root / ".dockerignore"
    if not path.is_file():
        return {"ok": False, "missing": list(REQUIRED_DOCKERIGNORE)}
    text = path.read_text(encoding="utf-8")
    lines = {ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")}
    missing = sorted(REQUIRED_DOCKERIGNORE - lines)
    return {"ok": not missing, "missing": missing}


def _dir_has_files(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def check_offline_bundle(manifest_path: Path, root: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checks: dict = {"manifest": str(manifest_path.relative_to(root)), "items": {}}

    dockerignore = check_dockerignore(root)
    checks["dockerignore"] = dockerignore

    for key in ("wheelhouse", "npm_cache", "frontend_dist"):
        rel = manifest.get(key)
        if rel:
            p = root / rel
            checks["items"][key] = {
                "path": rel,
                "exists": p.exists(),
                "populated": _dir_has_files(p) if p.is_dir() else p.is_file(),
            }

    models = manifest.get("models") or []
    model_checks = []
    for m in models:
        p = root / m.get("path", "")
        model_checks.append({"path": m.get("path"), "exists": p.exists()})
    checks["models"] = model_checks

    items = checks["items"]
    wheelhouse_ok = items.get("wheelhouse", {}).get("populated", False)
    npm_ok = items.get("npm_cache", {}).get("populated", False)
    dist_ok = items.get("frontend_dist", {}).get("exists", False)
    checks["build_assets"] = {
        "wheelhouse_or_dist": wheelhouse_ok or dist_ok,
        "npm_cache": npm_ok,
        "frontend_dist": dist_ok,
    }
    checks["ok"] = dockerignore["ok"] and (wheelhouse_ok or dist_ok)
    return checks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="deploy/offline-manifest.example.json")
    args = ap.parse_args()
    manifest = ROOT / args.manifest
    out = check_offline_bundle(manifest, ROOT)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
