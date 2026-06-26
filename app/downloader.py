"""Multi-source PDF downloader.

For each paper:
  1. Look up candidate URLs from paper_candidates (sorted by priority)
  2. For each candidate URL:
       a. Skip if its host is currently suppressed
       b. Skip with clear message if host is in HOSTILE_HOSTS (Cloudflare
          Managed Challenge — automation can't bypass without paid services)
       c. Try with curl_cffi (Chrome TLS fingerprint)
       d. On 4xx → permanent fail, move on
       e. On 5xx/network → retry up to 2 times with backoff
  3. On success: record candidate.status='success', mark paper downloaded
  4. On all-candidates-failed: collect attempt log into download_items.error
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
import time
from typing import Optional
from urllib.parse import urlparse

import aiosqlite
from curl_cffi import requests as curl_requests

from .config import PDF_DIR, settings
from .clients.oa_resolver import HOSTILE_HOSTS, is_hostile_host
from .host_state import HostStateTracker
from . import repo


log = logging.getLogger("nplibrary.downloader")
MIN_PDF_BYTES = 10 * 1024


class _RetryableError(Exception): ...
class _PermanentError(Exception): ...
class _HostileBlocked(_PermanentError): ...


def _effective_download_concurrency() -> int:
    configured = max(1, min(int(settings.download_concurrency or 1), 32))
    if settings.polite_mode:
        return min(configured, 4)
    return configured


def _download_start_interval() -> float:
    return 0.2 if settings.polite_mode else 0.0


def _doi_to_path(doi: str, issn: Optional[str]) -> str:
    h = hashlib.sha1(doi.encode("utf-8")).hexdigest()
    issn_dir = (issn or "unknown").replace("/", "_")
    return f"{issn_dir}/{h[:2]}/{h}.pdf"


def _publisher_referer(url: str) -> Optional[str]:
    host = (urlparse(url).hostname or "").lower()
    if "pubs.rsc.org" in host:
        return "https://pubs.rsc.org/"
    if "sciencedirect.com" in host or "elsevier.com" in host:
        return "https://www.sciencedirect.com/"
    if "pubs.acs.org" in host:
        return "https://pubs.acs.org/"
    if "wiley.com" in host or "onlinelibrary.wiley" in host:
        return "https://onlinelibrary.wiley.com/"
    if "springer.com" in host or "springeropen" in host:
        return "https://link.springer.com/"
    if "nature.com" in host:
        return "https://www.nature.com/"
    if "ncbi.nlm.nih.gov" in host or "europepmc.org" in host:
        return None  # PMC needs no referer
    return None


def _looks_like_pdf(buf: bytes) -> bool:
    return buf.startswith(b"%PDF-")


def _validate(tmp_path: str, size: int) -> None:
    if size < MIN_PDF_BYTES:
        raise _PermanentError(f"response too small ({size} bytes)")
    with open(tmp_path, "rb") as f:
        magic = f.read(5)
    if not _looks_like_pdf(magic):
        raise _PermanentError(f"not a PDF (magic bytes: {magic!r})")


async def _download_curl_cffi(
    session: curl_requests.AsyncSession, url: str, dest_path: str,
    _depth: int = 0,
) -> tuple[int, str]:
    """Stream URL → dest. Raises _Retry/_Permanent/_HostileBlocked.

    If the response turns out to be HTML (landing page rather than the PDF
    itself), parse it for <meta name="citation_pdf_url"> and follow the
    embedded PDF URL (one level deep) before giving up.
    """
    if is_hostile_host(url):
        raise _HostileBlocked(
            "出版商 Cloudflare Managed Challenge — 需手动下载（点 🌐 按钮）"
        )

    headers = {"Accept": "application/pdf,*/*;q=0.8"}
    ref = _publisher_referer(url)
    if ref:
        headers["Referer"] = ref

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf.part", dir=os.path.dirname(dest_path))
    os.close(tmp_fd)

    try:
        resp = await session.get(
            url, headers=headers, stream=True,
            allow_redirects=True, timeout=settings.download_timeout,
        )

        if resp.status_code in (401, 403, 404, 410):
            cf_mitigated = (resp.headers.get("cf-mitigated") or "").lower()
            server = (resp.headers.get("server") or "").lower()
            if resp.status_code == 403 and ("cloudflare" in server or cf_mitigated == "challenge"):
                raise _PermanentError("Cloudflare 403 — 需手动下载")
            raise _PermanentError(f"HTTP {resp.status_code}")
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("retry-after", "0") or 0)
            raise _RetryableError(f"HTTP 429 (retry-after={retry_after})")
        if resp.status_code >= 500:
            raise _RetryableError(f"HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise _PermanentError(f"HTTP {resp.status_code}")

        ctype = (resp.headers.get("content-type") or "").lower()

        # Buffer chunks, detect HTML on first chunk. If HTML, accumulate up to
        # 1MB then scrape for PDF URL and recurse. Otherwise stream to disk.
        body_chunks: list[bytes] = []
        sha = hashlib.sha256()
        size = 0
        is_html = False
        first_chunk = True

        async for chunk in resp.aiter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            if first_chunk:
                first_chunk = False
                head = chunk[:64].lstrip().lower()
                is_html = (
                    "html" in ctype
                    or head.startswith(b"<!doct")
                    or head.startswith(b"<html")
                )
            size += len(chunk)
            if is_html:
                body_chunks.append(chunk)
                if size > 1024 * 1024:
                    break
            else:
                sha.update(chunk)
                with open(tmp_path, "ab") as f:
                    f.write(chunk)
        await resp.aclose()

        if is_html:
            if _depth >= 1:
                raise _PermanentError("got HTML again on follow-up; landing chain too deep")
            html_text = b"".join(body_chunks).decode("utf-8", errors="ignore")
            pdf_url = _scrape_pdf_from_html(html_text, base_url=str(resp.url))
            if not pdf_url:
                raise _PermanentError("got HTML landing page, no citation_pdf_url found")
            log.info("following landing page %s → %s", url, pdf_url)
            return await _download_curl_cffi(session, pdf_url, dest_path, _depth=_depth + 1)

        _validate(tmp_path, size)
        os.replace(tmp_path, dest_path)
        return size, sha.hexdigest()
    except (_RetryableError, _PermanentError, _HostileBlocked):
        raise
    except Exception as e:
        raise _RetryableError(f"{type(e).__name__}: {e}") from e
    finally:
        if os.path.exists(tmp_path):
            try: os.unlink(tmp_path)
            except OSError: pass


def _scrape_pdf_from_html(html: str, base_url: str) -> Optional[str]:
    """Find a usable PDF URL inside an HTML landing page (one-shot)."""
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None

    # Highest signal: meta name=citation_pdf_url
    for name in ("citation_pdf_url", "citation_fulltext_pdf_url", "wkhealth_pdf_url"):
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return urljoin(base_url, tag["content"].strip())

    # Zenodo deposits expose PDF via /files/<name> links
    if "zenodo.org" in base_url:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/files/" in href and href.lower().endswith(".pdf"):
                return urljoin(base_url, href)

    # Generic fallback: first .pdf link on the page
    for a in soup.find_all("a", href=True)[:50]:
        href = a["href"].strip()
        if href.lower().endswith(".pdf") and not href.startswith("mailto:"):
            full = urljoin(base_url, href)
            if full != base_url:
                return full

    return None


async def _try_one_url(
    session: curl_requests.AsyncSession,
    host_state: HostStateTracker,
    cand_url: str,
    dest_path: str,
) -> tuple[int, str]:
    """Try a single candidate URL. Raises on fail."""
    st, host = await host_state.acquire(cand_url)
    try:
        try:
            size, sha = await _download_curl_cffi(session, cand_url, dest_path)
            await host_state.record_success(host)
            return size, sha
        except _PermanentError as e:
            if "Cloudflare" in str(e) or "Managed Challenge" in str(e):
                await host_state.record_403(host, cloudflare=True)
            raise
    finally:
        host_state.release(st)


async def _process_paper(
    *,
    doi: str,
    task_id: int,
    db_path: str,
    session: curl_requests.AsyncSession,
    host_state: HostStateTracker,
) -> None:
    """Try each candidate URL in priority order until one succeeds."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON;")

        paper = await repo.get_paper_by_doi(db, doi)
        if not paper:
            await repo.set_item_status(db, task_id, doi, "failed", "DOI not in library")
            return
        if paper.get("pdf_path"):
            await repo.set_item_status(db, task_id, doi, "skipped", "already downloaded")
            return

        candidates = await repo.get_candidates(db, doi)
        if not candidates:
            # Fall back to legacy oa_url field (papers downloaded before
            # OAResolver was introduced).
            if paper.get("oa_url"):
                candidates = [{
                    "url": paper["oa_url"],
                    "source": "unpaywall-best",
                    "priority": 30,
                }]
            else:
                await repo.set_item_status(
                    db, task_id, doi, "skipped", "no candidate URLs available",
                )
                return

        rel_path = _doi_to_path(doi, paper.get("issn"))
        abs_path = PDF_DIR / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        await repo.set_item_status(db, task_id, doi, "downloading")

        attempt_log: list[str] = []
        for cand in candidates:
            url = cand["url"]
            src = cand["source"]

            if await host_state.is_suppressed(url):
                attempt_log.append(f"[skip:{src}] host suppressed")
                await repo.mark_candidate_status(db, doi, url, "skipped", "host suppressed")
                continue

            for attempt in range(2):  # at most 2 attempts per URL
                try:
                    size, sha = await _try_one_url(session, host_state, url, str(abs_path))
                    await repo.mark_downloaded(db, doi, rel_path, size, sha)
                    await repo.mark_candidate_status(db, doi, url, "success", None)
                    await repo.set_item_status(db, task_id, doi, "done")
                    await db.commit()
                    return
                except _PermanentError as e:
                    msg = str(e)
                    attempt_log.append(f"[{src}] {msg}")
                    await repo.mark_candidate_status(db, doi, url, "permanent_fail", msg)
                    # 403 contributes to host suppression
                    if "403" in msg:
                        host = HostStateTracker.host_of(url)
                        await host_state.record_403(host, cloudflare="Cloudflare" in msg)
                    break  # don't retry permanent
                except _RetryableError as e:
                    msg = str(e)
                    if "429" in msg or "503" in msg:
                        host = HostStateTracker.host_of(url)
                        await host_state.record_429(host)
                    if attempt == 1:
                        attempt_log.append(f"[{src}] {msg} (gave up)")
                        await repo.mark_candidate_status(db, doi, url, "transient_fail", msg)
                    else:
                        await asyncio.sleep(min(0.5 * (2 ** attempt), 4))
            else:
                continue

        # All candidates exhausted
        error_summary = " | ".join(attempt_log) or "no candidates downloadable"
        await repo.mark_download_failed(db, doi, error_summary)
        await repo.set_item_status(db, task_id, doi, "failed", error_summary)
        await db.commit()


