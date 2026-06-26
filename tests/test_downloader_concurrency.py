"""Downloader concurrency behavior."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app import downloader
from app.config import settings


pytestmark = pytest.mark.asyncio


async def _measure_run_dois_concurrency(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dois: list[str],
    download_concurrency: int,
    polite_mode: bool,
) -> int:
    old_download_concurrency = settings.download_concurrency
    old_polite_mode = settings.polite_mode
    settings.download_concurrency = download_concurrency
    settings.polite_mode = polite_mode

    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def fake_process_paper(**_kwargs: Any) -> None:
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        async with lock:
            active -= 1

    monkeypatch.setattr(downloader, "_process_paper", fake_process_paper)

    class DummySession:
        async def __aenter__(self) -> "DummySession":
            return self

        async def __aexit__(self, *_exc: Any) -> None:
            return None

    monkeypatch.setattr(
        downloader.curl_requests,
        "AsyncSession",
        lambda **_kwargs: DummySession(),
    )

    try:
        await downloader._run_dois(1, "unused.db", dois)
    finally:
        settings.download_concurrency = old_download_concurrency
        settings.polite_mode = old_polite_mode

    return max_active


async def test_run_dois_respects_configured_global_download_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    max_active = await _measure_run_dois_concurrency(
        monkeypatch,
        dois=[f"10.1/{i}" for i in range(6)],
        download_concurrency=2,
        polite_mode=False,
    )

    assert max_active <= 2


async def test_run_dois_polite_mode_caps_global_download_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    max_active = await _measure_run_dois_concurrency(
        monkeypatch,
        dois=[f"10.1/{i}" for i in range(8)],
        download_concurrency=16,
        polite_mode=True,
    )

    assert max_active <= 4
