"""Sci-Hub fallback — resolve DOI to PDF URL via mirrors.

Disabled by default. Set ENABLE_SCIHUB=true in .env to opt in.
The PDFs accessed via sci-hub are not legally Open Access; their legal
status depends on jurisdiction. This module exists as a private-use
fallback for researchers without institutional access; do not redistribute
its output.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from ..config import settings


log = logging.getLogger("nplibrary.scihub")


DEFAULT_MIRRORS: tuple[str, ...] = (
    "https://sci-hub.se",
    "https://sci-hub.st",
    "https://sci-hub.ru",
    "https://sci-hub.run",
    "https://sci-hub.mobi",
    "https://scihub.asia",
)


def _absolutize(src: str, base_url: str) -> str:
    """Handle //host/path, /path, and full URLs."""
    src = src.strip()
    if src.startswith("//"):
        scheme = urlparse(base_url).scheme or "https"
        return f"{scheme}:{src}"
    if src.startswith(("http://", "https://")):
        return src
    return urljoin(base_url, src)


def _extract_pdf_url(html: str, base_url: str) -> Optional[str]:
    """Parse sci-hub HTML, find the embedded PDF URL.

    Sci-hub mirrors typically wrap the PDF in one of:
      <iframe id="pdf" src="...">
      <embed type="application/pdf" src="...">
      <embed src="...pdf">
    The src may be //host/path, /path, or absolute.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    iframe = soup.find("iframe", id="pdf")
    if iframe and iframe.get("src"):
        return _absolutize(iframe["src"], base_url)

    embed = soup.find("embed", attrs={"type": "application/pdf"})
    if embed and embed.get("src"):
        return _absolutize(embed["src"], base_url)

    for embed in soup.find_all("embed"):
        src = (embed.get("src") or "").strip()
        if src.endswith(".pdf") or "/downloads/" in src:
            return _absolutize(src, base_url)

    return None


async def resolve_via_scihub(
    doi: str,
    mirrors: tuple[str, ...] | None = None,
    timeout: float = 15.0,
) -> list[str]:
    """Try each mirror in order until one yields a PDF URL.

    Returns a list with 0 or 1 URLs (we don't aggregate across mirrors —
    once one works, that's our candidate).
    """
    doi = (doi or "").strip()
    if not doi:
        return []

    mirrors = mirrors or DEFAULT_MIRRORS

    async with curl_requests.AsyncSession(
        impersonate="chrome",
        timeout=timeout,
        headers={"User-Agent": settings.app_user_agent},
    ) as session:
        for mirror in mirrors:
            url = f"{mirror.rstrip('/')}/{doi}"
            try:
                resp = await session.get(url, allow_redirects=True)
            except Exception as e:
                log.debug("scihub mirror %s failed for %s: %r", mirror, doi, e)
                continue

            if resp.status_code != 200 or not resp.text:
                continue

            pdf_url = _extract_pdf_url(resp.text, str(resp.url))
            if pdf_url:
                log.info("scihub: resolved %s via %s", doi, mirror)
                return [pdf_url]

    return []
