"""Compound UI patterns built from primitives.

Pages should compose patterns only — no direct rx.box(padding=..., border=...).
"""
from __future__ import annotations

from typing import Any

import reflex as rx

from frontend.design import icons
from frontend.design.primitives import (
    badge,
    button,
    card,
    divider,
    heading,
    text,
)
from frontend.design.tokens import (
    DRAWER_WIDTH,
    FILTER_SIDEBAR_WIDTH,
    GAP,
    PAGE_MAX_WIDTH,
    SHELL_PADDING_X,
    SHELL_PADDING_Y,
)

NAV_ITEMS = [
    ("检索", "/", icons.SEARCH),
    ("文库", "/library", icons.BOOK_OPEN),
    ("下载", "/downloads", icons.DOWNLOAD),
    ("期刊", "/journals", icons.LAYERS),
]


def _nav_link(label: str, href: str, icon: str) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.icon(tag=icon, size=16),
            rx.text(label, size="3", weight="medium"),
            spacing="2",
            align="center",
        ),
        href=href,
        underline="none",
        color="var(--gray-12)",
        padding=f"{GAP['xs']} {GAP['sm']}",
        border_radius="6px",
        _hover={"background": "var(--gray-a3)"},
    )


def page_shell(*, title: str | rx.Var, content: rx.Component,
               drawer: rx.Component | None = None, on_refresh: Any = None,
               badges: list[rx.Component] | None = None) -> rx.Component:
    header = rx.hstack(
        rx.hstack(
            rx.box(
                "OA",
                width="2.25rem",
                height="2.25rem",
                display="flex",
                align_items="center",
                justify_content="center",
                border_radius="8px",
                background="var(--green-9)",
                color="white",
                font_weight="800",
            ),
            heading("OA Library", level="title"),
            spacing="3",
            align="center",
        ),
        rx.spacer(),
        rx.hstack(
            *[_nav_link(label, href, icon) for label, href, icon in NAV_ITEMS],
            spacing="1",
        ),
        width="100%",
        align="center",
    )

    title_row_right: list[rx.Component] = []
    if badges:
        title_row_right.extend(badges)
    if on_refresh is not None:
        title_row_right.append(
            button("刷新", variant="ghost", icon=icons.REFRESH, on_click=on_refresh)
        )

    title_row = rx.hstack(
        heading(title, level="title"),
        rx.spacer(),
        rx.hstack(*title_row_right, spacing="2", align="center"),
        width="100%",
        align="center",
    )

    body = rx.vstack(
        header,
        divider(),
        title_row,
        content,
        width="100%",
        max_width=PAGE_MAX_WIDTH,
        margin="0 auto",
        padding=f"{SHELL_PADDING_Y} {SHELL_PADDING_X}",
        spacing="4",
        align="stretch",
    )

    if drawer is None:
        return rx.box(body, width="100%", min_height="100vh",
                      background="var(--gray-1)")
    return rx.box(body, drawer, width="100%", min_height="100vh",
                  background="var(--gray-1)")


def section(title: str | rx.Var, *children: Any,
            right: rx.Component | None = None) -> rx.Component:
    head = rx.hstack(
        heading(title, level="section"),
        rx.spacer(),
        right if right is not None else rx.fragment(),
        width="100%",
        align="center",
    )
    return card(
        rx.vstack(head, *children, spacing="3", width="100%", align="stretch"),
        padding=GAP["md"],
    )


def metric_row(*items: tuple[str, Any]) -> rx.Component:
    cells = [
        card(
            rx.vstack(
                text(label, kind="caption"),
                rx.text(value, size="6", weight="bold"),
                spacing="1",
                align="start",
            ),
            padding=GAP["md"],
        )
        for label, value in items
    ]
    return rx.grid(
        *cells,
        columns="repeat(auto-fit, minmax(11rem, 1fr))",
        spacing="3",
        width="100%",
    )


def paper_card(*, title: Any, doi: Any, journal_date: Any, authors: Any,
               badges_row: rx.Component,
               selected: rx.Var | None = None,
               on_toggle: Any = None,
               on_open_detail: Any,
               primary_action: rx.Component | None = None,
               secondary_action: rx.Component | None = None) -> rx.Component:
    right_actions: list[rx.Component] = []
    if primary_action is not None:
        right_actions.append(primary_action)
    if secondary_action is not None:
        right_actions.append(secondary_action)
    right_actions.append(
        button("详情", variant="ghost", icon=icons.CHEVRON_RIGHT,
               on_click=on_open_detail)
    )

    left: rx.Component
    if selected is None:
        left = rx.fragment()
    else:
        left = rx.checkbox(checked=selected, on_change=on_toggle)

    return card(
        rx.hstack(
            left,
            rx.vstack(
                badges_row,
                heading(title, level="subsection"),
                text(doi, kind="muted"),
                text(journal_date, kind="muted"),
                text(authors, kind="muted"),
                spacing="1",
                align="start",
                width="100%",
            ),
            rx.spacer(),
            rx.vstack(*right_actions, spacing="2", align="end"),
            width="100%",
            align="start",
            spacing="3",
        ),
        padding=GAP["md"],
    )


