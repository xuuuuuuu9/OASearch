# Reflex 前端重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写 NP OA Library 的 Reflex 前端 UI，建立 design system 强约束，修复"滚动闪烁"与端口残留两个稳定性问题，并新增论文详情抽屉、任务自动轮询、文库高级筛选/排序、浮动批量操作栏四项交互。

**Architecture:** 四阶段串行执行：(1) 稳定性先修 — 启动脚本统一端口管理 + State 加 `_loaded` 哨兵；(2) Design System — 新建 `frontend/design/` 提供 tokens / primitives / patterns，并加 lint 测试强制页面只用 patterns；(3) 逐页重写 — `search → library → downloads → journals` 顺序，每页一次性带入新功能；(4) 收尾 — 删旧目录，补测试，更新 README 与 .gitignore。

**Tech Stack:** Python 3.11+ / Reflex ≥0.9.5 / Radix Themes (`accent_color="green"`) / FastAPI / SQLite + FTS5 / `psutil`（新增）/ pytest。

## Global Constraints

- **颜色完全交给 Radix `accent_color="green"`**：页面文件禁止字面量颜色（`#xxx` / `rgb(...)`），禁止 `import frontend.theme`。
- **圆角统一 8px**：全靠 `rxconfig.py` 的 `radius="small"`；页面文件禁止 `border_radius=` 字面量。
- **间距用 `frontend.design.tokens.GAP`**：页面文件禁止 `min_height=` / `max_width=` / `padding=` 字面量（除 `0` 或对 `GAP[...]`/`SHELL_PADDING_*` 的引用外）。
- **按钮通过 `frontend.design.primitives.button(variant=...)`**：禁止 `background=COLORS[...]` 硬覆盖。
- **页面文件必须 `from frontend.design import patterns` 或 `primitives`**。
- **lint 范围**：约束仅扫 `frontend/pages/*.py`，不扫 `frontend/design/*.py`（patterns 内部允许原子 props）。
- **不引入新依赖**：只新增 `psutil>=5.9`，其余依赖版本不变。
- **不破坏现有后端 API 契约**：仅在 stage 3 中**追加**可选查询参数到 `/api/library/search`，不修改/删除现有字段。

---

## 阶段 1：稳定性先修

## Task 1: 端口检测工具 `scripts/_portutil.py`

**Files:**
- Create: `scripts/__init__.py`（空）
- Create: `scripts/_portutil.py`
- Create: `tests/test_portutil.py`
- Modify: `requirements.txt`（加 `psutil>=5.9`）

**Interfaces:**
- Produces:
  - `find_listening_pid(port: int) -> int | None`
  - `is_our_process(pid: int, project_root: pathlib.Path) -> bool`
  - `kill_process_tree(pid: int, timeout: float = 5.0) -> bool`
  - `clean_reflex_lock(project_root: pathlib.Path) -> None`

- [ ] **Step 1: 加 psutil 依赖**

修改 `requirements.txt` 末尾加一行：
```
psutil>=5.9
```

然后：
```bash
cd c:/Users/AH/Desktop/search
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

- [ ] **Step 2: 写测试 `tests/test_portutil.py`**

```python
"""Unit tests for scripts/_portutil.py — mock psutil, no real processes."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import _portutil as pu


def test_find_listening_pid_returns_pid_when_listening():
    fake_conn = MagicMock()
    fake_conn.status = "LISTEN"
    fake_conn.laddr.port = 8000
    fake_conn.pid = 12345
    with patch.object(pu.psutil, "net_connections", return_value=[fake_conn]):
        assert pu.find_listening_pid(8000) == 12345


def test_find_listening_pid_returns_none_when_no_match():
    with patch.object(pu.psutil, "net_connections", return_value=[]):
        assert pu.find_listening_pid(8000) is None


def test_is_our_process_true_when_cwd_in_project_and_cmdline_matches(tmp_path):
    fake_proc = MagicMock()
    fake_proc.cwd.return_value = str(tmp_path / "subdir")
    fake_proc.cmdline.return_value = ["python", "-m", "reflex", "run"]
    (tmp_path / "subdir").mkdir()
    with patch.object(pu.psutil, "Process", return_value=fake_proc):
        assert pu.is_our_process(99, tmp_path) is True


def test_is_our_process_false_when_unrelated_cmdline(tmp_path):
    fake_proc = MagicMock()
    fake_proc.cwd.return_value = str(tmp_path)
    fake_proc.cmdline.return_value = ["chrome.exe"]
    with patch.object(pu.psutil, "Process", return_value=fake_proc):
        assert pu.is_our_process(99, tmp_path) is False


def test_is_our_process_false_when_cwd_outside_project(tmp_path):
    fake_proc = MagicMock()
    fake_proc.cwd.return_value = "/other/path"
    fake_proc.cmdline.return_value = ["reflex", "run"]
    with patch.object(pu.psutil, "Process", return_value=fake_proc):
        assert pu.is_our_process(99, tmp_path) is False


def test_is_our_process_false_when_process_gone():
    with patch.object(pu.psutil, "Process", side_effect=pu.psutil.NoSuchProcess(99)):
        assert pu.is_our_process(99, Path(".")) is False


def test_clean_reflex_lock_removes_existing(tmp_path):
    lock = tmp_path / "reflex.lock"
    lock.mkdir()
    (lock / "stale.txt").write_text("x")
    pu.clean_reflex_lock(tmp_path)
    assert not lock.exists()


def test_clean_reflex_lock_noop_if_missing(tmp_path):
    pu.clean_reflex_lock(tmp_path)  # 不抛
```

- [ ] **Step 3: 运行测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_portutil.py -v
```
预期：`ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 4: 写实现**

`scripts/__init__.py`：空文件。

`scripts/_portutil.py`：

```python
"""Cross-platform port / process utilities used by scripts/start.py."""
from __future__ import annotations

import shutil
from pathlib import Path

import psutil

# 命中以下任一关键词且 cwd 在项目根目录下 → 视为本项目残留进程
_OUR_CMDLINE_TOKENS = ("reflex", "uvicorn", "frontend.app", "app.main")


def find_listening_pid(port: int) -> int | None:
    """Return PID of the process LISTENing on `port`, or None."""
    for conn in psutil.net_connections(kind="inet"):
        if conn.status == "LISTEN" and conn.laddr and conn.laddr.port == port:
            return conn.pid
    return None


def is_our_process(pid: int, project_root: Path) -> bool:
    """True if `pid` looks like one of our reflex/uvicorn workers in this project."""
    try:
        proc = psutil.Process(pid)
        cwd = Path(proc.cwd())
        cmdline = " ".join(proc.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False
    project_root = project_root.resolve()
    try:
        cwd.resolve().relative_to(project_root)
    except (ValueError, OSError):
        return False
    return any(token in cmdline for token in _OUR_CMDLINE_TOKENS)


def kill_process_tree(pid: int, timeout: float = 5.0) -> bool:
    """SIGTERM the process and all its children. Return True on clean exit."""
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return True
    procs: list[psutil.Process] = [parent] + parent.children(recursive=True)
    for p in procs:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass
    gone, alive = psutil.wait_procs(procs, timeout=timeout)
    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=2.0)
    return not psutil.pid_exists(pid)


def clean_reflex_lock(project_root: Path) -> None:
    """Remove stale reflex.lock/ directory left by a crashed run."""
    lock = project_root / "reflex.lock"
    if lock.exists():
        shutil.rmtree(lock, ignore_errors=True)
```

- [ ] **Step 5: 运行测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_portutil.py -v
```
预期：8 passed。

- [ ] **Step 6: Commit**

```bash
git add scripts/__init__.py scripts/_portutil.py tests/test_portutil.py requirements.txt
git commit -m "feat(scripts): add cross-platform port detection utilities"
```

---

## Task 2: 启动脚本 `scripts/start.py`

**Files:**
- Create: `scripts/start.py`
- Create: `tests/test_start_script.py`

**Interfaces:**
- Consumes: `scripts._portutil.{find_listening_pid, is_our_process, kill_process_tree, clean_reflex_lock}`
- Produces: CLI entry `python scripts/start.py`

- [ ] **Step 1: 写测试 `tests/test_start_script.py`**

```python
"""Unit tests for scripts/start.py — mock subprocess / portutil."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts import start


