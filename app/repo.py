"""Database access helpers — papers / journals / download_tasks upsert + queries.

Keeps SQL out of routers and clients.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

import aiosqlite

from .db import utcnow_iso


# ---------- journals ----------

async def list_journals(db: aiosqlite.Connection, enabled_only: bool = False) -> list[dict[str, Any]]:
    sql = (
        "SELECT j.issn, j.name, j.publisher, j.enabled, "
        "       (SELECT COUNT(*) FROM papers p WHERE p.issn = j.issn) AS paper_count, "
        "       (SELECT COUNT(*) FROM papers p WHERE p.issn = j.issn AND p.pdf_path IS NOT NULL) AS pdf_count "
        "FROM journals j "
    )
    if enabled_only:
        sql += "WHERE j.enabled = 1 "
    sql += "ORDER BY j.name COLLATE NOCASE;"
    cur = await db.execute(sql)
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def add_journal(
    db: aiosqlite.Connection, issn: str, name: str, publisher: Optional[str]
) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO journals (issn, name, publisher, enabled, added_at) "
        "VALUES (?, ?, ?, 1, ?);",
        (issn, name, publisher, utcnow_iso()),
    )
    await db.commit()


async def set_journal_enabled(db: aiosqlite.Connection, issn: str, enabled: bool) -> None:
    await db.execute(
        "UPDATE journals SET enabled=? WHERE issn=?;", (1 if enabled else 0, issn)
    )
    await db.commit()


async def delete_journal(db: aiosqlite.Connection, issn: str) -> None:
    await db.execute("DELETE FROM journals WHERE issn=?;", (issn,))
    await db.commit()


# ---------- papers ----------

async def upsert_paper(
    db: aiosqlite.Connection, work: dict[str, Any], *, oa: Optional[dict[str, Any]] = None
) -> int:
    """Insert or update a paper from a CrossRef parsed work + optional OA info.

    Never overwrites an existing pdf_path / pdf_size / pdf_sha256 / downloaded_at.
    Returns the row id.
    """
    doi = work.get("doi")
    if not doi:
        raise ValueError("paper has no DOI")

    authors_json = json.dumps(work.get("authors") or [], ensure_ascii=False)
    fields = {
        "doi": doi,
        "issn": work.get("issn"),
        "title": work.get("title"),
        "authors": authors_json,
        "abstract": work.get("abstract"),
        "keywords": work.get("keywords"),
        "published_date": work.get("published_date"),
        "volume": work.get("volume"),
        "issue": work.get("issue"),
        "pages": work.get("pages"),
        "license": work.get("license"),
    }
    if oa is not None:
        if oa.get("is_oa") is not None:
            fields["is_oa"] = 1 if oa["is_oa"] else 0
        if oa.get("oa_url"):
            fields["oa_url"] = oa["oa_url"]
        if oa.get("license"):
            fields["license"] = oa["license"]
        if oa.get("pmcid"):
            fields["pmcid"] = oa["pmcid"]

    cur = await db.execute("SELECT id FROM papers WHERE doi=?;", (doi,))
    row = await cur.fetchone()
    if row:
        # UPDATE - preserve PDF-related columns
        sets = ", ".join(f"{k}=?" for k in fields.keys() if k != "doi")
        params: list[Any] = [v for k, v in fields.items() if k != "doi"]
        params.append(doi)
        await db.execute(f"UPDATE papers SET {sets} WHERE doi=?;", params)
        return row["id"]
    else:
        fields["discovered_at"] = utcnow_iso()
        cols = ", ".join(fields.keys())
        ph = ", ".join(["?"] * len(fields))
        cur = await db.execute(
            f"INSERT INTO papers ({cols}) VALUES ({ph});", list(fields.values())
        )
        return cur.lastrowid


async def mark_downloaded(
    db: aiosqlite.Connection,
    doi: str,
    pdf_path: str,
    size: int,
    sha256: str,
) -> None:
    await db.execute(
        "UPDATE papers SET pdf_path=?, pdf_size=?, pdf_sha256=?, downloaded_at=?, download_error=NULL "
        "WHERE doi=?;",
        (pdf_path, size, sha256, utcnow_iso(), doi),
    )


async def mark_papers_saved(db: aiosqlite.Connection, dois: list[str]) -> int:
    """Flip `saved=1` for each DOI present. Returns number of rows updated."""
    if not dois:
        return 0
    placeholders = ",".join(["?"] * len(dois))
    cur = await db.execute(
        f"UPDATE papers SET saved=1 WHERE doi IN ({placeholders});",
        dois,
    )
    await db.commit()
    return cur.rowcount or 0


async def delete_paper(db: aiosqlite.Connection, doi: str) -> tuple[bool, Optional[str]]:
    """Delete a paper row entirely. Returns (deleted, pdf_path_to_unlink)."""
    cur = await db.execute("SELECT pdf_path FROM papers WHERE doi=?;", (doi,))
    row = await cur.fetchone()
    if row is None:
        return False, None
    pdf_path = row[0]
    await db.execute("DELETE FROM paper_candidates WHERE doi=?;", (doi,))
    await db.execute("DELETE FROM papers WHERE doi=?;", (doi,))
    await db.commit()
    return True, pdf_path


async def mark_download_failed(db: aiosqlite.Connection, doi: str, err: str) -> None:
    await db.execute("UPDATE papers SET download_error=? WHERE doi=?;", (err, doi))


async def get_paper_by_doi(db: aiosqlite.Connection, doi: str) -> Optional[dict[str, Any]]:
    cur = await db.execute("SELECT * FROM papers WHERE doi=?;", (doi,))
    r = await cur.fetchone()
    return dict(r) if r else None


async def get_paper_by_id(db: aiosqlite.Connection, paper_id: int) -> Optional[dict[str, Any]]:
    cur = await db.execute("SELECT * FROM papers WHERE id=?;", (paper_id,))
    r = await cur.fetchone()
    return dict(r) if r else None


# ---------- local FTS search ----------

def _build_fts_query(q: str) -> str:
    """Tokenize user input → FTS5 MATCH expression.

    Keep simple: split on whitespace, treat each token as a prefix match,
    AND them together. Quoted phrases preserved verbatim.
    """
    q = q.strip()
    if not q:
        return ""
    # Preserve quoted phrases
    parts: list[str] = []
    cur = ""
    in_quote = False
    for ch in q:
        if ch == '"':
            if in_quote:
                if cur:
                    parts.append(f'"{cur}"')
                cur = ""
            in_quote = not in_quote
            continue
        if ch.isspace() and not in_quote:
            if cur:
                parts.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        parts.append(cur if in_quote else cur)

    safe: list[str] = []
    for p in parts:
        if p.startswith('"'):
            safe.append(p)
        else:
            # Strip any FTS-syntax characters that would break MATCH.
            clean = "".join(c for c in p if c.isalnum() or c in "-_'.")
            if clean:
                safe.append(clean + "*")
    return " ".join(safe)


async def search_local(
    db: aiosqlite.Connection,
    q: str,
    *,
    issns: Optional[list[str]] = None,
    scope: str = "all",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    author: Optional[str] = None,
    sort: str = "date_desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Search the local library with FTS5 + filters.

    scope: 'pdf' (downloaded only), 'meta' (no PDF yet), 'all'
    sort: 'date_desc' | 'date_asc' | 'journal' | 'title' (ignored in FTS mode)
    Returns (rows, total_count).
    """
    where: list[str] = []
    params: list[Any] = []

    fts_query = _build_fts_query(q)
    if fts_query:
        base_from = (
            "FROM papers p "
            "JOIN papers_fts f ON f.rowid = p.id "
            "JOIN (SELECT rowid, bm25(papers_fts) AS rank FROM papers_fts WHERE papers_fts MATCH ?) m "
            "ON m.rowid = p.id "
        )
        params.append(fts_query)
        order = "ORDER BY m.rank ASC"
        select_extra = (
            ", snippet(papers_fts, 0, '<mark>', '</mark>', '…', 16) AS title_hl, "
            "snippet(papers_fts, 2, '<mark>', '</mark>', '…', 20) AS abstract_hl"
        )
    else:
        base_from = "FROM papers p "
        order_map = {
            "date_desc": "ORDER BY coalesce(p.published_date, p.discovered_at) DESC",
            "date_asc":  "ORDER BY coalesce(p.published_date, p.discovered_at) ASC",
            "journal":   "ORDER BY j.name ASC, p.published_date DESC",
            "title":     "ORDER BY p.title ASC",
        }
        order = order_map.get(sort, order_map["date_desc"])
        select_extra = ", NULL AS title_hl, NULL AS abstract_hl"

    if scope == "pdf":
        where.append("p.pdf_path IS NOT NULL")
    elif scope == "meta":
        where.append("p.pdf_path IS NULL")

    # Library only shows papers the user has explicitly saved.
    where.append("p.saved = 1")

    if issns:
        placeholders = ",".join(["?"] * len(issns))
        where.append(f"p.issn IN ({placeholders})")
        params.extend(issns)

    if year_from is not None:
        where.append("substr(p.published_date, 1, 4) >= ?")
        params.append(str(year_from))
    if year_to is not None:
        where.append("substr(p.published_date, 1, 4) <= ?")
        params.append(str(year_to))
    if author:
        where.append("p.authors LIKE ?")
        params.append(f"%{author}%")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    count_sql = f"SELECT COUNT(*) {base_from} {where_sql};"
    cur = await db.execute(count_sql, params)
    (total,) = await cur.fetchone()

    sql = (
        f"SELECT p.*, j.name AS journal_name {select_extra} "
        f"{base_from} "
        "LEFT JOIN journals j ON j.issn = p.issn "
        f"{where_sql} "
        f"{order} LIMIT ? OFFSET ?;"
    )
    cur = await db.execute(sql, params + [limit, offset])
    rows = await cur.fetchall()
    return [dict(r) for r in rows], total


