"""Per-host download state — adaptive concurrency, 403 suppression, Retry-After.

Single in-memory tracker shared by the downloader. Not persisted; loss of state
on restart is fine (worst case: we re-discover a host is hostile).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse


log = logging.getLogger("nplibrary.host_state")


# Default per-host concurrency. Tuned by observation.
DEFAULT_PER_HOST = 6
HOST_LIMITS = {
    # Friendly, big infrastructure → high parallelism
    "europepmc.org":            16,
    "www.ncbi.nlm.nih.gov":     12,
    "arxiv.org":                12,
    # Throttling publishers → conservative
    "pubs.rsc.org":             6,
    "onlinelibrary.wiley.com":  4,
    "www.sciencedirect.com":    4,
    "link.springer.com":        6,
    "www.nature.com":           6,
    # Heavily bot-protected → tiny + cloudscraper-only
    "pubs.acs.org":             2,
}

# How many consecutive 403/Cloudflare to tolerate before suppressing the host
SUPPRESS_AFTER_403 = 3
# Suppression duration (seconds)
SUPPRESS_DURATION = 600   # 10 minutes


@dataclass
class HostState:
    sem: asyncio.Semaphore
    limit: int
    consecutive_403: int = 0
    suppressed_until: float = 0.0
    backoff_until: float = 0.0


class HostStateTracker:
    """Single global instance per process."""

    def __init__(self):
        self._states: dict[str, HostState] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def host_of(url: str) -> str:
        return (urlparse(url).hostname or "_").lower()

    async def _get(self, host: str) -> HostState:
        async with self._lock:
            st = self._states.get(host)
            if st is None:
                limit = HOST_LIMITS.get(host, DEFAULT_PER_HOST)
                st = HostState(sem=asyncio.Semaphore(limit), limit=limit)
                self._states[host] = st
            return st

    async def acquire(self, url: str) -> tuple[HostState, str]:
        """Block until allowed to start a request to this URL's host.

        Returns (state, host). Caller must release the semaphore via state.sem.
        If host is suppressed/back-off, sleeps until end of suppression, then
        acquires.
        """
        host = self.host_of(url)
        st = await self._get(host)
        # Sleep through any suppression / backoff before grabbing the slot.
        while True:
            now = time.monotonic()
            wait = max(st.suppressed_until - now, st.backoff_until - now, 0.0)
            if wait <= 0:
                break
            log.info("host %s on cooldown for %.1fs", host, wait)
            await asyncio.sleep(min(wait, 30))
        await st.sem.acquire()
        return st, host

    def release(self, st: HostState) -> None:
        st.sem.release()

    async def record_success(self, host: str) -> None:
        st = await self._get(host)
        st.consecutive_403 = 0

    async def record_403(self, host: str, cloudflare: bool = False) -> None:
        st = await self._get(host)
        st.consecutive_403 += 1
        if cloudflare or st.consecutive_403 >= SUPPRESS_AFTER_403:
            st.suppressed_until = time.monotonic() + SUPPRESS_DURATION
            log.warning(
                "host %s suppressed for %ds (consecutive_403=%d, cloudflare=%s)",
                host, SUPPRESS_DURATION, st.consecutive_403, cloudflare,
            )

    async def record_429(self, host: str, retry_after: float = 0.0) -> None:
        """429 / 503 → respect Retry-After or apply exponential backoff."""
        st = await self._get(host)
        delay = max(retry_after, 5.0)
        delay = min(delay, 120.0)
        st.backoff_until = max(st.backoff_until, time.monotonic() + delay)
        log.info("host %s backoff %.1fs (retry-after=%.1f)", host, delay, retry_after)

    async def is_suppressed(self, url: str) -> bool:
        st = await self._get(self.host_of(url))
        return time.monotonic() < st.suppressed_until

    async def clear_all_suppressions(self) -> int:
        """Reset every host's 403 counter and suppression deadline.

        Returns the number of hosts that were actively suppressed when called
        (informational only). Useful when a user knows a publisher's CF block
        has expired and wants to retry without waiting out the full timer.
        """
        async with self._lock:
            now = time.monotonic()
            cleared = sum(
                1 for st in self._states.values() if st.suppressed_until > now
            )
            for st in self._states.values():
                st.suppressed_until = 0.0
                st.backoff_until = 0.0
                st.consecutive_403 = 0
        log.info("cleared host suppressions: %d hosts were active", cleared)
        return cleared
