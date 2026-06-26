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
