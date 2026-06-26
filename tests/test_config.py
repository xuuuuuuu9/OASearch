"""Configuration defaults and path overrides."""
from __future__ import annotations

from pathlib import Path

from app.config import PROJECT_ROOT, Settings


def test_settings_default_storage_paths() -> None:
    settings = Settings()

    assert settings.data_dir == PROJECT_ROOT / "data"
    assert settings.resolved_db_path == PROJECT_ROOT / "data" / "library.db"
    assert settings.resolved_pdf_dir == PROJECT_ROOT / "data" / "pdfs"


def test_settings_support_storage_path_overrides(tmp_path: Path) -> None:
    data_dir = tmp_path / "library-data"
    pdf_dir = tmp_path / "pdf-folder"
    db_path = tmp_path / "metadata.sqlite"

    settings = Settings(data_dir=data_dir, pdf_dir=pdf_dir, db_path=db_path)

    assert settings.data_dir == data_dir
    assert settings.resolved_pdf_dir == pdf_dir
    assert settings.resolved_db_path == db_path
