"""Unpaywall API client.

Resolves a DOI to an OA status + PDF URL when one exists. We only call this
for DOIs that CrossRef returned to us. Free; requires `email` query param.

Uses curl_cffi instead of httpx because some corporate/ISP TLS-inspection
middleboxes (observed in this environment) reject Python's OpenSSL TLS
fingerprint mid-handshake on api.unpaywall.org. curl_cffi impersonates
Chrome's TLS ClientHello, which passes through.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from curl_cffi import requests as curl_requests

from ..config import settings


UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
log = logging.getLogger("nplibrary.unpaywall")
_email_warned = False


class UnpaywallClient:
    def __init__(self, concurrency: Optional[int] = None):
        self._session = curl_requests.AsyncSession(
            impersonate="chrome",
            timeout=settings.http_timeout,
            headers={"User-Agent": settings.app_user_agent},
        )
        self._sem = asyncio.Semaphore(concurrency or settings.oa_lookup_concurrency)

    async def __aenter__(self) -> "UnpaywallClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._session.close()

    async def lookup(self, doi: str) -> dict[str, Any]:
        """Return dict with keys: is_oa(bool|None), oa_url(str|None), license(str|None)."""
        if not doi:
            return {"is_oa": None, "oa_url": None, "license": None}

        global _email_warned
        async with self._sem:
            last_err: Optional[Exception] = None
            for attempt in range(3):
                try:
                    resp = await self._session.get(
                        f"{UNPAYWALL_BASE}/{doi}",
                        params={"email": settings.user_email},
                    )
                except Exception as e:
                    last_err = e
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue

                if resp.status_code == 404:
                    return {"is_oa": False, "oa_url": None, "license": None}
                if resp.status_code in (422, 400):
                    if not _email_warned:
                        _email_warned = True
                        try:
                            msg = resp.json().get("message", "")
                        except Exception:
                            msg = resp.text[:200]
                        log.error(
                            "Unpaywall rejected the request (HTTP %d): %s. "
                            "Set a real USER_EMAIL in .env — Unpaywall blocks "
                            "@example.com and similar placeholders.",
                            resp.status_code, msg,
                        )
                    return {"is_oa": None, "oa_url": None, "license": None}
                if resp.status_code >= 500 or resp.status_code == 429:
                    last_err = Exception(f"HTTP {resp.status_code}")
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                if resp.status_code >= 400:
                    return {"is_oa": None, "oa_url": None, "license": None}

                try:
                    data = resp.json()
                except Exception as e:
                    last_err = e
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                break
            else:
                log.warning("Unpaywall lookup failed for %s: %r", doi, last_err)
                return {"is_oa": None, "oa_url": None, "license": None}

        is_oa = bool(data.get("is_oa"))
        best = data.get("best_oa_location") or {}
        best_pdf = best.get("url_for_pdf")

        # Collect all PDF URLs from all oa_locations (each can be a separate
        # candidate — repositories vs publisher hosts vary in reliability).
        all_pdf_urls: list[str] = []
        for loc in (data.get("oa_locations") or []):
            u = loc.get("url_for_pdf")
            if u and u not in all_pdf_urls:
                all_pdf_urls.append(u)
        # Ensure best is first if known
        if best_pdf and best_pdf in all_pdf_urls:
            all_pdf_urls.remove(best_pdf)
            all_pdf_urls.insert(0, best_pdf)
        elif best_pdf:
            all_pdf_urls.insert(0, best_pdf)

        return {
            "is_oa": is_oa,
            "oa_url": best_pdf or (all_pdf_urls[0] if all_pdf_urls else None),
            "all_pdf_urls": all_pdf_urls,
            "license": (best.get("license") if best else None),
        }

    async def lookup_many(self, dois: list[str]) -> dict[str, dict[str, Any]]:
        """Concurrent batch lookup; returns DOI → result map."""
        async def _one(d: str) -> tuple[str, dict[str, Any]]:
            return d, await self.lookup(d)

        tasks = [asyncio.create_task(_one(d)) for d in dois]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return dict(results)
