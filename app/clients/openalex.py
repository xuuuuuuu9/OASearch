"""OpenAlex client.

OpenAlex aggregates OA discovery from a wider set of sources than Unpaywall
(institutional repositories, preprint servers, OpenAIRE, BASE, etc.).
Free, polite-pool friendly (mailto in query string).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from curl_cffi import requests as curl_requests

from ..config import settings


log = logging.getLogger("nplibrary.openalex")
OPENALEX_BASE = "https://api.openalex.org/works"


class OpenAlexClient:
    def __init__(self, concurrency: int = 12):
        self._session = curl_requests.AsyncSession(
            impersonate="chrome",
            timeout=15.0,
            headers={"User-Agent": settings.app_user_agent},
        )
        self._sem = asyncio.Semaphore(concurrency)

    async def __aenter__(self) -> "OpenAlexClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._session.close()

    async def lookup(self, doi: str) -> Optional[dict[str, Any]]:
        """Return dict with is_oa(bool), oa_status(str), pdf_urls(list[str]).

        pdf_urls is collected across all `locations` (publisher + repos +
        preprints), de-duplicated, ordered preferring repositories first
        (since publisher URL likely overlaps with what Unpaywall gave us).
        """
        doi = (doi or "").strip().lower()
        if not doi:
            return None

        async with self._sem:
            try:
                resp = await self._session.get(
                    f"{OPENALEX_BASE}/https://doi.org/{doi}",
                    params={"mailto": settings.user_email},
                )
            except Exception as e:
                log.debug("openalex network error %s: %r", doi, e)
                return None
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                return None
            try:
                data = resp.json()
            except Exception:
                return None

        oa = data.get("open_access") or {}
        is_oa = bool(oa.get("is_oa"))
        oa_status = oa.get("oa_status")  # gold / hybrid / green / bronze / closed

        # Gather PDF URLs across all locations (publisher + repositories).
        # Prefer non-publisher sources (repositories) because those bypass
        # publisher Cloudflare.
        repo_urls: list[str] = []
        pub_urls: list[str] = []
        for loc in data.get("locations") or []:
            pdf = loc.get("pdf_url")
            if not pdf:
                continue
            source = (loc.get("source") or {}).get("type") or ""
            if source == "repository":
                if pdf not in repo_urls:
                    repo_urls.append(pdf)
            else:
                if pdf not in pub_urls:
                    pub_urls.append(pdf)

        # Also the top-level open_access.oa_url
        top_pdf = oa.get("oa_url")
        if top_pdf and top_pdf not in repo_urls and top_pdf not in pub_urls:
            pub_urls.append(top_pdf)

        return {
            "is_oa": is_oa,
            "oa_status": oa_status,
            "repo_pdf_urls": repo_urls,    # preferred — usually repository PDFs
            "pub_pdf_urls": pub_urls,      # fallback — often same as Unpaywall
        }
