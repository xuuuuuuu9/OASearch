"""Global configuration loaded from environment / .env."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Storage paths. For a large private library, set PDF_DIR to a folder on a
    # roomy disk and keep DB_PATH on a local SSD when possible.
    data_dir: Path = PROJECT_ROOT / "data"
    pdf_dir: Optional[Path] = None
    db_path: Optional[Path] = None

    # Required for CrossRef polite pool and Unpaywall
    user_email: str = "anonymous@example.com"

    # Download pool
    download_concurrency: int = 16
    polite_mode: bool = False

    # CrossRef / Unpaywall worker concurrency for OA resolution
    oa_lookup_concurrency: int = 20

    # HTTP timeouts (seconds)
    http_timeout: float = 30.0
    download_timeout: float = 120.0

    # Default search results cap
    default_search_rows: int = 100
    max_search_rows: int = 500

    # Sci-Hub fallback. Adds sci-hub as the lowest-priority candidate source
    # (only used when no OA candidate exists). Set ENABLE_SCIHUB=false to
    # disable. Legal status depends on jurisdiction.
    enable_scihub: bool = True
    # Comma-separated override of the default mirror list. Leave empty to use
    # the built-in DEFAULT_MIRRORS in app/clients/scihub.py.
    scihub_mirrors: str = ""

    # Semantic Scholar Graph API key (optional). Without it the public rate
    # limit is ~0.33 req/s; with a key it can go up to ~10 req/s.
    semantic_scholar_api_key: str = ""

    @property
    def app_user_agent(self) -> str:
        return f"NPLibrary/0.1 (mailto:{self.user_email})"

    @property
    def resolved_pdf_dir(self) -> Path:
        return self.pdf_dir or self.data_dir / "pdfs"

    @property
    def resolved_db_path(self) -> Path:
        return self.db_path or self.data_dir / "library.db"

    @property
    def scihub_mirrors_list(self) -> list[str]:
        if not self.scihub_mirrors:
            return []
        return [m.strip() for m in self.scihub_mirrors.split(",") if m.strip()]


settings = Settings()
DATA_DIR = settings.data_dir
PDF_DIR = settings.resolved_pdf_dir
DB_PATH = settings.resolved_db_path


# Seed journals to insert on first launch.
SEED_JOURNALS: list[dict[str, str]] = [
    {"issn": "0031-9422", "name": "Phytochemistry", "publisher": "Elsevier"},
    {"issn": "0163-3864", "name": "Journal of Natural Products", "publisher": "American Chemical Society"},
    {"issn": "0265-0568", "name": "Natural Product Reports", "publisher": "Royal Society of Chemistry"},
]
