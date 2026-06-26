"""Semantic Scholar Graph API client — OA PDF lookup by DOI.

API doc: https://api.semanticscholar.org/api-docs/graph

Without an API key the public limit is 100 req / 5 min (≈0.33 req/s). Set
`SEMANTIC_SCHOLAR_API_KEY` in .env to raise the rate to ~10 req/s.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from ..config import settings


log = logging.getLogger("nplibrary.semantic_scholar")


BASE_URL = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarClient:
    def __init__(self, concurrency: int = 8, api_key: Optional[str] = None):
        self._sem = asyncio.Semaphore(concurrency)
        self._api_key = api_key or settings.semantic_scholar_api_key or None
        self._session: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "SemanticScholarClient":
        headers: dict[str, str] = {"User-Agent": settings.app_user_agent}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        self._session = httpx.AsyncClient(
            timeout=settings.http_timeout,
            headers=headers,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *a: Any) -> None:
        if self._session is not None:
            await self._session.aclose()

    async def lookup(self, doi: str) -> dict[str, Any]:
        """Fetch openAccessPdf for the given DOI.

        Returns a dict possibly containing:
          pdf_url:  the OA PDF link, when present
          status:   S2's classification ('GREEN' / 'GOLD' / 'BRONZE' / etc.)
          paper_id: S2's internal identifier (debugging only)
        Empty dict on miss / error.
        """
        doi = (doi or "").strip()
        if not doi or self._session is None:
            return {}

        url = f"{BASE_URL}/paper/DOI:{doi}"
        params = {"fields": "openAccessPdf,externalIds"}
        try:
            async with self._sem:
                resp = await self._session.get(url, params=params)
        except httpx.HTTPError as e:
            log.debug("semantic-scholar fetch failed %s: %r", doi, e)
            return {}

        if resp.status_code == 404:
            return {}
        if resp.status_code == 429:
            log.info("semantic-scholar rate-limited on %s", doi)
            return {}
        if resp.status_code != 200:
            log.debug("semantic-scholar %s -> %s", doi, resp.status_code)
            return {}

        try:
            data = resp.json()
        except ValueError:
            return {}

        oa_pdf = data.get("openAccessPdf") or {}
        pdf_url = (oa_pdf.get("url") or "").strip()
        return {
            "pdf_url": pdf_url if pdf_url else None,
            "status": oa_pdf.get("status") or None,
            "paper_id": data.get("paperId"),
        }
