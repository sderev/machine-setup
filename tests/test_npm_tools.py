"""Tests for npm_tools module."""

import logging
from types import SimpleNamespace

from machine_setup import npm_tools


def test_install_npm_tools_uses_sudo_prefix(monkeypatch) -> None:
    """Global npm installs should use sudo when required."""
    calls: list[list[str]] = []

    monkeypatch.setattr(npm_tools, "command_exists", lambda _: True)
    monkeypatch.setattr(npm_tools, "sudo_prefix", lambda: ["sudo"])

    def fake_run(cmd, check=True, capture=False, env=None):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(npm_tools, "run", fake_run)

    npm_tools.install_npm_tools(["tool"])

    assert calls == [["sudo", "npm", "install", "-g", "tool"]]


def test_install_npm_tools_skips_empty_list(monkeypatch, caplog) -> None:
    """Empty tool lists should short-circuit without running commands."""
    calls = {"command_exists": False, "run": False}

    def fake_command_exists(_):
        calls["command_exists"] = True
        return True

    def fake_run(cmd, check=True, capture=False, env=None):
        calls["run"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(npm_tools, "command_exists", fake_command_exists)
    monkeypatch.setattr(npm_tools, "run", fake_run)

    caplog.set_level(logging.INFO, logger="machine_setup")
    npm_tools.install_npm_tools([])

    assert calls == {"command_exists": False, "run": False}
    assert "No npm tools to install" in caplog.text


def test_install_npm_tools_skips_when_npm_missing(monkeypatch, caplog) -> None:
    """Missing npm should log a warning and skip installs."""
    calls = {"run": False}

    def fake_run(cmd, check=True, capture=False, env=None):
        calls["run"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(npm_tools, "command_exists", lambda _: False)
    monkeypatch.setattr(npm_tools, "run", fake_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    npm_tools.install_npm_tools(["tool"])

    assert calls["run"] is False
    assert "npm not found; skipping npm tool installation" in caplog.text


def test_install_npm_tools_warns_on_failure(monkeypatch, caplog) -> None:
    """Failed npm installs should be surfaced in logs."""
    monkeypatch.setattr(npm_tools, "command_exists", lambda _: True)
    monkeypatch.setattr(npm_tools, "sudo_prefix", lambda: [])

    def fake_run(cmd, check=True, capture=False, env=None):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(npm_tools, "run", fake_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    npm_tools.install_npm_tools(["tool"])

    assert "npm tool install failed for tool" in caplog.text
