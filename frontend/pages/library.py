"""Local library page — composed from design patterns only."""
from __future__ import annotations

import reflex as rx

from frontend.design import patterns
from frontend.design.icons import (
    CHEVRON_LEFT,
    CHEVRON_RIGHT,
    EXTERNAL_LINK,
    FILTER,
    SEARCH,
    TRASH,
)
from frontend.design.primitives import badge, button, divider, text
from frontend.state.library_state import LibraryState


def _scope_select() -> rx.Component:
    return rx.vstack(
        text("范围", kind="caption"),
        rx.select.root(
            rx.select.trigger(),
            rx.select.content(
                rx.select.item("全部", value="all"),
                rx.select.item("仅 PDF", value="pdf"),
                rx.select.item("仅元数据", value="meta"),
            ),
            value=LibraryState.scope,
            on_change=LibraryState.set_scope,
        ),
        spacing="1",
        align="stretch",
        width="100%",
    )


def _sort_select() -> rx.Component:
    return rx.select.root(
        rx.select.trigger(),
        rx.select.content(
            rx.select.item("日期 ↓ 新→旧", value="date_desc"),
            rx.select.item("日期 ↑ 旧→新", value="date_asc"),
            rx.select.item("按期刊", value="journal"),
            rx.select.item("按标题", value="title"),
        ),
        value=LibraryState.sort_by,
        on_change=LibraryState.set_sort,
        size="3",
    )


def _journals_filter_dropdown() -> rx.Component:
    label = rx.cond(
        LibraryState.journals_filter.length() > 0,
        "期刊：已选 "
        + LibraryState.journals_filter.length().to_string(use_json=False)
        + " 本",
        "期刊：全部",
    )
    return patterns.multi_select_dropdown(
        label=label,
        items_var=LibraryState.all_journals,
        render_item=lambda j: rx.checkbox(
            j.name,
            checked=LibraryState.journals_filter.contains(j.issn),
            on_change=LibraryState.toggle_journal_filter(j.issn),
        ),
        on_select_all=LibraryState.select_all_journal_filter,
        on_clear=LibraryState.clear_journal_filter,
        width="18rem",
    )


def _year_group() -> rx.Component:
    return rx.vstack(
        text("年份范围", kind="caption"),
        rx.hstack(
            rx.input(value=LibraryState.year_from, placeholder="from",
                     on_change=LibraryState.set_year_from, size="2",
                     type="number", min=1900, max=2100, step=1),
            rx.input(value=LibraryState.year_to, placeholder="to",
                     on_change=LibraryState.set_year_to, size="2",
                     type="number", min=1900, max=2100, step=1),
            spacing="2",
        ),
        spacing="1",
        align="stretch",
    )


def _author_group() -> rx.Component:
    return rx.vstack(
        text("作者", kind="caption"),
        rx.input(value=LibraryState.author_filter, placeholder="作者名包含…",
                 on_change=LibraryState.set_author_filter, size="2"),
        spacing="1",
        align="stretch",
    )


def _sidebar() -> rx.Component:
    return patterns.filter_sidebar(
        rx.hstack(rx.icon(tag=FILTER, size=16),
                  text("筛选", kind="caption"),
                  spacing="2", align="center"),
        _scope_select(),
        rx.vstack(
            text("期刊", kind="caption"),
            _journals_filter_dropdown(),
            spacing="1",
            align="stretch",
            width="100%",
        ),
        _year_group(),
        _author_group(),
        button("应用筛选", variant="primary", icon=SEARCH,
               on_click=LibraryState.search,
               loading=LibraryState.loading),
    )


def _badges_row(item) -> rx.Component:
    return rx.hstack(
        rx.cond(item.pdf_path != None,  # noqa: E711
                badge("已下载 PDF", tone="accent"),
                badge("仅元数据")),
        spacing="2",
        wrap="wrap",
    )


def _row(item) -> rx.Component:
    pdf_link = "/pdf/" + item.id.to_string(use_json=False)
    primary = rx.cond(
        item.pdf_path != None,  # noqa: E711
        rx.link(
            button("打开 PDF", variant="primary"),
            href=pdf_link,
            is_external=True,
        ),
        rx.fragment(),
    )
    return patterns.paper_card(
        title=item.title,
        doi=item.doi,
        journal_date=item.journal_name.to_string(use_json=False) + " · "
                     + item.published_date.to_string(use_json=False),
        authors=item.authors_list.join("; "),
        badges_row=_badges_row(item),
        selected=None,  # 文库页不支持批量选择
        on_open_detail=LibraryState.open_drawer(item.id),
        primary_action=primary,
        secondary_action=rx.hstack(
            rx.link(
                button("DOI", variant="ghost", icon=EXTERNAL_LINK),
                href="https://doi.org/" + item.doi.to_string(use_json=False),
                is_external=True,
            ),
            rx.link(
                button("sci-hub", variant="ghost", icon=EXTERNAL_LINK),
                href="https://sci-hub.ru/" + item.doi.to_string(use_json=False),
                is_external=True,
            ),
            button("删除", variant="danger", icon=TRASH,
                   on_click=LibraryState.request_delete(item.doi)),
            spacing="2",
        ),
    )


