from __future__ import annotations

from pathlib import Path
from typing import Any


def load_pdf(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    items: list[dict[str, Any]] = []
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    items.append({"text": text, "page": index, "source": path.name})
    except Exception:
        items = []
    if items:
        return items

    # Last-resort fallback for environments with pypdf installed.
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                items.append({"text": text, "page": index, "source": path.name})
    except Exception as exc:
        raise ValueError(f"Could not extract text from PDF: {exc}") from exc
    return items