# ---------- download tasks ----------

async def create_download_task(db: aiosqlite.Connection, dois: list[str]) -> int:
    cur = await db.execute(
        "INSERT INTO download_tasks (status, total, created_at) VALUES ('pending', ?, ?);",
        (len(dois), utcnow_iso()),
    )
    task_id = cur.lastrowid
    await db.executemany(
        "INSERT OR IGNORE INTO download_items (task_id, doi, status) VALUES (?, ?, 'pending');",
        [(task_id, d) for d in dois],
    )
    await db.commit()
    return task_id


async def set_task_status(
    db: aiosqlite.Connection, task_id: int, status: str, finished: bool = False
) -> None:
    if finished:
        await db.execute(
            "UPDATE download_tasks SET status=?, finished_at=? WHERE id=?;",
            (status, utcnow_iso(), task_id),
        )
    else:
        await db.execute(
            "UPDATE download_tasks SET status=? WHERE id=?;", (status, task_id)
        )
    await db.commit()


async def set_item_status(
    db: aiosqlite.Connection, task_id: int, doi: str, status: str, error: Optional[str] = None
) -> None:
    await db.execute(
        "UPDATE download_items SET status=?, error=? WHERE task_id=? AND doi=?;",
        (status, error, task_id, doi),
    )
    # Roll counters in the parent task.
    field = {
        "done": "succeeded",
        "failed": "failed",
        "skipped": "skipped",
    }.get(status)
    if field:
        await db.execute(
            f"UPDATE download_tasks SET {field} = {field} + 1 WHERE id=?;", (task_id,)
        )
    await db.commit()


