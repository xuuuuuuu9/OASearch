"""Search workbench page — composed from design patterns only."""
from __future__ import annotations

import reflex as rx

from frontend.design import patterns
from frontend.design.icons import DOWNLOAD, EXTERNAL_LINK, PLAY, REFRESH
from frontend.design.primitives import badge, button, divider, text
from frontend.state.search_state import SearchState


def _badges_row(paper) -> rx.Component:
    has_pdf = paper.pdf_path != None  # noqa: E711  (Reflex Var comparison)
    auto_dl = paper.auto_downloadable_count > 0
    return rx.hstack(
        rx.cond(
            has_pdf,
            badge("已在本地", tone="accent"),
            rx.cond(auto_dl, badge("可自动下载", tone="success"),
                    badge("仅元数据")),
        ),
        rx.cond(
            paper.saved,
            badge("已入库", tone="accent"),
            badge("未入库"),
        ),
        rx.cond(
            SearchState.selected_dois.contains(paper.doi),
            badge("已加入批量", tone="warn"),
            rx.fragment(),
        ),
        spacing="2",
        wrap="wrap",
    )


def _paper_row(paper) -> rx.Component:
    doi = paper.doi
    return patterns.paper_card(
        title=paper.title,
        doi=doi,
        journal_date=paper.journal_name.to_string(use_json=False) + " · "
                     + paper.published_date.to_string(use_json=False),
        authors=paper.authors_list.join("; "),
        badges_row=_badges_row(paper),
        selected=SearchState.selected_dois.contains(doi),
        on_toggle=SearchState.toggle_doi(doi),
        on_open_detail=SearchState.open_drawer(paper.id),
        primary_action=rx.link(
            button("打开 DOI", variant="ghost", icon=EXTERNAL_LINK),
            href="https://doi.org/" + doi.to_string(use_json=False),
            is_external=True,
        ),
        secondary_action=rx.link(
            button("sci-hub", variant="ghost", icon=EXTERNAL_LINK),
            href="https://sci-hub.ru/" + doi.to_string(use_json=False),
            is_external=True,
        ),
    )


def _journals_dropdown() -> rx.Component:
    label = rx.cond(
        SearchState.selected_issns.length() > 0,
        "期刊：已选 "
        + SearchState.selected_issns.length().to_string(use_json=False)
        + " 本",
        "期刊：未选",
    )
    return patterns.multi_select_dropdown(
        label=label,
        items_var=SearchState.journals,
        render_item=lambda j: rx.checkbox(
            j.name,
            checked=SearchState.selected_issns.contains(j.issn),
            on_change=SearchState.toggle_issn(j.issn),
        ),
        on_select_all=SearchState.select_all_journals,
        on_clear=SearchState.clear_journals,
        width="20rem",
    )


