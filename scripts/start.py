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

# When invoked as `python scripts/start.py`, sys.path[0] is scripts/ rather
# than the project root — so the `scripts` package itself is not importable.
# Insert the project root so `from scripts import _portutil` works either way.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import _portutil as portutil  # noqa: E402


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
    # In prod mode Reflex serves frontend bundle from the backend port.
    _ensure_port_free(backend_port, PROJECT_ROOT)

    os.environ["NP_OA_API_URL"] = f"http://127.0.0.1:{backend_port}"
    print(
        f"[start] launching reflex run --env prod on :{backend_port}\n"
        f"[start] open http://localhost:{backend_port} in your browser"
    )
    os.execvp(
        "reflex",
        [
            "reflex",
            "run",
            "--env",
            "prod",
            "--backend-port",
            str(backend_port),
        ],
    )


if __name__ == "__main__":
    main()