async def get_task(db: aiosqlite.Connection, task_id: int) -> Optional[dict[str, Any]]:
    cur = await db.execute("SELECT * FROM download_tasks WHERE id=?;", (task_id,))
    r = await cur.fetchone()
    if not r:
        return None
    task = dict(r)
    cur = await db.execute(
        "SELECT di.doi, di.status, di.error, p.title "
        "FROM download_items di LEFT JOIN papers p ON p.doi = di.doi "
        "WHERE di.task_id=? ORDER BY di.rowid;",
        (task_id,),
    )
    items = await cur.fetchall()
    task["items"] = [dict(i) for i in items]
    return task


async def list_tasks(db: aiosqlite.Connection, limit: int = 20) -> list[dict[str, Any]]:
    cur = await db.execute(
        "SELECT * FROM download_tasks ORDER BY id DESC LIMIT ?;", (limit,)
    )
    return [dict(r) for r in await cur.fetchall()]


# ---------- search tasks ----------

async def create_search_task(
    db: aiosqlite.Connection,
    q: str, issns: list[str],
    year_from: Optional[int], year_to: Optional[int], rows: int,
) -> int:
    cur = await db.execute(
        "INSERT INTO search_tasks (q, issns, year_from, year_to, rows, status, stage, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', 'queued', ?);",
        (q, json.dumps(issns), year_from, year_to, rows, utcnow_iso()),
    )
    await db.commit()
    return cur.lastrowid


