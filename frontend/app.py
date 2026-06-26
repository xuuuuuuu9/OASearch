"""Reflex application entrypoint."""
from __future__ import annotations

import reflex as rx

from app.backend import app as backend_app
from frontend.design.tokens import GLOBAL_STYLES
from frontend.pages import downloads, journals, library, search  # noqa: F401


app = rx.App(
    style=GLOBAL_STYLES,
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap",
    ],
    api_transformer=backend_app,
)
