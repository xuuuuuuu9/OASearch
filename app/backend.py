"""Pure FastAPI backend used by the Reflex frontend."""
from __future__ import annotations

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


@asynccontextmanager
async def lifespan(app_: FastAPI):
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