@pytest.fixture
def mock_portutil():
    with patch.object(start, "portutil") as pu:
        pu.find_listening_pid.return_value = None
        pu.is_our_process.return_value = False
        pu.kill_process_tree.return_value = True
        yield pu


def test_resolve_ports_uses_env(monkeypatch):
    monkeypatch.setenv("NP_OA_BACKEND_PORT", "9000")
    monkeypatch.setenv("NP_OA_FRONTEND_PORT", "4000")
    assert start._resolve_ports() == (9000, 4000)


def test_resolve_ports_defaults(monkeypatch):
    monkeypatch.delenv("NP_OA_BACKEND_PORT", raising=False)
    monkeypatch.delenv("NP_OA_FRONTEND_PORT", raising=False)
    assert start._resolve_ports() == (8000, 3000)


def test_ensure_port_free_noop_when_unused(mock_portutil, tmp_path):
    mock_portutil.find_listening_pid.return_value = None
    start._ensure_port_free(8000, tmp_path)
    mock_portutil.kill_process_tree.assert_not_called()


def test_ensure_port_free_kills_our_process(mock_portutil, tmp_path, capsys):
    mock_portutil.find_listening_pid.return_value = 12345
    mock_portutil.is_our_process.return_value = True
    start._ensure_port_free(8000, tmp_path)
    mock_portutil.kill_process_tree.assert_called_once_with(12345)
    out = capsys.readouterr().out
    assert "killing stale" in out
    assert "8000" in out


def test_ensure_port_free_aborts_on_foreign_process(mock_portutil, tmp_path):
    mock_portutil.find_listening_pid.return_value = 99999
    mock_portutil.is_our_process.return_value = False
    with pytest.raises(SystemExit) as exc:
        start._ensure_port_free(8000, tmp_path)
    assert exc.value.code == 1
    mock_portutil.kill_process_tree.assert_not_called()
```

- [ ] **Step 2: 运行测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_start_script.py -v
```
预期：`ImportError: cannot import name 'start' from 'scripts'`

- [ ] **Step 3: 写实现 `scripts/start.py`**

```python
"""Single-command launcher for NP OA Library.

Usage:
    uv run python scripts/start.py

Reads ports from NP_OA_BACKEND_PORT / NP_OA_FRONTEND_PORT (defaults 8000 / 3000),
detects & kills stale reflex/uvicorn processes holding them, clears reflex.lock,
then execs `reflex run`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from scripts import _portutil as portutil

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_ports() -> tuple[int, int]:
    return (
        int(os.environ.get("NP_OA_BACKEND_PORT", "8000")),
        int(os.environ.get("NP_OA_FRONTEND_PORT", "3000")),
    )


def _ensure_port_free(port: int, project_root: Path) -> None:
    pid = portutil.find_listening_pid(port)
    if pid is None:
        return
    if portutil.is_our_process(pid, project_root):
        print(f"[start] killing stale reflex/uvicorn on :{port} (PID {pid})")
        portutil.kill_process_tree(pid)
        return
    print(
        f"[start] ERROR: port :{port} is held by PID {pid} which does not look "
        f"like a reflex/uvicorn process in {project_root}. Refusing to kill.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    backend_port, frontend_port = _resolve_ports()
    portutil.clean_reflex_lock(PROJECT_ROOT)
    _ensure_port_free(backend_port, PROJECT_ROOT)
    _ensure_port_free(frontend_port, PROJECT_ROOT)

    os.environ["NP_OA_API_URL"] = f"http://127.0.0.1:{backend_port}"
    print(
        f"[start] launching reflex run "
        f"(backend :{backend_port}, frontend :{frontend_port})"
    )
    os.execvp(
        "reflex",
        [
            "reflex",
            "run",
            "--backend-port",
            str(backend_port),
            "--frontend-port",
            str(frontend_port),
        ],
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_start_script.py -v
```
预期：5 passed。

- [ ] **Step 5: Commit**

```bash
git add scripts/start.py tests/test_start_script.py
git commit -m "feat(scripts): add start.py launcher with port auto-cleanup"
```

---

## Task 3: State `_loaded` 哨兵与 `refresh()` 事件

**Files:**
- Modify: `frontend/state/search_state.py`
- Modify: `frontend/state/library_state.py`
- Modify: `frontend/state/downloads_state.py`
- Modify: `frontend/state/journals_state.py`
- Create: `tests/test_state_idempotent.py`

**Interfaces:**
- Produces: 每个 State 多两项
  - `_loaded: bool = False`
  - `async def refresh(self) -> None`  — 显式触发 fetch 的事件
  - `load_page` 改为幂等：`if self._loaded: return` 后才 fetch，结束置 `self._loaded = True`

- [ ] **Step 1: 确认 pytest-asyncio 配置**

```bash
cat c:/Users/AH/Desktop/search/pytest.ini
```

