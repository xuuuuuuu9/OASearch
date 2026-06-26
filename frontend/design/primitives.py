"""Thin Radix Themes wrappers with project-level defaults.

These wrappers exist so every page renders cards / buttons / typography
with identical sizes, weights, and tones. Pages MUST import from here
rather than from `rx.*` directly.
"""
from __future__ import annotations

from typing import Any, Literal

import reflex as rx

from frontend.design import icons as _icons
from frontend.design.tokens import CARD_RADIUS, ELEV, GAP

ButtonVariant = Literal["primary", "secondary", "ghost", "danger"]
HeadingLevel = Literal["title", "section", "subsection"]
TextKind = Literal["body", "caption", "muted"]
BadgeTone = Literal["neutral", "accent", "success", "warn", "danger"]


# ---------- card ----------

def card(*children: Any, padding: str = GAP["md"], elev: str = "sm",
         **props: Any) -> rx.Component:
    return rx.box(
        *children,
        padding=padding,
        border_radius=CARD_RADIUS,
        background="var(--color-panel-solid)",
        border="1px solid var(--gray-a4)",
        box_shadow=ELEV[elev],
        **props,
    )


# ---------- button ----------

_BUTTON_VARIANT_TO_RADIX: dict[ButtonVariant, dict[str, Any]] = {
    "primary":   {"variant": "solid",   "color_scheme": "green"},
    "secondary": {"variant": "outline", "color_scheme": "gray"},
    "ghost":     {"variant": "ghost",   "color_scheme": "gray"},
    "danger":    {"variant": "soft",    "color_scheme": "red"},
}


def button(label: str | rx.Var, *, variant: ButtonVariant = "secondary",
           icon: str | None = None,
           loading: bool | rx.Var = False, **props: Any) -> rx.Component:
    radix = _BUTTON_VARIANT_TO_RADIX[variant]
    children: list[Any] = []
    if icon:
        children.append(rx.icon(tag=icon, size=16))
    children.append(label)
    return rx.button(
        *children,
        variant=radix["variant"],
        color_scheme=radix["color_scheme"],
        loading=loading,
        **props,
    )


# ---------- typography ----------

_HEADING_SIZE: dict[HeadingLevel, str] = {
    "title": "6",
    "section": "4",
    "subsection": "3",
}


def heading(text_value: str | rx.Var, *, level: HeadingLevel = "section",
            **props: Any) -> rx.Component:
    return rx.heading(text_value, size=_HEADING_SIZE[level], weight="bold", **props)


def text(value: str | rx.Var, *, kind: TextKind = "body",
         **props: Any) -> rx.Component:
    if kind == "body":
        return rx.text(value, size="3", **props)
    if kind == "caption":
        return rx.text(value, size="2", color="var(--gray-11)", **props)
    # muted
    return rx.text(value, size="2", color="var(--gray-10)", **props)


# ---------- badge ----------

_BADGE_TONE_TO_RADIX: dict[BadgeTone, dict[str, Any]] = {
    "neutral": {"color_scheme": "gray",   "variant": "soft"},
    "accent":  {"color_scheme": "green",  "variant": "soft"},
    "success": {"color_scheme": "grass",  "variant": "soft"},
    "warn":    {"color_scheme": "amber",  "variant": "soft"},
    "danger":  {"color_scheme": "red",    "variant": "soft"},
}


def badge(label: str | rx.Var, *, tone: BadgeTone = "neutral") -> rx.Component:
    radix = _BADGE_TONE_TO_RADIX[tone]
    return rx.badge(label, color_scheme=radix["color_scheme"],
                    variant=radix["variant"], radius="medium")


# ---------- divider ----------

def divider() -> rx.Component:
    return rx.divider(color_scheme="gray")


# Re-export icon module for convenience.
icons = _icons
