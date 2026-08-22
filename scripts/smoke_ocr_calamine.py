#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCR + calamine evidence smoke (OCR_CALAMINE_OK)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="sms_ocr_"))
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
os.environ["DATA_DIR"] = str(TMP)
os.environ["OCR_ENABLED"] = "1"

sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.repositories.db import init_meta  # noqa: E402
from app.services.intake.evidence import _SUPPORTED, load_to_evidence  # noqa: E402
from app.services.ocr_evidence import boxes_to_cells, ocr_backend  # noqa: E402


def _make_xls(path: Path) -> None:
    import xlwt

    w = xlwt.Workbook()
    s = w.add_sheet("inv")
    s.write(0, 0, "物资名称")
    s.write(0, 1, "数量")
    s.write(1, 0, "轴承")
    s.write(1, 1, 12)
    w.save(str(path))


def _make_png(path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (520, 160), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    # ASCII for font-less environments; validates OCR→evidence path
    d.text((20, 30), "NAME", fill="black", font=font)
    d.text((200, 30), "QTY", fill="black", font=font)
    d.text((20, 90), "BEARING", fill="black", font=font)
    d.text((200, 90), "10", fill="black", font=font)
    img.save(path)


def _make_pdf_from_png(png: Path, pdf: Path) -> None:
    import pypdfium2 as pdfium
    from PIL import Image

    # pypdfium2 is primarily a reader; write a tiny PDF manually.
    # Minimal one-page PDF embedding is complex; instead render-check via
    # creating PDF with img2pdf if available, else skip PDF and mark optional.
    try:
        import img2pdf  # type: ignore

        pdf.write_bytes(img2pdf.convert(str(png)))
        return
    except Exception:
        pass
    # Fallback: write a text-only minimal PDF (no image) — OCR may get nothing;
    # still validates pdfium open path separately below.
    pdf.write_bytes(
        b"""%PDF-1.1
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj
4 0 obj<< /Length 44 >>stream
BT /F1 24 Tf 40 80 Td (QTY 10) Tj ET
endstream
endobj
5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000360 00000 n 
trailer<< /Size 6 /Root 1 0 R >>
startxref
433
%%EOF
"""
    )
    _ = pdfium  # imported for availability assertion
    _ = Image


def main() -> int:
    init_meta()
    config.RAW.mkdir(parents=True, exist_ok=True)
    assert "xls" in _SUPPORTED and "ods" in _SUPPORTED and "pdf" in _SUPPORTED

    # grid unit (no OCR)
    cells = boxes_to_cells(
        [
            ("物资名称", [[10, 10], [80, 10], [80, 30], [10, 30]]),
            ("数量", [[100, 12], [140, 12], [140, 28], [100, 28]]),
            ("轴承", [[10, 50], [60, 50], [60, 70], [10, 70]]),
            ("10", [[100, 52], [130, 52], [130, 68], [100, 68]]),
        ]
    )
    assert len(cells) == 4 and cells[0]["row"] == 1 and cells[2]["row"] == 2

    xls = TMP / "sample.xls"
    _make_xls(xls)
    df, fmt, sheets, tab = load_to_evidence(xls, "f_xls")
    assert fmt == "xls" and sheets >= 1 and len(df) >= 4, (fmt, sheets, len(df), df.head())
    assert any("轴承" in str(v) for v in df["raw_value"].tolist())

    png = TMP / "sample.png"
    _make_png(png)
    backend = ocr_backend()
    assert backend in {"rapidocr", "paddle"}, backend
    df2, fmt2, sheets2, _tab2 = load_to_evidence(png, "f_png")
    assert fmt2 == "png" and len(df2) >= 1, (fmt2, len(df2), df2)
    assert sheets2 >= 1

    pdf = TMP / "sample.pdf"
    _make_pdf_from_png(png, pdf)
    df3, fmt3, sheets3, _ = load_to_evidence(pdf, "f_pdf")
    assert fmt3 == "pdf" and sheets3 >= 1

    print("OCR_CALAMINE_OK")
    print(f"xls_rows={len(df)} ocr_backend={backend} png_rows={len(df2)} pdf_pages={sheets3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