def _delete_dialog() -> rx.Component:
    return rx.alert_dialog.root(
        rx.alert_dialog.content(
            rx.alert_dialog.title("确认从本地库删除"),
            rx.alert_dialog.description(
                "将删除 DOI " + LibraryState.pending_delete_doi
                + " 的元数据。如有本地 PDF 也会一并删除。"
            ),
            rx.hstack(
                rx.alert_dialog.cancel(
                    button("取消", variant="secondary",
                           on_click=LibraryState.cancel_delete),
                ),
                rx.alert_dialog.action(
                    button("确认删除", variant="danger",
                           on_click=LibraryState.confirm_delete),
                ),
                spacing="3",
                justify="end",
                width="100%",
            ),
        ),
        open=LibraryState.pending_delete_doi != "",
        on_open_change=LibraryState.cancel_delete,
    )


def _drawer() -> rx.Component:
    return patterns.paper_drawer(
        open=LibraryState.selected_paper_id > 0,
        on_close=LibraryState.close_drawer,
        title=LibraryState.drawer_paper.title,
        body=rx.vstack(
            text(LibraryState.drawer_paper.journal_name.to_string(use_json=False)
                 + " · "
                 + LibraryState.drawer_paper.published_date.to_string(use_json=False),
                 kind="caption"),
            text("DOI: " + LibraryState.drawer_paper.doi.to_string(use_json=False),
                 kind="muted"),
            divider(),
            text(LibraryState.drawer_paper.authors_list.join("; "), kind="caption"),
            divider(),
            rx.scroll_area(
                text(rx.cond(LibraryState.drawer_paper.abstract != "",
                             LibraryState.drawer_paper.abstract,
                             "（无摘要）"), kind="body"),
                type="auto",
                scrollbars="vertical",
                style={"max_height": "20rem"},
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        actions=[
            rx.link(
                button("打开 DOI", variant="secondary", icon=EXTERNAL_LINK),
                href="https://doi.org/" + LibraryState.drawer_paper.doi.to_string(use_json=False),
                is_external=True,
            ),
        ],
    )


def _main_area() -> rx.Component:
    return rx.vstack(
        patterns.section(
            "本地检索",
            rx.hstack(
                rx.input(value=LibraryState.query, placeholder="标题 / 摘要 / 作者…",
                         on_change=LibraryState.set_query, size="3",
                         width="100%"),
                _sort_select(),
                button("查询", variant="primary", icon=SEARCH,
                       on_click=LibraryState.search,
                       loading=LibraryState.loading),
                width="100%",
                spacing="2",
                align="center",
            ),
            right=badge(
                "共 " + LibraryState.total.to_string(use_json=False) + " 条",
                tone="accent",
            ),
        ),
        rx.cond(
            LibraryState.items.length() > 0,
            rx.vstack(
                rx.foreach(LibraryState.items, _row),
                spacing="2",
                width="100%",
                align="stretch",
            ),
            patterns.empty("暂无结果", "调整筛选或查询条件后重试。"),
        ),
        rx.hstack(
            button("上一页", variant="secondary", icon=CHEVRON_LEFT,
                   on_click=LibraryState.prev_page,
                   disabled=LibraryState.page <= 1),
            text("第 " + LibraryState.page.to_string(use_json=False) + " 页",
                 kind="caption"),
            button("下一页", variant="secondary", icon=CHEVRON_RIGHT,
                   on_click=LibraryState.next_page,
                   disabled=LibraryState.items.length() < LibraryState.page_size),
            justify="center",
            spacing="3",
            width="100%",
        ),
        width="100%",
        spacing="3",
        align="stretch",
    )


@rx.page(route="/library", title="OA Library · 文库", on_load=LibraryState.load_page)
def library_page() -> rx.Component:
    body = rx.hstack(
        _sidebar(),
        rx.vstack(
            _main_area(),
            _delete_dialog(),
            width="100%",
            align="stretch",
        ),
        width="100%",
        align="start",
        spacing="3",
    )
    return patterns.page_shell(
        title="本地文库",
        content=body,
        drawer=_drawer(),
        on_refresh=LibraryState.refresh,
    )
