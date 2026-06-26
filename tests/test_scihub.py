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


def test_extract_pdf_url_iframe_downloads_path():
    """Path prefix /downloads must be appended to mirror root, not the request URL."""
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


def test_extract_pdf_url_embed_tree_prefix():
    """Tree-rooted path should resolve against mirror root."""
    html = '<embed src="/tree/abcd/paper.pdf">'
    out = scihub._extract_pdf_url(html, "https://sci-hub.ru/10.1/x")
    assert out == "https://sci-hub.ru/tree/abcd/paper.pdf"


def test_extract_pdf_url_no_match_returns_none():
    html = "<html><body>article not found</body></html>"
    assert scihub._extract_pdf_url(html, "https://sci-hub.se/x") is None


def test_classify_response_unavailable():
    html = "<html><p>Unfortunately, Sci-Hub doesn't have the requested document:</p></html>"
    assert scihub._classify_response(html) == "unavailable"


def test_classify_response_altcha_challenge():
    html = "<html><title>Sci-Hub: are you a robot?</title><script>altcha</script></html>"
    assert scihub._classify_response(html) == "challenge"


def test_classify_response_ok_when_has_iframe():
    html = '<iframe id="pdf" src="//cdn/x.pdf">'
    assert scihub._classify_response(html) == "ok"


def test_absolutize_double_slash():
    assert scihub._absolutize("//host/path", "https://x.com/y") == "https://host/path"


def test_absolutize_already_absolute():
    assert scihub._absolutize("https://x/y.pdf", "https://other") == "https://x/y.pdf"


def test_absolutize_downloads_prefix_anchors_to_mirror_root():
    out = scihub._absolutize("/downloads/x.pdf", "https://sci-hub.se/10.1/something")
    assert out == "https://sci-hub.se/downloads/x.pdf"


def test_absolutize_plain_relative():
    assert scihub._absolutize("y.pdf", "https://x.com/a/b") == "https://x.com/a/y.pdf"


@pytest.mark.asyncio
async def test_resolve_via_scihub_skips_failed_mirror_and_returns_first_hit():
    # mirror 1: challenge page; mirror 2: 200 with iframe → should return mirror 2.
    responses = [
        MagicMock(
            status_code=200,
            text='<html><title>are you a robot?</title></html>',
            url="https://sci-hub.se/x",
        ),
        MagicMock(
            status_code=200,
            text='<iframe id="pdf" src="//cdn/paper.pdf"></iframe>',
            url="https://sci-hub.st/x",
        ),
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
            "10.1/x",
            mirrors=("https://sci-hub.se", "https://sci-hub.st"),
            inter_mirror_delay=(0, 0),
        )
    assert out == ["https://cdn/paper.pdf"]


@pytest.mark.asyncio
async def test_resolve_via_scihub_stops_on_unavailable():
    """Hitting an explicit 'doc not in corpus' page should NOT try further mirrors."""
    responses = [
        MagicMock(
            status_code=200,
            text="<p>Unfortunately, Sci-Hub doesn't have the requested document:</p>",
            url="https://sci-hub.se/x",
        ),
        # This mirror would succeed but we should never reach it.
        MagicMock(
            status_code=200,
            text='<iframe id="pdf" src="//cdn/x.pdf">',
            url="https://sci-hub.st/x",
        ),
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
            "10.1/x",
            mirrors=("https://sci-hub.se", "https://sci-hub.st"),
            inter_mirror_delay=(0, 0),
        )
    assert out == []


@pytest.mark.asyncio
async def test_resolve_via_scihub_returns_empty_when_all_mirrors_challenge():
    responses = [
        MagicMock(status_code=200, text="altcha challenge", url="https://m1/"),
        MagicMock(status_code=200, text="are you a robot?", url="https://m2/"),
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
            inter_mirror_delay=(0, 0),
        )
    assert out == []


@pytest.mark.asyncio
async def test_resolve_via_scihub_empty_doi():
    assert await scihub.resolve_via_scihub("") == []
    assert await scihub.resolve_via_scihub("   ") == []
