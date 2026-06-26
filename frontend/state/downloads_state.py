"""State for the downloads workbench page."""
from __future__ import annotations

import asyncio

import httpx
import reflex as rx

from frontend import api
from frontend.models import DownloadTaskRow, download_task_from_dict


class DownloadsState(rx.State):
    tasks: list[DownloadTaskRow] = []
    selected_task: DownloadTaskRow = DownloadTaskRow()
    loading: bool = False
    error_message: str = ""
    _loaded: bool = False
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
            task_rows = await api.get_json("/api/download-tasks", params={"limit": 50})
            self.tasks = [download_task_from_dict(item) for item in task_rows]
            if self.tasks and not self.selected_task.id:
                detail = await api.get_json(
                    f"/api/download-tasks/{self.tasks[0].id}"
                )
                self.selected_task = download_task_from_dict(detail)
        except httpx.HTTPError:
            self.error_message = "下载任务加载失败"
        finally:
            self.loading = False

    async def select_task(self, task_id: int):
        self.loading = True
        self.error_message = ""
        try:
            detail = await api.get_json(f"/api/download-tasks/{task_id}")
            self.selected_task = download_task_from_dict(detail)
            self.loading = False
            if self.selected_task.status in ("pending", "running"):
                return DownloadsState.poll_task
        except httpx.HTTPError:
            self.error_message = "任务详情加载失败"
        finally:
            self.loading = False

    async def retry_all(self):
        if not self.selected_task.id:
            return
        self.loading = True
        self.error_message = ""
        try:
            await api.post_json(f"/api/download-tasks/{self.selected_task.id}/retry", {})
            self.loading = False
            return DownloadsState.poll_task
        except httpx.HTTPError:
            self.error_message = "批量重试失败"
        finally:
            self.loading = False

    async def retry_item(self, doi: str):
        if not self.selected_task.id:
            return
        self.loading = True
        self.error_message = ""
        try:
            await api.post_json(
                f"/api/download-tasks/{self.selected_task.id}/items/{doi}/retry", {}
            )
            self.loading = False
            return DownloadsState.poll_task
        except httpx.HTTPError:
            self.error_message = "单条重试失败"
        finally:
            self.loading = False

    async def _fetch_selected_progress(self) -> None:
        if not self.selected_task.id:
            return
        try:
            detail = await api.get_json(
                f"/api/download-tasks/{self.selected_task.id}"
            )
            self.selected_task = download_task_from_dict(detail)
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
                    status = self.selected_task.status
                if status not in ("pending", "running"):
                    break
                await asyncio.sleep(2)
                async with self:
                    await self._fetch_selected_progress()
        finally:
            async with self:
                self.polling = False