async def _run_dois(task_id: int, db_path: str, dois: list[str]) -> None:
    if not dois:
        return

    host_state = HostStateTracker()
    global_sem = asyncio.Semaphore(_effective_download_concurrency())
    start_interval = _download_start_interval()
    start_lock = asyncio.Lock()
    last_start = 0.0

    async def _run_one(doi: str, session: curl_requests.AsyncSession) -> None:
        nonlocal last_start
        async with global_sem:
            if start_interval:
                async with start_lock:
                    now = time.monotonic()
                    wait = max(0.0, last_start + start_interval - now)
                    if wait:
                        await asyncio.sleep(wait)
                    last_start = time.monotonic()
            await _process_paper(
                doi=doi, task_id=task_id, db_path=db_path,
                session=session, host_state=host_state,
            )

    async with curl_requests.AsyncSession(
        impersonate="chrome",
        timeout=settings.download_timeout,
        headers={"User-Agent": settings.app_user_agent},
    ) as session:
        tasks = [
            asyncio.create_task(_run_one(d, session))
            for d in dois
        ]
        await asyncio.gather(*tasks, return_exceptions=False)


async def run_download_task(task_id: int, db_path: str) -> None:
    from .db import get_db
    async with get_db() as db:
        await repo.set_task_status(db, task_id, "running")
        cur = await db.execute(
            "SELECT doi FROM download_items WHERE task_id=? AND status='pending';",
            (task_id,),
        )
        dois = [r["doi"] for r in await cur.fetchall()]
    await _run_dois(task_id, db_path, dois)
    async with get_db() as db:
        await repo.set_task_status(db, task_id, "done", finished=True)


