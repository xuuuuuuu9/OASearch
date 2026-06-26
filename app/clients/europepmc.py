"""Europe PMC REST client.

DOI → PMCID lookup. When a PMCID exists, we generate the canonical PDF URL
which NIH/Europe PMC serves directly, without Cloudflare, very fast — by far
the highest-success-rate source for any PubMed-indexed paper.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from curl_cffi import requests as curl_requests

from ..config import settings


log = logging.getLogger("nplibrary.europepmc")
EPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"


class EuropePMCClient:
    """Async client; safe to share within one search task."""

    def __init__(self, concurrency: int = 8):
        self._session = curl_requests.AsyncSession(
            impersonate="chrome",
            timeout=15.0,
            headers={"User-Agent": settings.app_user_agent},
        )
        self._sem = asyncio.Semaphore(concurrency)

    async def __aenter__(self) -> "EuropePMCClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._session.close()

    async def lookup(self, doi: str) -> Optional[dict[str, Any]]:
        """Return dict with pmcid/pmid/in_pmc/oa_status, or None on miss/error.

        Sample response (interesting fields):
          pmcid     "PMC11234567"
          pmid      "39123456"
          inPMC     "Y" / "N"
          isOpenAccess "Y" / "N"
        """
        doi = (doi or "").strip()
        if not doi:
            return None

        async with self._sem:
            try:
                resp = await self._session.get(
                    f"{EPMC_BASE}/search",
                    params={
                        "query": f"DOI:{doi}",
                        "resultType": "lite",
                        "format": "json",
                        "pageSize": "1",
                    },
                )
            except Exception as e:
                log.debug("europepmc network error for %s: %r", doi, e)
                return None

            if resp.status_code != 200:
                return None
            try:
                data = resp.json()
            except Exception:
                return None

        results = (data.get("resultList") or {}).get("result") or []
        if not results:
            return None
        r = results[0]

        pmcid = r.get("pmcid")
        return {
            "pmcid": pmcid,
            "pmid": r.get("pmid"),
            "in_pmc": (r.get("inPMC") or "").upper() == "Y",
            "is_oa": (r.get("isOpenAccess") or "").upper() == "Y",
            "source": r.get("source"),
        }

    @staticmethod
    def pdf_url_for_pmcid(pmcid: str) -> str:
        """Canonical Europe PMC PDF URL — direct, no auth, very reliable."""
        pmcid = pmcid.strip()
        if pmcid.upper().startswith("PMC"):
            pmcid_num = pmcid[3:]
        else:
            pmcid_num = pmcid
        # Use the render endpoint; works regardless of publisher.
        return f"https://europepmc.org/articles/PMC{pmcid_num}?pdf=render"

    @staticmethod
    def ncbi_pdf_url_for_pmcid(pmcid: str) -> str:
        """Fallback PDF URL on NCBI's own PMC servers."""
        pmcid = pmcid.strip()
        if not pmcid.upper().startswith("PMC"):
            pmcid = "PMC" + pmcid
        return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"

    async def lookup_many(self, dois: list[str]) -> dict[str, Optional[dict[str, Any]]]:
        async def _one(d: str) -> tuple[str, Optional[dict[str, Any]]]:
            return d, await self.lookup(d)

        tasks = [asyncio.create_task(_one(d)) for d in dois]
        return dict(await asyncio.gather(*tasks))
