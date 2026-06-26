"""Project-level design tokens.

Colors come from Radix Themes (`accent_color="green"` in rxconfig.py);
do NOT define color values here. Only put things Radix does not give us.
"""
from __future__ import annotations

PAGE_MAX_WIDTH = "88rem"
SHELL_PADDING_X = "1.5rem"
SHELL_PADDING_Y = "1.25rem"

CARD_RADIUS = "8px"

GAP = {
    "xs": "0.5rem",
    "sm": "0.75rem",
    "md": "1rem",
    "lg": "1.5rem",
    "xl": "2rem",
}

ELEV = {
    "none": "none",
    "sm": "0 1px 2px rgba(15,23,34,.04), 0 1px 3px rgba(15,23,34,.06)",
    "md": "0 4px 12px rgba(15,23,34,.08)",
}

DRAWER_WIDTH = "24rem"
FILTER_SIDEBAR_WIDTH = "16rem"


GLOBAL_STYLES: dict[str, dict[str, str]] = {
    "html": {
        "background": "var(--gray-1)",
        "overscroll_behavior": "none",
    },
    "body": {
        "background": "var(--gray-1)",
        "color": "var(--gray-12)",
        "font_family": "'Inter', 'Segoe UI', sans-serif",
        "font_size": "16px",
        "line_height": "1.5",
        "letter_spacing": "0",
        "overscroll_behavior": "none",
    },
}
