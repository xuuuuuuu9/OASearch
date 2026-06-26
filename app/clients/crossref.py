"""CrossRef REST API client.

Used for keyword + ISSN search across journals. Polite-pool headers per
https://api.crossref.org/swagger-ui/index.html — passing a `mailto` in the
User-Agent dramatically increases rate limits.
"""
from __future__ import annotations

import re
from typing import Any, AsyncIterator, Optional

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import settings


CROSSREF_BASE = "https://api.crossref.org"
_HTML_TAG = re.compile(r"<[^>]+>")


def _strip_jats(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    # CrossRef abstracts often contain JATS XML (<jats:p>, <jats:italic>, etc.)
    cleaned = _HTML_TAG.sub("", text).strip()
    return cleaned or None


def _flatten_authors(items: Optional[list[dict[str, Any]]]) -> list[str]:
    if not items:
        return []
    out: list[str] = []
    for a in items:
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        if family or given:
            out.append(f"{given} {family}".strip())
        elif a.get("name"):
            out.append(a["name"])
    return out


def _date_parts(node: Optional[dict[str, Any]]) -> Optional[str]:
    if not node:
        return None
    parts = (node.get("date-parts") or [[]])[0]
    if not parts:
        return None
    y = parts[0] if len(parts) > 0 else None
    m = parts[1] if len(parts) > 1 else None
    d = parts[2] if len(parts) > 2 else None
    if y and m and d:
        return f"{y:04d}-{m:02d}-{d:02d}"
    if y and m:
        return f"{y:04d}-{m:02d}"
    if y:
        return f"{y:04d}"
    return None


def parse_work(item: dict[str, Any]) -> dict[str, Any]:
    """Map CrossRef /works item → our papers row dict."""
    title_list = item.get("title") or []
    title = title_list[0] if title_list else None

    issn_list = item.get("ISSN") or []
    issn = issn_list[0] if issn_list else None

    published = (
        item.get("published-print")
        or item.get("published-online")
        or item.get("issued")
        or item.get("created")
    )

    licenses = item.get("license") or []
    license_url = licenses[0].get("URL") if licenses else None

    # `link` array — publisher-supplied URLs. Only trust entries explicitly
    # typed application/pdf; skip text-mining / similarity-checking endpoints
    # (those are XML/text APIs behind auth, e.g. api.elsevier.com).
    pdf_links: list[str] = []
    for link in item.get("link") or []:
        url = link.get("URL")
        ctype = (link.get("content-type") or "").lower()
        intended = (link.get("intended-application") or "").lower()
        if not url or "pdf" not in ctype:
            continue
        # Filter out known auth-walled API hosts even if they claim PDF.
        if "api.elsevier.com" in url.lower() or "api.crossref.org" in url.lower():
            continue
        if intended in ("text-mining",):
            # Still skip text-mining even when content-type says pdf —
            # publishers wall these behind tokens.
            continue
        if url not in pdf_links:
            pdf_links.append(url)

    return {
        "doi": (item.get("DOI") or "").lower() or None,
        "issn": issn,
        "title": title.strip() if isinstance(title, str) else title,
        "authors": _flatten_authors(item.get("author")),
        "abstract": _strip_jats(item.get("abstract")),
        "keywords": ", ".join(item.get("subject") or []) or None,
        "published_date": _date_parts(published),
        "volume": item.get("volume"),
        "issue": item.get("issue"),
        "pages": item.get("page"),
        "license": license_url,
        "container_title": (item.get("container-title") or [None])[0],
        "pdf_links": pdf_links,
    }


class CrossRefClient:
    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=settings.http_timeout,
            headers={"User-Agent": settings.app_user_agent},
        )

    async def __aenter__(self) -> "CrossRefClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _build_filter(
        issns: list[str], year_from: Optional[int], year_to: Optional[int]
    ) -> Optional[str]:
        parts: list[str] = []
        for issn in issns:
            issn = issn.strip()
            if issn:
                parts.append(f"issn:{issn}")
        if year_from:
            parts.append(f"from-pub-date:{year_from:04d}")
        if year_to:
            parts.append(f"until-pub-date:{year_to:04d}-12-31")
        return ",".join(parts) if parts else None

    async def search(
        self,
        q: str,
        issns: list[str],
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        rows: int = 100,
    ) -> list[dict[str, Any]]:
        """Run one keyword search. Returns up to `rows` parsed items."""
        rows = max(1, min(rows, settings.max_search_rows))
        out: list[dict[str, Any]] = []
        async for item in self._iter(q, issns, year_from, year_to, max_items=rows):
            out.append(parse_work(item))
        return out

    async def _iter(
        self,
        q: str,
        issns: list[str],
        year_from: Optional[int],
        year_to: Optional[int],
        max_items: int,
    ) -> AsyncIterator[dict[str, Any]]:
        """Cursor-paginate CrossRef /works until max_items reached."""
        params: dict[str, Any] = {"rows": min(100, max_items), "cursor": "*"}
        if q.strip():
            params["query"] = q.strip()
        f = self._build_filter(issns, year_from, year_to)
        if f:
            params["filter"] = f

        yielded = 0
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type((httpx.HTTPError,)),
            reraise=True,
        ):
            with attempt:
                while True:
                    resp = await self._client.get(f"{CROSSREF_BASE}/works", params=params)
                    if resp.status_code >= 500:
                        resp.raise_for_status()
                    if resp.status_code == 429:
                        # respect the polite pool; tenacity will retry
                        resp.raise_for_status()
                    resp.raise_for_status()
                    data = resp.json()
                    message = data.get("message", {})
                    items = message.get("items") or []
                    if not items:
                        return
                    for it in items:
                        yield it
                        yielded += 1
                        if yielded >= max_items:
                            return
                    next_cursor = message.get("next-cursor")
                    if not next_cursor or next_cursor == params["cursor"]:
                        return
                    params["cursor"] = next_cursor

    async def validate_issn(self, issn: str) -> Optional[dict[str, Any]]:
        """Hit /journals/{issn}; return the journal node or None if not found."""
        issn = issn.strip()
        if not issn:
            return None
        resp = await self._client.get(f"{CROSSREF_BASE}/journals/{issn}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        msg = resp.json().get("message", {})
        title = msg.get("title")
        publisher = msg.get("publisher")
        if not title:
            return None
        return {"issn": issn, "name": title, "publisher": publisher}
