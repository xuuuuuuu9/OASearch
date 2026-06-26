"""State for the Search workbench page."""
from __future__ import annotations

import asyncio

import httpx
import reflex as rx

from frontend import api
from frontend.models import (
    JournalRow,
    PaperRow,
    SearchTaskRow,
    journal_from_dict,
    paper_from_dict,
    search_task_from_dict,
)


class SearchState(rx.State):
    query: str = ""
    year_from: str = ""
    year_to: str = ""
    rows: str = "100"
    journals: list[JournalRow] = []
    selected_issns: list[str] = []
    active_task: SearchTaskRow = SearchTaskRow()
    papers: list[PaperRow] = []
    selected_dois: list[str] = []
    loading: bool = False
    error_message: str = ""
    _loaded: bool = False

    # drawer
    selected_paper_id: int = 0
    drawer_paper: PaperRow = PaperRow()

    # polling
    polling: bool = False

    async def load_page(self) -> None:
        if self._loaded:
            return
        await self._do_load()
        self._loaded = True

    async def refresh(self) -> None:
        await self._do_load()

    async def _do_load(self) -> None:
        self.loading = True
        self.error_message = ""
        try:
            journal_rows = await api.get_json(
                "/api/journals", params={"enabled_only": True}
            )
            self.journals = [journal_from_dict(item) for item in journal_rows]
            if not self.selected_issns:
                self.selected_issns = [item.issn for item in self.journals]
            latest = await api.get_json("/api/search-tasks/latest")
            self.active_task = search_task_from_dict(latest)
            if latest.get("status") == "done":
                papers = await api.get_json(
                    f"/api/search-tasks/{latest['id']}/papers"
                )
                self.papers = [paper_from_dict(item) for item in papers]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                self.error_message = f"加载失败: {exc.response.status_code}"
        except httpx.HTTPError:
            self.error_message = "无法连接后端 API"
        finally:
            self.loading = False

    def set_query(self, value: str) -> None:
        self.query = value

    def set_year_from(self, value: str) -> None:
        self.year_from = value

    def set_year_to(self, value: str) -> None:
        self.year_to = value

    def set_rows(self, value: str) -> None:
        self.rows = value

    def toggle_issn(self, issn: str) -> None:
        if issn in self.selected_issns:
            self.selected_issns = [item for item in self.selected_issns if item != issn]
        else:
            self.selected_issns = [*self.selected_issns, issn]

    def select_all_journals(self) -> None:
        self.selected_issns = [j.issn for j in self.journals]

    def clear_journals(self) -> None:
        self.selected_issns = []

    def clear_selection(self) -> None:
        self.selected_dois = []

    async def run_search(self):
        if not self.query.strip():
            self.error_message = "请输入关键词"
            return
        if not self.selected_issns:
            self.error_message = "至少选择一个期刊"
            return
        self.loading = True
        self.error_message = ""
        self.selected_dois = []
        self.papers = []
        payload: dict[str, object] = {
            "q": self.query.strip(),
            "issns": self.selected_issns,
            "rows": int(self.rows or "100"),
        }
        if self.year_from.strip():
            payload["year_from"] = int(self.year_from)
        if self.year_to.strip():
            payload["year_to"] = int(self.year_to)
        try:
            task_data = await api.post_json("/api/search-tasks", payload)
            self.active_task = search_task_from_dict(task_data)
            self.loading = False
            return SearchState.poll_task
        except httpx.HTTPError:
            self.error_message = "创建检索任务失败"
        finally:
            self.loading = False

    def toggle_doi(self, doi: str) -> None:
        if doi in self.selected_dois:
            self.selected_dois = [item for item in self.selected_dois if item != doi]
        else:
            self.selected_dois = [*self.selected_dois, doi]

    async def start_download(self) -> None:
        if not self.selected_dois:
            self.error_message = "先选择要下载的论文"
            return
        self.loading = True
        self.error_message = ""
        try:
            await api.post_json("/api/download-tasks", {"dois": self.selected_dois})
            self.selected_dois = []
        except httpx.HTTPError:
            self.error_message = "发起下载任务失败"
        finally:
            self.loading = False

    def open_drawer(self, paper_id: int) -> None:
        for p in self.papers:
            if p.id == paper_id:
                self.drawer_paper = p
                self.selected_paper_id = paper_id
                return

    def close_drawer(self) -> None:
        self.selected_paper_id = 0

    async def _fetch_task_progress(self) -> None:
        if not self.active_task.id:
            return
        try:
            data = await api.get_json(f"/api/search-tasks/{self.active_task.id}")
            self.active_task = search_task_from_dict(data)
            if self.active_task.status == "done":
                papers = await api.get_json(
                    f"/api/search-tasks/{self.active_task.id}/papers"
                )
                self.papers = [paper_from_dict(item) for item in papers]
        except httpx.HTTPError:
            pass

    @rx.event(background=True)
    async def poll_task(self):
        async with self:
            if self.polling:
                return
            self.polling = True
        try:
            while True:
                async with self:
                    status = self.active_task.status
                if status not in ("queued", "running", "pending"):
                    break
                await asyncio.sleep(2)
                async with self:
                    await self._fetch_task_progress()
        finally:
            async with self:
                self.polling = False
