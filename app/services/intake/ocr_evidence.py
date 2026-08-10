# -*- coding: utf-8 -*-
"""PDF/image → cell evidence via rapidocr (PaddleOCR optional).

Docs/03 §2.3: PP-Structure primary when available; rapidocr fallback.
Grid reconstruction is heuristic (row/col clustering by bbox centers).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

_OCR_ENGINE = None
_OCR_BACKEND: str | None = None


def ocr_enabled() -> bool:
    return os.environ.get("OCR_ENABLED", "1").strip() not in {"0", "false", "False", "no"}


def _init_ocr():
    global _OCR_ENGINE, _OCR_BACKEND
    if _OCR_ENGINE is not None or _OCR_BACKEND == "unavailable":
        return
    # Prefer paddle when installed (docs primary); else rapidocr.
    try:
        from paddleocr import PaddleOCR  # type: ignore

        _OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        _OCR_BACKEND = "paddle"
        return
    except Exception:
        pass
    try:
        from rapidocr_onnxruntime import RapidOCR

        _OCR_ENGINE = RapidOCR()
        _OCR_BACKEND = "rapidocr"
        return
    except Exception:
        _OCR_BACKEND = "unavailable"
        _OCR_ENGINE = None


def ocr_backend() -> str:
    _init_ocr()
    return _OCR_BACKEND or "unavailable"


def _run_ocr_image(image_path: Path) -> list[tuple[str, list[list[float]]]]:
    """Return list of (text, quad_box)."""
    _init_ocr()
    if _OCR_ENGINE is None:
        raise RuntimeError("OCR engine unavailable (install rapidocr-onnxruntime or paddleocr)")
    path = str(image_path)
    out: list[tuple[str, list[list[float]]]] = []
    if _OCR_BACKEND == "paddle":
        result = _OCR_ENGINE.ocr(path, cls=True)
        for block in result or []:
            for line in block or []:
                box, (txt, _score) = line[0], line[1]
                if txt and str(txt).strip():
                    out.append((str(txt).strip(), box))
        return out
    # rapidocr: list of [box, text, score]
    result, _ = _OCR_ENGINE(path)
    for item in result or []:
        box, txt = item[0], item[1]
        if txt and str(txt).strip():
            out.append((str(txt).strip(), box))
    return out


def _center(box: list[list[float]]) -> tuple[float, float]:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def boxes_to_cells(
    items: list[tuple[str, list[list[float]]]],
    *,
    row_tol: float = 18.0,
) -> list[dict[str, Any]]:
    """Cluster OCR boxes into sheet-like cells (row/col 1-based)."""
    if not items:
        return []
    enriched = []
    for text, box in items:
        cx, cy = _center(box)
        enriched.append({"text": text, "box": box, "cx": cx, "cy": cy})
    enriched.sort(key=lambda r: (r["cy"], r["cx"]))

    rows: list[list[dict]] = []
    for rec in enriched:
        placed = False
        for cluster in rows:
            mean_y = sum(x["cy"] for x in cluster) / len(cluster)
            if abs(rec["cy"] - mean_y) <= row_tol:
                cluster.append(rec)
                placed = True
                break
        if not placed:
            rows.append([rec])

    cells: list[dict[str, Any]] = []
    for r_i, cluster in enumerate(rows, 1):
        cluster.sort(key=lambda r: r["cx"])
        for c_i, rec in enumerate(cluster, 1):
            cells.append(
                {
                    "row": r_i,
                    "col_idx": c_i,
                    "raw_value": rec["text"],
                    "cx": rec["cx"],
                    "cy": rec["cy"],
                }
            )
    return cells


def cells_to_evidence_df(
    cells: list[dict[str, Any]],
    *,
    file_id: str,
    sheet: str,
) -> pd.DataFrame:
    from app.services.evidence import col_letter

    rows = []
    for c in cells:
        rows.append(
            {
                "file_id": file_id,
                "sheet": sheet,
                "row": int(c["row"]),
                "col": col_letter(int(c["col_idx"]) - 1),
                "raw_value": str(c["raw_value"]),
                "value_type": "ocr",
            }
        )
    return pd.DataFrame(rows)


def cells_to_tabular(cells: list[dict[str, Any]]) -> pd.DataFrame | None:
    if not cells:
        return None
    max_r = max(int(c["row"]) for c in cells)
    max_c = max(int(c["col_idx"]) for c in cells)
    grid = [["" for _ in range(max_c)] for _ in range(max_r)]
    for c in cells:
        grid[int(c["row"]) - 1][int(c["col_idx"]) - 1] = str(c["raw_value"])
    if max_r < 1:
        return None
    header = [str(x).strip() or f"c{i+1}" for i, x in enumerate(grid[0])]
    body = grid[1:] if max_r > 1 else []
    if not body:
        return pd.DataFrame(columns=header)
    return pd.DataFrame(body, columns=header)


def _pdf_to_images(path: Path, *, max_pages: int = 5, scale: float = 2.0) -> list[Path]:
    import pypdfium2 as pdfium
    from PIL import Image

    out_dir = path.parent / f".ocr_{path.stem}"
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(str(path))
    images: list[Path] = []
    n = min(len(doc), max_pages)
    for i in range(n):
        page = doc[i]
        bitmap = page.render(scale=scale)
        pil: Image.Image = bitmap.to_pil()
        out = out_dir / f"page_{i+1:03d}.png"
        pil.save(out)
        images.append(out)
    return images


def load_ocr_evidence(
    path: Path,
    file_id: str,
    *,
    max_pages: int = 5,
) -> tuple[pd.DataFrame, int, pd.DataFrame | None, dict[str, Any]]:
    """Parse image/PDF into evidence + optional tabular projection."""
    if not ocr_enabled():
        raise RuntimeError("OCR_DISABLED")
    ext = path.suffix.lstrip(".").lower()
    meta: dict[str, Any] = {"backend": ocr_backend(), "pages": 1}
    image_paths: list[Path]
    if ext == "pdf":
        image_paths = _pdf_to_images(path, max_pages=max_pages)
        meta["pages"] = len(image_paths)
    else:
        image_paths = [path]

    all_cells: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []
    for i, img in enumerate(image_paths, 1):
        sheet = "pdf" if ext == "pdf" else "ocr"
        if ext == "pdf":
            sheet = f"pdf_p{i}"
        items = _run_ocr_image(img)
        cells = boxes_to_cells(items)
        for c in cells:
            c["sheet"] = sheet
        ev = cells_to_evidence_df(cells, file_id=file_id, sheet=sheet)
        frames.append(ev)
        # offset row numbers across pages for combined tabular attempt on page1 only
        if i == 1:
            all_cells = cells

    if not frames:
        empty = pd.DataFrame(
            columns=["file_id", "sheet", "row", "col", "raw_value", "value_type"]
        )
        return empty, meta["pages"], None, meta

    df = pd.concat(frames, ignore_index=True)
    tabular = cells_to_tabular(all_cells)
    meta["cells"] = int(len(df))
    meta["ocr_items"] = int(sum(1 for _ in df.iterrows()))
    return df, int(meta["pages"]), tabular, meta