async def update_search_task(
    db: aiosqlite.Connection, sid: int, *,
    status: Optional[str] = None, stage: Optional[str] = None,
    total: Optional[int] = None, oa: Optional[int] = None,
    error: Optional[str] = None, result_dois: Optional[list[str]] = None,
    finished: bool = False,
) -> None:
    sets, params = [], []
    if status is not None: sets.append("status=?"); params.append(status)
    if stage is not None: sets.append("stage=?"); params.append(stage)
    if total is not None: sets.append("total=?"); params.append(total)
    if oa is not None: sets.append("oa=?"); params.append(oa)
    if error is not None: sets.append("error=?"); params.append(error)
    if result_dois is not None:
        sets.append("result_dois=?"); params.append(json.dumps(result_dois))
    if finished:
        sets.append("finished_at=?"); params.append(utcnow_iso())
    if not sets:
        return
    params.append(sid)
    await db.execute(f"UPDATE search_tasks SET {', '.join(sets)} WHERE id=?;", params)
    await db.commit()


async def get_search_task(db: aiosqlite.Connection, sid: int) -> Optional[dict[str, Any]]:
    cur = await db.execute("SELECT * FROM search_tasks WHERE id=?;", (sid,))
    r = await cur.fetchone()
    return dict(r) if r else None


async def get_search_task_papers(
    db: aiosqlite.Connection, sid: int
) -> list[dict[str, Any]]:
    """Return the papers (joined w/ journal name) referenced by a finished search task."""
    cur = await db.execute("SELECT result_dois FROM search_tasks WHERE id=?;", (sid,))
    r = await cur.fetchone()
    if not r or not r["result_dois"]:
        return []
    dois = json.loads(r["result_dois"])
    if not dois:
        return []
    placeholders = ",".join(["?"] * len(dois))
    cur = await db.execute(
        f"SELECT p.*, j.name AS journal_name FROM papers p "
        f"LEFT JOIN journals j ON j.issn = p.issn "
        f"WHERE p.doi IN ({placeholders});",
        dois,
    )
    by_doi = {r["doi"]: dict(r) for r in await cur.fetchall()}
    return [by_doi[d] for d in dois if d in by_doi]


async def list_recent_searches(
    db: aiosqlite.Connection, limit: int = 10
) -> list[dict[str, Any]]:
    cur = await db.execute(
        "SELECT id, q, status, total, oa, created_at FROM search_tasks "
        "ORDER BY id DESC LIMIT ?;", (limit,)
    )
    return [dict(r) for r in await cur.fetchall()]


# ---------- paper_candidates ----------

async def upsert_candidates(
    db: aiosqlite.Connection, doi: str, candidates: list[dict[str, Any]]
) -> None:
    """Replace the candidate URL set for a DOI.

    Each entry: {'url': str, 'source': str, 'priority': int}
    Preserves last_status of URLs that already existed (so a successful
    download stays marked success across re-resolution).
    """
    if not doi or not candidates:
        return

    # Read existing statuses to preserve
    cur = await db.execute(
        "SELECT url, last_status, last_error FROM paper_candidates WHERE doi=?;",
        (doi,),
    )
    prev = {r["url"]: (r["last_status"], r["last_error"]) for r in await cur.fetchall()}

    # Wipe and re-insert (priority may have changed across sources).
    await db.execute("DELETE FROM paper_candidates WHERE doi=?;", (doi,))
    rows = []
    for c in candidates:
        ls, le = prev.get(c["url"], ("untried", None))
        rows.append((doi, c["url"], c["source"], c["priority"], ls, le))
    await db.executemany(
        "INSERT INTO paper_candidates (doi, url, source, priority, last_status, last_error) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        rows,
    )
    await db.execute(
        "UPDATE papers SET candidates_resolved_at=? WHERE doi=?;",
        (utcnow_iso(), doi),
    )


async def get_candidates(
    db: aiosqlite.Connection, doi: str
) -> list[dict[str, Any]]:
    """Return sorted by priority, success-first then untried then fails."""
    cur = await db.execute(
        "SELECT url, source, priority, last_status, last_error, last_tried_at "
        "FROM paper_candidates WHERE doi=? "
        "ORDER BY CASE last_status "
        "  WHEN 'success' THEN 0 "
        "  WHEN 'untried' THEN 1 "
        "  WHEN 'transient_fail' THEN 2 "
        "  WHEN 'permanent_fail' THEN 3 "
        "  ELSE 4 END, priority ASC;",
        (doi,),
    )
    return [dict(r) for r in await cur.fetchall()]


async def mark_candidate_status(
    db: aiosqlite.Connection, doi: str, url: str, status: str, error: Optional[str]
) -> None:
    await db.execute(
        "UPDATE paper_candidates SET last_status=?, last_error=?, last_tried_at=? "
        "WHERE doi=? AND url=?;",
        (status, error, utcnow_iso(), doi, url),
    )
