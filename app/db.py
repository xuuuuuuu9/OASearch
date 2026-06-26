"""SQLite schema, connection helper, FTS5 sync triggers, and journal seeding."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

import aiosqlite

from .config import DB_PATH, DATA_DIR, PDF_DIR, SEED_JOURNALS


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS journals (
  issn       TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  publisher  TEXT,
  enabled    INTEGER DEFAULT 1,
  added_at   TEXT
);

CREATE TABLE IF NOT EXISTS papers (
  id              INTEGER PRIMARY KEY,
  doi             TEXT UNIQUE NOT NULL,
  issn            TEXT,
  title           TEXT,
  authors         TEXT,                 -- JSON array of "Given Family" strings
  abstract        TEXT,
  keywords        TEXT,                 -- comma-separated
  published_date  TEXT,
  volume          TEXT,
  issue           TEXT,
  pages           TEXT,
  is_oa           INTEGER,              -- 1=yes, 0=no, NULL=unknown
  oa_url          TEXT,
  license         TEXT,
  pdf_path        TEXT,                 -- relative to data/pdfs
  pdf_size        INTEGER,
  pdf_sha256      TEXT,
  downloaded_at   TEXT,
  download_error  TEXT,
  discovered_at   TEXT,
  pmcid           TEXT,
  candidates_resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_papers_issn ON papers(issn);
CREATE INDEX IF NOT EXISTS idx_papers_is_oa ON papers(is_oa);
CREATE INDEX IF NOT EXISTS idx_papers_pdf ON papers(pdf_path);

CREATE TABLE IF NOT EXISTS paper_candidates (
  doi           TEXT NOT NULL,
  url           TEXT NOT NULL,
  source        TEXT NOT NULL,        -- pmc / crossref-link / unpaywall-best / unpaywall-alt / arxiv / biorxiv / chemrxiv / landing
  priority      INTEGER NOT NULL,     -- smaller = try first
  last_status   TEXT,                 -- success / permanent_fail / transient_fail / untried
  last_error    TEXT,
  last_tried_at TEXT,
  PRIMARY KEY (doi, url),
  FOREIGN KEY (doi) REFERENCES papers(doi) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_candidates_doi ON paper_candidates(doi, priority);

CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
  title, authors, abstract, keywords,
  content='papers',
  content_rowid='id',
  tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS papers_ai AFTER INSERT ON papers BEGIN
  INSERT INTO papers_fts(rowid, title, authors, abstract, keywords)
  VALUES (new.id,
          coalesce(new.title, ''),
          coalesce(new.authors, ''),
          coalesce(new.abstract, ''),
          coalesce(new.keywords, ''));
END;

CREATE TRIGGER IF NOT EXISTS papers_ad AFTER DELETE ON papers BEGIN
  INSERT INTO papers_fts(papers_fts, rowid, title, authors, abstract, keywords)
  VALUES ('delete', old.id,
          coalesce(old.title, ''),
          coalesce(old.authors, ''),
          coalesce(old.abstract, ''),
          coalesce(old.keywords, ''));
END;

CREATE TRIGGER IF NOT EXISTS papers_au AFTER UPDATE ON papers BEGIN
  INSERT INTO papers_fts(papers_fts, rowid, title, authors, abstract, keywords)
  VALUES ('delete', old.id,
          coalesce(old.title, ''),
          coalesce(old.authors, ''),
          coalesce(old.abstract, ''),
          coalesce(old.keywords, ''));
  INSERT INTO papers_fts(rowid, title, authors, abstract, keywords)
  VALUES (new.id,
          coalesce(new.title, ''),
          coalesce(new.authors, ''),
          coalesce(new.abstract, ''),
          coalesce(new.keywords, ''));
END;

CREATE TABLE IF NOT EXISTS download_tasks (
  id           INTEGER PRIMARY KEY,
  status       TEXT NOT NULL,
  total        INTEGER DEFAULT 0,
  succeeded    INTEGER DEFAULT 0,
  failed       INTEGER DEFAULT 0,
  skipped      INTEGER DEFAULT 0,
  created_at   TEXT NOT NULL,
  finished_at  TEXT
);

CREATE TABLE IF NOT EXISTS download_items (
  task_id  INTEGER NOT NULL REFERENCES download_tasks(id) ON DELETE CASCADE,
  doi      TEXT NOT NULL,
  status   TEXT NOT NULL,
  error    TEXT,
  PRIMARY KEY (task_id, doi)
);

CREATE INDEX IF NOT EXISTS idx_dl_items_status ON download_items(task_id, status);

CREATE TABLE IF NOT EXISTS search_tasks (
  id            INTEGER PRIMARY KEY,
  q             TEXT NOT NULL,
  issns         TEXT,                -- JSON array
  year_from     INTEGER, year_to INTEGER, rows INTEGER,
  status        TEXT NOT NULL,       -- pending/running/done/failed
  stage         TEXT,                -- 'crossref' / 'unpaywall' / 'done'
  total         INTEGER DEFAULT 0,
  oa            INTEGER DEFAULT 0,
  error         TEXT,
  result_dois   TEXT,                -- JSON array of DOIs (ordered)
  created_at    TEXT NOT NULL,
  finished_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_search_tasks_status ON search_tasks(status);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def init_db() -> None:
    """Create schema, ensure dirs, seed journals (idempotent)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.executescript(SCHEMA_SQL)
        await db.commit()

        # Lightweight migrations — add new columns to old DBs.
        for col, ddl in (
            ("pmcid", "ALTER TABLE papers ADD COLUMN pmcid TEXT"),
            ("candidates_resolved_at", "ALTER TABLE papers ADD COLUMN candidates_resolved_at TEXT"),
        ):
            cur = await db.execute("PRAGMA table_info(papers);")
            cols = {r[1] for r in await cur.fetchall()}
            if col not in cols:
                await db.execute(ddl + ";")
        await db.commit()

        cur = await db.execute("SELECT COUNT(*) FROM journals;")
        (count,) = await cur.fetchone()
        if count == 0:
            now = utcnow_iso()
            await db.executemany(
                "INSERT INTO journals (issn, name, publisher, enabled, added_at) VALUES (?, ?, ?, 1, ?);",
                [(j["issn"], j["name"], j["publisher"], now) for j in SEED_JOURNALS],
            )
            await db.commit()

        # Recover any tasks that were 'running' when the process died.
        await db.execute(
            "UPDATE download_tasks SET status='failed', finished_at=? "
            "WHERE status IN ('running','pending') AND finished_at IS NULL;",
            (utcnow_iso(),),
        )
        await db.execute(
            "UPDATE download_items SET status='failed', error='interrupted' "
            "WHERE status IN ('pending','downloading');"
        )
        await db.execute(
            "UPDATE search_tasks SET status='failed', error='interrupted', finished_at=? "
            "WHERE status IN ('running','pending') AND finished_at IS NULL;",
            (utcnow_iso(),),
        )
        await db.commit()


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """FastAPI dependency / context manager for a single request."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON;")
        yield db


def dumps(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False)
