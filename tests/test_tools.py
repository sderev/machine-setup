"""Tests for tools module."""

import logging
import subprocess
from types import SimpleNamespace

from machine_setup import tools

# --- install_uv_tools tests ---


def test_install_uv_tools_empty_list(caplog) -> None:
    """Log info message when no tools to install."""
    caplog.set_level(logging.INFO, logger="machine_setup")
    tools.install_uv_tools([])

    assert "No uv tools to install" in caplog.text


def test_install_uv_tools_skips_when_uv_missing(monkeypatch, caplog) -> None:
    """Skip installation when uv not found."""
    monkeypatch.setattr(tools, "command_exists", lambda _: False)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    tools.install_uv_tools(["some-tool"])

    assert "uv not found" in caplog.text


def test_install_uv_tools_installs_tools(monkeypatch, caplog) -> None:
    """Install each tool via uv tool install."""
    calls: list[list[str]] = []

    monkeypatch.setattr(tools, "command_exists", lambda _: True)
    monkeypatch.setattr(
        tools,
        "run",
        lambda cmd, check: calls.append(list(cmd)) or SimpleNamespace(returncode=0),
    )

    caplog.set_level(logging.INFO, logger="machine_setup")
    tools.install_uv_tools(["tool-a", "tool-b"])

    assert calls[0] == ["uv", "tool", "install", "tool-a"]
    assert calls[1] == ["uv", "tool", "install", "tool-b"]
    assert "Installing tool-a via uv tool" in caplog.text
    assert "Installing tool-b via uv tool" in caplog.text


def test_install_uv_tools_handles_failure(monkeypatch, caplog) -> None:
    """Log warning when tool installation fails."""
    monkeypatch.setattr(tools, "command_exists", lambda _: True)
    monkeypatch.setattr(
        tools,
        "run",
        lambda cmd, check: SimpleNamespace(returncode=1),
    )

    caplog.set_level(logging.WARNING, logger="machine_setup")
    tools.install_uv_tools(["failing-tool"])

    assert "uv tool install failed for failing-tool" in caplog.text


# --- install_claude_code tests ---


def test_install_claude_code_skips_when_already_installed(monkeypatch, caplog) -> None:
    """Skip installation when claude command already exists."""
    monkeypatch.setattr(tools, "command_exists", lambda cmd: cmd == "claude")

    caplog.set_level(logging.INFO, logger="machine_setup")
    tools.install_claude_code()

    assert "Claude Code already installed" in caplog.text


def test_install_claude_code_runs_installer(monkeypatch, caplog) -> None:
    """Run curl and bash to install Claude Code."""
    calls: list[list[str]] = []
    bash_inputs: list[str] = []

    monkeypatch.setattr(tools, "command_exists", lambda _: False)

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
    tools.install_claude_code()

    assert calls[0] == ["curl", "-fsSL", "--max-time", "30", tools.CLAUDE_INSTALL_URL]
    assert calls[1] == ["bash"]
    assert bash_inputs[0] == "fake installer script"
    assert "Claude Code installed successfully" in caplog.text
    assert "You may need to restart your shell" in caplog.text


def test_install_claude_code_handles_failure(monkeypatch, caplog) -> None:
    """Log warning when installation fails."""
    monkeypatch.setattr(tools, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    tools.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


def test_install_claude_code_handles_curl_failure(monkeypatch, caplog) -> None:
    """Log warning when curl fails to fetch installer."""
    monkeypatch.setattr(tools, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            raise subprocess.CalledProcessError(22, cmd)  # HTTP error
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    tools.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


def test_install_claude_code_handles_bash_failure(monkeypatch, caplog) -> None:
    """Log warning when bash installer script fails."""
    monkeypatch.setattr(tools, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            return SimpleNamespace(returncode=0, stdout="fake installer script")
        elif cmd[0] == "bash":
            raise subprocess.CalledProcessError(1, cmd)
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    tools.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


def test_install_claude_code_handles_curl_timeout(monkeypatch, caplog) -> None:
    """Log warning when curl times out (exit code 28)."""
    monkeypatch.setattr(tools, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            raise subprocess.CalledProcessError(28, cmd)  # curl timeout exit code
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    tools.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text
