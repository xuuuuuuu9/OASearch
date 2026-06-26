# Reflex 前端重设计 · 设计规范

**日期**：2026-06-26
**状态**：草案，待实施
**适用范围**：`frontend/` 目录、`scripts/start.py`、相关后端字段补全

---

## 1. 背景与目标

NP OA Library 已完成 NiceGUI → Reflex 框架迁移，但当前前端存在三类用户报告的问题：

1. **稳定性 bug**：PC 浏览器滚动时页面"闪一下"重新加载，列表与选择状态丢失。
2. **视觉不一致**：四个页面间卡片高度、按钮宽度、圆角、间距各处硬编码不同值（详见附录 A）。
3. **端口冲突反复出现**：旧 `reflex` / `uvicorn` 进程残留导致 `8000` / `8001` 端口反复被占，需手动换端口启动。

同时，作为文献检索工具，当前 UI 缺少几个核心交互：论文详情快速预览、任务进度自动追踪、本地库高级筛选、批量操作的便捷入口。

### 目标

- 用 Radix Themes 原生组件 + 项目级 design system 重写前端 UI，建立可执行的一致性约束。
- 修复"滚动闪烁"与端口残留两个稳定性问题。
- 新增四项交互：论文详情侧抽屉、任务进度自动轮询、文库高级筛选/排序、浮动批量操作栏。
- 保留现有 4 页面路由（`/` `/library` `/downloads` `/journals`），不做信息架构重构。

### 非目标（YAGNI）

- 不引入 PDF 内嵌预览。
- 不实现 BibTeX 导出（可作浮动栏占位 disabled 按钮，后续 issue）。
- 不做移动端响应式抽屉，桌面优先。
- 不做暗色主题，保持单一 light。
- 不引入多用户/权限/登录。
- 不替换 SQLite。

---

## 2. 总体架构

四个阶段串行执行，每阶段独立可合并、可暂停：

```
阶段 1  稳定性先修      scripts/start.py + _loaded 哨兵 + overscroll-behavior
阶段 2  Design System   frontend/design/{tokens,primitives,patterns,icons}.py + lint
阶段 3  逐页重写         search → library → downloads → journals，按页面加新功能
阶段 4  收尾             删 app/ui/ + theme.py + shell.py，补测试，更新 README/.env/.gitignore
```

整体策略：稳定性优先 → 设计系统定型 → 逐页重写时一次性带入新功能 → 收尾。

---

## 3. 阶段 1：稳定性先修

### 3.1 启动脚本 `scripts/start.py`

替代用户手动运行 `uv run reflex run`。职责：

1. 清理 `reflex.lock/` 残留目录。
2. 检测 `NP_OA_BACKEND_PORT`（默认 8000）与 `NP_OA_FRONTEND_PORT`（默认 3000）是否被占用。
3. 如被占用，识别监听进程是否属于本项目（命令行同时含 `reflex|uvicorn|frontend` 且工作目录在本项目内）：
   - 是 → kill 进程树，继续启动。
   - 否 → 打印持有者信息后 `sys.exit(1)`，拒绝误杀。
4. 设置 `NP_OA_API_URL=http://127.0.0.1:{backend_port}` 后 exec `reflex run --backend-port {bp} --frontend-port {fp}`。

跨平台使用 `psutil` 替代 `netstat`/`lsof` 解析。封装 `scripts/_portutil.py` 暴露 `find_listening_pid(port) -> int | None`、`kill_process_tree(pid)`、`is_our_process(pid) -> bool`。

入口：`uv run python scripts/start.py`。README 替换原启动指令。

### 3.2 修复"滚动闪烁"

根因：所有页面使用 `@rx.page(on_load=...State.load_page)`，每次 websocket 重连或 hot reload 都会重跑 `load_page`，将 `papers=[]`/`items=[]` 清空并重新 fetch，UI 出现闪烁与状态丢失。

三层防护：

**a) State 哨兵**：每个 `*State` 增加 `_loaded: bool = False`，`load_page` 开头判断 `if self._loaded: return`；新增显式 `refresh()` 事件供"刷新"按钮调用。

