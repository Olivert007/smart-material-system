# -*- coding: utf-8 -*-
"""Populate offline/wheelhouse and offline/npm-cache for doc 21 builds."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WHEELHOUSE = ROOT / "offline" / "wheelhouse"
NPM_CACHE = ROOT / "offline" / "npm-cache"
LOCK = ROOT / "requirements-lock.txt"
FRONTEND = ROOT / "frontend"


def prepare_wheelhouse() -> None:
    WHEELHOUSE.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "-r",
            str(LOCK),
            "-d",
            str(WHEELHOUSE),
        ],
        cwd=ROOT,
        check=True,
    )


def prepare_npm_cache() -> None:
    NPM_CACHE.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["npm", "ci", "--legacy-peer-deps", "--cache", str(NPM_CACHE)],
        cwd=FRONTEND,
        check=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wheelhouse-only", action="store_true")
    ap.add_argument("--npm-cache-only", action="store_true")
    args = ap.parse_args()
    do_wheel = not args.npm_cache_only
    do_npm = not args.wheelhouse_only
    if do_wheel:
        prepare_wheelhouse()
        print(f"wheelhouse: {WHEELHOUSE}")
    if do_npm:
        prepare_npm_cache()
        print(f"npm-cache: {NPM_CACHE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
