"""Tests for claude_code module."""

import logging
import subprocess
from types import SimpleNamespace

from machine_setup import claude_code


def test_install_claude_code_skips_when_already_installed(monkeypatch, caplog) -> None:
    """Skip installation when claude command already exists."""
    monkeypatch.setattr(claude_code, "command_exists", lambda cmd: cmd == "claude")

    caplog.set_level(logging.INFO, logger="machine_setup")
    claude_code.install_claude_code()

    assert "Claude Code already installed" in caplog.text


def test_install_claude_code_runs_installer(monkeypatch, caplog) -> None:
    """Run curl and bash to install Claude Code."""
    calls: list[list[str]] = []
    bash_inputs: list[str] = []

    monkeypatch.setattr(claude_code, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            calls.append(list(cmd))
            return SimpleNamespace(returncode=0, stdout="fake installer script")
        elif cmd[0] == "bash":
            calls.append(["bash"])
            bash_inputs.append(kwargs.get("input", ""))
            return SimpleNamespace(returncode=0)
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.INFO, logger="machine_setup")
    claude_code.install_claude_code()

    assert calls[0] == ["curl", "-fsSL", "--max-time", "30", claude_code.INSTALL_URL]
    assert calls[1] == ["bash"]
    assert bash_inputs[0] == "fake installer script"
    assert "Claude Code installed successfully" in caplog.text
    assert "You may need to restart your shell" in caplog.text


def test_install_claude_code_handles_failure(monkeypatch, caplog) -> None:
    """Log warning when installation fails."""
    monkeypatch.setattr(claude_code, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    claude_code.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


def test_install_claude_code_handles_curl_failure(monkeypatch, caplog) -> None:
    """Log warning when curl fails to fetch installer."""
    monkeypatch.setattr(claude_code, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            raise subprocess.CalledProcessError(22, cmd)  # HTTP error
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    claude_code.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


def test_install_claude_code_handles_bash_failure(monkeypatch, caplog) -> None:
    """Log warning when bash installer script fails."""
    monkeypatch.setattr(claude_code, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            return SimpleNamespace(returncode=0, stdout="fake installer script")
        elif cmd[0] == "bash":
            raise subprocess.CalledProcessError(1, cmd)
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    claude_code.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


def test_install_claude_code_handles_curl_timeout(monkeypatch, caplog) -> None:
    """Log warning when curl times out (exit code 28)."""
    monkeypatch.setattr(claude_code, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            raise subprocess.CalledProcessError(28, cmd)  # curl timeout exit code
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    claude_code.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text
