# -*- coding: utf-8 -*-
"""Report legacy service imports (doc 18 S3). Report-only; exit 0 always."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LEGACY_TO_CANONICAL: dict[str, str] = {
    "app.services.evidence": "app.services.intake.evidence",
    "app.services.profile": "app.services.intake.profile",
    "app.services.quality_precheck": "app.services.intake.quality_precheck",
    "app.services.mapping": "app.services.govern.mapping",
    "app.services.map_gov": "app.services.govern.map_gov",
    "app.services.rule_dict": "app.services.govern.rule_dict",
    "app.services.flow_parse": "app.services.govern.flow_parse",
    "app.services.flow_gov": "app.services.govern.flow_gov",
    "app.services.flow_config": "app.services.govern.flow_config",
    "app.services.model_client": "app.services.llm.model_client",
    "app.services.embed_recall": "app.services.llm.embed_recall",
}

SCAN_DIRS = ("app", "tests", "scripts")


def _module_from_node(node: ast.AST) -> str | None:
    if isinstance(node, ast.ImportFrom) and node.module:
        return node.module
    if isinstance(node, ast.Import):
        return None
    return None


def scan_file(path: Path) -> list[dict]:
    hits: list[dict] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, OSError):
        return hits
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        mod = node.module
        for legacy, canonical in LEGACY_TO_CANONICAL.items():
            if mod == legacy or mod.startswith(legacy + "."):
                hits.append(
                    {
                        "file": str(path.relative_to(ROOT)),
                        "line": node.lineno,
                        "legacy": mod,
                        "canonical": canonical,
                    }
                )
                break
    return hits


def scan_repo() -> dict:
    findings: list[dict] = []
    for dirname in SCAN_DIRS:
        base = ROOT / dirname
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            findings.extend(scan_file(path))
    by_legacy: dict[str, int] = {}
    for f in findings:
        by_legacy[f["legacy"]] = by_legacy.get(f["legacy"], 0) + 1
    return {
        "total": len(findings),
        "by_legacy": by_legacy,
        "findings": findings,
    }


def main() -> int:
    report = scan_repo()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
