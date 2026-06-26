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
    fake_proc.cwd.return_value = str(Path(tmp_path).parent)
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
