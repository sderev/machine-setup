"""Tests for installers module."""

import json
import logging
import os
import subprocess
from types import SimpleNamespace
from urllib import request as urllib_request

import pytest

from machine_setup import installers


class FakeResponse:
    """Simple response wrapper for urlopen mocks."""

    def __init__(self, data: bytes, status: int = 200) -> None:
        self._data = data
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


# --- Quarto tests ---


def test_install_quarto_skips_when_installed(monkeypatch, caplog) -> None:
    """Skip Quarto install when command exists."""
    monkeypatch.setattr(installers, "command_exists", lambda cmd: cmd == "quarto")

    caplog.set_level("INFO", logger="machine_setup")
    installers.install_quarto()

    assert "Quarto already installed" in caplog.text


def test_install_quarto_downloads_and_cleans_tempfile(monkeypatch, caplog) -> None:
    """Install Quarto and remove the temporary package."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    api_payload = json.dumps(
        {
            "assets": [
                {
                    "name": "quarto-1.0.0-linux-amd64.deb",
                    "browser_download_url": "https://example.com/quarto.deb",
                }
            ]
        }
    ).encode("utf-8")
    responses = [
        FakeResponse(api_payload, status=200),
        FakeResponse(b"deb-contents", status=200),
    ]

    def fake_urlopen(req, timeout=0):
        if isinstance(req, urllib_request.Request):
            assert req.headers.get("User-agent") == "machine-setup/1.0"
        return responses.pop(0)

    monkeypatch.setattr(installers.urllib.request, "urlopen", fake_urlopen)

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:2] == ["dpkg", "--print-architecture"]:
            return SimpleNamespace(stdout="amd64\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(installers, "run", fake_run)

    removed: list[str] = []
    real_remove = os.remove

    def fake_remove(path: str) -> None:
        removed.append(path)
        real_remove(path)

    monkeypatch.setattr(installers.os, "remove", fake_remove)

    caplog.set_level("INFO", logger="machine_setup")
    installers.install_quarto()

    assert any(cmd[:2] == ["dpkg", "--print-architecture"] for cmd in calls)
    assert any(cmd[idx : idx + 2] == ["dpkg", "-i"] for cmd in calls for idx in range(len(cmd) - 1))
    assert removed
    assert not os.path.exists(removed[0])
    assert "Quarto installation complete" in caplog.text


def test_install_quarto_rejects_unsupported_arch(monkeypatch) -> None:
    """Raise when architecture has no matching asset."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    api_payload = json.dumps({"assets": []}).encode("utf-8")
    monkeypatch.setattr(
        installers.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(api_payload, status=200),
    )

    monkeypatch.setattr(
        installers,
        "run",
        lambda cmd, **kwargs: SimpleNamespace(stdout="riscv64\n"),
    )

    with pytest.raises(RuntimeError, match="Unsupported architecture"):
        installers.install_quarto()


def test_install_quarto_cleans_tempfile_on_failure(monkeypatch) -> None:
    """Remove the temporary package when installation fails."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    api_payload = json.dumps(
        {
            "assets": [
                {
                    "name": "quarto-1.0.0-linux-amd64.deb",
                    "browser_download_url": "https://example.com/quarto.deb",
                }
            ]
        }
    ).encode("utf-8")
    responses = [
        FakeResponse(api_payload, status=200),
        FakeResponse(b"deb-contents", status=200),
    ]

    monkeypatch.setattr(
        installers.urllib.request,
        "urlopen",
        lambda *args, **kwargs: responses.pop(0),
    )

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["dpkg", "--print-architecture"]:
            return SimpleNamespace(stdout="amd64\n")
        raise installers.subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(installers, "run", fake_run)

    removed: list[str] = []
    real_remove = os.remove

    def fake_remove(path: str) -> None:
        removed.append(path)
        real_remove(path)

    monkeypatch.setattr(installers.os, "remove", fake_remove)

    with pytest.raises(installers.subprocess.CalledProcessError):
        installers.install_quarto()

    assert removed
    assert not os.path.exists(removed[0])


# --- npm tools tests ---


def test_install_npm_tools_uses_sudo_prefix(monkeypatch) -> None:
    """Global npm installs should use sudo when required."""
    calls: list[list[str]] = []

    monkeypatch.setattr(installers, "command_exists", lambda _: True)
    monkeypatch.setattr(installers, "sudo_prefix", lambda: ["sudo"])

    def fake_run(cmd, check=True, capture=False, env=None):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(installers, "run", fake_run)

    installers.install_npm_tools(["tool"])

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

    monkeypatch.setattr(installers, "command_exists", fake_command_exists)
    monkeypatch.setattr(installers, "run", fake_run)

    caplog.set_level(logging.INFO, logger="machine_setup")
    installers.install_npm_tools([])

    assert calls == {"command_exists": False, "run": False}
    assert "No npm tools to install" in caplog.text


def test_install_npm_tools_skips_when_npm_missing(monkeypatch, caplog) -> None:
    """Missing npm should log a warning and skip installs."""
    calls = {"run": False}

    def fake_run(cmd, check=True, capture=False, env=None):
        calls["run"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(installers, "command_exists", lambda _: False)
    monkeypatch.setattr(installers, "run", fake_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_npm_tools(["tool"])

    assert calls["run"] is False
    assert "npm not found; skipping npm tool installation" in caplog.text


def test_install_npm_tools_warns_on_failure(monkeypatch, caplog) -> None:
    """Failed npm installs should be surfaced in logs."""
    monkeypatch.setattr(installers, "command_exists", lambda _: True)
    monkeypatch.setattr(installers, "sudo_prefix", lambda: [])

    def fake_run(cmd, check=True, capture=False, env=None):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(installers, "run", fake_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_npm_tools(["tool"])

    assert "npm tool install failed for tool" in caplog.text


# --- uv tools tests ---


def test_install_uv_tools_empty_list(caplog) -> None:
    """Log info message when no tools to install."""
    caplog.set_level(logging.INFO, logger="machine_setup")
    installers.install_uv_tools([])

    assert "No uv tools to install" in caplog.text


def test_install_uv_tools_skips_when_uv_missing(monkeypatch, caplog) -> None:
    """Skip installation when uv not found."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_uv_tools(["some-tool"])

    assert "uv not found" in caplog.text


