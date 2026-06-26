"""Unit tests for app/clients/semantic_scholar.py — mock HTTP."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.clients import semantic_scholar as ss_mod


@pytest.fixture
def fake_session():
    """Build a fake httpx.AsyncClient that returns scripted responses."""
    session = MagicMock()
    session.aclose = AsyncMock(return_value=None)
    return session


@pytest.mark.asyncio
async def test_lookup_returns_pdf_url_when_present(fake_session):
    fake_session.get = AsyncMock(return_value=MagicMock(
        status_code=200,
        json=lambda: {
            "paperId": "abc123",
            "openAccessPdf": {
                "url": "https://repo.example/pdf.pdf",
                "status": "GREEN",
            },
        },
    ))
    client = ss_mod.SemanticScholarClient()
    client._session = fake_session
    out = await client.lookup("10.1/x")
    assert out["pdf_url"] == "https://repo.example/pdf.pdf"
    assert out["status"] == "GREEN"
    assert out["paper_id"] == "abc123"


@pytest.mark.asyncio
async def test_lookup_returns_none_pdf_when_missing_field(fake_session):
    fake_session.get = AsyncMock(return_value=MagicMock(
        status_code=200,
        json=lambda: {"paperId": "p1", "openAccessPdf": None},
    ))
    client = ss_mod.SemanticScholarClient()
    client._session = fake_session
    out = await client.lookup("10.1/x")
    assert out["pdf_url"] is None


@pytest.mark.asyncio
async def test_lookup_404_returns_empty(fake_session):
    fake_session.get = AsyncMock(return_value=MagicMock(status_code=404))
    client = ss_mod.SemanticScholarClient()
    client._session = fake_session
    assert await client.lookup("10.1/x") == {}


@pytest.mark.asyncio
async def test_lookup_429_returns_empty(fake_session):
    fake_session.get = AsyncMock(return_value=MagicMock(status_code=429))
    client = ss_mod.SemanticScholarClient()
    client._session = fake_session
    assert await client.lookup("10.1/x") == {}


@pytest.mark.asyncio
async def test_lookup_empty_doi():
    client = ss_mod.SemanticScholarClient()
    client._session = MagicMock()  # never accessed
    assert await client.lookup("") == {}
    assert await client.lookup("   ") == {}
