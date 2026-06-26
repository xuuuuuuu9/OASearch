"""File serving — PDF only. The rest of the UI is NiceGUI-based."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import PDF_DIR
from ..db import get_db
from .. import repo


router = APIRouter()


@router.get("/pdf/{paper_id}")
async def serve_pdf(paper_id: int):
    async with get_db() as db:
        paper = await repo.get_paper_by_id(db, paper_id)
    if not paper or not paper.get("pdf_path"):
        raise HTTPException(404, "PDF not found")
    abs_path = PDF_DIR / paper["pdf_path"]
    if not abs_path.exists():
        raise HTTPException(404, "PDF file missing on disk")

    title = (paper.get("title") or "paper").strip()
    title = title.replace("/", "_").replace("\\", "_")[:80]
    ascii_fallback = "".join(c if ord(c) < 128 and c not in '"\\' else "_" for c in title)
    encoded = quote(title.encode("utf-8"))

    return FileResponse(
        path=abs_path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="{ascii_fallback}.pdf"; '
                f"filename*=UTF-8''{encoded}.pdf"
            )
        },
    )
