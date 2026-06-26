"""Lint: enforce that frontend/pages/*.py only uses the design system.

Disallows direct color literals, atomic layout props, theme imports,
and background=COLORS[...] in page modules.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PAGES_DIR = Path(__file__).resolve().parent.parent / "frontend" / "pages"


# Pages that have been rewritten on top of frontend.design.*
# Add page filenames here as each stage-3 task completes.
_STAGE3_COMPLETED: set[str] = {"search.py", "library.py", "downloads.py", "journals.py"}


_FORBIDDEN = [
    (re.compile(r"from\s+frontend\.theme"), "import frontend.theme is forbidden"),
    (re.compile(r"from\s+frontend\.components"),
     "import frontend.components is forbidden (legacy shell)"),
    (re.compile(r"#[0-9a-fA-F]{3,8}\b"), "hex color literal is forbidden"),
    (re.compile(r"\brgba?\("), "rgb()/rgba() literal is forbidden"),
    (re.compile(r"\bborder_radius\s*="), "border_radius= literal is forbidden"),
    (re.compile(r"\bmin_height\s*="), "min_height= literal is forbidden"),
    (re.compile(r"\bmax_width\s*="), "max_width= literal is forbidden"),
    (re.compile(r"\bbox_shadow\s*="), "box_shadow= literal is forbidden"),
    (re.compile(r"background\s*=\s*COLORS\["),
     "background=COLORS[...] is forbidden"),
]

# `padding=` is allowed only when the right-hand side references a token.
_PADDING_RE = re.compile(r"padding\s*=\s*([^,)\n]+)")
_PADDING_ALLOWED = re.compile(
    r'^\s*(GAP\[|SHELL_PADDING_|"0"\s*$|0\s*$|f"\{GAP|f"\{SHELL_PADDING_)'
)


def _page_files() -> list[Path]:
    return [p for p in PAGES_DIR.glob("*.py") if p.name != "__init__.py"]


@pytest.mark.parametrize("page", _page_files(), ids=lambda p: p.name)
def test_page_uses_design_only(page: Path) -> None:
    if page.name not in _STAGE3_COMPLETED:
        pytest.xfail(f"{page.name} not yet rewritten")
    src = page.read_text(encoding="utf-8")
    for pattern, message in _FORBIDDEN:
        matches = pattern.findall(src)
        assert not matches, (
            f"{page.name}: {message} — found {matches[:3]!r}"
        )
    for raw in _PADDING_RE.findall(src):
        raw = raw.strip()
        assert _PADDING_ALLOWED.match(raw), (
            f"{page.name}: padding={raw!r} not allowed; use GAP['...']"
            f" or SHELL_PADDING_*"
        )


@pytest.mark.parametrize("page", _page_files(), ids=lambda p: p.name)
def test_page_imports_design(page: Path) -> None:
    if page.name not in _STAGE3_COMPLETED:
        pytest.xfail(f"{page.name} not yet rewritten")
    src = page.read_text(encoding="utf-8")
    assert "from frontend.design" in src, (
        f"{page.name} must import from frontend.design (patterns / primitives)"
    )
