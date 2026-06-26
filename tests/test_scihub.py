"""Unit tests for app/clients/scihub.py — mock HTTP, no real requests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.clients import scihub


def test_extract_pdf_url_iframe_with_protocol_relative():
    html = '<html><body><iframe id="pdf" src="//moscow.sci-hub.se/foo/paper.pdf"></iframe></body></html>'
    out = scihub._extract_pdf_url(html, "https://sci-hub.se/10.1/x")
    assert out == "https://moscow.sci-hub.se/foo/paper.pdf"


def test_extract_pdf_url_iframe_absolute():
    html = '<iframe id="pdf" src="https://twin.sci-hub.se/x.pdf"></iframe>'
    out = scihub._extract_pdf_url(html, "https://sci-hub.se/10.1/x")
    assert out == "https://twin.sci-hub.se/x.pdf"


def test_extract_pdf_url_iframe_relative_path():
    html = '<iframe id="pdf" src="/downloads/2024/01/paper.pdf"></iframe>'
    out = scihub._extract_pdf_url(html, "https://sci-hub.se/10.1/x")
    assert out == "https://sci-hub.se/downloads/2024/01/paper.pdf"


def test_extract_pdf_url_embed_type_attribute():
    html = '<embed type="application/pdf" src="//cdn.example/p.pdf">'
    out = scihub._extract_pdf_url(html, "https://sci-hub.ru/10.1/x")
    assert out == "https://cdn.example/p.pdf"


def test_extract_pdf_url_embed_pdf_extension():
    html = '<html><body><embed src="//cdn.x/paper.pdf"></body></html>'
    out = scihub._extract_pdf_url(html, "https://sci-hub.ru/10.1/x")
    assert out == "https://cdn.x/paper.pdf"


def test_extract_pdf_url_no_match_returns_none():
    html = "<html><body>article not found</body></html>"
    assert scihub._extract_pdf_url(html, "https://sci-hub.se/x") is None


def test_absolutize_double_slash():
    assert scihub._absolutize("//host/path", "https://x.com/y") == "https://host/path"


def test_absolutize_already_absolute():
    assert scihub._absolutize("https://x/y.pdf", "https://other") == "https://x/y.pdf"


def test_absolutize_relative_path():
    assert scihub._absolutize("/y.pdf", "https://x.com/a/b") == "https://x.com/y.pdf"


@pytest.mark.asyncio
async def test_resolve_via_scihub_skips_failed_mirror_and_returns_first_hit():
    # mirror 1: 404; mirror 2: 200 with iframe → should return mirror 2's URL
    responses = [
        MagicMock(status_code=404, text="", url="https://sci-hub.se/x"),
        MagicMock(
            status_code=200,
            text='<iframe id="pdf" src="//cdn/paper.pdf"></iframe>',
            url="https://sci-hub.st/x",
        ),
    ]

    class FakeSession:
        def __init__(self, *a, **kw):
            self._i = 0
            self.get = AsyncMock(side_effect=responses)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    with patch.object(scihub.curl_requests, "AsyncSession",
                      return_value=FakeSession()):
        out = await scihub.resolve_via_scihub(
            "10.1/x",
            mirrors=("https://sci-hub.se", "https://sci-hub.st"),
        )
    assert out == ["https://cdn/paper.pdf"]


@pytest.mark.asyncio
async def test_resolve_via_scihub_returns_empty_when_all_mirrors_miss():
    responses = [
        MagicMock(status_code=404, text="", url="https://m1/"),
        MagicMock(status_code=200, text="article not found", url="https://m2/"),
    ]

    class FakeSession:
        def __init__(self, *a, **kw):
            self.get = AsyncMock(side_effect=responses)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    with patch.object(scihub.curl_requests, "AsyncSession",
                      return_value=FakeSession()):
        out = await scihub.resolve_via_scihub(
            "10.1/x", mirrors=("https://m1", "https://m2"),
        )
    assert out == []


@pytest.mark.asyncio
async def test_resolve_via_scihub_empty_doi():
    assert await scihub.resolve_via_scihub("") == []
    assert await scihub.resolve_via_scihub("   ") == []
