"""Sci-Hub fallback — resolve DOI to PDF URL via mirrors.

Strategies borrowed from pypaperretriever (after comparing implementations):
- rotate User-Agent across requests
- include browser-style Referer / Accept-Language headers
- random delay between mirrors to look less like a tight loop
- detect sci-hub's "we don't have this document" page so we stop early
  on misses instead of trying every mirror

Limitations: modern sci-hub mirrors (`.se`, `.ru`, `.st`) now serve an
altcha proof-of-work challenge that requires JS execution. Plain HTTP
clients cannot solve it. The `_smoke` script honestly reports when all
mirrors fall back to that. For long-tail reliability the recommended
workflow is the "在 sci-hub 打开" UI button (added separately) that lets
the user solve the challenge once in their own browser.
"""
from __future__ import annotations

import asyncio
import logging
import random
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


# Browser-class user agents to rotate per request.
_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 "
    "Firefox/124.0",
)


# Path prefixes sci-hub uses for self-hosted PDFs (per pypaperretriever).
_SCIHUB_PATH_PREFIXES = ("/downloads", "/tree", "/uptodate")


# Marker sci-hub shows when DOI isn't in their corpus.
_UNAVAILABLE_MARKERS = (
    "unfortunately, sci-hub doesn't have the requested document",
    "статья не найдена",
)


# Marker sci-hub shows when an altcha / robot challenge is served.
_CHALLENGE_MARKERS = (
    "are you a robot",
    "altcha",
)


def _browser_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }


def _absolutize(src: str, base_url: str) -> str:
    """Convert //host/path, /downloads/..., or absolute URLs to absolute https URL."""
    src = src.strip()
    if src.startswith("//"):
        scheme = urlparse(base_url).scheme or "https"
        return f"{scheme}:{src}"
    if src.startswith(("http://", "https://")):
        return src
    # /downloads/..., /tree/..., /uptodate/... — relative to mirror root
    if any(src.startswith(p) for p in _SCIHUB_PATH_PREFIXES):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{src}"
    return urljoin(base_url, src)


def _classify_response(html: str) -> str:
    """Inspect HTML once and return a tag: 'unavailable' / 'challenge' / 'ok'."""
    if not html:
        return "challenge"
    lowered = html.lower()
    for marker in _UNAVAILABLE_MARKERS:
        if marker in lowered:
            return "unavailable"
    for marker in _CHALLENGE_MARKERS:
        if marker in lowered:
            return "challenge"
    return "ok"


def _extract_pdf_url(html: str, base_url: str) -> Optional[str]:
    """Parse sci-hub HTML and return the embedded PDF URL, if any.

    Tries (in order): <iframe id="pdf">, <embed type="application/pdf">,
    then any <embed src> ending in .pdf or rooted at /downloads.
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
        if not src:
            continue
        if src.endswith(".pdf") or any(p in src for p in _SCIHUB_PATH_PREFIXES):
            return _absolutize(src, base_url)

    return None


async def resolve_via_scihub(
    doi: str,
    mirrors: tuple[str, ...] | None = None,
    timeout: float = 15.0,
    inter_mirror_delay: tuple[float, float] = (0.5, 1.5),
) -> list[str]:
    """Try each mirror until one yields a PDF URL.

    Returns a list with 0 or 1 URLs. If sci-hub explicitly reports the
    DOI is not in their corpus on any mirror, returns [] immediately
    (stop trying further mirrors — the answer won't change).
    """
    doi = (doi or "").strip()
    if not doi:
        return []

    mirrors = mirrors or DEFAULT_MIRRORS

    for i, mirror in enumerate(mirrors):
        if i > 0 and inter_mirror_delay:
            # Random gap between mirror attempts — avoids looking like a sweep.
            await asyncio.sleep(random.uniform(*inter_mirror_delay))

        url = f"{mirror.rstrip('/')}/{doi}"
        try:
            async with curl_requests.AsyncSession(
                impersonate="chrome",
                timeout=timeout,
                headers=_browser_headers(),
            ) as session:
                resp = await session.get(url, allow_redirects=True)
        except Exception as e:
            log.debug("scihub mirror %s connect failed for %s: %r", mirror, doi, e)
            continue

        if resp.status_code != 200 or not resp.text:
            log.debug("scihub mirror %s status=%s for %s", mirror,
                      resp.status_code, doi)
            continue

        tag = _classify_response(resp.text)
        if tag == "unavailable":
            log.info("scihub: %s reports DOI %s not in corpus — stopping",
                     mirror, doi)
            return []
        if tag == "challenge":
            log.debug("scihub mirror %s served challenge for %s", mirror, doi)
            continue

        pdf_url = _extract_pdf_url(resp.text, str(resp.url))
        if pdf_url:
            log.info("scihub: resolved %s via %s", doi, mirror)
            return [pdf_url]
        log.debug("scihub mirror %s 200 but no PDF element for %s", mirror, doi)

    return []
