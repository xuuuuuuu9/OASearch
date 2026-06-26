"""Tests for new OA resolution and host state."""
from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import pytest

from app import repo
from app.clients import url_patterns
from app.clients.europepmc import EuropePMCClient
from app.clients.oa_resolver import SOURCE_PRIORITY, Candidate, _dedupe
from app.db import SCHEMA_SQL
from app.host_state import HostStateTracker


async def _open(tmp_path: Path) -> aiosqlite.Connection:
    db = await aiosqlite.connect(tmp_path / "t.db")
    db.row_factory = aiosqlite.Row
    await db.executescript(SCHEMA_SQL)
    return db


def test_url_patterns_arxiv() -> None:
    urls = url_patterns.infer_urls("10.48550/arxiv.2401.12345")
    assert urls == [("https://arxiv.org/pdf/2401.12345.pdf", "arxiv")]


def test_url_patterns_biorxiv() -> None:
    urls = url_patterns.infer_urls("10.1101/2024.01.01.123456")
    assert len(urls) == 1
    assert urls[0][1] == "biorxiv"
    assert "biorxiv.org/content" in urls[0][0]
    assert urls[0][0].endswith(".full.pdf")


def test_url_patterns_no_match() -> None:
    # Regular publisher DOI shouldn't trigger patterns
    assert url_patterns.infer_urls("10.1039/d3np00018d") == []
    assert url_patterns.infer_urls("10.1016/j.phytochem.2024.114228") == []


def test_url_patterns_chemrxiv() -> None:
    urls = url_patterns.infer_urls("10.26434/chemrxiv-2024-abcde")
    assert len(urls) == 1
    assert urls[0][1] == "chemrxiv"


def test_url_patterns_empty() -> None:
    assert url_patterns.infer_urls("") == []
    assert url_patterns.infer_urls(None) == []


def test_europepmc_pdf_url_for_pmcid() -> None:
    assert "PMC123" in EuropePMCClient.pdf_url_for_pmcid("PMC123")
    assert "PMC123" in EuropePMCClient.pdf_url_for_pmcid("123")
    assert "pdf=render" in EuropePMCClient.pdf_url_for_pmcid("PMC123")
    assert "PMC456" in EuropePMCClient.ncbi_pdf_url_for_pmcid("456")


def test_oa_resolver_dedupe_keeps_higher_priority() -> None:
    # Same URL appears twice with different priorities — higher (smaller num) wins.
    cands = [
        Candidate("https://example.com/x.pdf", "unpaywall-best", 30),
        Candidate("https://example.com/x.pdf", "pmc", 10),
        Candidate("https://example.com/y.pdf", "landing", 60),
    ]
    out = _dedupe(cands)
    assert len(out) == 2
    assert out[0].url == "https://example.com/x.pdf"
    assert out[0].source == "pmc"  # higher priority survived
    assert out[1].url == "https://example.com/y.pdf"


def test_source_priority_ordering() -> None:
    # PMC < CrossRef-link < Unpaywall-best < Unpaywall-alt < patterns < landing
    assert SOURCE_PRIORITY["pmc"] < SOURCE_PRIORITY["crossref-link"]
    assert SOURCE_PRIORITY["crossref-link"] < SOURCE_PRIORITY["unpaywall-best"]
    assert SOURCE_PRIORITY["unpaywall-best"] < SOURCE_PRIORITY["unpaywall-alt"]
    assert SOURCE_PRIORITY["unpaywall-alt"] < SOURCE_PRIORITY["arxiv"]
    assert SOURCE_PRIORITY["arxiv"] < SOURCE_PRIORITY["landing"]


