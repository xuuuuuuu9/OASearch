"""Background search task execution shared by UI and API layers."""
from __future__ import annotations

import logging

from . import repo
from .clients import oa_resolver
from .clients.crossref import CrossRefClient
from .db import get_db
from .models import SearchRequest


log = logging.getLogger("nplibrary.search_tasks")


async def run_search_task(task_id: int, req: SearchRequest) -> None:
    """Run a persisted search task from CrossRef through OA resolution."""
    try:
        async with get_db() as db:
            await repo.update_search_task(db, task_id, status="running", stage="crossref")

        async with CrossRefClient() as cr:
            works = await cr.search(
                q=req.q,
                issns=req.issns,
                year_from=req.year_from,
                year_to=req.year_to,
                rows=req.rows,
            )

        async with get_db() as db:
            await repo.update_search_task(db, task_id, stage="resolve_oa", total=len(works))

        crossref_links_map: dict[str, list[str]] = {}
        dois: list[str] = []
        for work in works:
            doi = work.get("doi")
            if not doi:
                continue
            dois.append(doi)
            if work.get("pdf_links"):
                crossref_links_map[doi] = work["pdf_links"]

        candidate_map = await oa_resolver.resolve_many(
            dois,
            crossref_pdf_links_map=crossref_links_map,
        )

        ordered_dois: list[str] = []
        oa_count = 0
        async with get_db() as db:
            for work in works:
                doi = work.get("doi")
                if not doi:
                    continue
                cands, oa_info = candidate_map.get(doi, ([], {}))
                await repo.upsert_paper(db, work, oa=oa_info)
                if cands:
                    await repo.upsert_candidates(
                        db,
                        doi,
                        [{"url": c.url, "source": c.source, "priority": c.priority} for c in cands],
                    )
                ordered_dois.append(doi)
                if oa_info.get("is_oa") and cands:
                    oa_count += 1
            await db.commit()
            await repo.update_search_task(
                db,
                task_id,
                status="done",
                stage="done",
                total=len(ordered_dois),
                oa=oa_count,
                result_dois=ordered_dois,
                finished=True,
            )
    except Exception as exc:
        log.exception("search task %d failed", task_id)
        async with get_db() as db:
            await repo.update_search_task(
                db,
                task_id,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                finished=True,
            )