def paper_drawer(*, open: rx.Var, on_close: Any, title: Any,
                 body: rx.Component, actions: list[rx.Component]) -> rx.Component:
    return rx.drawer.root(
        rx.drawer.overlay(z_index="5"),
        rx.drawer.portal(
            rx.drawer.content(
                rx.vstack(
                    rx.hstack(
                        heading(title, level="section"),
                        rx.spacer(),
                        button("", variant="ghost", icon=icons.X,
                               on_click=on_close),
                        width="100%",
                        align="center",
                    ),
                    divider(),
                    body,
                    divider(),
                    rx.hstack(*actions, spacing="2", width="100%", justify="end"),
                    width="100%",
                    height="100%",
                    padding=GAP["md"],
                    spacing="3",
                    align="stretch",
                ),
                top="0",
                right="0",
                height="100%",
                width=DRAWER_WIDTH,
                background="var(--color-panel-solid)",
                border_left="1px solid var(--gray-a4)",
            )
        ),
        open=open,
        on_open_change=on_close,
        direction="right",
    )


def floating_toolbar(*, visible: rx.Var, label: Any,
                     actions: list[rx.Component]) -> rx.Component:
    return rx.cond(
        visible,
        rx.box(
            rx.hstack(
                text(label, kind="body"),
                *actions,
                spacing="3",
                align="center",
            ),
            position="fixed",
            bottom="1.25rem",
            left="50%",
            transform="translateX(-50%)",
            background="var(--gray-12)",
            color="white",
            padding=f"{GAP['sm']} {GAP['md']}",
            border_radius="999px",
            box_shadow="0 8px 24px rgba(0,0,0,.2)",
            z_index="10",
        ),
        rx.fragment(),
    )


def filter_sidebar(*groups: rx.Component) -> rx.Component:
    return card(
        rx.vstack(*groups, spacing="4", align="stretch", width="100%"),
        padding=GAP["md"],
        width=FILTER_SIDEBAR_WIDTH,
        min_width=FILTER_SIDEBAR_WIDTH,
    )


def empty(title: str, hint: str = "",
          action: rx.Component | None = None) -> rx.Component:
    children: list[Any] = [text(title, kind="muted")]
    if hint:
        children.append(text(hint, kind="caption"))
    if action is not None:
        children.append(action)
    return rx.box(
        rx.vstack(*children, spacing="2", align="center"),
        padding=GAP["lg"],
        border="1px dashed var(--gray-a6)",
        border_radius="8px",
        background="var(--gray-a2)",
        width="100%",
    )


def progress_row(*, label: Any, value: Any, max_value: Any,
                 hint: Any = "") -> rx.Component:
    return rx.vstack(
        rx.hstack(
            text(label, kind="body"),
            rx.spacer(),
            text(hint, kind="caption"),
            width="100%",
            align="center",
        ),
        rx.progress(value=value, max=max_value, color_scheme="green"),
        width="100%",
        spacing="1",
    )


def multi_select_dropdown(*, label: Any, items_var: rx.Var,
                          render_item: Any,
                          on_select_all: Any = None,
                          on_clear: Any = None,
                          width: str = "16rem") -> rx.Component:
    """A popover trigger that opens a checkbox list (multi-select).

    `items_var` is a Reflex Var iterable; `render_item` is a callable that
    receives one var element and returns a rx.checkbox.
    """
    helper_row: list[rx.Component] = []
    if on_select_all is not None:
        helper_row.append(button("全选", variant="ghost", on_click=on_select_all))
    if on_clear is not None:
        helper_row.append(button("清空", variant="ghost", on_click=on_clear))

    return rx.popover.root(
        rx.popover.trigger(
            rx.button(
                rx.hstack(
                    label,
                    rx.icon(tag=icons.CHEVRON_DOWN, size=14),
                    spacing="2",
                    align="center",
                ),
                variant="outline",
                color_scheme="gray",
            ),
        ),
        rx.popover.content(
            rx.vstack(
                rx.cond(
                    len(helper_row) > 0,
                    rx.hstack(*helper_row, spacing="2", width="100%"),
                    rx.fragment(),
                ),
                rx.scroll_area(
                    rx.vstack(
                        rx.foreach(items_var, render_item),
                        spacing="2",
                        align="start",
                        width="100%",
                    ),
                    type="auto",
                    scrollbars="vertical",
                    style={"max_height": "20rem"},
                ),
                spacing="2",
                width=width,
                align="stretch",
            ),
        ),
    )
