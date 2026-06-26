"""Typed frontend view models for Reflex state."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class JournalRow:
    issn: str
    name: str
    publisher: Optional[str] = None
    enabled: bool = True
    paper_count: int = 0
    pdf_count: int = 0


@dataclass
class PaperRow:
    id: int = 0
    doi: str = ""
    title: str = ""
    journal_name: str = ""
    published_date: str = ""
    pdf_path: Optional[str] = None
    auto_downloadable_count: int = 0
    authors_list: list[str] = field(default_factory=list)
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)


@dataclass
class SearchTaskRow:
    id: int = 0
    q: str = ""
    status: str = ""
    total: int = 0
    oa: int = 0


@dataclass
class DownloadItemRow:
    doi: str = ""
    title: str = ""
    status: str = ""
    error: Optional[str] = None


@dataclass
class DownloadTaskRow:
    id: int = 0
    status: str = ""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    created_at: str = ""
    task_items: list[DownloadItemRow] = field(default_factory=list)


def journal_from_dict(data: dict[str, Any]) -> JournalRow:
    return JournalRow(
        issn=str(data.get("issn") or ""),
        name=str(data.get("name") or ""),
        publisher=data.get("publisher"),
        enabled=bool(data.get("enabled", True)),
        paper_count=int(data.get("paper_count") or 0),
        pdf_count=int(data.get("pdf_count") or 0),
    )


def paper_from_dict(data: dict[str, Any]) -> PaperRow:
    raw_keywords = data.get("keywords") or ""
    if isinstance(raw_keywords, str):
        keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
    else:
        keywords = [str(k) for k in raw_keywords if str(k).strip()]
    return PaperRow(
        id=int(data.get("id") or 0),
        doi=str(data.get("doi") or ""),
        title=str(data.get("title") or ""),
        journal_name=str(data.get("journal_name") or data.get("issn") or ""),
        published_date=str(data.get("published_date") or ""),
        pdf_path=data.get("pdf_path"),
        auto_downloadable_count=int(data.get("auto_downloadable_count") or 0),
        authors_list=[str(item) for item in data.get("authors_list") or []],
        abstract=str(data.get("abstract") or ""),
        keywords=keywords,
    )


def search_task_from_dict(data: dict[str, Any]) -> SearchTaskRow:
    return SearchTaskRow(
        id=int(data.get("id") or 0),
        q=str(data.get("q") or ""),
        status=str(data.get("status") or ""),
        total=int(data.get("total") or 0),
        oa=int(data.get("oa") or 0),
    )


def download_task_from_dict(data: dict[str, Any]) -> DownloadTaskRow:
    return DownloadTaskRow(
        id=int(data.get("id") or 0),
        status=str(data.get("status") or ""),
        total=int(data.get("total") or 0),
        succeeded=int(data.get("succeeded") or 0),
        failed=int(data.get("failed") or 0),
        skipped=int(data.get("skipped") or 0),
        created_at=str(data.get("created_at") or ""),
        task_items=[
            DownloadItemRow(
                doi=str(item.get("doi") or ""),
                title=str(item.get("title") or ""),
                status=str(item.get("status") or ""),
                error=item.get("error"),
            )
            for item in data.get("items") or []
        ],
    )
