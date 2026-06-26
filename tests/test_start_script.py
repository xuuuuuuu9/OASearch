"""Unit tests for scripts/start.py — mock subprocess / portutil."""
from __future__ import annotations

from unittest.mock import patch

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
