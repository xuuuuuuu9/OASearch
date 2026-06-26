"""Pydantic models used in API request/response shapes."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class JournalIn(BaseModel):
    issn: str = Field(..., min_length=7, max_length=20)
    name: str = Field(..., min_length=1)
    publisher: Optional[str] = None


class JournalOut(BaseModel):
    issn: str
    name: str
    publisher: Optional[str] = None
    enabled: bool = True
    paper_count: int = 0
    pdf_count: int = 0


class SearchRequest(BaseModel):
    q: str = Field("", description="Full-text query against CrossRef")
    issns: list[str] = Field(default_factory=list)
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    rows: int = 100

    @field_validator("year_from", "year_to", mode="before")
    @classmethod
    def _empty_to_none(cls, v: Any) -> Any:
        if v == "" or v is None:
            return None
        return v

    @field_validator("rows", mode="before")
    @classmethod
    def _rows_default(cls, v: Any) -> Any:
        if v == "" or v is None:
            return 100
        return v


class PaperOut(BaseModel):
    id: int
    doi: str
    issn: Optional[str]
    title: Optional[str]
    authors: list[str] = Field(default_factory=list)
    abstract: Optional[str] = None
    published_date: Optional[str] = None
    journal_name: Optional[str] = None
    is_oa: Optional[bool] = None
    oa_url: Optional[str] = None
    has_pdf: bool = False
    pdf_url: Optional[str] = None


class DownloadRequest(BaseModel):
    dois: list[str]


class DownloadItemStatus(BaseModel):
    doi: str
    title: Optional[str] = None
    status: str
    error: Optional[str] = None


class DownloadTaskStatus(BaseModel):
    id: int
    status: str
    total: int
    succeeded: int
    failed: int
    skipped: int
    created_at: str
    finished_at: Optional[str] = None
    items: list[DownloadItemStatus] = Field(default_factory=list)