若没有 `asyncio_mode = auto`，把整个文件改为：
```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 2: 写测试 `tests/test_state_idempotent.py`**

```python
"""Calling load_page() twice must not re-fetch (sentinel works)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from frontend.state.search_state import SearchState
from frontend.state.library_state import LibraryState
from frontend.state.downloads_state import DownloadsState
from frontend.state.journals_state import JournalsState


async def test_search_load_page_idempotent():
    state = SearchState()
    with patch("frontend.state.search_state.api.get_json",
               new=AsyncMock(return_value=[])) as mock_get:
        await state.load_page()
        first_run_calls = mock_get.call_count
        await state.load_page()
    assert state._loaded is True
    assert mock_get.call_count == first_run_calls


async def test_search_refresh_always_fetches():
    state = SearchState()
    state._loaded = True
    with patch("frontend.state.search_state.api.get_json",
               new=AsyncMock(return_value=[])) as mock_get:
        await state.refresh()
    assert mock_get.call_count >= 1


async def test_library_load_page_idempotent():
    state = LibraryState()
    with patch("frontend.state.library_state.api.get_json",
               new=AsyncMock(return_value={"items": [], "total": 0})) as mock_get:
        await state.load_page()
        first = mock_get.call_count
        await state.load_page()
    assert state._loaded is True
    assert mock_get.call_count == first


async def test_downloads_load_page_idempotent():
    state = DownloadsState()
    with patch("frontend.state.downloads_state.api.get_json",
               new=AsyncMock(return_value=[])) as mock_get:
        await state.load_page()
        first = mock_get.call_count
        await state.load_page()
    assert state._loaded is True
    assert mock_get.call_count == first


async def test_journals_load_page_idempotent():
    state = JournalsState()
    with patch("frontend.state.journals_state.api.get_json",
               new=AsyncMock(return_value=[])) as mock_get:
        await state.load_page()
        first = mock_get.call_count
        await state.load_page()
    assert state._loaded is True
    assert mock_get.call_count == first
```

- [ ] **Step 3: 运行测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_state_idempotent.py -v
```
预期：AttributeError: `_loaded` 不存在 / `refresh` 不存在。

- [ ] **Step 4: 改 `frontend/state/search_state.py`**

在 `class SearchState(rx.State):` 字段块末尾（`error_message: str = ""` 之后）加：
```python
    _loaded: bool = False
```

把现有 `async def load_page(self) -> None:` 整段替换为：
```python
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
            journal_rows = await api.get_json(
                "/api/journals", params={"enabled_only": True}
            )
            self.journals = [journal_from_dict(item) for item in journal_rows]
            if not self.selected_issns:
                self.selected_issns = [item.issn for item in self.journals]
            latest = await api.get_json("/api/search-tasks/latest")
            self.active_task = search_task_from_dict(latest)
            if latest.get("status") == "done":
                papers = await api.get_json(
                    f"/api/search-tasks/{latest['id']}/papers"
                )
                self.papers = [paper_from_dict(item) for item in papers]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                self.error_message = f"加载失败: {exc.response.status_code}"
        except httpx.HTTPError:
            self.error_message = "无法连接后端 API"
        finally:
            self.loading = False
```

（关键差异：`selected_issns` 只在首次空时初始化，避免每次 refresh 都覆盖用户取消的选择。）

- [ ] **Step 5: 改 `frontend/state/library_state.py`**

加 `_loaded: bool = False` 到字段块末尾。

替换 `load_page` 为：
```python
    async def load_page(self) -> None:
        if self._loaded:
            return
        await self.search()
        self._loaded = True

    async def refresh(self) -> None:
        await self.search()
```

- [ ] **Step 6: 改 `frontend/state/downloads_state.py`**

加 `_loaded: bool = False`。

替换 `load_page` 现有体为：
```python
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
```

- [ ] **Step 7: 改 `frontend/state/journals_state.py`**

加 `_loaded: bool = False`。

把现有 `async def load_page(self) -> None:` 整体改名为 `_do_load`，然后加：
```python
    async def load_page(self) -> None:
        if self._loaded:
            return
        await self._do_load()
        self._loaded = True

    async def refresh(self) -> None:
        await self._do_load()
```

并把 `add_journal` / `toggle_enabled` / `delete_journal` 里调用的 `await self.load_page()` 改为 `await self._do_load()`（这些是数据变更后的强制刷新，不应被哨兵拦截）。

- [ ] **Step 8: 运行测试看通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_state_idempotent.py -v
```
预期：5 passed。

- [ ] **Step 9: Commit**

```bash
git add frontend/state/ tests/test_state_idempotent.py pytest.ini
git commit -m "fix(state): add _loaded sentinel to make load_page idempotent

prevents websocket reconnect from re-running on_load and wiping
list state mid-scroll. adds explicit refresh() event."
```

---

## Task 4: 全局 CSS `overscroll-behavior` + README 启动指令

**Files:**
- Modify: `frontend/theme.py`（GLOBAL_STYLES 增加 overscroll-behavior）
- Modify: `README.md`

- [ ] **Step 1: 改 `frontend/theme.py` 的 `GLOBAL_STYLES`**

替换 `GLOBAL_STYLES` 字典为：
```python
GLOBAL_STYLES = {
    "html": {
        "background": COLORS["bg"],
        "overscroll_behavior": "none",
    },
    "body": {
        "background": COLORS["bg"],
        "color": COLORS["ink"],
        "font_family": "'Inter', 'Segoe UI', sans-serif",
        "font_size": "16px",
        "line_height": "1.5",
        "letter_spacing": "0",
        "overscroll_behavior": "none",
    },
}
```

（Reflex 会把 Python 键 `overscroll_behavior` 自动转换为 CSS `overscroll-behavior`。）

- [ ] **Step 2: 改 README.md 启动节**

在 `README.md` 找到 `## 启动` 那一节（约第 76 行起），把整段（包括 `### 前后端地址统一环境变量` 子节、"如果遇到前端包下载失败" 子节）替换为：

````markdown
## 启动

```bash
uv run python scripts/start.py
```

会自动：
- 清理上次崩溃残留的 `reflex.lock/`
- 检测 `:8000`（后端）和 `:3000`（前端）端口
  - 如果被旧的 reflex / uvicorn 进程占用，自动结束它
  - 如果被无关进程占用，会报错让你决定，不会乱杀
- 启动 Reflex 应用

默认地址：
- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:8000/api/...`

想换端口：

```bash
NP_OA_BACKEND_PORT=8765 NP_OA_FRONTEND_PORT=3765 uv run python scripts/start.py
```

Windows PowerShell：
```powershell
$env:NP_OA_BACKEND_PORT="8765"; $env:NP_OA_FRONTEND_PORT="3765"; uv run python scripts/start.py
```

想停止：在终端按 `Ctrl+C`。下次启动如果有残留进程，`scripts/start.py` 会自动清理。

> 如果第一次启动时 Reflex 需要初始化前端依赖，稍等它自动安装即可（已预设 npmmirror）。
````

- [ ] **Step 3: 跑全量测试确保未破坏**

```bash
cd c:/Users/AH/Desktop/search
.venv/Scripts/python.exe -m pytest tests/ -x
```
预期：所有现有测试 + 新加的全部通过。

- [ ] **Step 4: Commit**

```bash
git add frontend/theme.py README.md
git commit -m "fix(ui): add overscroll-behavior: none to prevent native pull-refresh"
```

---

**阶段 1 完成检查点**：项目仍能 `uv run python scripts/start.py` 启动，UI 视觉与之前一致，但：(a) 端口冲突自动处理；(b) 浏览器原生下拉刷新失效；(c) 切页回来 state 保留。

---

## 阶段 2：Design System

## Task 5: Tokens + Icons

**Files:**
- Create: `frontend/design/__init__.py`
- Create: `frontend/design/tokens.py`
- Create: `frontend/design/icons.py`

**Interfaces:**
- Produces (`tokens.py`):
  - `PAGE_MAX_WIDTH: str = "88rem"`
  - `SHELL_PADDING_X: str`、`SHELL_PADDING_Y: str`
  - `CARD_RADIUS: str = "8px"`（不在页面直接用，由 patterns 引用）
  - `GAP: dict[str, str]`，keys: `xs sm md lg xl`
  - `ELEV: dict[str, str]`，keys: `none sm md`
  - `DRAWER_WIDTH: str = "24rem"`
  - `FILTER_SIDEBAR_WIDTH: str = "16rem"`
- Produces (`icons.py`): 字符串常量

- [ ] **Step 1: 新建 `frontend/design/__init__.py`**

```python
"""Project-level design system for the Reflex workbench.

Pages MUST import from `patterns` or `primitives`. Direct atomic-prop usage
(border_radius, min_height, max_width, padding literals, color literals,
background=COLORS[...]) is blocked by `tests/test_ui_consistency.py`.
"""
```

- [ ] **Step 2: 新建 `frontend/design/tokens.py`**

```python
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
```

- [ ] **Step 3: 新建 `frontend/design/icons.py`**

```python
"""Centralized icon name constants — typo-safe references to lucide icons.