def test_install_uv_tools_installs_tools(monkeypatch, caplog) -> None:
    """Install each tool via uv tool install."""
    calls: list[list[str]] = []

    monkeypatch.setattr(installers, "command_exists", lambda _: True)
    monkeypatch.setattr(
        installers,
        "run",
        lambda cmd, check: calls.append(list(cmd)) or SimpleNamespace(returncode=0),
    )

    caplog.set_level(logging.INFO, logger="machine_setup")
    installers.install_uv_tools(["tool-a", "tool-b"])

    assert calls[0] == ["uv", "tool", "install", "tool-a"]
    assert calls[1] == ["uv", "tool", "install", "tool-b"]
    assert "Installing tool-a via uv tool" in caplog.text
    assert "Installing tool-b via uv tool" in caplog.text


def test_install_uv_tools_handles_failure(monkeypatch, caplog) -> None:
    """Log warning when tool installation fails."""
    monkeypatch.setattr(installers, "command_exists", lambda _: True)
    monkeypatch.setattr(
        installers,
        "run",
        lambda cmd, check: SimpleNamespace(returncode=1),
    )

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_uv_tools(["failing-tool"])

    assert "uv tool install failed for failing-tool" in caplog.text


# --- Claude Code tests ---


def test_install_claude_code_skips_when_already_installed(monkeypatch, caplog) -> None:
    """Skip installation when claude command already exists."""
    monkeypatch.setattr(installers, "command_exists", lambda cmd: cmd == "claude")

    caplog.set_level("INFO", logger="machine_setup")
    installers.install_claude_code()

    assert "Claude Code already installed" in caplog.text


def test_install_claude_code_runs_installer(monkeypatch, caplog) -> None:
    """Run curl and bash to install Claude Code."""
    calls: list[list[str]] = []
    bash_inputs: list[str] = []

    monkeypatch.setattr(installers, "command_exists", lambda _: False)

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

    caplog.set_level("INFO", logger="machine_setup")
    installers.install_claude_code()

    assert calls[0] == ["curl", "-fsSL", "--max-time", "30", installers.CLAUDE_INSTALL_URL]
    assert calls[1] == ["bash"]
    assert bash_inputs[0] == "fake installer script"
    assert "Claude Code installed successfully" in caplog.text
    assert "You may need to restart your shell" in caplog.text


def test_install_claude_code_handles_failure(monkeypatch, caplog) -> None:
    """Log warning when installation fails."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


def test_install_claude_code_handles_curl_failure(monkeypatch, caplog) -> None:
    """Log warning when curl fails to fetch installer."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            raise subprocess.CalledProcessError(22, cmd)  # HTTP error
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


def test_install_claude_code_handles_bash_failure(monkeypatch, caplog) -> None:
    """Log warning when bash installer script fails."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            return SimpleNamespace(returncode=0, stdout="fake installer script")
        elif cmd[0] == "bash":
            raise subprocess.CalledProcessError(1, cmd)
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


def test_install_claude_code_handles_curl_timeout(monkeypatch, caplog) -> None:
    """Log warning when curl times out (exit code 28)."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            raise subprocess.CalledProcessError(28, cmd)  # curl timeout exit code
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


# --- SCC tests ---


def test_install_scc_skips_when_installed(monkeypatch, caplog) -> None:
    """Skip SCC install when command exists."""
    monkeypatch.setattr(installers, "command_exists", lambda cmd: cmd == "scc")

    caplog.set_level("INFO", logger="machine_setup")
    installers.install_scc()

    assert "SCC already installed" in caplog.text


def test_install_scc_skips_when_go_missing(monkeypatch, caplog) -> None:
    """Skip SCC install when go is not available."""
    monkeypatch.setattr(installers, "command_exists", lambda cmd: False)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_scc()

    assert "Go not found; skipping SCC installation" in caplog.text


def test_install_scc_installs_via_go(monkeypatch, caplog) -> None:
    """Install SCC via go install."""
    calls: list[list[str]] = []

    def fake_command_exists(cmd):
        return cmd == "go"

    monkeypatch.setattr(installers, "command_exists", fake_command_exists)

    def fake_run(cmd, check=False, capture=False, env=None):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(installers, "run", fake_run)

    caplog.set_level(logging.INFO, logger="machine_setup")
    installers.install_scc()

    assert calls == [["go", "install", "github.com/boyter/scc/v3@latest"]]
    assert "Installing SCC via go install" in caplog.text
    assert "SCC installed successfully" in caplog.text


def test_install_scc_handles_failure(monkeypatch, caplog) -> None:
    """Log warning when SCC installation fails."""

    def fake_command_exists(cmd):
        return cmd == "go"

    monkeypatch.setattr(installers, "command_exists", fake_command_exists)

    def fake_run(cmd, check=False, capture=False, env=None):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(installers, "run", fake_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_scc()

    assert "Failed to install SCC" in caplog.text
