"""JSON API for the Reflex frontend."""
from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import repo
from ..clients.crossref import CrossRefClient
from ..config import DB_PATH
from ..db import get_db
from ..downloader import retry_failed_items, run_download_task
from ..models import DownloadRequest, SearchRequest
from ..search_tasks import run_search_task


router = APIRouter(prefix="/api")


class JournalCreate(BaseModel):
    issn: str = Field(..., min_length=7, max_length=20)
    name: Optional[str] = None
    publisher: Optional[str] = None


class JournalUpdate(BaseModel):
    enabled: bool


def spawn_search_task(task_id: int, req: SearchRequest) -> None:
    asyncio.create_task(run_search_task(task_id, req))


def spawn_download_task(task_id: int, db_path: str) -> None:
    asyncio.create_task(run_download_task(task_id, db_path))


def retry_download_items(task_id: int, db_path: str, dois: Optional[list[str]] = None) -> None:
    asyncio.create_task(retry_failed_items(task_id, db_path, dois))


def _decode_json_list(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    with suppress(json.JSONDecodeError):
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


async def _serialize_task_papers(task_id: int) -> list[dict[str, Any]]:
    async with get_db() as db:
        papers = await repo.get_search_task_papers(db, task_id)
        for paper in papers:
            raw = paper.get("authors") or ""
            with suppress(json.JSONDecodeError):
                paper["authors_list"] = json.loads(raw) if raw else []
            if "authors_list" not in paper:
                paper["authors_list"] = []
            candidates = await repo.get_candidates(db, paper["doi"])
            viable = [c for c in candidates if c["last_status"] != "permanent_fail"]
            paper["candidate_count"] = len(viable)
            paper["candidate_sources"] = sorted({c["source"] for c in viable})
            paper["auto_downloadable_count"] = len(viable)
        return papers


@router.get("/journals")
async def api_list_journals(enabled_only: bool = False) -> list[dict[str, Any]]:
    async with get_db() as db:
        return await repo.list_journals(db, enabled_only=enabled_only)


@router.post("/journals")
async def api_create_journal(payload: JournalCreate) -> dict[str, Any]:
    name = (payload.name or "").strip()
    publisher = payload.publisher
    if not name:
        try:
            async with CrossRefClient() as cr:
                info = await cr.validate_issn(payload.issn)
        except Exception:
            info = None
        if info:
            name = info.get("name") or ""
            publisher = publisher or info.get("publisher")
    if not name:
        raise HTTPException(400, "name is required when ISSN validation cannot resolve a journal")
    async with get_db() as db:
        await repo.add_journal(db, payload.issn, name, publisher)
        journals = await repo.list_journals(db)
    for journal in journals:
        if journal["issn"] == payload.issn:
            return journal
    raise HTTPException(500, "journal create failed")


@router.patch("/journals/{issn}")
async def api_update_journal(issn: str, payload: JournalUpdate) -> dict[str, Any]:
    async with get_db() as db:
        await repo.set_journal_enabled(db, issn, payload.enabled)
        journals = await repo.list_journals(db)
    for journal in journals:
        if journal["issn"] == issn:
            return journal
    raise HTTPException(404, "journal not found")


@router.delete("/journals/{issn}")
async def api_delete_journal(issn: str) -> dict[str, bool]:
    async with get_db() as db:
        await repo.delete_journal(db, issn)
    return {"ok": True}


@router.get("/library/search")
async def api_library_search(
    q: str = "",
    scope: str = "all",
    page: int = 1,
    page_size: int = 20,
    issn: Optional[list[str]] = Query(default=None),
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    author: Optional[str] = None,
    sort: str = "date_desc",
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    async with get_db() as db:
        items, total = await repo.search_local(
            db,
            q,
            issns=issn or None,
            scope=scope,
            year_from=year_from,
            year_to=year_to,
            author=author,
            sort=sort,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
    for item in items:
        raw = item.get("authors") or ""
        with suppress(json.JSONDecodeError):
            item["authors_list"] = json.loads(raw) if raw else []
        if "authors_list" not in item:
            item["authors_list"] = []
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/search-tasks")
async def api_list_search_tasks(limit: int = 10) -> list[dict[str, Any]]:
    async with get_db() as db:
        items = await repo.list_recent_searches(db, limit=max(1, min(limit, 50)))
    for item in items:
        item["issns"] = _decode_json_list(item.get("issns"))
    return items


@router.post("/search-tasks")
async def api_create_search_task(payload: SearchRequest) -> dict[str, Any]:
    async with get_db() as db:
        task_id = await repo.create_search_task(
            db,
            payload.q,
            payload.issns,
            payload.year_from,
            payload.year_to,
            payload.rows,
        )
        task = await repo.get_search_task(db, task_id)
    spawn_search_task(task_id, payload)
    return task or {"id": task_id}


@router.get("/search-tasks/latest")
async def api_get_latest_search_task() -> dict[str, Any]:
    async with get_db() as db:
        items = await repo.list_recent_searches(db, limit=1)
        if not items:
            raise HTTPException(404, "no search task found")
        task = await repo.get_search_task(db, items[0]["id"])
    if not task:
        raise HTTPException(404, "no search task found")
    return task


@router.get("/search-tasks/{task_id}")
async def api_get_search_task(task_id: int) -> dict[str, Any]:
    async with get_db() as db:
        task = await repo.get_search_task(db, task_id)
    if not task:
        raise HTTPException(404, "search task not found")
    return task


@router.get("/search-tasks/{task_id}/papers")
async def api_get_search_task_papers(task_id: int) -> list[dict[str, Any]]:
    return await _serialize_task_papers(task_id)


@router.get("/download-tasks")
async def api_list_download_tasks(limit: int = 20) -> list[dict[str, Any]]:
    async with get_db() as db:
        return await repo.list_tasks(db, limit=max(1, min(limit, 100)))


@router.post("/download-tasks")
async def api_create_download_task(payload: DownloadRequest) -> dict[str, Any]:
    async with get_db() as db:
        placeholders = ",".join(["?"] * len(payload.dois))
        cur = await db.execute(
            f"SELECT DISTINCT p.doi FROM papers p "
            f"LEFT JOIN paper_candidates c ON c.doi = p.doi "
            f"WHERE p.doi IN ({placeholders}) AND p.pdf_path IS NULL "
            f"AND (c.url IS NOT NULL OR p.oa_url IS NOT NULL);",
            payload.dois,
        )
        eligible = [r["doi"] for r in await cur.fetchall()]
        if not eligible:
            raise HTTPException(400, "no eligible papers to download")
        task_id = await repo.create_download_task(db, eligible)
        task = await repo.get_task(db, task_id)
    spawn_download_task(task_id, str(DB_PATH))
    return task or {"id": task_id}


@router.get("/download-tasks/{task_id}")
async def api_get_download_task(task_id: int) -> dict[str, Any]:
    async with get_db() as db:
        task = await repo.get_task(db, task_id)
    if not task:
        raise HTTPException(404, "download task not found")
    return task


@router.post("/download-tasks/{task_id}/retry")
async def api_retry_download_task(task_id: int) -> dict[str, Any]:
    retry_download_items(task_id, str(DB_PATH), None)
    return {"accepted": True, "task_id": task_id}


@router.post("/download-tasks/{task_id}/items/{doi:path}/retry")
async def api_retry_download_item(task_id: int, doi: str) -> dict[str, Any]:
    retry_download_items(task_id, str(DB_PATH), [doi])
    return {"accepted": True, "task_id": task_id, "doi": doi}