async def retry_failed_items(
    task_id: int, db_path: str, dois: Optional[list[str]] = None
) -> int:
    from .db import get_db
    async with get_db() as db:
        params: list = [task_id]
        sql = "SELECT doi FROM download_items WHERE task_id=? AND status='failed'"
        if dois:
            placeholders = ",".join(["?"] * len(dois))
            sql += f" AND doi IN ({placeholders})"
            params += list(dois)
        cur = await db.execute(sql + ";", params)
        target = [r["doi"] for r in await cur.fetchall()]
        if not target:
            return 0

        placeholders = ",".join(["?"] * len(target))
        await db.execute(
            "UPDATE download_tasks SET failed = failed - ?, finished_at = NULL, status='running' WHERE id=?;",
            (len(target), task_id),
        )
        await db.execute(
            f"UPDATE download_items SET status='pending', error=NULL WHERE task_id=? AND doi IN ({placeholders});",
            [task_id] + target,
        )
        await db.execute(
            f"UPDATE papers SET download_error=NULL WHERE doi IN ({placeholders});",
            target,
        )
        # Also reset failed candidates so we retry them
        await db.execute(
            f"UPDATE paper_candidates SET last_status='untried', last_error=NULL "
            f"WHERE doi IN ({placeholders}) AND last_status IN ('permanent_fail','transient_fail');",
            target,
        )
        await db.commit()

    await _run_dois(task_id, db_path, target)
    async with get_db() as db:
        await repo.set_task_status(db, task_id, "done", finished=True)
    return len(target)