Reflex passes the string straight to lucide-react. Adding a name here lets
callers do `icons.SEARCH` instead of `"search"` and surfaces typos at import.
"""
from __future__ import annotations

SEARCH = "search"
REFRESH = "refresh-cw"
DOWNLOAD = "download"
TRASH = "trash-2"
EXTERNAL_LINK = "external-link"
CHECK = "check"
X = "x"
CHEVRON_DOWN = "chevron-down"
CHEVRON_LEFT = "chevron-left"
CHEVRON_RIGHT = "chevron-right"
ARROW_UP_DOWN = "arrow-up-down"
INFO = "info"
ALERT = "triangle-alert"
COPY = "copy"
FILTER = "list-filter"
BOOK_OPEN = "book-open"
LAYERS = "layers"
PLAY = "play"
```

- [ ] **Step 4: 烟雾测试**

```bash
.venv/Scripts/python.exe -c "from frontend.design import tokens, icons; print(tokens.PAGE_MAX_WIDTH, icons.SEARCH)"
```
预期：`88rem search`

- [ ] **Step 5: Commit**

```bash
git add frontend/design/__init__.py frontend/design/tokens.py frontend/design/icons.py
git commit -m "feat(design): add project-level tokens and icon constants"
```

---

## Task 6: Primitives — Radix 薄包装

**Files:**
- Create: `frontend/design/primitives.py`

**Interfaces:**
- Consumes: `frontend/design/tokens.py`
- Produces:
  - `card(*children, padding=GAP["md"], elev="sm", **props) -> rx.Component`
  - `button(label, *, variant: Literal["primary","secondary","ghost","danger"]="secondary", icon: str | None = None, loading: bool | rx.Var = False, **props) -> rx.Component`
  - `heading(text, *, level: Literal["title","section","subsection"]="section", **props) -> rx.Component`
  - `text(value, *, kind: Literal["body","caption","muted"]="body", **props) -> rx.Component`
  - `badge(label, *, tone: Literal["neutral","accent","success","warn","danger"]="neutral") -> rx.Component`
  - `divider() -> rx.Component`

- [ ] **Step 1: 新建 `frontend/design/primitives.py`**

```python
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


# Re-export icon module for convenience: from frontend.design.primitives import icons
icons = _icons
```

- [ ] **Step 2: 烟雾测试**

```bash
.venv/Scripts/python.exe -c "
from frontend.design import primitives as p
b = p.button('Hi', variant='primary')
c = p.card(p.text('x', kind='caption'))
print(type(b).__name__, type(c).__name__)
"
```
预期：`Button Box`（或具体 Reflex 组件类名）。

- [ ] **Step 3: Commit**

```bash
git add frontend/design/primitives.py
git commit -m "feat(design): add Radix-themed primitives (card, button, text, badge)"
```

---

## Task 7: Patterns — 复合模式

**Files:**
- Create: `frontend/design/patterns.py`

**Interfaces:**
- Consumes: `frontend.design.{tokens, primitives, icons}`
- Produces：
  - `page_shell(*, title: str | rx.Var, content: rx.Component, drawer: rx.Component | None = None, on_refresh = None, badges: list[rx.Component] | None = None) -> rx.Component`
  - `section(title: str, *children, right: rx.Component | None = None) -> rx.Component`
  - `metric_row(*items: tuple[str, Any]) -> rx.Component`
  - `paper_card(*, title, doi, journal_date, authors, badges_row, selected, on_toggle, on_open_detail, primary_action: rx.Component | None = None, secondary_action: rx.Component | None = None) -> rx.Component`
  - `paper_drawer(*, open: rx.Var[bool], on_close, title, body: rx.Component, actions: list[rx.Component]) -> rx.Component`
  - `floating_toolbar(*, visible: rx.Var[bool], label: rx.Var[str] | str, actions: list[rx.Component]) -> rx.Component`
  - `filter_sidebar(*groups: rx.Component) -> rx.Component`
  - `empty(title: str, hint: str = "", action: rx.Component | None = None) -> rx.Component`
  - `progress_row(*, label: rx.Var[str] | str, value: rx.Var[int] | int, max_value: rx.Var[int] | int, hint: rx.Var[str] | str = "") -> rx.Component`

- [ ] **Step 1: 新建 `frontend/design/patterns.py`**

```python
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
```

- [ ] **Step 2: 烟雾测试**

```bash
.venv/Scripts/python.exe -c "
from frontend.design import patterns
shell = patterns.page_shell(title='x', content=patterns.empty('y'))
sec = patterns.section('s')
print(type(shell).__name__, type(sec).__name__)
"
```
预期：组件类名打印，无异常。

- [ ] **Step 3: Commit**

```bash
git add frontend/design/patterns.py
git commit -m "feat(design): add compound UI patterns (shell, paper_card, drawer, toolbar)"
```

---

## Task 8: UI 一致性 lint 测试

**Files:**
- Create: `tests/test_ui_consistency.py`

**Interfaces:**
- 无新接口；该测试只读 `frontend/pages/*.py` 源码

- [ ] **Step 1: 写测试**

```python
"""Lint: enforce that frontend/pages/*.py only uses the design system.

Disallows direct color literals, atomic layout props, theme imports,
and background=COLORS[...] in page modules.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PAGES_DIR = Path(__file__).resolve().parent.parent / "frontend" / "pages"

# Compiled once, applied per-page.
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

# `padding=` is allowed only when value is `GAP[`, `SHELL_PADDING_`, or `0`.
_PADDING_RE = re.compile(r"padding\s*=\s*([^,)]+)")
_PADDING_ALLOWED = re.compile(r"^(GAP\[|SHELL_PADDING_|0\s*$|\"0\"\s*$)")


def _page_files() -> list[Path]:
    return [p for p in PAGES_DIR.glob("*.py") if p.name != "__init__.py"]


@pytest.mark.parametrize("page", _page_files(), ids=lambda p: p.name)
def test_page_uses_design_only(page: Path) -> None:
    src = page.read_text(encoding="utf-8")
    # whole-source scan
    for pattern, message in _FORBIDDEN:
        matches = pattern.findall(src)
        assert not matches, f"{page.name}: {message} — found {matches[:3]!r}"

    # padding= must reference token
    for raw in _PADDING_RE.findall(src):
        raw = raw.strip()
        assert _PADDING_ALLOWED.match(raw), (
            f"{page.name}: padding={raw!r} not allowed; use GAP['...']"
        )


@pytest.mark.parametrize("page", _page_files(), ids=lambda p: p.name)
def test_page_imports_design(page: Path) -> None:
    src = page.read_text(encoding="utf-8")
    assert "from frontend.design" in src, (
        f"{page.name} must import from frontend.design (patterns / primitives)"
    )
```

- [ ] **Step 2: 运行测试看失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ui_consistency.py -v
```

预期：每个现有页面都失败（因为它们还在用 `from frontend.theme` / `border_radius` / `#xxx` 等）。这正是 stage 3 要修复的清单。

> **重要**：这个测试在 stage 2 末暂时**期望失败**。stage 3 中每个页面重写完毕后会陆续转绿。

把这一组测试用 `@pytest.mark.xfail(strict=False, reason="enforced after stage 3 page rewrites")` 临时 mark，确保 CI 不被中断。在 stage 3 每页完成后会把对应的 `xfail` 解掉。

修改测试文件，给两个 test 函数加 decorator：
```python
@pytest.mark.xfail(strict=False, reason="enforced after stage 3 page rewrites")
@pytest.mark.parametrize(...)
def test_page_uses_design_only(...): ...
```

- [ ] **Step 3: 运行确认 xfail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ui_consistency.py -v
```
预期：所有 `xfail`。

- [ ] **Step 4: Commit**

```bash
git add tests/test_ui_consistency.py
git commit -m "test(design): add UI consistency lint, xfail until stage 3 completes"
```

---

**阶段 2 完成检查点**：`frontend/design/` 已可用；lint 测试存在并 xfail；任何页面都没动过；现有 UI 视觉与 stage 1 末尾完全一致。

---

## 阶段 3：逐页重写 + 新功能

## Task 9: 模型层加 `abstract` / `keywords`

**Files:**
- Modify: `frontend/models.py`

**Interfaces:**
- Produces:
  - `PaperRow` 新增字段 `abstract: str = ""`、`keywords: list[str] = []`
  - `paper_from_dict` 解析这两个字段

> 后端验证：`papers` 表已含 `abstract TEXT` 和 `keywords TEXT`（comma-separated），`app/repo.py:239` 的 `SELECT p.*` 已返回。无需改后端。

- [ ] **Step 1: 改 `frontend/models.py` `PaperRow` 数据类**

替换 `PaperRow` 整段定义为：
```python
@dataclass
class PaperRow:
    id: int = 0
    doi: str = ""
    title: str = ""
    journal_name: str = ""
    published_date: str = ""
    pdf_path: Optional[str] = None
    auto_downloadable_count: int = 0
    authors_list: list[str] = field(default_factory=list)
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
```

替换 `paper_from_dict` 为：
```python
def paper_from_dict(data: dict[str, Any]) -> PaperRow:
    raw_keywords = data.get("keywords") or ""
    keywords = [k.strip() for k in str(raw_keywords).split(",") if k.strip()] \
        if isinstance(raw_keywords, str) else \
        [str(k) for k in raw_keywords if str(k).strip()]
    return PaperRow(
        id=int(data.get("id") or 0),
        doi=str(data.get("doi") or ""),
        title=str(data.get("title") or ""),
        journal_name=str(data.get("journal_name") or data.get("issn") or ""),
        published_date=str(data.get("published_date") or ""),
        pdf_path=data.get("pdf_path"),
        auto_downloadable_count=int(data.get("auto_downloadable_count") or 0),
        authors_list=[str(item) for item in data.get("authors_list") or []],
        abstract=str(data.get("abstract") or ""),
        keywords=keywords,
    )
```

- [ ] **Step 2: 烟雾测试**

```bash
.venv/Scripts/python.exe -c "
from frontend.models import paper_from_dict
p = paper_from_dict({'id':1,'doi':'10/x','title':'T','abstract':'an abstract','keywords':'a, b, c'})
print(p.abstract, p.keywords)
"
```
预期：`an abstract ['a', 'b', 'c']`

- [ ] **Step 3: Commit**

```bash
git add frontend/models.py
git commit -m "feat(models): expose abstract and keywords on PaperRow"
```

---

## Task 10: SearchState 扩展（抽屉 + 轮询）+ 重写检索页

**Files:**
- Modify: `frontend/state/search_state.py`
- Rewrite: `frontend/pages/search.py`

**Interfaces:**
- Consumes: `frontend.design.{patterns, primitives, icons, tokens}`、`frontend.models.PaperRow`
- Produces (SearchState 新增):
  - `selected_paper_id: int = 0`
  - `drawer_paper: PaperRow = PaperRow()`
  - `polling: bool = False`
  - `def open_drawer(self, paper_id: int) -> None`
  - `def close_drawer(self) -> None`
  - `@rx.event(background=True) async def poll_task(self) -> None`
  - `async def _fetch_task_progress(self) -> None`

- [ ] **Step 1: 改 `frontend/state/search_state.py`**

在 `import` 区段加：
```python
import asyncio
```

在字段块加（紧跟 `_loaded` 之后）：
```python
    selected_paper_id: int = 0
    drawer_paper: PaperRow = PaperRow()
    polling: bool = False
```

在 class 末尾追加：
```python
    def open_drawer(self, paper_id: int) -> None:
        for p in self.papers:
            if p.id == paper_id:
                self.drawer_paper = p
                self.selected_paper_id = paper_id
                return

    def close_drawer(self) -> None:
        self.selected_paper_id = 0

    async def _fetch_task_progress(self) -> None:
        if not self.active_task.id:
            return
        try:
            data = await api.get_json(f"/api/search-tasks/{self.active_task.id}")
            self.active_task = search_task_from_dict(data)
            if self.active_task.status == "done":
                papers = await api.get_json(
                    f"/api/search-tasks/{self.active_task.id}/papers"
                )
                self.papers = [paper_from_dict(item) for item in papers]
        except httpx.HTTPError:
            pass  # 单次失败不打断轮询

    @rx.event(background=True)
    async def poll_task(self):
        async with self:
            if self.polling:
                return
            self.polling = True
        try:
            while True:
                async with self:
                    status = self.active_task.status
                if status not in ("queued", "running", "pending"):
                    break
                await asyncio.sleep(2)
                async with self:
                    await self._fetch_task_progress()
        finally:
            async with self:
                self.polling = False
```

在现有 `run_search` 方法的 `finally:` 之前**加一行**返回轮询事件：
```python
            self.active_task = search_task_from_dict(task_data)
            return SearchState.poll_task   # ← 新加这一行
```
（在 `try` 的 `await api.post_json(...)` 之后、`except` 之前）

具体替换：把
```python
            task_data = await api.post_json("/api/search-tasks", payload)
            self.active_task = search_task_from_dict(task_data)
        except httpx.HTTPError:
```
替换为：
```python
            task_data = await api.post_json("/api/search-tasks", payload)
            self.active_task = search_task_from_dict(task_data)
            self.loading = False
            return SearchState.poll_task
        except httpx.HTTPError:
```

（注意：`return SearchState.poll_task` 必须在 `finally` 之前 return；我们在 try 内显式置 `self.loading = False` 然后 return，触发轮询。`finally:` 块会再设一次 `self.loading = False`，幂等无害。）

- [ ] **Step 2: 重写 `frontend/pages/search.py`**

替换**整个文件**为：

```python
"""Search workbench page — composed from design patterns only."""
from __future__ import annotations

import reflex as rx

from frontend.design import patterns
from frontend.design.icons import DOWNLOAD, EXTERNAL_LINK, PLAY, REFRESH, SEARCH
from frontend.design.primitives import badge, button, divider, heading, text
from frontend.design.tokens import GAP
from frontend.state.search_state import SearchState


def _badges_row(paper) -> rx.Component:
    has_pdf = paper.pdf_path != None
    auto_dl = paper.auto_downloadable_count > 0
    return rx.hstack(
        rx.cond(
            has_pdf,
            badge("已在本地", tone="accent"),
            rx.cond(auto_dl, badge("可自动下载", tone="success"),
                    badge("仅元数据")),
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
    has_pdf = paper.pdf_path != None
    auto_dl = paper.auto_downloadable_count > 0
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
    )


def _journal_checkboxes() -> rx.Component:
    return rx.hstack(
        rx.foreach(
            SearchState.journals,
            lambda j: rx.checkbox(
                j.name,
                checked=SearchState.selected_issns.contains(j.issn),
                on_change=SearchState.toggle_issn(j.issn),
            ),
        ),
        spacing="3",
        wrap="wrap",
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
        _journal_checkboxes(),
        rx.hstack(
            rx.input(value=SearchState.year_from, placeholder="起始年份",
                     on_change=SearchState.set_year_from, size="2"),
            rx.input(value=SearchState.year_to, placeholder="截止年份",
                     on_change=SearchState.set_year_to, size="2"),
            rx.input(value=SearchState.rows, placeholder="最多条数",
                     on_change=SearchState.set_rows, size="2"),
            rx.spacer(),
            button("开始检索", variant="primary", icon=PLAY,
                   on_click=SearchState.run_search,
                   loading=SearchState.loading),
            width="100%",
            spacing="2",
            align="center",
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
            right=badge(
                "已选 " + SearchState.selected_dois.length().to_string(use_json=False)
                + " 篇",
                tone="success",
            ),
        ),
        patterns.empty("暂无结果", "输入关键词并点击\"开始检索\"。"),
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
                   on_click=SearchState.set_selected_dois([])),
            button("加入下载", variant="primary", icon=DOWNLOAD,
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
```

> 注意：`SearchState.set_selected_dois([])` 是 Reflex 自动生成的 setter；如果不可用，可以自行加一个方法：
> ```python
>     def clear_selection(self) -> None:
>         self.selected_dois = []
> ```
> 然后浮动栏改成 `on_click=SearchState.clear_selection`。

- [ ] **Step 3: 解除该页的 xfail**

修改 `tests/test_ui_consistency.py` 顶部加：
```python
_STAGE3_COMPLETED = {"search.py"}
```
把两个 test 函数前的 `@pytest.mark.xfail(...)` 改为：
```python
@pytest.mark.xfail(condition=lambda page: page.name not in _STAGE3_COMPLETED,
                   strict=False, reason="enforced after stage 3 page rewrites")
```

> **Reflex 注意**：`pytest.mark.xfail` 的 `condition` 参数必须能在 collect 阶段静态判断。改用 **runtime skip**：

把 `xfail` 装饰器完全去掉，改成 test body 开头加：
```python
    if page.name not in _STAGE3_COMPLETED:
        pytest.xfail(f"{page.name} not yet rewritten")
```
插在两个 test 函数最开头。

更新 `_STAGE3_COMPLETED` 集合：本任务结束时为 `{"search.py"}`。

- [ ] **Step 4: 跑测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ui_consistency.py -v
.venv/Scripts/python.exe -m pytest tests/test_state_idempotent.py -v
.venv/Scripts/python.exe -m pytest tests/test_reflex_smoke.py -v
```
预期：consistency 测试中 `search.py` 通过，其余三页 xfail；其他测试通过。

- [ ] **Step 5: 手动验收（启动应用）**

```bash
uv run python scripts/start.py
```
浏览器打开 `http://localhost:3000`：
1. 输入关键词、勾选期刊、点击"开始检索"
2. 任务进度区出现并每 2 秒更新一次进度
3. done 后停止轮询、结果出现
4. 选中 3 篇 → 底部浮动栏出现 → 点"清除" → 浮动栏消失
5. 点行尾"详情" → 右抽屉打开，显示摘要 → 关闭抽屉

按 Ctrl+C 停。

- [ ] **Step 6: Commit**

```bash
git add frontend/state/search_state.py frontend/pages/search.py tests/test_ui_consistency.py
git commit -m "feat(search): rewrite page on design system + add drawer & task polling"
```

---

## Task 11: 后端扩展 + LibraryState 扩展 + 重写文库页

**Files:**
- Modify: `app/routers/api.py`（`/api/library/search` 加可选参数）
- Modify: `app/repo.py`（`search_local` 加 year/author/sort 支持）
- Modify: `frontend/state/library_state.py`
- Rewrite: `frontend/pages/library.py`
- Modify: `tests/test_api_routes.py`（加新参数 case）

**Interfaces:**
- Produces (API): `/api/library/search` 新增可选 query params
  - `year_from: int | None`、`year_to: int | None`
  - `author: str | None`（子串匹配 authors 字段）
  - `sort: str | None`（`date_desc` / `date_asc` / `journal` / `title`）
- Produces (LibraryState 新增):
  - `journals_filter: list[str] = []`
  - `year_from: str = ""`、`year_to: str = ""`、`author_filter: str = ""`
  - `sort_by: str = "date_desc"`
  - `all_journals: list[JournalRow] = []`（左栏 chips 数据源）
  - `selected_paper_id` / `drawer_paper` / `open_drawer` / `close_drawer`（同 SearchState 模式）

- [ ] **Step 1: 改 `app/repo.py` `search_local` 签名**

找到 `async def search_local(` 函数签名，扩展为：
```python
async def search_local(
    db: aiosqlite.Connection,
    q: str,
    *,
    issns: list[str] | None = None,
    scope: str = "all",
    year_from: int | None = None,
    year_to: int | None = None,
    author: str | None = None,
    sort: str = "date_desc",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
```

在 `if issns:` 那个 block 之后加：
```python
    if year_from is not None:
        where.append("substr(p.published_date, 1, 4) >= ?")
        params.append(str(year_from))
    if year_to is not None:
        where.append("substr(p.published_date, 1, 4) <= ?")
        params.append(str(year_to))
    if author:
        where.append("p.authors LIKE ?")
        params.append(f"%{author}%")
```

把 `order = "ORDER BY coalesce(...)"` 那一行（else 分支）改为下面的 sort 分发：
```python
        order_map = {
            "date_desc": "ORDER BY coalesce(p.published_date, p.discovered_at) DESC",
            "date_asc":  "ORDER BY coalesce(p.published_date, p.discovered_at) ASC",
            "journal":   "ORDER BY j.name ASC, p.published_date DESC",
            "title":     "ORDER BY p.title ASC",
        }
        order = order_map.get(sort, order_map["date_desc"])
```

（仅在 `else` 分支即非全文 search 时生效；FTS rank 模式保留 `m.rank ASC` 不变。）

- [ ] **Step 2: 改 `app/routers/api.py` `api_library_search`**

替换整个函数签名为：
```python
@router.get("/library/search")
async def api_library_search(
    q: str = "",
    scope: str = "all",
    page: int = 1,
    page_size: int = 20,
    issn: Optional[list[str]] = Query(default=None),
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    author: Optional[str] = None,
    sort: str = "date_desc",
) -> dict[str, Any]:
```

确保文件顶部有 `from fastapi import Query`（若无则加）。

把内部 `await repo.search_local(...)` 调用替换为：
```python
        items, total = await repo.search_local(
            db,
            q,
            issns=issn or None,
            scope=scope,
            year_from=year_from,
            year_to=year_to,
            author=author,
            sort=sort,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
```

- [ ] **Step 3: 加测试到 `tests/test_api_routes.py`**

在文件末尾追加：
```python
@pytest.mark.asyncio
async def test_library_search_year_filter(client):
    resp = await client.get("/api/library/search",
                            params={"year_from": 2020, "year_to": 2024,
                                    "sort": "title"})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and "total" in body
```

(若 `tests/test_api_routes.py` 已有 `client` fixture 与现有用法，沿用；否则参考文件已有 setup。)

- [ ] **Step 4: 跑后端测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_api_routes.py -v
```
预期：包括新加的 case 全部通过。

- [ ] **Step 5: 改 `frontend/state/library_state.py`**

替换字段块为：
```python
class LibraryState(rx.State):
    query: str = ""
    scope: str = "all"
    page: int = 1
    page_size: int = 20
    total: int = 0
    items: list[PaperRow] = []
    loading: bool = False
    error_message: str = ""
    _loaded: bool = False

    # filters
    all_journals: list[JournalRow] = []
    journals_filter: list[str] = []
    year_from: str = ""
    year_to: str = ""
    author_filter: str = ""
    sort_by: str = "date_desc"

    # drawer
    selected_paper_id: int = 0
    drawer_paper: PaperRow = PaperRow()
```

文件顶部 imports 加：
```python
from frontend.models import JournalRow, journal_from_dict
```
（如果未导入）。

替换/扩展所有方法体为：
```python
    async def load_page(self) -> None:
        if self._loaded:
            return
        await self._load_journals()
        await self.search()
        self._loaded = True

    async def refresh(self) -> None:
        await self._load_journals()
        await self.search()

    async def _load_journals(self) -> None:
        try:
            rows = await api.get_json("/api/journals")
            self.all_journals = [journal_from_dict(item) for item in rows]
        except httpx.HTTPError:
            pass  # 期刊列表加载失败不影响主查询

    def set_query(self, value: str) -> None:
        self.query = value

    def set_scope(self, value: str) -> None:
        self.scope = value
        self.page = 1

    def set_year_from(self, value: str) -> None:
        self.year_from = value

    def set_year_to(self, value: str) -> None:
        self.year_to = value

    def set_author_filter(self, value: str) -> None:
        self.author_filter = value

    def set_sort(self, value: str) -> None:
        self.sort_by = value
        self.page = 1

    def toggle_journal_filter(self, issn: str) -> None:
        if issn in self.journals_filter:
            self.journals_filter = [x for x in self.journals_filter if x != issn]
        else:
            self.journals_filter = [*self.journals_filter, issn]
        self.page = 1

    async def search(self) -> None:
        self.loading = True
        self.error_message = ""
        params: dict[str, object] = {
            "q": self.query,
            "scope": self.scope,
            "page": self.page,
            "page_size": self.page_size,
            "sort": self.sort_by,
        }
        if self.year_from.strip().isdigit():
            params["year_from"] = int(self.year_from)
        if self.year_to.strip().isdigit():
            params["year_to"] = int(self.year_to)
        if self.author_filter.strip():
            params["author"] = self.author_filter.strip()
        if self.journals_filter:
            params["issn"] = self.journals_filter
        try:
            payload = await api.get_json("/api/library/search", params=params)
            self.total = payload["total"]
            self.items = [paper_from_dict(item) for item in payload["items"]]
        except httpx.HTTPError:
            self.error_message = "本地库查询失败"
        finally:
            self.loading = False

    async def next_page(self) -> None:
        self.page += 1
        await self.search()

    async def prev_page(self) -> None:
        self.page = max(1, self.page - 1)
        await self.search()

    def open_drawer(self, paper_id: int) -> None:
        for p in self.items:
            if p.id == paper_id:
                self.drawer_paper = p
                self.selected_paper_id = paper_id
                return

    def close_drawer(self) -> None:
        self.selected_paper_id = 0
```

- [ ] **Step 6: 重写 `frontend/pages/library.py`**

替换整个文件：
```python
"""Local library page — composed from design patterns only."""
from __future__ import annotations

import reflex as rx

from frontend.design import patterns
from frontend.design.icons import (
    CHEVRON_LEFT,
    CHEVRON_RIGHT,
    EXTERNAL_LINK,
    FILTER,
    REFRESH,
    SEARCH,
)
from frontend.design.primitives import badge, button, divider, heading, text
from frontend.design.tokens import GAP
from frontend.state.library_state import LibraryState


def _journal_filter_group() -> rx.Component:
    return rx.vstack(
        text("期刊", kind="caption"),
        rx.hstack(
            rx.foreach(
                LibraryState.all_journals,
                lambda j: rx.checkbox(
                    j.name,
                    checked=LibraryState.journals_filter.contains(j.issn),
                    on_change=LibraryState.toggle_journal_filter(j.issn),
                ),
            ),
            spacing="2",
            wrap="wrap",
        ),
        spacing="1",
        align="stretch",
        width="100%",
    )


def _scope_segment() -> rx.Component:
    return rx.vstack(
        text("范围", kind="caption"),
        rx.segmented_control.root(
            rx.segmented_control.item("全部", value="all"),
            rx.segmented_control.item("仅 PDF", value="pdf"),
            rx.segmented_control.item("仅元数据", value="meta"),
            value=LibraryState.scope,
            on_change=LibraryState.set_scope,
        ),
        spacing="1",
        align="stretch",
    )


def _year_group() -> rx.Component:
    return rx.vstack(
        text("年份范围", kind="caption"),
        rx.hstack(
            rx.input(value=LibraryState.year_from, placeholder="from",
                     on_change=LibraryState.set_year_from, size="2"),
            rx.input(value=LibraryState.year_to, placeholder="to",
                     on_change=LibraryState.set_year_to, size="2"),
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
        _scope_segment(),
        _journal_filter_group(),
        _year_group(),
        _author_group(),
        button("应用筛选", variant="primary", icon=SEARCH,
               on_click=LibraryState.search,
               loading=LibraryState.loading),
    )


def _badges_row(item) -> rx.Component:
    return rx.hstack(
        rx.cond(item.pdf_path != None,
                badge("已下载 PDF", tone="accent"),
                badge("仅元数据")),
        spacing="2",
        wrap="wrap",
    )


def _row(item) -> rx.Component:
    pdf_link = "/pdf/" + item.id.to_string(use_json=False)
    primary = rx.cond(
        item.pdf_path != None,
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
        secondary_action=rx.link(
            button("DOI", variant="ghost", icon=EXTERNAL_LINK),
            href="https://doi.org/" + item.doi.to_string(use_json=False),
            is_external=True,
        ),
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
                rx.select(
                    ["date_desc", "date_asc", "journal", "title"],
                    value=LibraryState.sort_by,
                    on_change=LibraryState.set_sort,
                    size="3",
                ),
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
        _main_area(),
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
```

- [ ] **Step 7: 更新 lint xfail 集合**

修改 `tests/test_ui_consistency.py`：`_STAGE3_COMPLETED = {"search.py", "library.py"}`。

- [ ] **Step 8: 跑测试**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v -x
```
预期：`search.py` 和 `library.py` 的 consistency 测试通过；其余两页仍 xfail；API 与 state 测试全过。

- [ ] **Step 9: 手动验收**

启动后访问 `/library`：
1. 左栏筛选：勾选某期刊 + 输入年份 + 排序换为"title" → 点"应用筛选"
2. 主区检索框输入关键词 → 点"查询"
3. 点列表某条 → 抽屉显示摘要
4. 翻页按钮可用

- [ ] **Step 10: Commit**

```bash
git add app/repo.py app/routers/api.py frontend/state/library_state.py \
        frontend/pages/library.py tests/test_api_routes.py tests/test_ui_consistency.py
git commit -m "feat(library): rewrite page with filters/sort/drawer + extend search API"
```

---

## Task 12: DownloadsState 加轮询 + 重写下载页

**Files:**
- Modify: `frontend/state/downloads_state.py`
- Rewrite: `frontend/pages/downloads.py`

**Interfaces:**
- Produces (DownloadsState 新增):
  - `polling: bool = False`
  - `@rx.event(background=True) async def poll_task(self) -> None`
  - `async def _fetch_selected_progress(self) -> None`

- [ ] **Step 1: 改 `frontend/state/downloads_state.py`**

文件顶部 imports 加：
```python
import asyncio
```

字段块加（在 `_loaded` 之后）：
```python
    polling: bool = False
```

class 末尾追加：
```python
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
```

把 `select_task` 方法体内的 `try:` 末尾追加：
```python
            self.selected_task = download_task_from_dict(detail)
            if self.selected_task.status in ("pending", "running"):
                return DownloadsState.poll_task
```
（替换原 `try` body 的最后一行 `self.selected_task = ...` 整段；意思：选中一个还在跑的任务自动启动轮询。）

把 `retry_all` 和 `retry_item` 的成功分支也加 `return DownloadsState.poll_task`（在 `await api.post_json(...)` 之后、`except` 之前）。

- [ ] **Step 2: 重写 `frontend/pages/downloads.py`**

替换整个文件：
```python
"""Download tasks page — composed from design patterns only."""
from __future__ import annotations

import reflex as rx

from frontend.design import patterns
from frontend.design.icons import REFRESH
from frontend.design.primitives import badge, button, divider, heading, text
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
        border_radius="8px",
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
                            button("重试", variant="ghost",
                                   on_click=DownloadsState.retry_item(item.doi)),
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
```

> 注：`width="20rem"` 在页面文件里出现 — 但 lint 只禁 `max_width=` 和 `min_height=`，不禁 `width=`。这是有意的：列表栏宽度是布局尺寸而非内容尺寸。

- [ ] **Step 3: 更新 lint 集合**

`tests/test_ui_consistency.py`：`_STAGE3_COMPLETED = {"search.py", "library.py", "downloads.py"}`。

- [ ] **Step 4: 跑测试 + 手动验收**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v -x
uv run python scripts/start.py
```

手动验收：
1. 启动一个下载任务（从 search 页选 3 篇 → 下载）
2. 跳转 `/downloads`，左栏看到新任务
3. 点该任务 → 右侧详情：进度条每 2 秒更新
4. 状态变成 done 后，"已停止" 文字出现，轮询停止

- [ ] **Step 5: Commit**

```bash
git add frontend/state/downloads_state.py frontend/pages/downloads.py \
        tests/test_ui_consistency.py
git commit -m "feat(downloads): rewrite page on design system + add task polling"
```

---

## Task 13: JournalsState 加二次确认 + 重写期刊页

**Files:**
- Modify: `frontend/state/journals_state.py`
- Rewrite: `frontend/pages/journals.py`

**Interfaces:**
- Produces (JournalsState 新增):
  - `pending_delete_issn: str = ""`（非空时显示二次确认对话框）
  - `def request_delete(self, issn: str) -> None`
  - `def cancel_delete(self) -> None`
  - `async def confirm_delete(self) -> None`

- [ ] **Step 1: 改 `frontend/state/journals_state.py`**

字段块加（在 `_loaded` 之后）：
```python
    pending_delete_issn: str = ""
```

class 末尾追加：
```python
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
```

保留现有 `delete_journal` 实现不变。

- [ ] **Step 2: 重写 `frontend/pages/journals.py`**

替换整个文件：
```python
"""Journal management page — composed from design patterns only."""
from __future__ import annotations

import reflex as rx

from frontend.design import patterns
from frontend.design.icons import TRASH
from frontend.design.primitives import badge, button, divider, heading, text
from frontend.design.tokens import GAP
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
                text(rx.cond(item.publisher != None,
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
                    on_change=lambda v: JournalsState.toggle_enabled(item.issn, v),
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
            rx.input(value=JournalsState.name, placeholder="名称（可空，自动从 CrossRef 补全）",
                     on_change=JournalsState.set_name, size="3"),
            rx.input(value=JournalsState.publisher, placeholder="出版社（可空）",
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
                button("取消", variant="secondary",
                       on_click=JournalsState.cancel_delete),
                button("确认删除", variant="danger",
                       on_click=JournalsState.confirm_delete),
                spacing="3",
                justify="end",
                width="100%",
            ),
        ),
        open=JournalsState.pending_delete_issn != "",
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
```

- [ ] **Step 3: 关闭 lint xfail**

`tests/test_ui_consistency.py`：把 `_STAGE3_COMPLETED` 改为 4 页全列：
```python
_STAGE3_COMPLETED = {"search.py", "library.py", "downloads.py", "journals.py"}
```

也可以更直接：删除 `_STAGE3_COMPLETED` 和 `pytest.xfail(...)` 那两行，让所有页面都参与硬约束。

- [ ] **Step 4: 跑测试**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```
预期：lint 测试 4 页全过；所有其他测试通过。

- [ ] **Step 5: 手动验收**

启动应用访问 `/journals`：
1. switch 切换某期刊的启停 → 列表实时反映
2. 点"删除" → 弹出二次确认对话框 → 取消 → 列表不变
3. 再点"删除" → 确认 → 期刊消失
4. "添加"一本只填 ISSN 的期刊，CrossRef 自动补名

- [ ] **Step 6: Commit**

```bash
git add frontend/state/journals_state.py frontend/pages/journals.py \
        tests/test_ui_consistency.py
git commit -m "feat(journals): rewrite page with switch + delete confirmation dialog"
```

---

**阶段 3 完成检查点**：四个页面全部用 design system 重写；lint 全绿；任务自动轮询、论文详情抽屉、文库高级筛选/排序、浮动批量栏全部可用。

---

## 阶段 4：收尾

## Task 14: 删除遗留代码

**Files:**
- Delete: `app/ui/`（整目录）
- Delete: `frontend/theme.py`
- Delete: `frontend/components/shell.py`、`frontend/components/`（若整空）

**Interfaces:**
- 仍需保留 `frontend/app.py` 对 `GLOBAL_STYLES` 的引用；要把 `frontend/app.py` 中的 import 改掉。

- [ ] **Step 1: 检查 `app/ui/` 是否被其他模块引用**

```bash
cd c:/Users/AH/Desktop/search
grep -rn "from app.ui\|import app.ui\|from app import ui" app/ frontend/ tests/ 2>&1 | grep -v __pycache__
```
预期：仅 `app/ui/__init__.py` 或 `app/ui/` 内部相对引用；外部无引用。

如果有外部引用，先删除/修复那些引用，再继续。

- [ ] **Step 2: 把 `GLOBAL_STYLES` 从 `theme.py` 迁到 `frontend/design/tokens.py`**

在 `frontend/design/tokens.py` 末尾追加：
```python
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
```

- [ ] **Step 3: 改 `frontend/app.py`**

整个文件替换为：
```python
"""Reflex application entrypoint."""
from __future__ import annotations

import reflex as rx

from app.backend import app as backend_app
from frontend.design.tokens import GLOBAL_STYLES
from frontend.pages import downloads, journals, library, search  # noqa: F401


app = rx.App(
    style=GLOBAL_STYLES,
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap",
    ],
    api_transformer=backend_app,
)
```

- [ ] **Step 4: 删除文件**

```bash
rm -rf c:/Users/AH/Desktop/search/app/ui
rm c:/Users/AH/Desktop/search/frontend/theme.py
rm c:/Users/AH/Desktop/search/frontend/components/shell.py
rmdir c:/Users/AH/Desktop/search/frontend/components 2>/dev/null || true
```

- [ ] **Step 5: 跑全量测试 + 烟雾测试**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
.venv/Scripts/python.exe -c "import frontend.app"
```
预期：测试通过；import 不抛。

如果 `test_ui_compat.py` 因 NiceGUI 删除而失败：删除该测试文件（功能由 `test_ui_consistency.py` 替代）。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: remove legacy NiceGUI UI and old theme/shell"
```

---

## Task 15: `.gitignore` + `.env.example` 收尾

**Files:**
- Modify: `.gitignore`
- Modify: `.env.example`

- [ ] **Step 1: 加 `.gitignore` 条目**

读取现 `.gitignore`，在末尾追加（去重）：
```
# reflex runtime artifacts
reflex.lock/
reflex.err.log
reflex.out.log
uvicorn-*.log
uvicorn-*.err.log
uvicorn-*.out.log
.states/
```

`.web/` 通常已经在；若没有也加上。

- [ ] **Step 2: 加 `.env.example` 端口注释**

在 `.env.example` 现有内容**末尾**追加：
```
# 服务端口（可选，默认 8000 / 3000）
# NP_OA_BACKEND_PORT=8000
# NP_OA_FRONTEND_PORT=3000
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore .env.example
git commit -m "chore: ignore reflex runtime logs/locks, document port env vars"
```

---

## Task 16: 全量回归 + 手动验收清单

- [ ] **Step 1: 跑全量测试**

```bash
cd c:/Users/AH/Desktop/search
.venv/Scripts/python.exe -m pytest tests/ -v
```
预期：全绿。

- [ ] **Step 2: 启动并通过验收清单**

```bash
uv run python scripts/start.py
```

逐项验证：

- [ ] 1. 检索页：输入关键词 → 点开始 → 进度条 ~2s 自动更新 → done 后停轮询
- [ ] 2. 检索页：选 3 篇 → 底部浮动栏出现 → 点"加入下载" → 跳到下载页且本任务自动选中并轮询
- [ ] 3. 检索页：点行尾"详情" → 右抽屉显示 abstract → 关闭后选择状态不变
- [ ] 4. 检索页：滚动结果列表 10 秒 → 列表不消失、状态不重置
- [ ] 5. 检索页 → 文库页 → 返回检索页 → 结果仍在
- [ ] 6. 文库页：左栏勾选 1 期刊 + 年份 2020-2024 + 排序 "title" → 应用 → 结果变化
- [ ] 7. 文库页：翻页按钮正常
- [ ] 8. 下载页：进度条自动更新；某条 failed 时点"重试"该条 → 状态变 pending
- [ ] 9. 期刊页：switch 启停期刊 → 检索页期刊列表实时变化
- [ ] 10. 期刊页：删除某期刊 → 弹确认对话框 → 取消 → 列表不变 → 再确认 → 消失
- [ ] 11. 视觉一致性：四页所有 card 圆角 = 8px、所有 primary 按钮 = 绿色实心、所有 caption 灰字大小一致

- [ ] **Step 3: 验证端口脚本**

故意保留一个旧 reflex 进程，再启动一次：
```bash
# 终端 1
uv run python scripts/start.py
# 不要 Ctrl+C，关掉终端
# 终端 2
uv run python scripts/start.py
```
预期：第二次启动看到 `[start] killing stale reflex/uvicorn on :8000 (PID ...)` 然后正常拉起。

- [ ] **Step 4: 验证 lint 守门**

故意在 `frontend/pages/search.py` 加一行 `border_radius="12px"` 然后跑：
```bash
.venv/Scripts/python.exe -m pytest tests/test_ui_consistency.py -v
```
预期：搜索页失败，错误信息明确指出 `border_radius= literal is forbidden`。

撤回该改动：`git checkout frontend/pages/search.py`。

- [ ] **Step 5: 最终 commit（如有任何手动收尾）**

```bash
git add -A
git status   # 应空
git log --oneline -20
```

---

## 完成

实施完毕后项目状态：
- 四个页面全部用 design system 重写，视觉一致
- 端口冲突由 `scripts/start.py` 自动处理
- 滚动闪烁、原生下拉刷新均已消除
- 论文详情抽屉、任务自动轮询、文库高级筛选/排序、浮动批量栏可用
- lint 测试守门防止后续偏离
- `app/ui/` 旧 NiceGUI 代码彻底清除
- 唯一新依赖：`psutil>=5.9`
