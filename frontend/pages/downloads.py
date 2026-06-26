"""Download tasks page — composed from design patterns only."""
from __future__ import annotations

import reflex as rx

from frontend.design import patterns
from frontend.design.icons import EXTERNAL_LINK, REFRESH
from frontend.design.primitives import badge, button, divider, text
from frontend.design.tokens import GAP
from frontend.state.downloads_state import DownloadsState


def _task_list_item(task) -> rx.Component:
    is_selected = DownloadsState.selected_task.id == task.id
    return rx.box(
        rx.vstack(
            rx.hstack(
                text("任务 #" + task.id.to_string(use_json=False),
                     kind="body"),
                rx.spacer(),
                badge(task.status, tone="accent"),
                width="100%",
                align="center",
            ),
            text(
                "总 " + task.total.to_string(use_json=False)
                + " · 成 " + task.succeeded.to_string(use_json=False)
                + " · 失 " + task.failed.to_string(use_json=False),
                kind="caption",
            ),
            text(task.created_at, kind="muted"),
            spacing="1",
            align="start",
        ),
        padding=GAP["sm"],
        background=rx.cond(is_selected, "var(--green-a3)", "var(--gray-a2)"),
        border=rx.cond(is_selected,
                       "1px solid var(--green-8)",
                       "1px solid var(--gray-a4)"),
        cursor="pointer",
        width="100%",
        on_click=DownloadsState.select_task(task.id),
    )


def _items_table() -> rx.Component:
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("DOI"),
                rx.table.column_header_cell("Title"),
                rx.table.column_header_cell("Status"),
                rx.table.column_header_cell(""),
            ),
        ),
        rx.table.body(
            rx.foreach(
                DownloadsState.selected_task.task_items,
                lambda item: rx.table.row(
                    rx.table.cell(text(item.doi, kind="caption")),
                    rx.table.cell(text(item.title, kind="caption")),
                    rx.table.cell(
                        rx.cond(item.status == "done", badge("done", tone="success"),
                            rx.cond(item.status == "failed",
                                    badge("failed", tone="danger"),
                                    badge(item.status))),
                    ),
                    rx.table.cell(
                        rx.cond(
                            item.status == "failed",
                            rx.hstack(
                                button("重试", variant="ghost",
                                       on_click=DownloadsState.retry_item(item.doi)),
                                rx.link(
                                    button("DOI", variant="ghost",
                                           icon=EXTERNAL_LINK),
                                    href="https://doi.org/" + item.doi,
                                    is_external=True,
                                ),
                                rx.link(
                                    button("sci-hub", variant="ghost",
                                           icon=EXTERNAL_LINK),
                                    href="https://sci-hub.ru/" + item.doi,
                                    is_external=True,
                                ),
                                spacing="1",
                            ),
                            rx.fragment(),
                        ),
                    ),
                ),
            ),
        ),
        variant="surface",
        width="100%",
    )


def _detail_panel() -> rx.Component:
    return patterns.section(
        "任务详情",
        rx.cond(
            DownloadsState.selected_task.id > 0,
            rx.vstack(
                patterns.progress_row(
                    label="任务 #" + DownloadsState.selected_task.id.to_string(use_json=False)
                          + " · " + DownloadsState.selected_task.status,
                    value=DownloadsState.selected_task.succeeded,
                    max_value=rx.cond(
                        DownloadsState.selected_task.total > 0,
                        DownloadsState.selected_task.total,
                        1,
                    ),
                    hint=rx.cond(DownloadsState.polling,
                                 "自动轮询每 2 秒", "已停止"),
                ),
                divider(),
                _items_table(),
                width="100%",
                spacing="3",
                align="stretch",
            ),
            patterns.empty("未选择任务", "在左侧选择一个任务查看详情。"),
        ),
        right=button(
            "重试全部失败",
            variant="primary",
            icon=REFRESH,
            on_click=DownloadsState.retry_all,
            disabled=DownloadsState.selected_task.failed == 0,
        ),
    )


@rx.page(route="/downloads", title="OA Library · 下载",
         on_load=DownloadsState.load_page)
def downloads_page() -> rx.Component:
    content = rx.hstack(
        rx.vstack(
            patterns.section(
                "任务列表",
                rx.cond(
                    DownloadsState.tasks.length() > 0,
                    rx.vstack(
                        rx.foreach(DownloadsState.tasks, _task_list_item),
                        spacing="2",
                        width="100%",
                        align="stretch",
                    ),
                    patterns.empty("暂无任务"),
                ),
            ),
            width="20rem",
            align="stretch",
            spacing="2",
        ),
        rx.vstack(_detail_panel(), width="100%", align="stretch"),
        width="100%",
        align="start",
        spacing="3",
    )
    return patterns.page_shell(
        title="下载任务",
        content=content,
        on_refresh=DownloadsState.refresh,
    )
