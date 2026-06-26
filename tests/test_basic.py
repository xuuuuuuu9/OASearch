"""Basic offline tests — schema, FTS, repo round-trip, CrossRef parser, FTS query builder."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import aiosqlite
import pytest

from app import repo
from app.clients import crossref
from app.db import SCHEMA_SQL


async def _open(tmp_path: Path) -> aiosqlite.Connection:
    db = await aiosqlite.connect(tmp_path / "t.db")
    db.row_factory = aiosqlite.Row
    await db.executescript(SCHEMA_SQL)
    return db


@pytest.mark.asyncio
async def test_schema_and_fts_insert(tmp_path: Path) -> None:
    db = await _open(tmp_path)
    try:
        await repo.add_journal(db, "0031-9422", "Phytochemistry", "Elsevier")
        pid = await repo.upsert_paper(
            db,
            {
                "doi": "10.1016/test1",
                "issn": "0031-9422",
                "title": "Novel flavonoid biosynthesis pathway in plants",
                "authors": ["Alice Smith", "Bob Jones"],
                "abstract": "We discovered a new pathway for flavonoid production.",
                "keywords": "flavonoid, biosynthesis",
                "published_date": "2024-05",
                "volume": None, "issue": None, "pages": None, "license": None,
            },
            oa={"is_oa": True, "oa_url": "http://example.com/x.pdf", "license": "cc-by"},
        )
        await db.commit()
        assert pid > 0

        rows, total = await repo.search_local(db, "flavonoid")
        assert total == 1
        assert rows[0]["doi"] == "10.1016/test1"

        rows, _ = await repo.search_local(db, "xyznotfound")
        assert rows == []

        # scope filters
        rows, total = await repo.search_local(db, "flavonoid", scope="pdf")
        assert total == 0  # no pdf_path yet
        rows, total = await repo.search_local(db, "flavonoid", scope="meta")
        assert total == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_upsert_preserves_pdf_path(tmp_path: Path) -> None:
    db = await _open(tmp_path)
    try:
        await repo.upsert_paper(
            db,
            {"doi": "10.1/keep", "issn": None, "title": "A", "authors": [], "abstract": None,
             "keywords": None, "published_date": None, "volume": None, "issue": None, "pages": None,
             "license": None},
        )
        await repo.mark_downloaded(db, "10.1/keep", "0031-9422/ab/abc.pdf", 12345, "sha")
        await db.commit()

        # Update again — pdf_path must survive.
        await repo.upsert_paper(
            db,
            {"doi": "10.1/keep", "issn": None, "title": "A updated", "authors": [],
             "abstract": "newabs", "keywords": None, "published_date": None,
             "volume": None, "issue": None, "pages": None, "license": None},
        )
        await db.commit()
        p = await repo.get_paper_by_doi(db, "10.1/keep")
        assert p["title"] == "A updated"
        assert p["pdf_path"] == "0031-9422/ab/abc.pdf"
        assert p["pdf_sha256"] == "sha"
    finally:
        await db.close()


def test_crossref_parse_work_basics() -> None:
    item = {
        "DOI": "10.1016/J.PHYTOCHEM.2024.123",
        "ISSN": ["0031-9422"],
        "title": ["A study of natural compounds"],
        "author": [{"given": "Jane", "family": "Doe"}, {"given": "John", "family": "Roe"}],
        "abstract": "<jats:p>This is an <jats:italic>important</jats:italic> finding.</jats:p>",
        "subject": ["Chemistry", "Biology"],
        "published-print": {"date-parts": [[2024, 3, 15]]},
        "container-title": ["Phytochemistry"],
        "volume": "100",
        "issue": "2",
        "page": "10-20",
        "license": [{"URL": "http://creativecommons.org/licenses/by/4.0/"}],
    }
    out = crossref.parse_work(item)
    assert out["doi"] == "10.1016/j.phytochem.2024.123"
    assert out["issn"] == "0031-9422"
    assert out["title"] == "A study of natural compounds"
    assert out["authors"] == ["Jane Doe", "John Roe"]
    assert "important" in out["abstract"]
    assert "<jats" not in out["abstract"]
    assert out["published_date"] == "2024-03-15"
    assert out["keywords"] == "Chemistry, Biology"


def test_crossref_build_filter() -> None:
    f = crossref.CrossRefClient._build_filter(
        ["0031-9422", "0163-3864"], 2020, 2024
    )
    assert "issn:0031-9422" in f
    assert "issn:0163-3864" in f
    assert "from-pub-date:2020" in f
    assert "until-pub-date:2024-12-31" in f


def test_fts_query_builder() -> None:
    assert repo._build_fts_query("") == ""
    assert repo._build_fts_query("flavonoid") == "flavonoid*"
    assert repo._build_fts_query("foo bar") == "foo* bar*"
    # quoted phrase preserved
    out = repo._build_fts_query('"natural products" alkaloid')
    assert '"natural products"' in out
    assert "alkaloid*" in out
    # FTS-special chars stripped
    assert "*" not in repo._build_fts_query("a*b").replace("ab*", "")


@pytest.mark.asyncio
async def test_download_task_lifecycle(tmp_path: Path) -> None:
    db = await _open(tmp_path)
    try:
        await repo.upsert_paper(db, {"doi": "10.1/a", "issn": None, "title": "A", "authors": [],
                                     "abstract": None, "keywords": None, "published_date": None,
                                     "volume": None, "issue": None, "pages": None, "license": None})
        await repo.upsert_paper(db, {"doi": "10.1/b", "issn": None, "title": "B", "authors": [],
                                     "abstract": None, "keywords": None, "published_date": None,
                                     "volume": None, "issue": None, "pages": None, "license": None})
        await db.commit()

        task_id = await repo.create_download_task(db, ["10.1/a", "10.1/b"])
        t = await repo.get_task(db, task_id)
        assert t["total"] == 2
        assert {i["doi"] for i in t["items"]} == {"10.1/a", "10.1/b"}

        await repo.set_item_status(db, task_id, "10.1/a", "done")
        await repo.set_item_status(db, task_id, "10.1/b", "failed", "oops")
        t = await repo.get_task(db, task_id)
        assert t["succeeded"] == 1
        assert t["failed"] == 1
    finally:
        await db.close()