**b) 全局 CSS**：`frontend/app.py` 的 `GLOBAL_STYLES` 加入：
```python
"html": {"overscroll-behavior": "none"},
"body": {"overscroll-behavior": "none"},
```
防止浏览器原生下拉刷新手势触发整页 reload。

**c) `load_page` 仅做首次填充**：所有 fetch 在显式 `refresh()` 或事件回调（搜索按钮、分页按钮等）中触发，而非自动。

### 3.3 阶段 1 文件改动清单

| 文件 | 操作 |
|---|---|
| `scripts/start.py` | 新建 |
| `scripts/_portutil.py` | 新建 |
| `frontend/state/search_state.py` | 加 `_loaded` 哨兵 + `refresh()` |
| `frontend/state/library_state.py` | 同上 |
| `frontend/state/downloads_state.py` | 同上 |
| `frontend/state/journals_state.py` | 同上 |
| `frontend/app.py` | `GLOBAL_STYLES` 加 `overscroll-behavior` |
| `requirements.txt` | 加 `psutil>=5.9` |
| `README.md` | 启动指令改为 `uv run python scripts/start.py`，删除"换端口"那段 |

---

## 4. 阶段 2：Design System

### 4.1 设计原则

- **颜色全交给 Radix**：`rxconfig.py` 已经 `accent_color="green"`，所有 accent 用 Radix 内置变量；放弃当前 `theme.py` 中 26 个手写颜色值。
- **圆角与间距只允许 token**：项目级 token 集中在一处；页面代码禁止字面量。
- **复合模式优于原子布局**：页面只组合 `patterns`，不直接用 `rx.box(padding=..., border=...)`。

### 4.2 目录结构

```
frontend/design/
  __init__.py
  tokens.py       # PAGE_MAX_WIDTH, SHELL_PADDING_*, CARD_RADIUS, GAP, ELEV
  primitives.py   # Radix 薄包装：card / button(variant=primary|secondary|ghost|danger) / heading / text
  patterns.py     # page_shell, paper_card, paper_drawer, floating_toolbar, filter_sidebar, metric_row, empty, section
  icons.py        # rx.icon 名字常量
```

### 4.3 `tokens.py`

```python
PAGE_MAX_WIDTH = "88rem"
SHELL_PADDING_X = "1.5rem"
SHELL_PADDING_Y = "1.25rem"
CARD_RADIUS = "8px"
GAP = {"xs": "0.5rem", "sm": "0.75rem", "md": "1rem", "lg": "1.5rem", "xl": "2rem"}
ELEV = {
    "none": "none",
    "sm":   "0 1px 2px rgba(15,23,34,.04), 0 1px 3px rgba(15,23,34,.06)",
    "md":   "0 4px 12px rgba(15,23,34,.08)",
}
```

颜色：所有页面与 patterns 只使用 Radix Themes 语义色（`gray.11`、`accent.9` 等），不再 import 自定义颜色。

### 4.4 `patterns.py` API（核心签名）

```python
def page_shell(*, title: str, content: rx.Component,
               drawer: rx.Component | None = None,
               on_refresh=None) -> rx.Component: ...

def paper_card(paper, *, selected: rx.Var[bool],
               on_toggle, on_open_detail,
               primary_action: rx.Component | None = None) -> rx.Component: ...

def paper_drawer(*, open: rx.Var[bool], paper, on_close,
                 actions: list[rx.Component]) -> rx.Component: ...

def floating_toolbar(*, visible: rx.Var[bool],
                     label: rx.Var[str],
                     actions: list[rx.Component]) -> rx.Component: ...

def filter_sidebar(*groups: rx.Component) -> rx.Component: ...

def metric_row(*items: tuple[str, rx.Var]) -> rx.Component: ...

def empty(title: str, hint: str = "", action: rx.Component | None = None) -> rx.Component: ...

def section(title: str, *children, right: rx.Component | None = None) -> rx.Component: ...
```

### 4.5 一致性约束（lint）

`tests/test_ui_consistency.py` 通过 grep 强制：

