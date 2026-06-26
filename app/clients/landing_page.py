"""Fetch DOI landing page and scrape PDF URLs.

Many publishers expose the canonical PDF via `<meta name="citation_pdf_url">`
or similar tags. This is a last-resort source when Unpaywall/PMC have nothing.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from ..config import settings


log = logging.getLogger("nplibrary.landing")


PDF_META_NAMES = (
    "citation_pdf_url",
    "citation_fulltext_pdf_url",
    "wkhealth_pdf_url",
    "prism.url",
    "eprints.document_url",
)


async def scrape_pdf_urls(doi: str, timeout: float = 12.0) -> list[str]:
    """Fetch https://doi.org/{doi}, follow redirects, return PDF URLs found.

    Looks at: meta[name=citation_pdf_url] etc., plus <a href> ending in .pdf
    on the landing page.
    """
    doi = (doi or "").strip()
    if not doi:
        return []

    found: list[str] = []
    async with curl_requests.AsyncSession(
        impersonate="chrome",
        timeout=timeout,
        headers={"User-Agent": settings.app_user_agent},
    ) as session:
        try:
            resp = await session.get(
                f"https://doi.org/{doi}",
                allow_redirects=True,
            )
        except Exception as e:
            log.debug("landing fetch failed for %s: %r", doi, e)
            return []

        if resp.status_code != 200 or not resp.text:
            return []

        base_url = str(resp.url)
        try:
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception:
            soup = BeautifulSoup(resp.text, "html.parser")

        # 1) meta tags
        for name in PDF_META_NAMES:
            for tag in soup.find_all("meta", attrs={"name": name}):
                content = (tag.get("content") or "").strip()
                if content:
                    url = urljoin(base_url, content)
                    if url not in found:
                        found.append(url)

        # 2) <a href> ending in .pdf (limit a few — landing pages can have many)
        for a in soup.find_all("a", href=True)[:60]:
            href = (a["href"] or "").strip()
            if not href:
                continue
            if ".pdf" in href.lower():
                url = urljoin(base_url, href)
                if url not in found and url.lower().startswith(("http://", "https://")):
                    found.append(url)
                    if len(found) >= 5:
                        break

    return found
