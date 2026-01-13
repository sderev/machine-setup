"""Tests for npm_tools module."""

import logging

from machine_setup import npm_tools


class _Result:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


def test_install_npm_tools_uses_sudo_prefix(monkeypatch) -> None:
    """Global npm installs should use sudo when required."""
    calls: list[list[str]] = []

    monkeypatch.setattr(npm_tools, "command_exists", lambda _: True)
    monkeypatch.setattr(npm_tools, "sudo_prefix", lambda: ["sudo"])

    def fake_run(cmd, check=True, capture=False, env=None):
        calls.append(list(cmd))
        return _Result(0)

    monkeypatch.setattr(npm_tools, "run", fake_run)

    npm_tools.install_npm_tools(["tool"])

    assert calls == [["sudo", "npm", "install", "-g", "tool"]]


def test_install_npm_tools_warns_on_failure(monkeypatch, caplog) -> None:
    """Failed npm installs should be surfaced in logs."""
    monkeypatch.setattr(npm_tools, "command_exists", lambda _: True)
    monkeypatch.setattr(npm_tools, "sudo_prefix", lambda: [])

    def fake_run(cmd, check=True, capture=False, env=None):
        return _Result(1)

    monkeypatch.setattr(npm_tools, "run", fake_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    npm_tools.install_npm_tools(["tool"])

    assert "npm tool install failed for tool" in caplog.text