1. `frontend/pages/*.py` 不允许出现：`from frontend.theme`、字面量颜色（`#[0-9a-fA-F]{3,6}` / `rgb(`）、`border_radius=`、`min_height=`、`max_width=`、`padding=`（除 0 / token 引用外）、`background=COLORS[`、`box_shadow=`。
2. `frontend/pages/*.py` 必须 `from frontend.design import patterns` 或 `primitives`。
3. lint 不扫 `frontend/design/*.py`（patterns 内部允许原子 props）。

### 4.6 阶段 2 文件改动清单

| 文件 | 操作 |
|---|---|
| `frontend/design/__init__.py` | 新建 |
| `frontend/design/tokens.py` | 新建 |
| `frontend/design/primitives.py` | 新建 |
| `frontend/design/patterns.py` | 新建 |
| `frontend/design/icons.py` | 新建 |
| `tests/test_ui_consistency.py` | 新建 |

阶段 2 **不修改任何页面文件**，仅建库与约束，可独立合并。

---

## 5. 阶段 3：逐页重写 + 新功能

### 5.1 实施顺序

`search` → `library` → `downloads` → `journals`。

`search` 作为试点页面：抽屉、轮询、浮动栏首次集成完毕并验证后，再复用到其余页面。

### 5.2 State 层共用改造

每个 `*State` 加：

```python
class XxxState(rx.State):
    _loaded: bool = False
    selected_paper_id: int = 0           # 0 表示抽屉关闭
    drawer_paper: PaperRow = PaperRow()   # 抽屉当前展示的论文

    async def load_page(self):
        if self._loaded: return
        await self._fetch()
        self._loaded = True

    async def refresh(self):
        await self._fetch()

    def open_drawer(self, paper_id: int):
        self.selected_paper_id = paper_id
        for p in self._current_paper_pool():     # subclass returns self.papers / self.items
            if p.id == paper_id:
                self.drawer_paper = p
                break

    def close_drawer(self):
        self.selected_paper_id = 0
```

`SearchState` 与 `DownloadsState` 额外有：

```python
polling: bool = False

@rx.event(background=True)
async def poll_task(self):
    if self.polling: return
    async with self:
        self.polling = True
    try:
        while True:
            async with self:
                status = self.active_task.status
            if status not in ("queued", "running"):
                break
            await asyncio.sleep(2)
            async with self:
                await self._fetch_task_progress()
    finally:
        async with self:
            self.polling = False
```

`run_search` / `start_download` 完成后立即 `return XxxState.poll_task`。

### 5.3 检索页 `/`

**布局**：单列垂直堆叠 + 浮动栏 + 右侧抽屉。

**区域 a · 检索参数（粘性顶部）**
- 一行：关键词输入（大）+ "开始检索"按钮
- 一行：期刊 checkbox.group + 年份 from/to + Rows 输入
- 删除原"期刊范围"独占大卡。

**区域 b · 任务进度（仅当 `active_task.id > 0`）**
- 一行：`#42 "flavonoid" · running · 23/100 OA`
- 进度条 `rx.progress`，值 = `succeeded/total` 或 `oa/total`
- 右侧小字 "自动轮询每 2s"，done 后变 "已完成"

**区域 c · 结果列表**
- `rx.foreach(papers, paper_card)`，每个 `paper_card` 行首 checkbox（绑定 `selected_dois` 中是否含 doi）、行尾 "详情 →" 触发 `open_drawer`。
- 元数据徽章：`OA` / `仅元数据` / `已下载`。

**浮动操作栏**：`floating_toolbar(visible=selected_dois.length() > 0)`，内容 "已选 N 篇 · [清除] · [加入下载]"。

**抽屉内容**：title / journal · date / DOI（含复制按钮）/ authors / abstract（若后端有）/ actions: [加入下载, 打开 doi.org]。

**删除项**：顶部 4 个 metric_card（信息已通过参数行 + 任务行体现）。

### 5.4 文库页 `/library`

**布局**：两列。左侧 `filter_sidebar`（16rem 固定宽），右侧主区域。

**左侧筛选**：
- Scope：`全部 / 仅 PDF / 仅元数据` 分段控件
- 期刊：多选 chips（数据来自 `/api/journals?enabled_only=false`）
- 年份范围：from / to 数字输入
- 作者过滤：输入框，回车成 tag

