"""Journal management page — composed from design patterns only."""
from __future__ import annotations

import reflex as rx

from frontend.design import patterns
from frontend.design.icons import TRASH
from frontend.design.primitives import badge, button, text
from frontend.state.journals_state import JournalsState


def _journal_row(item) -> rx.Component:
    return patterns.section(
        item.name,
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    badge(item.issn, tone="accent"),
                    rx.cond(item.enabled, badge("启用中", tone="success"),
                            badge("已停用", tone="warn")),
                    spacing="2",
                ),
                text(rx.cond(item.publisher != None,  # noqa: E711
                             item.publisher, "未识别出版社"), kind="caption"),
                text("已收录 " + item.paper_count.to_string(use_json=False)
                     + " 篇 · 已下载 " + item.pdf_count.to_string(use_json=False)
                     + " 篇 PDF", kind="muted"),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.hstack(
                rx.switch(
                    checked=item.enabled,
                    on_change=JournalsState.flip_enabled(item.issn),
                ),
                button("删除", variant="danger", icon=TRASH,
                       on_click=JournalsState.request_delete(item.issn)),
                spacing="3",
                align="center",
            ),
            width="100%",
            align="center",
        ),
    )


def _add_form() -> rx.Component:
    return patterns.section(
        "新增期刊",
        rx.hstack(
            rx.input(value=JournalsState.issn, placeholder="ISSN",
                     on_change=JournalsState.set_issn, size="3"),
            rx.input(value=JournalsState.name,
                     placeholder="名称（可空，自动从 CrossRef 补全）",
                     on_change=JournalsState.set_name, size="3"),
            rx.input(value=JournalsState.publisher,
                     placeholder="出版社（可空）",
                     on_change=JournalsState.set_publisher, size="3"),
            button("添加", variant="primary",
                   on_click=JournalsState.add_journal,
                   loading=JournalsState.loading),
            width="100%",
            spacing="2",
            align="center",
        ),
    )


def _delete_dialog() -> rx.Component:
    return rx.alert_dialog.root(
        rx.alert_dialog.content(
            rx.alert_dialog.title("确认删除期刊"),
            rx.alert_dialog.description(
                "将删除 ISSN " + JournalsState.pending_delete_issn
                + " 的期刊条目。已入库论文不受影响。",
            ),
            rx.hstack(
                rx.alert_dialog.cancel(
                    button("取消", variant="secondary",
                           on_click=JournalsState.cancel_delete),
                ),
                rx.alert_dialog.action(
                    button("确认删除", variant="danger",
                           on_click=JournalsState.confirm_delete),
                ),
                spacing="3",
                justify="end",
                width="100%",
            ),
        ),
        open=JournalsState.pending_delete_issn != "",
        on_open_change=JournalsState.cancel_delete,
    )


@rx.page(route="/journals", title="OA Library · 期刊",
         on_load=JournalsState.load_page)
def journals_page() -> rx.Component:
    content = rx.vstack(
        rx.cond(
            JournalsState.error_message != "",
            rx.callout(JournalsState.error_message, color_scheme="amber"),
            rx.fragment(),
        ),
        _add_form(),
        rx.cond(
            JournalsState.journals.length() > 0,
            rx.vstack(
                rx.foreach(JournalsState.journals, _journal_row),
                spacing="2",
                width="100%",
                align="stretch",
            ),
            patterns.empty("暂无期刊"),
        ),
        _delete_dialog(),
        width="100%",
        spacing="3",
        align="stretch",
    )
    return patterns.page_shell(
        title="期刊管理",
        content=content,
        on_refresh=JournalsState.refresh,
    )
