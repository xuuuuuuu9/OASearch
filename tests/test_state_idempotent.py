"""Calling load_page() twice must not re-fetch (sentinel works)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from frontend.state.search_state import SearchState
from frontend.state.library_state import LibraryState
from frontend.state.downloads_state import DownloadsState
from frontend.state.journals_state import JournalsState


def _make_search_api_mock():
    """Return a side_effect callable that returns the right shape per path."""
    async def fake(path, params=None):
        if "/search-tasks/latest" in path:
            return {"id": 0, "status": "", "total": 0, "oa": 0, "q": ""}
        if "/search-tasks/" in path and "/papers" in path:
            return []
        if "/journals" in path:
            return []
        return []
    return fake


async def test_search_load_page_idempotent():
    state = SearchState()
    with patch("frontend.state.search_state.api.get_json",
               new=AsyncMock(side_effect=_make_search_api_mock())) as mock_get:
        await state.load_page()
        first_run_calls = mock_get.call_count
        await state.load_page()
    assert state._loaded is True
    assert mock_get.call_count == first_run_calls


async def test_search_refresh_always_fetches():
    state = SearchState()
    state._loaded = True
    with patch("frontend.state.search_state.api.get_json",
               new=AsyncMock(side_effect=_make_search_api_mock())) as mock_get:
        await state.refresh()
    assert mock_get.call_count >= 1


async def test_library_load_page_idempotent():
    state = LibraryState()
    async def fake(path, params=None):
        if "/journals" in path:
            return []
        return {"items": [], "total": 0}
    with patch("frontend.state.library_state.api.get_json",
               new=AsyncMock(side_effect=fake)) as mock_get:
        await state.load_page()
        first = mock_get.call_count
        await state.load_page()
    assert state._loaded is True
    assert mock_get.call_count == first


async def test_downloads_load_page_always_refetches():
    """Downloads is a live dashboard — load_page should re-fetch every visit,
    NOT cache like the other pages do. New tasks created elsewhere must
    appear when the user navigates back."""
    state = DownloadsState()
    with patch("frontend.state.downloads_state.api.get_json",
               new=AsyncMock(return_value=[])) as mock_get:
        await state.load_page()
        first = mock_get.call_count
        await state.load_page()
    assert state._loaded is True
    # second call MUST also fetch (no sentinel) — that's the whole point
    assert mock_get.call_count > first


async def test_journals_load_page_idempotent():
    state = JournalsState()
    with patch("frontend.state.journals_state.api.get_json",
               new=AsyncMock(return_value=[])) as mock_get:
        await state.load_page()
        first = mock_get.call_count
        await state.load_page()
    assert state._loaded is True
    assert mock_get.call_count == first