**右侧主区域**：
- 顶部：主关键词输入 + "查询" 按钮 + 排序 select（`日期 ↓` / `日期 ↑` / `期刊` / `标题`）
- 中部：`rx.foreach(items, paper_card)`，行尾 `打开 PDF`（若有）或 `打开 DOI`，行尾 `详情 →` 触发抽屉
- 底部：分页 `上一页 / 第 N / 共 ⌈total/page_size⌉ 页 / 下一页`

**State 增量**：

```python
class LibraryState(rx.State):
    journals_filter: list[str] = []
    year_from: str = ""
    year_to: str = ""
    author_filter: str = ""
    sort_by: str = "date_desc"
```

后端 `/api/library/search` 增加 `journals` / `year_from` / `year_to` / `author` / `sort_by` 查询参数（兼容缺省）。

### 5.5 下载页 `/downloads`

**布局**：左右两栏（任务列表 + 任务详情）维持不变。

**任务列表（左）**：紧凑 `rx.card size="1"`，高度自适应，不再固定 `min_height=8.5rem`。

**任务详情（右）**：
- 顶部：徽章行 + 进度条 + "重试全部失败（N）"
- 主区：`rx.table` 表格 `DOI | Title | Status | Action`
  - Status：成功 → 绿、失败 → 红、跳过 → 灰
  - Action：失败行显示 `重试`；其他不显示
- 自动轮询同检索页

### 5.6 期刊页 `/journals`

最简单。仅做视觉统一：

- 新增期刊表单：放进一个 `rx.card`，三 input + 一按钮一行
- 期刊列表：每行用 `paper_card` 同款 card 样式
- 启停：用 `rx.switch` 替代当前的"启用 / 停用"按钮
- 删除：`rx.alert_dialog` 二次确认

### 5.7 后端字段补全（依赖性）

抽屉需要 `abstract` / `keywords`。实施前先核验：

```bash
# 核验 SQLite schema 是否含 abstract 列
sqlite3 data/library.db ".schema papers"
```

- **若 schema 已有 `abstract` 列**：仅修改 `app/repo.py` SELECT 与 `app/routers/api.py` 响应序列化，将字段加入 `/api/library/search` 与 `/api/search-tasks/{id}/papers` 两个端点的返回；`frontend/models.py` `PaperRow` 加 `abstract: str = ""`。
- **若 schema 没有 `abstract` 列**：缩减阶段 3 范围，抽屉里只展示 title / journal / authors / DOI，**不显示 abstract**，**不改后端**。决定在阶段 3 启动当天做并记录到实施计划。

### 5.8 阶段 3 文件改动清单（按页面）

`search` 页：`frontend/pages/search.py` 重写、`frontend/state/search_state.py` 加抽屉与轮询。
`library` 页：`frontend/pages/library.py` 重写、`frontend/state/library_state.py` 加筛选/排序/抽屉、`app/routers/api.py` 与 `app/repo.py` 加查询参数。
`downloads` 页：`frontend/pages/downloads.py` 重写、`frontend/state/downloads_state.py` 加轮询。
`journals` 页：`frontend/pages/journals.py` 重写、`frontend/state/journals_state.py` 加 switch / 确认对话框 state。
共用：`frontend/models.py` 加 `abstract` / `keywords`。

---

## 6. 阶段 4：收尾

### 6.1 删除项

- `app/ui/` 整个目录（旧 NiceGUI UI 残留）。先 grep 确认无外部 import 再删。
- `frontend/theme.py`（迁移至 `frontend/design/tokens.py`）。
- `frontend/components/shell.py`（迁移至 `frontend/design/patterns.py` 的 `page_shell`）。

### 6.2 配置 / 文档

- `README.md`：启动指令改为 `uv run python scripts/start.py`；删除"换端口"那段冗余说明；加一节"端口与重启"。
- `.env.example`：注释项加 `# NP_OA_BACKEND_PORT=8000` `# NP_OA_FRONTEND_PORT=3000`。
- `.gitignore`：加入 `uvicorn-*.log`、`reflex.err.log`、`reflex.out.log`、`reflex.lock/`、`.states/`。

