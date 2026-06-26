"""Manual smoke test for sci-hub resolver — DOES make real network calls.

Run only when you want to verify sci-hub mirror reachability from your network:

    .venv/Scripts/python.exe scripts/scihub_smoke.py 10.1038/nrd1632

It tries each configured mirror in turn and reports which one returns a PDF URL.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root on sys.path when invoked as `python scripts/scihub_smoke.py`.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.clients.scihub import DEFAULT_MIRRORS, resolve_via_scihub  # noqa: E402


async def main(doi: str) -> int:
    print(f"trying mirrors: {', '.join(DEFAULT_MIRRORS)}")
    print(f"DOI: {doi}\n")
    urls = await resolve_via_scihub(doi)
    if not urls:
        print("\n[FAIL] no mirror returned a PDF URL.")
        print("   possible causes: all mirrors blocked by your network,")
        print("   article truly not on sci-hub, or temporary mirror outage.")
        return 1
    print(f"\n[OK] resolved: {urls[0]}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/scihub_smoke.py <DOI>")
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1])))
