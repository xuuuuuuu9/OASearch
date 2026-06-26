"""State for the journals workbench page."""
from __future__ import annotations

import httpx
import reflex as rx

from frontend import api
from frontend.models import JournalRow, journal_from_dict


class JournalsState(rx.State):
    journals: list[JournalRow] = []
    issn: str = ""
    name: str = ""
    publisher: str = ""
    loading: bool = False
    error_message: str = ""
    _loaded: bool = False
    pending_delete_issn: str = ""

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
            rows = await api.get_json("/api/journals")
            self.journals = [journal_from_dict(item) for item in rows]
        except httpx.HTTPError:
            self.error_message = "加载期刊列表失败"
        finally:
            self.loading = False

    def set_issn(self, value: str) -> None:
        self.issn = value

    def set_name(self, value: str) -> None:
        self.name = value

    def set_publisher(self, value: str) -> None:
        self.publisher = value

    async def add_journal(self) -> None:
        if not self.issn.strip():
            self.error_message = "请先输入 ISSN"
            return
        self.loading = True
        self.error_message = ""
        try:
            await api.post_json(
                "/api/journals",
                {
                    "issn": self.issn.strip(),
                    "name": self.name.strip() or None,
                    "publisher": self.publisher.strip() or None,
                },
            )
            self.issn = ""
            self.name = ""
            self.publisher = ""
            await self._do_load()
        except httpx.HTTPError:
            self.error_message = "添加期刊失败"
        finally:
            self.loading = False

    async def toggle_enabled(self, issn: str, enabled: bool) -> None:
        self.loading = True
        self.error_message = ""
        try:
            await api.patch_json(f"/api/journals/{issn}", {"enabled": enabled})
            await self._do_load()
        except httpx.HTTPError:
            self.error_message = "更新期刊状态失败"
        finally:
            self.loading = False

    async def flip_enabled(self, issn: str) -> None:
        """Find current `enabled` for `issn`, send the inverse to backend."""
        current = next(
            (j.enabled for j in self.journals if j.issn == issn),
            True,
        )
        await self.toggle_enabled(issn, not current)

    async def delete_journal(self, issn: str) -> None:
        self.loading = True
        self.error_message = ""
        try:
            await api.delete_json(f"/api/journals/{issn}")
            await self._do_load()
        except httpx.HTTPError:
            self.error_message = "删除期刊失败"
        finally:
            self.loading = False

    def request_delete(self, issn: str) -> None:
        self.pending_delete_issn = issn

    def cancel_delete(self) -> None:
        self.pending_delete_issn = ""

    async def confirm_delete(self) -> None:
        if not self.pending_delete_issn:
            return
        issn = self.pending_delete_issn
        self.pending_delete_issn = ""
        await self.delete_journal(issn)