### 6.3 阶段 4 文件改动清单

| 文件 | 操作 |
|---|---|
| `app/ui/` | 删除目录 |
| `frontend/theme.py` | 删除 |
| `frontend/components/shell.py` | 删除 |
| `README.md` | 改启动指令 |
| `.env.example` | 加端口注释项 |
| `.gitignore` | 加日志/锁 ignore |

---

## 7. 测试策略

| 测试 | 内容 | 类型 |
|---|---|---|
| `tests/test_port_script.py` | 端口检测、PID 解析、`reflex.lock` 清理；mock `psutil` 不真起进程 | 单元 |
| `tests/test_ui_consistency.py` | grep：`frontend/pages/*.py` 不含禁词；必须 import `frontend.design` | lint |
| `tests/test_reflex_smoke.py`（已有） | 扩展：4 页都能 import + `rx.page` 装饰正确 + 不抛异常 | 烟雾 |
| `tests/test_state_idempotent.py` | 调 `load_page()` 两次，第二次必须 no-op | 单元 |
| `tests/test_api_routes.py`（已有） | 加 case：`/api/library/search` 响应含 `abstract`（条件：schema 有该列） | 集成 |

### 手动验收清单

1. 滚动检索页结果列表 10 秒，列表不消失、状态不重置。
2. 检索页 → 文库页 → 返回检索页，结果仍在。
3. 启动一个 search 任务，进度条每 ~2 秒自动更新，done 后停止轮询。
4. 在结果中选 3 篇 → 浮动栏出现 → 点"加入下载"清空选择。
5. 点列表里"详情 →" → 右侧抽屉出现 → 关闭后列表选择状态不变。
6. `uv run python scripts/start.py` 在端口被占用时输出 `killing stale ... on :8000 (PID xxx)` 后正常启动。
7. 期刊页启停 switch、删除二次确认对话框。
8. 全部 4 页样式一致：圆角、阴影、间距、按钮颜色。

---

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 端口脚本误杀非项目进程 | 命令行匹配必须同时含 `(reflex\|uvicorn\|frontend)` 且工作目录在本项目下；否则报错让用户决定 |
| `rx.drawer` + `background=True` 首次集成踩坑 | 阶段 3 先在 `search` 页打通这两个，验证后再复用到其他页 |
| 后端 `abstract` 字段不存在 | 阶段 3 实施开头核验 schema；若无则缩减范围，抽屉不显示 abstract，不改后端 |
| lint 测试误伤合理用法 | lint 只 grep `frontend/pages/*.py`，不扫 `frontend/design/*.py` |
| Radix `accent_color="green"` 与原 `#1677ff` 蓝色视觉差异 | 预期变化（用户已确认）；保留正文深色不变 |
| Windows 下 `netstat` 输出格式差异 | 使用 `psutil` 跨平台 API，避免 shell 解析 |

---

## 9. 依赖变更

```diff
# requirements.txt
+ psutil >= 5.9
```

无其他新依赖。Reflex / FastAPI / SQLite / curl_cffi 版本不变。

---

## 附录 A：当前 UI 不一致硬编码值清单

| 处 | 值 | 文件:行 |
|---|---|---|
| `metric_card` 最小高 | `6.5rem` | `frontend/components/shell.py:63` |
| `_task_card` 最小高 | `8.5rem` | `frontend/pages/downloads.py:47` |
| `_journal_chip` 最小高 | `5.5rem` | `frontend/pages/search.py:29` |
| `_paper_row` 按钮列宽 | `max=13/min=11rem` | `frontend/pages/search.py:92-93` |
| `_library_row` 按钮列宽 | `max=12/min=10.5rem` | `frontend/pages/library.py:64-65` |
| `_download_item` 按钮列宽 | `max=9/min=8rem` | `frontend/pages/downloads.py:78-79` |
| grid `minmax()` | `11/12/15/22rem` 各处混用 | 所有页面 |
| 圆角 | shell `8px` / 任务卡 `18px` / 期刊片 `radius="large"` | 不统一 |
| 颜色定义 | 26 个手写颜色值 | `frontend/theme.py:4-26` |
