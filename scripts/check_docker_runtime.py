# -*- coding: utf-8 -*-
"""Docker runtime checks for offline compose (doc 21 §13.2)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _fetch_json(url: str, timeout: float = 3.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def compose_ps(compose_file: Path) -> dict[str, bool]:
    r = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "ps", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    services = {
        "frontend": False,
        "api": False,
        "worker": False,
        "vllm-big": False,
        "vllm-fast": False,
        "vllm-embed": False,
    }
    if r.returncode != 0:
        return services
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = str(row.get("Service") or row.get("Name") or "")
        state = str(row.get("State") or row.get("Status") or "").lower()
        for key in list(services.keys()):
            if key in name:
                services[key] = "running" in state or state == "running"
    return services


def check_docker_runtime() -> dict:
    compose_file = ROOT / "deploy" / "compose-offline.yml"
    # Offline stack exposes API only inside the compose network; probe via nginx :8080.
    api_base = os.environ.get("API_BASE", "http://127.0.0.1:8080").rstrip("/")
    compose = compose_ps(compose_file)

    api_ready = False
    model_runtime = "none"
    blocking: list[str] = []

    try:
        ready = _fetch_json(f"{api_base}/health/ready")
        api_ready = ready.get("status") == "ready"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        blocking.append("api_not_ready")
        if isinstance(e, FileNotFoundError) or "No such file or directory" in str(e):
            pass

    if api_ready:
        try:
            models = _fetch_json(f"{api_base}/api/v1/models/status")
            model_runtime = str(models.get("model_runtime") or "degraded")
            blocking = list(models.get("blocking") or [])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            blocking.append("models_status_unreachable")

    return {
        "compose": compose,
        "api_ready": api_ready,
        "model_runtime": model_runtime,
        "blocking": blocking,
    }


def main() -> int:
    try:
        print(json.dumps(check_docker_runtime(), ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"api_ready": False, "model_runtime": "none", "blocking": ["check_failed"], "error": str(e)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