@pytest.mark.asyncio
async def test_candidates_upsert_and_get(tmp_path: Path) -> None:
    db = await _open(tmp_path)
    try:
        # Need a paper row first (FK)
        await repo.upsert_paper(db, {
            "doi": "10.1/test", "issn": None, "title": "T", "authors": [],
            "abstract": None, "keywords": None, "published_date": None,
            "volume": None, "issue": None, "pages": None, "license": None,
        })
        await db.commit()

        await repo.upsert_candidates(db, "10.1/test", [
            {"url": "https://europepmc.org/x.pdf", "source": "pmc", "priority": 10},
            {"url": "https://unpaywall.org/x.pdf", "source": "unpaywall-best", "priority": 30},
        ])
        await db.commit()

        cands = await repo.get_candidates(db, "10.1/test")
        assert len(cands) == 2
        # Untried, so order is by priority — pmc first
        assert cands[0]["source"] == "pmc"
        assert cands[0]["last_status"] == "untried"

        # Mark pmc as success, unpaywall as failed → success should sort first
        await repo.mark_candidate_status(db, "10.1/test", "https://europepmc.org/x.pdf", "success", None)
        await repo.mark_candidate_status(
            db, "10.1/test", "https://unpaywall.org/x.pdf", "permanent_fail", "HTTP 403",
        )
        await db.commit()

        cands = await repo.get_candidates(db, "10.1/test")
        assert cands[0]["last_status"] == "success"
        assert cands[1]["last_status"] == "permanent_fail"
        assert "403" in cands[1]["last_error"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_candidates_preserved_on_reupsert(tmp_path: Path) -> None:
    """Re-resolving must keep success markers (don't re-download forever)."""
    db = await _open(tmp_path)
    try:
        await repo.upsert_paper(db, {
            "doi": "10.1/persist", "issn": None, "title": "T", "authors": [],
            "abstract": None, "keywords": None, "published_date": None,
            "volume": None, "issue": None, "pages": None, "license": None,
        })
        await db.commit()

        await repo.upsert_candidates(db, "10.1/persist", [
            {"url": "https://a.com/x.pdf", "source": "pmc", "priority": 10},
        ])
        await repo.mark_candidate_status(db, "10.1/persist", "https://a.com/x.pdf", "success", None)
        await db.commit()

        # User re-runs the search; resolver returns the same URL.
        await repo.upsert_candidates(db, "10.1/persist", [
            {"url": "https://a.com/x.pdf", "source": "pmc", "priority": 10},
            {"url": "https://b.com/x.pdf", "source": "unpaywall-best", "priority": 30},
        ])
        await db.commit()

        cands = await repo.get_candidates(db, "10.1/persist")
        a = next(c for c in cands if "a.com" in c["url"])
        assert a["last_status"] == "success"   # preserved
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_host_state_403_suppression() -> None:
    tracker = HostStateTracker()
    for _ in range(3):
        await tracker.record_403("pubs.acs.org")
    assert await tracker.is_suppressed("https://pubs.acs.org/foo")
    # Different host — should not be affected.
    assert not await tracker.is_suppressed("https://europepmc.org/foo")


@pytest.mark.asyncio
async def test_host_state_cloudflare_immediate_suppression() -> None:
    tracker = HostStateTracker()
    await tracker.record_403("pubs.acs.org", cloudflare=True)
    assert await tracker.is_suppressed("https://pubs.acs.org/foo")


@pytest.mark.asyncio
async def test_host_state_success_resets_counter() -> None:
    tracker = HostStateTracker()
    await tracker.record_403("pubs.rsc.org")
    await tracker.record_403("pubs.rsc.org")
    await tracker.record_success("pubs.rsc.org")
    await tracker.record_403("pubs.rsc.org")
    # Two 403s in a row again, but counter reset → still under limit, not suppressed.
    assert not await tracker.is_suppressed("https://pubs.rsc.org/foo")


def test_crossref_parse_extracts_pdf_links() -> None:
    from app.clients.crossref import parse_work
    item = {
        "DOI": "10.1/test",
        "ISSN": ["1234-5678"],
        "title": ["A paper"],
        "link": [
            {"URL": "https://pub.example.com/abstract", "content-type": "text/html"},
            {"URL": "https://pub.example.com/article.pdf", "content-type": "application/pdf"},
            # Text-mining endpoint behind auth — must be skipped
            {"URL": "https://api.elsevier.com/article.pdf", "content-type": "application/pdf",
             "intended-application": "text-mining"},
            # Similar but non-text-mining intent → should be included
            {"URL": "https://pub.example.com/sim.pdf", "content-type": "application/pdf",
             "intended-application": "similarity-checking"},
        ],
    }
    out = parse_work(item)
    assert "https://pub.example.com/article.pdf" in out["pdf_links"]
    assert "https://pub.example.com/sim.pdf" in out["pdf_links"]
    assert "https://pub.example.com/abstract" not in out["pdf_links"]
    assert not any("api.elsevier.com" in u for u in out["pdf_links"])
