from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app import repo
from app.db import SCHEMA_SQL


async def _init_db(db_path: Path) -> None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(SCHEMA_SQL)
        await db.commit()


@pytest.mark.asyncio
async def test_journals_and_library_search_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import api

    db_path = tmp_path / "api.db"
    await _init_db(db_path)

    async with aiosqlite.connect(db_path) as seed_db:
        seed_db.row_factory = aiosqlite.Row
        await repo.add_journal(seed_db, "0031-9422", "Phytochemistry", "Elsevier")
        await repo.upsert_paper(
            seed_db,
            {
                "doi": "10.1/test-paper",
                "issn": "0031-9422",
                "title": "Flavonoid pathways in medicinal plants",
                "authors": ["Alice Smith"],
                "abstract": "A compact abstract.",
                "keywords": "flavonoid, medicinal",
                "published_date": "2024-04",
                "volume": None,
                "issue": None,
                "pages": None,
                "license": None,
            },
            oa={"is_oa": True},
        )
        await repo.mark_papers_saved(seed_db, ["10.1/test-paper"])
        await seed_db.commit()

    @asynccontextmanager
    async def fake_get_db():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    monkeypatch.setattr(api, "get_db", fake_get_db)

    app = FastAPI()
    app.include_router(api.router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        journals = await client.get("/api/journals")
        assert journals.status_code == 200
        assert journals.json()[0]["issn"] == "0031-9422"

        search = await client.get("/api/library/search", params={"q": "flavonoid"})
        assert search.status_code == 200
        payload = search.json()
        assert payload["total"] == 1
        assert payload["items"][0]["doi"] == "10.1/test-paper"

        filtered = await client.get(
            "/api/library/search",
            params={"year_from": 2020, "year_to": 2024, "sort": "title"},
        )
        assert filtered.status_code == 200
        body = filtered.json()
        assert "items" in body and "total" in body
        assert body["total"] >= 1


@pytest.mark.asyncio
async def test_save_and_delete_paper_endpoints(tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import api
    db_path = tmp_path / "sd.db"
    await _init_db(db_path)
    async with aiosqlite.connect(db_path) as seed_db:
        seed_db.row_factory = aiosqlite.Row
        await repo.add_journal(seed_db, "0031-9422", "Phytochemistry", "Elsevier")
        await repo.upsert_paper(
            seed_db,
            {
                "doi": "10.1/sd-paper", "issn": "0031-9422",
                "title": "T", "authors": [], "abstract": "", "keywords": "",
                "published_date": "2024-01", "volume": None, "issue": None,
                "pages": None, "license": None,
            },
            oa={"is_oa": True},
        )
        await seed_db.commit()

    @asynccontextmanager
    async def fake_get_db():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    monkeypatch.setattr(api, "get_db", fake_get_db)
    app = FastAPI()
    app.include_router(api.router)

    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://testserver") as client:
        # before save: not visible in library
        r1 = await client.get("/api/library/search", params={"q": ""})
        assert r1.json()["total"] == 0
        # save it
        r2 = await client.post("/api/papers/save", json={"dois": ["10.1/sd-paper"]})
        assert r2.status_code == 200
        assert r2.json()["updated"] == 1
        # now visible
        r3 = await client.get("/api/library/search", params={"q": ""})
        assert r3.json()["total"] == 1
        # delete it
        from urllib.parse import quote
        r4 = await client.delete(f"/api/papers/{quote('10.1/sd-paper', safe='')}")
        assert r4.status_code == 200
        assert r4.json()["deleted"] is True
        # gone
        r5 = await client.get("/api/library/search", params={"q": ""})
        assert r5.json()["total"] == 0


@pytest.mark.asyncio
async def test_search_and_download_task_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import api

    db_path = tmp_path / "tasks.db"
    await _init_db(db_path)

    async with aiosqlite.connect(db_path) as seed_db:
        seed_db.row_factory = aiosqlite.Row
        await repo.add_journal(seed_db, "0031-9422", "Phytochemistry", "Elsevier")
        await repo.upsert_paper(
            seed_db,
            {
                "doi": "10.1/dl-paper",
                "issn": "0031-9422",
                "title": "Download ready paper",
                "authors": ["Alice Smith"],
                "abstract": "A compact abstract.",
                "keywords": "flavonoid",
                "published_date": "2024-04",
                "volume": None,
                "issue": None,
                "pages": None,
                "license": None,
            },
            oa={"is_oa": True, "oa_url": "https://example.org/paper.pdf"},
        )
        await repo.upsert_candidates(
            seed_db,
            "10.1/dl-paper",
            [{"url": "https://example.org/paper.pdf", "source": "manual", "priority": 1}],
        )
        await seed_db.commit()

    @asynccontextmanager
    async def fake_get_db():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    monkeypatch.setattr(api, "get_db", fake_get_db)
    monkeypatch.setattr(api, "spawn_search_task", lambda task_id, req: None)
    monkeypatch.setattr(api, "spawn_download_task", lambda task_id, db_path: None)
    monkeypatch.setattr(api, "retry_download_items", lambda task_id, db_path, dois=None: None)

    app = FastAPI()
    app.include_router(api.router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        create_search = await client.post(
            "/api/search-tasks",
            json={"q": "flavonoid", "issns": ["0031-9422"], "rows": 20},
        )
        assert create_search.status_code == 200
        search_task = create_search.json()
        assert search_task["status"] == "pending"

        latest = await client.get("/api/search-tasks/latest")
        assert latest.status_code == 200
        assert latest.json()["id"] == search_task["id"]

        create_download = await client.post(
            "/api/download-tasks",
            json={"dois": ["10.1/dl-paper"]},
        )
        assert create_download.status_code == 200
        task_payload = create_download.json()
        assert task_payload["total"] == 1

        task_detail = await client.get(f"/api/download-tasks/{task_payload['id']}")
        assert task_detail.status_code == 200
        assert task_detail.json()["items"][0]["doi"] == "10.1/dl-paper"

        retry_all = await client.post(f"/api/download-tasks/{task_payload['id']}/retry")
        assert retry_all.status_code == 200
        assert retry_all.json()["accepted"] is True

        retry_one = await client.post(f"/api/download-tasks/{task_payload['id']}/items/10.1%2Fdl-paper/retry")
        assert retry_one.status_code == 200
        assert retry_one.json()["accepted"] is True


@pytest.mark.asyncio
async def test_create_journal_can_autofill_from_crossref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import api

    db_path = tmp_path / "journals.db"
    await _init_db(db_path)

    @asynccontextmanager
    async def fake_get_db():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    class FakeCrossRefClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def validate_issn(self, issn: str):
            assert issn == "0378-8741"
            return {"name": "Journal of Ethnopharmacology", "publisher": "Elsevier"}

    monkeypatch.setattr(api, "get_db", fake_get_db)
    monkeypatch.setattr(api, "CrossRefClient", FakeCrossRefClient)

    app = FastAPI()
    app.include_router(api.router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/journals",
            json={"issn": "0378-8741"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == "Journal of Ethnopharmacology"
        assert payload["publisher"] == "Elsevier"
