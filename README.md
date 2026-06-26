# NP OA Library

在指定期刊里按关键词搜论文 → 自动入库元数据 → 一键下载开放获取（OA）PDF → 本地全文检索。

默认 3 本天然产物期刊：Phytochemistry / Journal of Natural Products / Natural Product Reports，可随时增删。

---

## 安装

需要 Python 3.11+ 和 [uv](https://github.com/astral-sh/uv)。

```bash
# 进入项目目录
cd path/to/search

# 创建虚拟环境（第一次）
uv venv

# 装依赖 / 更新依赖
uv pip install -r requirements.txt
```

## 配置邮箱（必做）

打开 `.env` 文件，把里面的邮箱改成**你自己的真实邮箱**：

```
USER_EMAIL=你的邮箱@gmail.com
```

> 这个邮箱用来标识身份给 CrossRef 和 Unpaywall API。**必须真实**——`@example.com` 会被 Unpaywall 直接拒绝，导致永远找不到可下载的 OA 论文。邮箱**不会**收到任何邮件。

## 配置存储位置（可选）

默认会把数据库和 PDF 都放在项目下的 `data/`：

```env
DB_PATH=data/library.db
PDF_DIR=data/pdfs
```

如果你准备长期下载大量 PDF，建议把 `PDF_DIR` 放到容量更大的磁盘文件夹，例如：

```env
PDF_DIR=D:/NP-OA-Library/pdfs
```

也可以把数据库一起放过去：

```env
DATA_DIR=D:/NP-OA-Library
PDF_DIR=D:/NP-OA-Library/pdfs
DB_PATH=D:/NP-OA-Library/library.db
```

PDF 仍会按期刊和 DOI 哈希自动分子目录，避免一个文件夹里堆太多文件。

## 并发建议

默认配置偏向私人批量下载时的速度：

```env
DOWNLOAD_CONCURRENCY=16
POLITE_MODE=false
```

含义：
- `DOWNLOAD_CONCURRENCY` 是全局同时下载 PDF 的上限，建议私人单机使用 `12-16`。
- 程序还会按出版商 host 做单独限流，比如 PMC/arXiv 更快，ACS/Elsevier/Wiley 更保守。
- 遇到 `429/503` 会自动退避；同一 host 连续 `403` 或 Cloudflare challenge 会临时压制，避免继续撞墙。
- 如果失败里大量出现 `403`、`429`、`503`，把 `POLITE_MODE=true`，它会把全局并发降到 4，并让请求启动间隔约 200ms。

经验：想快一点，先保持 `DOWNLOAD_CONCURRENCY=16`；如果某天失败明显变多，再开 `POLITE_MODE=true` 或把并发降到 `8-12`。

## 启动

```bash
uv run python scripts/start.py
```

会自动：
- 清理上次崩溃残留的 `reflex.lock/`
- 检测 `:8000` 端口
  - 如果被旧的 reflex / uvicorn 进程占用，自动结束它
  - 如果被无关进程占用，会报错让你决定，不会乱杀
- 用 production 模式启动 Reflex（前后端共享一个端口，无 HMR）

默认地址：
- 应用：`http://localhost:8000`
- API：`http://localhost:8000/api/...`

想换端口：

```bash
NP_OA_BACKEND_PORT=8765 uv run python scripts/start.py
```

Windows PowerShell：
```powershell
$env:NP_OA_BACKEND_PORT="8765"; uv run python scripts/start.py
```

想停止：在终端按 `Ctrl+C`。下次启动如果有残留进程，`scripts/start.py` 会自动清理。

> 首次启动（或删了 `.web/` 后）会做一次完整编译，约需 30-60 秒。后续启动几秒。

---

## 怎么用

### 1️⃣ 在线检索（首页）

1. 输入关键词，如 `flavonoid`、`"natural product"`、`alkaloid AND antiviral`
2. 勾选要搜的期刊（默认全选）
3. 可选填年份范围、最大结果数
4. 点 **🔍 开始检索**

检索在后台运行，**可以随时切换到其他页面**，回来时进度还在。

结果出来后：
- **● OA** 绿色徽章 = 有公开 PDF 链接，可下载
- **仅元数据** 灰色徽章 = 只能拿到摘要等信息，无 PDF
- **✓ 已下载** 蓝色徽章 = 本地已有

**所有命中论文的元数据都会自动入库**，之后在「本地文献库」里能检索得到。

### 2️⃣ 下载 PDF

1. 勾选想要的 OA 行（非 OA 的复选框是灰的，无法勾）
2. 点表头的 ☐ **全选 OA** 可一键全选
3. 点底部浮动栏的 **⬇️ 下载选中的 PDF**
4. 跳转到任务进度页，任务运行中会自动刷新

下载完成后点 **📁 前往本地库**，就能在线预览 PDF 了。

**如果有失败的**：
- 每行有 **🔄 重试** 按钮，单独重试
- 顶部 **🔄 重试所有失败** 可一键批量重试
- **🌐** 按钮直接在浏览器打开 doi.org 链接，手动下载（适用于 Cloudflare 反爬的出版商，比如 ACS）

### 3️⃣ 本地文献库

在已经入库的论文中检索：

- 顶部输入关键词，自动模糊匹配 **标题 / 作者 / 摘要 / 关键词**
- 用分段控件切换范围：
  - **全部** — 所有入过库的（含未下载的元数据条目）
  - **仅 PDF** — 已下载的
  - **仅元数据** — 没下载的，提供 doi.org 跳转
- 勾选期刊药丸做筛选
- 点 **📄 打开 PDF** 直接在浏览器内预览

支持引号短语搜索：`"natural product"` 精确匹配整个短语。

### 4️⃣ 期刊管理

添加新期刊（例如 *Journal of Ethnopharmacology* ISSN `0378-8741`）：

1. 进入「期刊管理」页
2. 顶部表单填 ISSN，名称留空（系统会自动调 CrossRef 校验并回填官方名称）
3. 点 **添加期刊**

之后这本期刊就会出现在「在线检索」的勾选列表里。

**启用 / 禁用**：点右侧绿色徽章按钮，禁用的期刊在检索页面不会显示（已入库的论文不受影响）。

**删除**：仅删期刊条目本身，已入库的论文保留。

---

## 常见问题

### Q: 搜出来 10 篇 OA 但只能下 3 篇，怎么回事？

| 情形 | 含义 |
|---|---|
| **OA 但 UI 不让勾选** | Unpaywall 标记 OA 但没给 PDF 直链（可能只有 HTML 版） |
| **403 错误** | 出版商屏蔽程序化下载，最常见的是 ACS（用 Cloudflare 反爬） → 点 🌐 按钮浏览器手动下 |
| **HTTP 5xx / 超时** | 出版商服务器临时问题 → 点 🔄 重试 |

经验：**Natural Product Reports（RSC）OA 比例最高也最好下**，ACS 和 Elsevier 卡得严。

### Q: 摘要看着不全 / 不像论文摘要？

页面上的摘要来自 **CrossRef** 元数据库，部分出版商提交时会简化或省略。这是数据源的限制，不是 bug——点标题或 🔗 doi.org 看完整版本即可。

### Q: 检索过程中切换了页面，结果会丢吗？

不会。检索是后台任务，回到 **在线检索** 页面会自动恢复上次的结果。任务被持久化到数据库。

### Q: PDF 存在哪？

默认存在 `data/pdfs/{ISSN}/{hash前两位}/{hash}.pdf`，例如：
```
data/pdfs/0265-0568/11/11e3b936...bce.pdf
```

如果 `.env` 里设置了 `PDF_DIR`，则存在：

```
{PDF_DIR}/{ISSN}/{hash前两位}/{hash}.pdf
```

文件名是 DOI 的 SHA-1 哈希前缀，可以直接拷贝走。

### Q: 数据库在哪？怎么清空？

默认是 `data/library.db`（SQLite 单文件）；如果设置了 `DB_PATH`，则以 `.env` 为准。

**清空全部**：停止服务，删掉这个文件，下次启动会自动重建并恢复 3 本默认期刊。

### Q: 私人下载大量文献，需要换数据库吗？

暂时不需要。这个项目是单机私人使用，SQLite 很合适：

- 元数据、任务记录、候选 URL 都是结构化小数据，SQLite 足够快。
- 已启用 WAL 和 FTS5，本地搜索不需要额外服务。
- PDF 文件本身不进数据库，只存文件夹，数据库只记录路径、大小和哈希。
- 备份也简单：复制 `library.db` 和 `pdfs/` 文件夹即可。

只有这些情况才建议考虑 PostgreSQL：多人同时访问、跨电脑共享同一个库、元数据达到百万级以上、需要远程部署或复杂统计报表。私人批量下载 PDF，优先把 `PDF_DIR` 放到大磁盘，而不是换数据库。

### Q: 想让别的电脑也能访问？

启动时加 `--host 0.0.0.0`：

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

同局域网用 `http://你的电脑IP:8000` 访问。

### Q: 下载太慢 / 出版商封 IP？

先看失败原因：

- 少量 `403`：常见于 ACS/Cloudflare，点 🌐 手动下载更稳。
- 很多 `429/503`：说明请求太密，建议降并发或开保守模式。

打开 `.env`：

```
DOWNLOAD_CONCURRENCY=8
POLITE_MODE=true
```

`POLITE_MODE=true` 会把全局并发降到 4 + 每请求启动间隔约 200ms。重启服务生效。

---

## 文件位置

| 文件 / 目录 | 内容 |
|---|---|
| `.env` | 邮箱、并发数等配置 |
| `data/library.db` 或 `DB_PATH` | 所有元数据 + 任务记录（SQLite） |
| `data/pdfs/` 或 `PDF_DIR` | 下载下来的 PDF |
| `requirements.txt` | Python 依赖列表 |