def _search_params_card() -> rx.Component:
    return patterns.section(
        "检索参数",
        rx.input(
            value=SearchState.query,
            placeholder='例如: flavonoid OR "natural product"',
            on_change=SearchState.set_query,
            size="3",
            width="100%",
        ),
        rx.hstack(
            _journals_dropdown(),
            rx.vstack(
                text("起始年份", kind="caption"),
                rx.input(value=SearchState.year_from, placeholder="2010",
                         on_change=SearchState.set_year_from, size="2",
                         type="number", min=1900, max=2100, step=1,
                         width="7rem"),
                spacing="1",
                align="start",
            ),
            rx.vstack(
                text("截止年份", kind="caption"),
                rx.input(value=SearchState.year_to, placeholder="2025",
                         on_change=SearchState.set_year_to, size="2",
                         type="number", min=1900, max=2100, step=1,
                         width="7rem"),
                spacing="1",
                align="start",
            ),
            rx.vstack(
                text("最多条数", kind="caption"),
                rx.input(value=SearchState.rows, placeholder="100",
                         on_change=SearchState.set_rows, size="2",
                         type="number", min=1, max=1000, step=10,
                         width="7rem"),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            button("开始检索", variant="primary", icon=PLAY,
                   on_click=SearchState.run_search,
                   loading=SearchState.loading),
            width="100%",
            spacing="3",
            align="end",
            wrap="wrap",
        ),
        right=button("刷新任务", variant="ghost", icon=REFRESH,
                     on_click=SearchState.refresh),
    )


def _task_progress() -> rx.Component:
    return rx.cond(
        SearchState.active_task.id > 0,
        patterns.section(
            "任务进度",
            patterns.progress_row(
                label="#" + SearchState.active_task.id.to_string(use_json=False)
                      + " · " + SearchState.active_task.q
                      + " · " + SearchState.active_task.status,
                value=SearchState.active_task.total,
                max_value=rx.cond(
                    SearchState.active_task.total > 0,
                    SearchState.active_task.total,
                    1,
                ),
                hint=rx.cond(
                    SearchState.polling,
                    "自动轮询每 2 秒",
                    "已完成",
                ),
            ),
        ),
        rx.fragment(),
    )


def _results() -> rx.Component:
    return rx.cond(
        SearchState.papers.length() > 0,
        patterns.section(
            "检索结果",
            rx.vstack(
                rx.foreach(SearchState.papers, _paper_row),
                spacing="2",
                width="100%",
                align="stretch",
            ),
            right=rx.hstack(
                badge(
                    "已选 " + SearchState.selected_dois.length().to_string(use_json=False)
                    + " 篇",
                    tone="success",
                ),
                button("全选可下载", variant="ghost",
                       on_click=SearchState.select_all_downloadable),
                button("全选", variant="ghost",
                       on_click=SearchState.select_all_results),
                button("清空", variant="ghost",
                       on_click=SearchState.clear_selection),
                spacing="2",
                align="center",
                wrap="wrap",
            ),
        ),
        patterns.empty("暂无结果", "输入关键词并点击「开始检索」。"),
    )


def _drawer() -> rx.Component:
    return patterns.paper_drawer(
        open=SearchState.selected_paper_id > 0,
        on_close=SearchState.close_drawer,
        title=SearchState.drawer_paper.title,
        body=rx.vstack(
            text(SearchState.drawer_paper.journal_name.to_string(use_json=False)
                 + " · "
                 + SearchState.drawer_paper.published_date.to_string(use_json=False),
                 kind="caption"),
            text("DOI: " + SearchState.drawer_paper.doi.to_string(use_json=False),
                 kind="muted"),
            divider(),
            text(SearchState.drawer_paper.authors_list.join("; "), kind="caption"),
            divider(),
            rx.scroll_area(
                text(rx.cond(SearchState.drawer_paper.abstract != "",
                             SearchState.drawer_paper.abstract,
                             "（无摘要）"), kind="body"),
                type="auto",
                scrollbars="vertical",
                style={"max_height": "20rem"},
            ),
            width="100%",
            spacing="2",
            align="start",
        ),
        actions=[
            rx.link(
                button("打开 DOI", variant="secondary", icon=EXTERNAL_LINK),
                href="https://doi.org/" + SearchState.drawer_paper.doi.to_string(use_json=False),
                is_external=True,
            ),
        ],
    )


def _toolbar() -> rx.Component:
    return patterns.floating_toolbar(
        visible=SearchState.selected_dois.length() > 0,
        label="已选 " + SearchState.selected_dois.length().to_string(use_json=False)
              + " 篇",
        actions=[
            button("清除", variant="ghost",
                   on_click=SearchState.clear_selection),
            button("保存元数据", variant="secondary",
                   on_click=SearchState.save_selected_metadata),
            button("保存并下载", variant="primary", icon=DOWNLOAD,
                   on_click=SearchState.start_download),
        ],
    )


@rx.page(route="/", title="OA Library · 检索", on_load=SearchState.load_page)
def search_page() -> rx.Component:
    content = rx.vstack(
        rx.cond(
            SearchState.error_message != "",
            rx.callout(SearchState.error_message,
                       icon="triangle_alert", color_scheme="amber"),
            rx.fragment(),
        ),
        _search_params_card(),
        _task_progress(),
        _results(),
        _toolbar(),
        width="100%",
        spacing="4",
        align="stretch",
    )
    return patterns.page_shell(
        title="检索工作台",
        content=content,
        drawer=_drawer(),
        on_refresh=SearchState.refresh,
    )
