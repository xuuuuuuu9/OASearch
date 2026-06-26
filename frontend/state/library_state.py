"""State for the local library page."""
from __future__ import annotations

import httpx
import reflex as rx

from frontend import api
from frontend.models import JournalRow, PaperRow, journal_from_dict, paper_from_dict


class LibraryState(rx.State):
    query: str = ""
    scope: str = "all"
    page: int = 1
    page_size: int = 20
    total: int = 0
    items: list[PaperRow] = []
    loading: bool = False
    error_message: str = ""
    _loaded: bool = False

    # filters
    all_journals: list[JournalRow] = []
    journals_filter: list[str] = []
    year_from: str = ""
    year_to: str = ""
    author_filter: str = ""
    sort_by: str = "date_desc"

    # drawer
    selected_paper_id: int = 0
    drawer_paper: PaperRow = PaperRow()

    async def load_page(self) -> None:
        if self._loaded:
            return
        await self._load_journals()
        await self.search()
        self._loaded = True

    async def refresh(self) -> None:
        await self._load_journals()
        await self.search()

    async def _load_journals(self) -> None:
        try:
            rows = await api.get_json("/api/journals")
            self.all_journals = [journal_from_dict(item) for item in rows]
        except httpx.HTTPError:
            pass  # 期刊列表加载失败不影响主查询

    def set_query(self, value: str) -> None:
        self.query = value

    def set_scope(self, value: str) -> None:
        self.scope = value
        self.page = 1

    def set_year_from(self, value: str) -> None:
        self.year_from = value

    def set_year_to(self, value: str) -> None:
        self.year_to = value

    def set_author_filter(self, value: str) -> None:
        self.author_filter = value

    def set_sort(self, value: str) -> None:
        self.sort_by = value
        self.page = 1

    def toggle_journal_filter(self, issn: str) -> None:
        if issn in self.journals_filter:
            self.journals_filter = [x for x in self.journals_filter if x != issn]
        else:
            self.journals_filter = [*self.journals_filter, issn]
        self.page = 1

    def select_all_journal_filter(self) -> None:
        self.journals_filter = [j.issn for j in self.all_journals]
        self.page = 1

    def clear_journal_filter(self) -> None:
        self.journals_filter = []
        self.page = 1

    async def search(self) -> None:
        self.loading = True
        self.error_message = ""
        params: dict[str, object] = {
            "q": self.query,
            "scope": self.scope,
            "page": self.page,
            "page_size": self.page_size,
            "sort": self.sort_by,
        }
        if self.year_from.strip().isdigit():
            params["year_from"] = int(self.year_from)
        if self.year_to.strip().isdigit():
            params["year_to"] = int(self.year_to)
        if self.author_filter.strip():
            params["author"] = self.author_filter.strip()
        if self.journals_filter:
            params["issn"] = self.journals_filter
        try:
            payload = await api.get_json("/api/library/search", params=params)
            self.total = payload["total"]
            self.items = [paper_from_dict(item) for item in payload["items"]]
        except httpx.HTTPError:
            self.error_message = "本地库查询失败"
        finally:
            self.loading = False

    async def next_page(self) -> None:
        self.page += 1
        await self.search()

    async def prev_page(self) -> None:
        self.page = max(1, self.page - 1)
        await self.search()

    def open_drawer(self, paper_id: int) -> None:
        for p in self.items:
            if p.id == paper_id:
                self.drawer_paper = p
                self.selected_paper_id = paper_id
                return

    def close_drawer(self) -> None:
        self.selected_paper_id = 0
