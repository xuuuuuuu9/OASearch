"""Pure FastAPI backend used by the Reflex frontend."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .db import init_db
from .routers import api, files


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("nplibrary")


def _bootstrap_schema_sync() -> None:
    """Create the SQLite schema synchronously at module import.

    Reflex's `api_transformer=backend_app` only mounts our routes; it does
    NOT invoke this app's lifespan, so we can't rely on FastAPI's lifespan
    to create tables. Run synchronously here so the schema exists before
    any request lands.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to run a one-shot.
        asyncio.run(init_db())
        return
    # We're already inside a running loop (atypical at import time).
    # Skip; the FastAPI lifespan below will catch it in direct-uvicorn mode.
    log.debug("skipping sync init_db; event loop already running")


_bootstrap_schema_sync()


@asynccontextmanager
async def lifespan(app_: FastAPI):
    # In direct-uvicorn mode this still runs (idempotent). In Reflex mode
    # this lifespan is not invoked; the module-level _bootstrap_schema_sync
    # call above handles it.
    await init_db()
    if (
        settings.user_email == "anonymous@example.com"
        or "example.com" in settings.user_email.lower()
    ):
        log.warning(
            "=" * 70 + "\n"
            "  USER_EMAIL is unset or uses an example.com address.\n"
            "  Unpaywall WILL reject every OA lookup with HTTP 422.\n"
            "  Action: copy .env.example to .env and set a real email.\n"
            + "=" * 70
        )
    log.info(
        "Ready. concurrency=%d polite=%s ua=%r",
        settings.download_concurrency,
        settings.polite_mode,
        settings.app_user_agent,
    )
    yield


app = FastAPI(title="NP OA Library", lifespan=lifespan)
app.include_router(files.router)
app.include_router(api.router)
